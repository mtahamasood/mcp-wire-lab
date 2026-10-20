"""Says `ready`, then waits; on SIGINT or SIGTERM says which and exits 10 + the signal number."""

from __future__ import annotations

import os
import signal
import time
from types import FrameType


def on_signal(signum: int, _frame: FrameType | None) -> None:
    os.write(1, f"got {signal.Signals(signum).name}\n".encode())
    os._exit(10 + signum)


def main() -> int:
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, on_signal)
    os.write(1, b"ready\n")
    time.sleep(30)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
