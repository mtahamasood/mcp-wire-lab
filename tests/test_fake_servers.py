"""Phase 8, P8-FL-5 follow-up: a test fake does not outlive the process that started it."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "tests/fake_servers/http_upstream.py"
WAIT = 10.0  # seconds a fake may take to notice that its parent is gone

# A stand-in for the tap: starts the fake with nothing on its stdin, as the tap does for an
# upstream under --http, prints its number, and waits to be killed.
PARENT = (
    "import os, subprocess, sys, time\n"
    "argv = [sys.executable, sys.argv[1], os.devnull]\n"
    "child = subprocess.Popen(argv, stdin=subprocess.DEVNULL)\n"
    "print(child.pid, flush=True)\n"
    "time.sleep(600)\n"
)


def alive(pid: int) -> bool:
    """True while `pid` runs (a zombie waiting to be reaped is not running)."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as stat:
            return stat.read().rpartition(")")[2].split()[0] != "Z"
    except OSError:
        return False


class OrphanTest(unittest.TestCase):
    def test_http_upstream_exits_when_its_parent_is_killed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "PORT": str(Path(tmp) / "upstream.sock")}
            parent = subprocess.Popen(
                [sys.executable, "-c", PARENT, str(UPSTREAM)], stdout=subprocess.PIPE, env=env,
                text=True)
            assert parent.stdout is not None
            child = int(parent.stdout.readline())
            self.addCleanup(lambda: os.kill(child, signal.SIGKILL) if alive(child) else None)
            self.addCleanup(parent.stdout.close)
            time.sleep(0.5)  # the fake is up and has noted its parent
            self.assertTrue(alive(child), "the fake should run while its parent does")
            parent.kill()
            parent.wait()
            deadline = time.monotonic() + WAIT
            while alive(child) and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertFalse(alive(child), f"the fake outlived its killed parent by {WAIT:g} s")


if __name__ == "__main__":
    unittest.main()
