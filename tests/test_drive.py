"""C1: the driver's `_drive` member (phase 4 D2): removed, the rest forwarded unchanged."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 30

# A child that writes everything it receives to a file and answers only lines that contain
# the word "answer" (it echoes that line back), so a line without it gets no reply.
CHILD = (
    "import os, sys\n"
    "got = bytearray()\n"
    "buf = b''\n"
    "while c := os.read(0, 65536):\n"
    "    got += c\n"
    "    buf += c\n"
    "    while b'\\n' in buf:\n"
    "        line, _, buf = buf.partition(b'\\n')\n"
    "        if b'answer' in line:\n"
    "            os.write(1, line + b'\\n')\n"
    "open(sys.argv[1], 'wb').write(bytes(got))\n"
)


class DriveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.received = Path(self.tmp.name) / "received.bin"

    def drive(
        self, fixture: bytes, timeout: str = "5"
    ) -> tuple[subprocess.CompletedProcess[bytes], float]:
        path = Path(self.tmp.name) / "fixture.ndjson"
        path.write_bytes(fixture)
        start = time.monotonic()
        done = subprocess.run(
            [sys.executable, "tests/drive.py", str(path), "--timeout", timeout, "--",
             sys.executable, "-c", CHILD, str(self.received)],
            cwd=ROOT, capture_output=True, timeout=TIMEOUT,
        )
        return done, time.monotonic() - start

    def test_plain_lines_unchanged(self) -> None:
        fixture = (
            b'{"jsonrpc" : "2.0",  "id":1, "method":"answer"}\n'
            b'not json at all\n'
            b'["batch", "array"]\n'
            b'{"id":2,"method":"answer","params":{"_drive_like":1}}\n'
        )
        done, _ = self.drive(fixture)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.received.read_bytes(), fixture)
        self.assertEqual(
            done.stdout,
            b'{"jsonrpc" : "2.0",  "id":1, "method":"answer"}\n'
            b'{"id":2,"method":"answer","params":{"_drive_like":1}}\n',
        )

    def test_drive_member_is_removed_and_rest_unchanged(self) -> None:
        fixture = (
            b'{"jsonrpc" : "2.0",  "id":1, "method":"answer" , "_drive": {"expect": "reply"}}\n'
            b'{"_drive":{"expect":"none","wait_ms":10}, "z": 1, "a": "answer"}\n'
            b'{"z":1,"_drive":{"expect":"none","wait_ms":10},"a":"answer\\u00e9 \xc3\xa9"}\n'
            b'{"id":3,"method":"answer","_drive":{"expect":"none","wait_ms":10}}\n'
        )
        done, _ = self.drive(fixture)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(
            self.received.read_bytes(),
            b'{"jsonrpc" : "2.0",  "id":1, "method":"answer"}\n'
            b'{"z": 1, "a": "answer"}\n'
            b'{"z":1,"a":"answer\\u00e9 \xc3\xa9"}\n'
            b'{"id":3,"method":"answer"}\n',
        )
        self.assertNotIn(b"_drive", self.received.read_bytes())

    def test_expect_none_does_not_wait_for_id(self) -> None:
        # The child never answers id 7; waiting for it would hit the 5 s timeout and fail.
        fixture = (
            b'{"id":7,"method":"quiet","_drive":{"expect":"none","wait_ms":400}}\n'
            b'{"id":8,"method":"answer"}\n'
        )
        done, took = self.drive(fixture)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn(b"no response", done.stderr)
        self.assertGreaterEqual(took, 0.4, "the driver did not wait wait_ms")
        self.assertLess(took, 4.0, "the driver waited for an id that never comes")
        self.assertEqual(done.stdout, b'{"id":8,"method":"answer"}\n')

    def test_expect_none_still_relays_a_reply_that_arrives(self) -> None:
        fixture = b'{"id":7,"method":"answer","_drive":{"expect":"none","wait_ms":200}}\n'
        done, _ = self.drive(fixture)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, b'{"id":7,"method":"answer"}\n')

    def test_expect_reply_waits_for_id(self) -> None:
        fixture = b'{"id":7,"method":"quiet","_drive":{"expect":"reply"}}\n'
        done, _ = self.drive(fixture, timeout="1")
        self.assertEqual(done.returncode, 1)
        self.assertIn(b"no response with id 7", done.stderr)


if __name__ == "__main__":
    unittest.main()
