"""Writes STDERR_BYTES to stderr (ending in a partial line) and STDOUT_BYTES to stdout."""

from __future__ import annotations

import os

STDERR_BYTES = b"warn: starting\nwarn: still here\nwarn: no newline"
STDOUT_BYTES = b'{"jsonrpc":"2.0","method":"ready"}\n'


def main() -> int:
    os.write(2, STDERR_BYTES)
    os.write(1, STDOUT_BYTES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
