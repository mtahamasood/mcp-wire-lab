"""The wire tap (D1-D4).

Usage:
  python3 -m tap --trace <file> -- <server command...>

Spawns the server command as a child and relays bytes unchanged: the tap's stdin to the
child's stdin, the child's stdout to the tap's stdout, the child's stderr to the tap's
stderr. Every frame (a run of bytes ending in a newline, or a final run without one) is
written to the trace as one JSON Lines record, on a single timeline (D3).
"""

from __future__ import annotations

import base64
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import IO, Any

CHUNK = 65536
USAGE = "usage: python3 -m tap --trace <file> -- <server command...>"


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not valid JSON")


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
        fields["json"] = json.loads(text, parse_constant=_reject_constant)
    except ValueError as exc:
        fields["json"] = None
        fields["parse_error"] = str(exc)
    return fields


class Trace:
    """The single trace writer: one lock orders every record on one timeline."""

    def __init__(self, path: Path) -> None:
        self._file: IO[bytes] = path.open("wb")
        self._lock = threading.Lock()
        self._start = time.monotonic_ns()
        self._seq = 0
        self._closed = False

    def record(self, direction: str, fields: dict[str, Any]) -> None:
        with self._lock:
            if self._closed:
                return
            rec = {"seq": self._seq, "t_ns": time.monotonic_ns() - self._start, "dir": direction}
            rec.update(fields)
            try:
                line = json.dumps(rec, ensure_ascii=False).encode("utf-8")
            except UnicodeEncodeError:  # a lone surrogate from a \ud800 escape in the frame
                line = json.dumps(rec).encode("ascii")
            self._file.write(line + b"\n")
            self._file.flush()
            self._seq += 1

    def event(self, event: str, **fields: Any) -> None:
        self.record("tap", {"event": event, **fields})

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._file.close()


def write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


def relay(
    src: int, dst: int, direction: str, trace: Trace, at_eof: Callable[[], None] | None = None
) -> None:
    """Copy src to dst byte for byte; cut the copy into frames for the trace only (D2).

    Frames are recorded before the chunk that completes them is forwarded, so a frame that
    causes a reply is always on the timeline before the reply.
    """
    pending = b""
    forwarding = True
    while chunk := os.read(src, CHUNK):
        pending += chunk
        *frames, pending = pending.split(b"\n")
        for frame in frames:
            trace.record(direction, frame_fields(frame + b"\n"))
        if forwarding:
            try:
                write_all(dst, chunk)
            except BrokenPipeError:  # the reader went away; keep draining into the trace
                forwarding = False
    if pending:
        trace.record(direction, {**frame_fields(pending), "partial": True})
    if at_eof is not None:
        at_eof()


def parse_args(argv: list[str]) -> tuple[Path, list[str]]:
    if "--" not in argv:
        raise SystemExit(f"{USAGE}\ntap: missing -- before the server command")
    split = argv.index("--")
    options, command = argv[:split], argv[split + 1 :]
    if len(options) != 2 or options[0] != "--trace" or not command:
        raise SystemExit(USAGE)
    return Path(options[1]), command


def exit_code(returncode: int) -> int:
    """The child's exit code, or 128 + the signal number if a signal killed it (D4)."""
    return 128 - returncode if returncode < 0 else returncode


def main(argv: list[str]) -> int:
    trace_path, command = parse_args(argv)
    trace = Trace(trace_path)

    child: subprocess.Popen[bytes] | None = None
    early: list[int] = []

    def forward(signum: int, _frame: FrameType | None) -> None:
        if child is None:
            early.append(signum)
        else:
            child.send_signal(signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
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
        print(f"tap: cannot start {command[0]}: {exc}", file=sys.stderr)
        trace.event("exit", code=127, error=str(exc))
        trace.close()
        return 127
    for signum in early:
        child.send_signal(signum)

    assert child.stdin and child.stdout and child.stderr
    to_child = child.stdin
    relays = [
        threading.Thread(
            target=relay,
            args=(sys.stdin.fileno(), to_child.fileno(), "c2s", trace, to_child.close),
            daemon=True,  # a client that never closes stdin must not keep the tap alive
        ),
        threading.Thread(
            target=relay, args=(child.stdout.fileno(), sys.stdout.fileno(), "s2c", trace)
        ),
        threading.Thread(
            target=relay, args=(child.stderr.fileno(), sys.stderr.fileno(), "stderr", trace)
        ),
    ]
    for thread in relays:
        thread.start()

    returncode = child.wait()
    for thread in relays[1:]:
        thread.join()

    code = exit_code(returncode)
    if returncode < 0:
        trace.event("exit", code=code, signal=-returncode)
    else:
        trace.event("exit", code=code)
    trace.close()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
