"""Writes FRAMES to stdout: one not valid UTF-8, one not JSON, one valid JSON."""

from __future__ import annotations

import os

FRAMES = [b"\xff\xfe not utf-8 \xc3\x28\n", b"this is not json\n", b'{"ok": true}\n']


def main() -> int:
    os.write(1, b"".join(FRAMES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
