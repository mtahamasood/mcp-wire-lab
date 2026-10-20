"""Says `ready`, then waits; on each forwarded signal says which, and exits 10 + its number.

It stays up for half a second after the first signal, so a signal delivered twice (once by
the tap, once straight from the process group) shows as two `got` lines.
"""

from __future__ import annotations

import os
import signal
import time
from types import FrameType

SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)
received: list[int] = []


def on_signal(signum: int, _frame: FrameType | None) -> None:
    os.write(1, f"got {signal.Signals(signum).name}\n".encode())
    received.append(signum)


def main() -> int:
    for sig in SIGNALS:
        signal.signal(sig, on_signal)
    os.write(1, b"ready\n")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if received:
            time.sleep(0.5)
            os._exit(10 + received[0])
        time.sleep(0.01)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
