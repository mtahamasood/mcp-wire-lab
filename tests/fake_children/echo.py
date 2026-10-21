"""Transforming echo: writes PREFIX + each line it reads, keeping a final partial line.

Writes the exact bytes it received to RECEIVED and the exact bytes it sent to SENT, so a
test can compare both directions of the tap with the child's own view of them.
"""

from __future__ import annotations

import argparse
import os
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("received")
    parser.add_argument("sent")
    parser.add_argument("--prefix", default="echo:")
    parser.add_argument("--say-eof", action="store_true", help="after stdin EOF, wait, then say so")
    args = parser.parse_args()
    prefix = args.prefix.encode()
    received = bytearray()
    sent = bytearray()

    def send(data: bytes) -> None:
        sent.extend(data)
        os.write(1, data)

    pending = b""
    while chunk := os.read(0, 65536):
        received.extend(chunk)
        pending += chunk
        while b"\n" in pending:
            line, _, pending = pending.partition(b"\n")
            send(prefix + line + b"\n")
    if pending:
        send(prefix + pending)
    if args.say_eof:
        time.sleep(0.3)
        send(b"eof\n")
    with open(args.received, "wb") as f:
        f.write(received)
    with open(args.sent, "wb") as f:
        f.write(sent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
