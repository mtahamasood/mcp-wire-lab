"""C7, C14 (real half) and C16: tap, driver, viewer and record.sh against the real server (G5)."""

from __future__ import annotations

import json
import os
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


def record_client(name: str, env: dict[str, str] | None = None) -> Path:
    """Run `scripts/record.sh --client tour`; return the run directory it reports."""
    done = subprocess.run(
        ["scripts/record.sh", "--client", "tour", name],
        cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT, env=env,
    )
    assert done.returncode == 0, done.stderr
    first = done.stdout.splitlines()[0]
    return ROOT / first.removeprefix("recorded: ").removesuffix("/trace.jsonl")


def frames(run: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        json.loads(ln) for ln in (run / "trace.jsonl").read_text().splitlines()
    ]
    return out


# What the tour sends, in order (D3): every request, and the one notification after initialize.
TOUR_METHODS = [
    "initialize", "notifications/initialized", "ping", "tools/list", "tools/call", "tools/call",
    "resources/list", "resources/templates/list", "resources/read", "resources/subscribe",
    "resources/unsubscribe", "prompts/list", "prompts/get", "prompts/get", "completion/complete",
    "logging/setLevel", "tools/call", "tools/call", "notifications/cancelled",
]


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


class RawClientTest(unittest.TestCase):
    """Phase 2: the raw client against the real server, recorded through the tap."""

    run_dir: Path

    @classmethod
    def setUpClass(cls) -> None:
        assert SERVER.is_file(), f"{SERVER} missing: run scripts/bootstrap.sh"
        cls.run_dir = record_client("test-tour")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.run_dir, ignore_errors=True)

    def test_tour_runs_every_client_initiated_method(self) -> None:
        recs = frames(self.run_dir)
        sent = [r["json"] for r in recs if r.get("dir") == "c2s"]
        self.assertEqual([m["method"] for m in sent], TOUR_METHODS)
        self.assertEqual([m["params"]["name"] for m in sent if m["method"] == "tools/call"],
                         ["echo", "get-sum", "trigger-long-running-operation",
                          "trigger-long-running-operation"])
        self.assertEqual([m["id"] for m in sent if "id" in m], list(range(17)))
        replies = {r["json"]["id"]: r["json"] for r in recs
                   if r.get("dir") == "s2c" and "id" in r["json"] and "method" not in r["json"]}
        self.assertEqual(set(replies), set(range(17)) - {16}, "every request but the cancelled")
        self.assertTrue(all("result" in m for m in replies.values()))
        exits = [r for r in recs if r.get("dir") == "tap" and r.get("event") == "exit"]
        self.assertEqual([e.get("code") for e in exits], [0])
        self.assertEqual((self.run_dir / "stderr.txt").read_text().count("client:"), 0)

    def test_record_client_tour(self) -> None:
        # A secret in the caller's environment reaches neither the server nor the trace (D14).
        env = {**os.environ, "FAKE_SECRET_FOR_C8": "leak"}
        run = record_client("test-c8", env)
        try:
            text = (run / "trace.jsonl").read_text()
            self.assertNotIn("FAKE_SECRET_FOR_C8", text)
            self.assertNotIn(os.environ["HOME"], text)
            spawn = next(r for r in frames(run) if r.get("event") == "spawn")
            argv = spawn["argv"]
            after_env = argv[argv.index("env") + 1 : argv.index("node")]
            self.assertEqual(after_env[0], "-i")
            self.assertEqual(sorted(a.split("=")[0] for a in after_env[1:]), sorted(ALLOWLIST))
            self.assertTrue((run / "stderr.txt").is_file())
        finally:
            shutil.rmtree(run, ignore_errors=True)
        # the fixture form is unchanged, and a bad mode fails fast
        fixture_run = record("handshake-2025.ndjson", "test-c8-fixture")
        try:
            self.assertTrue((fixture_run / "trace.jsonl").is_file())
        finally:
            shutil.rmtree(fixture_run, ignore_errors=True)
        bad = subprocess.run(["scripts/record.sh", "--client", "nope"], cwd=ROOT,
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("unknown client mode", bad.stderr)


if __name__ == "__main__":
    unittest.main()
