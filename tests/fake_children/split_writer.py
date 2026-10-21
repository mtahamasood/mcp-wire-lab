"""Writes OUTPUT to stdout in two writes with a pause, so a frame arrives split across reads.

The first frame is cut in two around the pause; the second is larger than two read chunks.
"""

from __future__ import annotations

import os
import time

BIG = b'{"id":2,"result":{"text":"' + b"x" * 200_000 + b'"}}\n'
FRAMES = [b'{"id":1,"result":{}}\n', BIG, b'{"id":3,"result":{}}\n']
OUTPUT = b"".join(FRAMES)


def write_all(data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(1, view) :]


def main() -> int:
    write_all(OUTPUT[:10])
    time.sleep(0.2)
    write_all(OUTPUT[10:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
