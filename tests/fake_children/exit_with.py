"""Exits with the code given, or kills itself with a signal: `exit_with.py 3` or `-15`."""

from __future__ import annotations

import os
import sys


def main() -> int:
    code = int(sys.argv[1])
    if code < 0:
        os.kill(os.getpid(), -code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
