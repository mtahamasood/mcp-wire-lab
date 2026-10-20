"""C7 and C16: the tap, the driver and record.sh against the real, pinned, built server (G5)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests/fixtures"
SERVER = ROOT / "vendor/servers/src/everything/dist/index.js"
TIMEOUT = 120


def record(fixture: str, env: dict[str, str] | None = None) -> Path:
    """Run scripts/record.sh on a fixture; return the run directory it reports."""
    done = subprocess.run(
        ["scripts/record.sh", str(FIXTURES / fixture), "test"],
        cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT, env=env,
    )
    assert done.returncode == 0, done.stderr
    first = done.stdout.splitlines()[0]
    return ROOT / first.removeprefix("recorded: ").removesuffix("/trace.jsonl")


class E2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert SERVER.is_file(), f"{SERVER} missing: run scripts/bootstrap.sh"

    def test_c7_handshake_against_the_real_server(self) -> None:
        # Driver -> tap -> server directly: what the driver prints is what a client would see.
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            done = subprocess.run(
                [sys.executable, "tests/drive.py", str(FIXTURES / "handshake-2025.ndjson"),
                 "--timeout", "10", "--", sys.executable, "-m", "tap", "--trace", str(trace),
                 "--", "node", str(SERVER), "stdio"],
                cwd=ROOT, capture_output=True, timeout=TIMEOUT,
            )
            seen = [json.loads(ln) for ln in done.stdout.splitlines()]
            sent = [json.loads(ln)["json"] for ln in trace.read_text().splitlines()
                    if json.loads(ln).get("dir") == "c2s"]

        def response(msg_id: int) -> dict[str, Any]:
            found = [m for m in seen if m.get("id") == msg_id]
            self.assertEqual(len(found), 1, f"responses with id {msg_id} reaching the driver")
            result: dict[str, Any] = found[0]
            return result

        init = response(0)
        self.assertIn("protocolVersion", init["result"])
        self.assertIn("capabilities", init["result"])
        self.assertIn("name", init["result"]["serverInfo"])
        self.assertTrue(response(1)["result"]["tools"])
        self.assertEqual(response(2)["result"], {})
        for request in (m for m in sent if "id" in m):
            self.assertEqual(sum(m.get("id") == request["id"] for m in seen), 1)
        self.assertEqual(done.returncode, 0, done.stderr.decode())

    def test_c16_minimal_environment(self) -> None:
        env = {**os.environ, "FAKE_SECRET_FOR_C16": "leak"}
        run = record("get-env.ndjson", env)
        text = (run / "trace.jsonl").read_text()
        # Presence first: an empty or failed get-env result must not pass.
        self.assertIn("MCP_WIRE_LAB", text)
        self.assertNotIn("FAKE_SECRET_FOR_C16", text)
        self.assertNotIn(os.environ["HOME"], text)


if __name__ == "__main__":
    unittest.main()
