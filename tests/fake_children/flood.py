"""Writes LINES lines to stdout and STDERR_LINES lines to stderr, then exits at once."""

from __future__ import annotations

import os

LINES = 20_000
STDERR_LINES = 2_000


def main() -> int:
    out = b"".join(b'{"n":%d}\n' % n for n in range(LINES))
    err = b"".join(b"log %d\n" % n for n in range(STDERR_LINES))
    for fd, data in ((2, err[: len(err) // 2]), (1, out), (2, err[len(err) // 2 :])):
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
