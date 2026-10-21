"""Writes OUTPUT to stdout, which ends without a newline, then exits."""

from __future__ import annotations

import os

OUTPUT = b'{"id":1,"result":{}}\n{"id":2,"res'


def main() -> int:
    os.write(1, OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
