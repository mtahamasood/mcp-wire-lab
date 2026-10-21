"""The fixture driver (D9): sends a fixture through a command, one line at a time.

Usage:
  python3 tests/drive.py <fixture> [--timeout SECONDS] -- <command...>

Runs the command (normally the tap), writes each fixture line to its stdin, and after a line
that carries an "id" reads its stdout until a line with the same "id" arrives. Then it sends
the next line. A line whose JSON object has the member "_drive" is the exception (phase 4 D2):
the member is cut out of the bytes (everything else is sent as written), and
{"expect": "none", "wait_ms": N} makes the driver wait N milliseconds, relaying whatever
arrives, instead of waiting for an id; {"expect": "reply"} keeps the rule above.
At the end it closes stdin and waits for the command. It matches ids and
nothing else: it never builds, inspects, or decides on a message (it is not a client).
Everything the command writes to stdout is copied to this process's stdout.
"""

from __future__ import annotations

import json
import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_TIMEOUT = 20.0
USAGE = "usage: python3 tests/drive.py <fixture> [--timeout SECONDS] -- <command...>"


def line_id(line: bytes) -> object:
    """The "id" of a JSON object line, or None (also for anything that is not one)."""
    try:
        value = json.loads(line)
    except ValueError:
        return None
    return value.get("id") if isinstance(value, dict) else None


# The `_drive` member and the comma that joins it to its neighbour. Its value is a flat object.
_MEMBER = rb'"_drive"\s*:\s*\{[^{}]*\}'
_BEFORE_COMMA = re.compile(_MEMBER + rb"\s*,\s*")  # a member follows it: cut `"_drive":{...},`
_AFTER_COMMA = re.compile(rb"\s*,\s*" + _MEMBER)  # it is last: cut `,"_drive":{...}`
_ONLY_MEMBER = re.compile(_MEMBER)


class FixtureError(Exception):
    """A fixture line whose `_drive` member the driver cannot read."""


def split_drive(line: bytes) -> tuple[bytes, dict[str, object] | None]:
    """The line without its `_drive` member (all other bytes as written), and that member."""
    try:
        value = json.loads(line)
    except ValueError:
        return line, None
    if not isinstance(value, dict) or "_drive" not in value:
        return line, None
    control = value["_drive"]
    if not isinstance(control, dict) or control.get("expect") not in ("none", "reply"):
        raise FixtureError(f'_drive must be an object with "expect" of none or reply: {control!r}')
    if control["expect"] == "none" and not isinstance(control.get("wait_ms"), int):
        raise FixtureError('_drive with "expect": "none" needs an integer "wait_ms"')
    for pattern in (_BEFORE_COMMA, _AFTER_COMMA, _ONLY_MEMBER):
        cut, count = pattern.subn(b"", line, count=1)
        if count:
            expected = {k: v for k, v in value.items() if k != "_drive"}
            try:
                if json.loads(cut) == expected:
                    return cut, control
            except ValueError:
                pass
    raise FixtureError("could not cut the _drive member out of the line")


def wait_ms(stdout_fd: int, pending: bytearray, ms: int) -> None:
    """Copy the command's stdout through for `ms` milliseconds, waiting on no id."""
    deadline = time.monotonic() + ms / 1000
    while True:
        left = deadline - time.monotonic()
        if left > 0:
            ready, _, _ = select.select([stdout_fd], [], [], left)
            if ready:
                chunk = os.read(stdout_fd, 65536)
                if not chunk:
                    return
                pending.extend(chunk)
        while b"\n" in pending:
            end = pending.index(b"\n") + 1
            os.write(sys.stdout.fileno(), bytes(pending[:end]))
            del pending[:end]
        if left <= 0:
            return


def wait_for_id(stdout_fd: int, want: object, pending: bytearray, deadline: float) -> bool:
    """Copy the command's stdout through until a line with id `want` has been seen."""
    while True:
        while b"\n" in pending:
            end = pending.index(b"\n") + 1
            line = bytes(pending[:end])
            del pending[:end]
            os.write(sys.stdout.fileno(), line)
            if line_id(line) == want:
                return True
        left = deadline - time.monotonic()
        if left <= 0:
            return False
        ready, _, _ = select.select([stdout_fd], [], [], left)
        if not ready:
            return False
        chunk = os.read(stdout_fd, 65536)
        if not chunk:
            return False
        pending.extend(chunk)


def main(argv: list[str]) -> int:
    if "--" not in argv or not argv[: argv.index("--")]:
        print(USAGE, file=sys.stderr)
        return 2
    split = argv.index("--")
    options, command = argv[:split], argv[split + 1 :]
    fixture, timeout = Path(options[0]), DEFAULT_TIMEOUT
    if options[1:2] == ["--timeout"] and len(options) == 3:
        timeout = float(options[2])
    elif len(options) != 1 or not command:
        print(USAGE, file=sys.stderr)
        return 2

    lines = [ln for ln in fixture.read_bytes().splitlines(keepends=True) if ln.strip()]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
    assert proc.stdin and proc.stdout
    pending = bytearray()
    status = 0
    for line in lines:
        try:
            line, control = split_drive(line)
        except FixtureError as exc:
            print(f"drive: {exc}", file=sys.stderr)
            status = 2
            break
        if not line.endswith(b"\n"):
            line += b"\n"
        proc.stdin.write(line)
        if control is not None and control["expect"] == "none":
            wait_ms(proc.stdout.fileno(), pending, int(str(control["wait_ms"])))
            continue
        want = line_id(line)
        if want is not None and not wait_for_id(
            proc.stdout.fileno(), want, pending, time.monotonic() + timeout
        ):
            print(f"drive: no response with id {want!r} within {timeout}s", file=sys.stderr)
            status = 1
            break
    proc.stdin.close()
    # Relay whatever remains (late notifications, the end of the stream) until it closes.
    while chunk := (bytes(pending) if pending else os.read(proc.stdout.fileno(), 65536)):
        pending.clear()
        os.write(sys.stdout.fileno(), chunk)
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        print("drive: command did not exit after stdin closed", file=sys.stderr)
        return 1
    return status or code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
