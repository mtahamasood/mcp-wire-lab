"""The wire tap (D1-D4).

Usage:
  python3 -m tap --trace <file> -- <server command...>

Spawns the server command as a child and relays bytes unchanged: the tap's stdin to the
child's stdin, the child's stdout to the tap's stdout, the child's stderr to the tap's
stderr. Every frame (a run of bytes ending in a newline, or a final run without one) is
written to the trace as one JSON Lines record, on a single timeline (D3). Forwarding never
depends on recording: if the trace fails, the tap says so once and keeps relaying (D2).
"""

from __future__ import annotations

import base64
import json
import math
import os
import select
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import Any

CHUNK = 65536
USAGE = "usage: python3 -m tap --trace <file> -- <server command...>"
FORWARDED_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)
# JSON leaves these unescaped in strings, but many line readers split on them (D3).
LINE_BREAKS = ("\x85", " ", " ")


class UsageError(Exception):
    pass


def say(message: str) -> None:
    """One line on the tap's stderr; the tap must not fail because stderr is gone."""
    try:
        write_all(2, f"{message}\n".encode())
    except OSError:
        pass


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not valid JSON")


def _finite_float(text: str) -> float:
    value = float(text)
    if math.isinf(value):
        raise ValueError(f"the number {text[:40]} overflows to infinity")
    return value


def frame_fields(frame: bytes) -> dict[str, Any]:
    """The D3 fields that describe one frame's bytes."""
    fields: dict[str, Any] = {"bytes": len(frame)}
    try:
        text = frame.decode("utf-8")
    except UnicodeDecodeError as exc:
        fields["raw_b64"] = base64.b64encode(frame).decode("ascii")
        fields["json"] = None
        fields["parse_error"] = f"not valid UTF-8: {exc}"
        return fields
    fields["raw"] = text
    try:
        fields["json"] = json.loads(
            text, parse_constant=_reject_constant, parse_float=_finite_float
        )
    except (ValueError, RecursionError) as exc:
        fields["json"] = None
        fields["parse_error"] = str(exc)
    return fields


def encode_record(rec: dict[str, Any]) -> bytes:
    """One strict JSON line; a parsed value that cannot be written becomes `json: null`."""
    try:
        text = json.dumps(rec, ensure_ascii=False, allow_nan=False)
    except (ValueError, RecursionError) as exc:
        rec = {**rec, "json": None, "parse_error": f"tap could not write the parsed value: {exc}"}
        text = json.dumps(rec, ensure_ascii=False, allow_nan=False)
    for char in LINE_BREAKS:
        text = text.replace(char, f"\\u{ord(char):04x}")
    try:
        return text.encode("utf-8") + b"\n"
    except UnicodeEncodeError:  # a lone surrogate from a \ud800 escape in the frame
        return json.dumps(rec, allow_nan=False).encode("ascii") + b"\n"


class Trace:
    """The single trace writer: one lock orders every record on one timeline."""

    def __init__(self, path: Path) -> None:
        self._fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(self._fd, 0o600)
        self._lock = threading.Lock()
        self._start = time.monotonic_ns()
        self._seq = 0
        self._closed = False

    def _write(self, direction: str, fields: dict[str, Any]) -> None:
        if self._closed:
            return
        rec = {"seq": self._seq, "t_ns": time.monotonic_ns() - self._start, "dir": direction}
        rec.update(fields)
        try:
            write_all(self._fd, encode_record(rec))
        except OSError as exc:  # fail open (D2): stop recording, keep forwarding
            say(f"tap: trace write failed, recording stopped: {exc}")
            self._close()
            return
        self._seq += 1

    def _close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                os.close(self._fd)
            except OSError:
                pass

    def record(self, direction: str, fields: dict[str, Any]) -> None:
        with self._lock:
            self._write(direction, fields)

    def frame(self, direction: str, frame: bytes, partial: bool = False) -> None:
        try:
            fields = frame_fields(frame)
        except Exception as exc:  # describing a frame must never stop its direction (D2)
            fields = {
                "bytes": len(frame),
                "raw_b64": base64.b64encode(frame).decode("ascii"),
                "json": None,
                "parse_error": f"tap could not describe this frame: {exc}",
            }
        if partial:
            fields["partial"] = True
        self.record(direction, fields)

    def event(self, event: str, **fields: Any) -> None:
        self.record("tap", {"event": event, **fields})

    def finish(self, **fields: Any) -> None:
        """Write `exit` and close in one step, so nothing is recorded after it (D3)."""
        with self._lock:
            self._write("tap", {"event": "exit", **fields})
            self._close()


def read_some(fd: int) -> bytes:
    while True:
        try:
            return os.read(fd, CHUNK)
        except BlockingIOError:  # a descriptor someone else set non-blocking
            select.select([fd], [], [])


def write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            view = view[os.write(fd, view) :]
        except BlockingIOError:
            select.select([], [fd], [])


def relay(
    src: int, dst: int, direction: str, trace: Trace, at_eof: Callable[[], None] | None = None
) -> None:
    """Copy src to dst byte for byte; cut the copy into frames for the trace only (D2).

    Frames are recorded before the chunk that completes them is forwarded, so a frame that
    causes a reply is always on the timeline before the reply. EOF is passed on (at_eof)
    however the copy ends.
    """
    pending: list[bytes] = []  # the unterminated frame so far, in pieces
    forwarding = True
    try:
        while True:
            try:
                chunk = read_some(src)
            except OSError as exc:
                say(f"tap: reading {direction} failed, treated as end of file: {exc}")
                break
            if not chunk:
                break
            start = 0
            while (end := chunk.find(b"\n", start)) >= 0:
                pending.append(chunk[start : end + 1])
                trace.frame(direction, b"".join(pending))
                pending.clear()
                start = end + 1
            if start < len(chunk):
                pending.append(chunk[start:])
            if forwarding:
                try:
                    write_all(dst, chunk)
                except BrokenPipeError:  # the reader went away; keep draining into the trace
                    forwarding = False
                except OSError as exc:
                    say(f"tap: forwarding {direction} failed, still recording: {exc}")
                    forwarding = False
        if pending:
            trace.frame(direction, b"".join(pending), partial=True)
    finally:
        if at_eof is not None:
            at_eof()


def parse_args(argv: list[str]) -> tuple[Path, list[str]]:
    if "--" not in argv:
        raise UsageError(f"{USAGE}\ntap: missing -- before the server command")
    split = argv.index("--")
    options, command = argv[:split], argv[split + 1 :]
    if len(options) != 2 or options[0] != "--trace" or not command:
        raise UsageError(USAGE)
    return Path(options[1]), command


def exit_code(returncode: int) -> int:
    """The child's exit code, or 128 + the signal number if a signal killed it (D4)."""
    return 128 - returncode if returncode < 0 else returncode


def open_standard_fds() -> None:
    """Put /dev/null on a closed stdin, stdout or stderr, so no pipe or trace lands there."""
    for fd in (0, 1, 2):
        try:
            os.fstat(fd)
        except OSError:
            null = os.open(os.devnull, os.O_RDWR)
            if null != fd:
                os.dup2(null, fd)
                os.close(null)


def close_stdout() -> None:
    """Pass the child's stdout EOF on to the client at once (D4)."""
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 1)
    os.close(null)


def main(argv: list[str]) -> int:
    open_standard_fds()
    try:
        trace_path, command = parse_args(argv)
    except UsageError as exc:
        say(str(exc))
        return 2
    try:
        trace = Trace(trace_path)
    except OSError as exc:
        say(f"tap: cannot write trace: {exc}")
        return 2

    child: subprocess.Popen[bytes] | None = None
    early: list[int] = []

    def forward(signum: int, _frame: FrameType | None) -> None:
        if child is None:
            early.append(signum)
        else:
            child.send_signal(signum)

    for sig in FORWARDED_SIGNALS:
        signal.signal(sig, forward)

    trace.event("spawn", argv=command)
    try:
        # Own process group: a terminal's Ctrl-C reaches only the tap, which forwards it
        # once, instead of the child receiving it twice.
        child = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            process_group=0,
        )
    except OSError as exc:
        say(f"tap: cannot start {command[0]}: {exc}")
        trace.finish(code=127, error=str(exc))
        return 127
    for signum in early:
        child.send_signal(signum)

    assert child.stdin and child.stdout and child.stderr
    to_child = child.stdin
    relays = [
        threading.Thread(
            target=relay,
            args=(0, to_child.fileno(), "c2s", trace, to_child.close),
            daemon=True,  # a client that never closes stdin must not keep the tap alive
        ),
        threading.Thread(
            target=relay, args=(child.stdout.fileno(), 1, "s2c", trace, close_stdout)
        ),
        threading.Thread(target=relay, args=(child.stderr.fileno(), 2, "stderr", trace)),
    ]
    for thread in relays:
        thread.start()

    returncode = child.wait()
    for thread in relays[1:]:
        thread.join()

    code = exit_code(returncode)
    if returncode < 0:
        trace.finish(code=code, signal=-returncode)
    else:
        trace.finish(code=code)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
