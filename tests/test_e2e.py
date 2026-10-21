"""C7, C14 (real half), C16, phase 4 C5: tap, driver, viewer, record.sh vs the real server (G5)."""

from __future__ import annotations

import json
import os
import re
import shutil
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
# record.sh's environment allowlist (D14). Node adds no variable of its own (measured).
ALLOWLIST = {"PATH", "HOME", "LANG", "MCP_WIRE_LAB"}


def record(fixture: str, name: str, env: dict[str, str] | None = None) -> Path:
    """Run scripts/record.sh on a fixture; return the run directory it reports."""
    done = subprocess.run(
        ["scripts/record.sh", str(FIXTURES / fixture), name],
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

    def test_c14_explain_covers_a_fresh_run(self) -> None:
        run = record("handshake-2025.ndjson", "test-c14")
        done = subprocess.run(
            [sys.executable, "-m", "tap.show", str(run / "trace.jsonl"), "--explain",
             str(ROOT / "docs/walkthrough/01-handshake-2025.md")],
            cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("(no note)", done.stdout)
        self.assertNotIn("(no frame)", done.stdout)
        self.assertIn("The first thing any client says", done.stdout)

    def test_c16_minimal_environment(self) -> None:
        env = {**os.environ, "FAKE_SECRET_FOR_C16": "leak"}
        run = record("get-env.ndjson", "test-c16", env)
        text = (run / "trace.jsonl").read_text()
        # Presence first, in the frame that answers get-env (id 1), so neither the spawn record's
        # argv (which names MCP_WIRE_LAB=1) nor an empty or failed reply can satisfy it.
        frames = [json.loads(ln) for ln in text.splitlines()]
        replies = [r for r in frames if r.get("dir") == "s2c"
                   and isinstance(r.get("json"), dict) and r["json"].get("id") == 1]
        self.assertEqual(len(replies), 1, "s2c frames answering get-env")
        self.assertIn("MCP_WIRE_LAB", json.dumps(replies[0]["json"]))
        variables = json.loads(replies[0]["json"]["result"]["content"][0]["text"])
        self.assertEqual(set(variables), ALLOWLIST, "variable names must equal the allowlist")
        self.assertNotIn("FAKE_SECRET_FOR_C16", text)
        self.assertNotIn(os.environ["HOME"], text)

    def test_c18_unusable_name_fails_fast(self) -> None:
        # A name with a missing parent folder makes mkdir fail without the folder existing.
        try:
            done = subprocess.run(
                ["scripts/record.sh", str(FIXTURES / "handshake-2025.ndjson"), "sub/name"],
                cwd=ROOT, capture_output=True, text=True, timeout=10,
            )
        except subprocess.TimeoutExpired:
            self.fail("record.sh did not exit within 10 s")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertTrue(done.stderr.splitlines()[-1].startswith("record: cannot create runs/"),
                        done.stderr)
        self.assertEqual(list((ROOT / "runs").glob("*-sub")), [], "a runs/*-sub folder was left")

    def test_r15_same_name_twice_in_one_second(self) -> None:
        # A fake `date` pins the timestamp, so both runs want the same folder name (D14).
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "date"
            fake.write_text("#!/bin/sh\necho 19990101T000000Z\n")
            fake.chmod(0o755)
            env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}"}
            runs = [record("get-env.ndjson", "test-dup", env) for _ in range(2)]
        try:
            self.assertEqual(len({r.name for r in runs}), 2, "two distinct run folders")
            for r in runs:
                self.assertTrue(r.name.startswith("19990101T000000Z-test-dup"))
                self.assertTrue((r / "trace.jsonl").is_file())
        finally:
            for r in runs:
                shutil.rmtree(r, ignore_errors=True)


# The edge experiments (phase 4 D1): walkthrough section -> fixture. `before-initialize` reuses
# phase 1's `exp-list-first`; `oversized-frame` has no committed fixture (the test writes it).
EDGE_FIXTURES = {
    "missing-jsonrpc": "edge-missing-jsonrpc.ndjson",
    "before-initialize": "exp-list-first.ndjson",
    "unknown-method": "edge-unknown-method.ndjson",
    "duplicate-id": "edge-duplicate-id.ndjson",
    "string-id": "edge-string-id.ndjson",
    "notification-with-id": "edge-notification-with-id.ndjson",
    "batch-array": "edge-batch-array.ndjson",
}
OVERSIZED = "oversized-frame"
VERDICT = re.compile(r"^\*\*Verdict: (follows the spec|stricter|looser|spec silent)\.", re.M)


def write_oversized_fixture(path: Path) -> None:
    """The handshake and one `echo` call whose argument is a 1 MiB string (D1)."""
    handshake = (FIXTURES / "handshake-2025.ndjson").read_text().splitlines()[:2]
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "echo", "arguments": {"message": "x" * 1024 * 1024}}}
    path.write_text("\n".join([*handshake, json.dumps(call, separators=(",", ":"))]) + "\n")


class EdgeLabTest(unittest.TestCase):
    WALKTHROUGH = ROOT / "docs/walkthrough/04-edge-lab.md"

    def explain(self, run: Path, name: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "tap.show", str(run / "trace.jsonl"), "--explain",
             f"{self.WALKTHROUGH}#{name}"],
            cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT,
        )

    def check_explained(self, run: Path, name: str) -> None:
        done = self.explain(run, name)
        self.assertEqual(done.returncode, 0, f"{name}:\n{done.stdout}{done.stderr}")
        self.assertNotIn("(no note)", done.stdout, name)
        self.assertNotIn("(no frame)", done.stdout, name)

    def test_every_edge_fixture_is_explained(self) -> None:
        # No edge fixture without an experiment, none without a fixture, a verdict for each.
        committed = {p.name for p in FIXTURES.glob("edge-*.ndjson")}
        expected = {f for f in EDGE_FIXTURES.values() if f.startswith("edge-")}
        self.assertEqual(committed, expected)
        text = self.WALKTHROUGH.read_text()
        sections = dict(re.findall(r"^## (\S+)\n(.*?)(?=^## |\Z)", text, re.M | re.S))
        self.assertEqual(set(sections) - {"shared"}, {*EDGE_FIXTURES, OVERSIZED})
        for name, body in sections.items():
            if name != "shared":
                self.assertEqual(len(VERDICT.findall(body)), 1, f"{name}: one verdict line")
        runs = []
        try:
            for name, fixture in EDGE_FIXTURES.items():
                runs.append(record(fixture, f"test-edge-{name}"))
                self.check_explained(runs[-1], name)
            with tempfile.TemporaryDirectory() as tmp:
                big = Path(tmp) / "edge-oversized-frame.ndjson"
                write_oversized_fixture(big)
                self.assertGreaterEqual(big.stat().st_size, 1024 * 1024)
                done = subprocess.run(["scripts/record.sh", str(big), "test-edge-oversized"],
                                      cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
                self.assertEqual(done.returncode, 0, done.stderr)
                first = done.stdout.splitlines()[0]
                runs.append(ROOT / first.removeprefix("recorded: ").removesuffix("/trace.jsonl"))
            self.check_explained(runs[-1], OVERSIZED)
        finally:
            for r in runs:
                shutil.rmtree(r, ignore_errors=True)

    def test_unknown_method_gets_method_not_found(self) -> None:
        run = record("edge-unknown-method.ndjson", "test-edge-unknown")
        try:
            frames = [json.loads(ln) for ln in (run / "trace.jsonl").read_text().splitlines()]
            replies = [r["json"] for r in frames if r["dir"] == "s2c" and r["json"].get("id") == 1]
            self.assertEqual(len(replies), 1)
            self.assertEqual(replies[0]["error"]["code"], -32601)
        finally:
            shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
