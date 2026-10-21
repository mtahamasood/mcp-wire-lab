"""The wire tap (D1-D4).

Usage:
  python3 -m tap --trace <file> [--delay <dir>:<ms>] [--drop <dir>:<method>] -- <server command...>

Spawns the server command as a child and relays bytes unchanged: the tap's stdin to the
child's stdin, the child's stdout to the tap's stdout, the child's stderr to the tap's
stderr. Every frame (a run of bytes ending in a newline, or a final run without one) is
written to the trace as one JSON Lines record, on a single timeline (D3). Forwarding never
depends on recording: if the trace fails, the tap says so once and keeps relaying (D2).

Fault mode (phase 4 D3), off unless asked: --delay holds every frame of one direction (c2s or
s2c) for <ms> milliseconds before forwarding it; --drop does not forward the first frame of one
direction whose "method" is <method>. Each fault is a `fault` record on the timeline.
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
USAGE = (
    "usage: python3 -m tap --trace <file> [--delay <dir>:<ms>] [--drop <dir>:<method>]"
    " -- <server command...>\n"
    "  Runs the server command between your client (this process's stdin and stdout) and the\n"
    "  server, and records every byte to the trace file.\n"
    "  <dir> is c2s (client to server) or s2c (server to client).\n"
    "  --delay <dir>:<ms>      hold every frame in that direction for <ms> after recording it\n"
    "  --drop <dir>:<method>   record the first such frame but never forward it\n"
    "  Read the trace with: python3 -m tap.show <file>"
)
FAULT_DIRECTIONS = ("c2s", "s2c")
FORWARDED_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)
# JSON leaves these unescaped in strings, but many line readers split on them (D3).
LINE_BREAKS = ("\x85", " ", " ")


class UsageError(Exception):
    pass


class Faults:
    """The fault options for one direction (D3): an optional delay and an optional drop."""

    def __init__(self, delay_ms: int | None = None, drop_method: str | None = None) -> None:
        self.delay_ms = delay_ms
        self.drop_method = drop_method
        self.dropped = False

    def drops(self, frame: bytes) -> bool:
        """True once, for the first frame whose JSON `method` equals the drop method."""
        if self.drop_method is None or self.dropped:
            return False
        try:
            message = json.loads(frame)
        except (ValueError, RecursionError):
            return False
        if isinstance(message, dict) and message.get("method") == self.drop_method:
            self.dropped = True
            return True
        return False


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

    def _write(self, direction: str, fields: dict[str, Any]) -> int | None:
        """Write one record; return its seq, or None if nothing was written."""
        if self._closed:
            return None
        rec = {"seq": self._seq, "t_ns": time.monotonic_ns() - self._start, "dir": direction}
        rec.update(fields)
        try:
            write_all(self._fd, encode_record(rec))
        except OSError as exc:  # fail open (D2): stop recording, keep forwarding
            say(f"tap: trace write failed, recording stopped: {exc}")
            self._close()
            return None
        self._seq += 1
        return self._seq - 1

    def _close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                os.close(self._fd)
            except OSError:
                pass

    def record(self, direction: str, fields: dict[str, Any]) -> int | None:
        with self._lock:
            return self._write(direction, fields)

    def frame(self, direction: str, frame: bytes, partial: bool = False) -> int | None:
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
        return self.record(direction, fields)

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


def relay_with_faults(
    src: int,
    dst: int,
    direction: str,
    trace: Trace,
    faults: Faults,
    at_eof: Callable[[], None] | None = None,
) -> None:
    """relay() for a direction with a fault option: forwards one frame at a time (D3).

    Each frame is recorded, then (if a fault applies) a `fault` record names its seq, then the
    frame is held for the delay or not forwarded at all. One thread handles the direction, so
    a delay keeps order. A final frame without a newline is forwarded at end of file.
    """
    pending = b""
    forwarding = True

    def handle(frame: bytes, partial: bool = False) -> None:
        nonlocal forwarding
        seq = trace.frame(direction, frame, partial=partial)
        if faults.drops(frame):
            trace.event(
                "fault", kind="drop", on=direction, method=faults.drop_method, frame_seq=seq,
                forwarded=False,
            )  # fmt: skip
            return
        if faults.delay_ms is not None:
            trace.event(
                "fault", kind="delay", on=direction, ms=faults.delay_ms, frame_seq=seq
            )  # fmt: skip
            time.sleep(faults.delay_ms / 1000)
        if forwarding:
            try:
                write_all(dst, frame)
            except BrokenPipeError:
                forwarding = False
            except OSError as exc:
                say(f"tap: forwarding {direction} failed, still recording: {exc}")
                forwarding = False

    try:
        while True:
            try:
                chunk = read_some(src)
            except OSError as exc:
                say(f"tap: reading {direction} failed, treated as end of file: {exc}")
                break
            if not chunk:
                break
            pending += chunk
            while (end := pending.find(b"\n")) >= 0:
                frame, pending = pending[: end + 1], pending[end + 1 :]
                handle(frame)
        if pending:
            handle(pending, partial=True)
    finally:
        if at_eof is not None:
            at_eof()


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


def parse_fault(option: str, value: str, faults: dict[str, Faults]) -> None:
    """Add one `--delay <dir>:<ms>` or `--drop <dir>:<method>` value to the per-direction faults."""
    direction, colon, argument = value.partition(":")
    if direction not in FAULT_DIRECTIONS or not colon or not argument:
        raise UsageError(f"{USAGE}\ntap: {option} needs <dir>:<value>, got {value!r}")
    entry = faults.setdefault(direction, Faults())
    if option == "--delay":
        if not argument.isascii() or not argument.isdigit():
            raise UsageError(f"{USAGE}\ntap: --delay needs whole milliseconds, got {argument!r}")
        entry.delay_ms = int(argument)
    else:
        entry.drop_method = argument


def parse_args(argv: list[str]) -> tuple[Path, list[str], dict[str, Faults]]:
    if "--" not in argv:
        raise UsageError(f"{USAGE}\ntap: missing -- before the server command")
    split = argv.index("--")
    options, command = argv[:split], argv[split + 1 :]
    if len(options) < 2 or options[0] != "--trace" or not command:
        raise UsageError(USAGE)
    faults: dict[str, Faults] = {}
    rest = options[2:]
    if len(rest) % 2:
        raise UsageError(USAGE)
    for option, value in zip(rest[::2], rest[1::2], strict=True):
        if option not in ("--delay", "--drop"):
            raise UsageError(USAGE)
        parse_fault(option, value, faults)
    return Path(options[1]), command, faults


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
        trace_path, command, faults = parse_args(argv)
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

    def relay_for(direction: str, src: int, dst: int, at_eof: Callable[[], None]) -> Any:
        """The plain relay, or the per-frame one if this direction has a fault option."""
        if direction in faults:
            return relay_with_faults, (src, dst, direction, trace, faults[direction], at_eof)
        return relay, (src, dst, direction, trace, at_eof)

    c2s_target, c2s_args = relay_for("c2s", 0, to_child.fileno(), to_child.close)
    s2c_target, s2c_args = relay_for("s2c", child.stdout.fileno(), 1, close_stdout)
    relays = [
        threading.Thread(
            target=c2s_target,
            args=c2s_args,
            daemon=True,  # a client that never closes stdin must not keep the tap alive
        ),
        threading.Thread(target=s2c_target, args=s2c_args),
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
