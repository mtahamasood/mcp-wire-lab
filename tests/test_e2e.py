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


def record_client(name: str, env: dict[str, str] | None = None, mode: str = "tour") -> Path:
    """Run `scripts/record.sh --client <mode>`; return the run directory it reports."""
    done = subprocess.run(
        ["scripts/record.sh", "--client", mode, name],
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


class AtlasClaimsTest(unittest.TestCase):
    """C9, real half: a lesson's `exercises` line is true of a fresh trace of its recording."""

    # Lesson file -> what it records: a fixture file name, or ("client", <mode>) for a run of
    # the raw client recorded by `scripts/record.sh --client <mode>`.
    LESSON_FIXTURES: dict[str, list[str | tuple[str, str]]] = {
        "01-the-wire-and-the-handshake.md": ["handshake-2025.ndjson"],
        "02-raw-client.md": [("client", "tour")],
        "03-server-initiated.md": [("client", "server-tour")],
        "05-sdk-client.md": [("client", "tour"), ("client", "sdk-tour")],
        "04-edge-lab.md": ["edge-unknown-method.ndjson", "edge-batch-array.ndjson",
                           "handshake-2025.ndjson"],
        "06-era-2026.md": [("client", "tour-2026")],
    }

    @classmethod
    def setUpClass(cls) -> None:
        assert SERVER.is_file(), f"{SERVER} missing: run scripts/bootstrap.sh"

    def test_lesson_declarations_appear_in_fresh_traces(self) -> None:
        from tools import atlas

        declared = atlas.declared_methods(ROOT)
        self.assertTrue(declared, "no lesson declares methods")
        for lesson, methods in declared.items():
            self.assertIn(lesson, self.LESSON_FIXTURES, f"{lesson} has no fixture mapped")
            seen: set[str] = set()
            for fixture in self.LESSON_FIXTURES[lesson]:
                run = (record_client("test-c9", mode=fixture[1]) if isinstance(fixture, tuple)
                       else record(fixture, "test-c9"))
                try:
                    for line in (run / "trace.jsonl").read_text().splitlines():
                        message = json.loads(line).get("json")
                        if isinstance(message, dict) and "method" in message:
                            seen.add(message["method"])
                        # 2026-07-28 carries roots/list, sampling/createMessage and
                        # elicitation/create only inside a result's inputRequests (phase 6 D10)
                        if isinstance(message, dict) and isinstance(message.get("result"), dict):
                            asked = message["result"].get("inputRequests")
                            if isinstance(asked, dict):
                                seen.update(r["method"] for r in asked.values()
                                            if isinstance(r, dict) and "method" in r)
                finally:
                    shutil.rmtree(run, ignore_errors=True)
            for method in methods:
                self.assertIn(method, seen, f"{lesson} declares {method}, absent from its trace")


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

    def test_tour_trace_passes_schema_check(self) -> None:
        done = subprocess.run(
            [sys.executable, "-m", "tap.check", str(self.run_dir / "trace.jsonl"),
             "--revision", "2025-11-25"],
            cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"check: ok \(\d+ frames\)")

    def test_tour_walkthrough_explains_fresh_trace(self) -> None:
        done = subprocess.run(
            [sys.executable, "-m", "tap.show", str(self.run_dir / "trace.jsonl"), "--explain",
             str(ROOT / "docs/walkthrough/02-raw-client-tour.md")],
            cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("(no note)", done.stdout)
        self.assertNotIn("(no frame)", done.stdout)
        self.assertIn("The first thing any client says", done.stdout)

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


# D4: the methods the server sends the client, and what the server tour's trace must hold.
SERVER_REQUESTS = {"roots/list", "sampling/createMessage", "elicitation/create"}
SERVER_NOTES = {
    "notifications/tools/list_changed", "notifications/prompts/list_changed",
    "notifications/resources/list_changed", "notifications/resources/updated",
    "notifications/message",
}
MATRIX_EXPECTED = {
    "none": set(),
    "roots": {"get-roots-list"},
    "sampling": {"trigger-sampling-request"},
    "elicitation": {"trigger-elicitation-request", "trigger-multi-step-elicitation"},
    "elicitation-url": {"trigger-url-elicitation"},
    "all": {"get-roots-list", "trigger-sampling-request", "trigger-elicitation-request",
            "trigger-multi-step-elicitation", "trigger-url-elicitation"},
}


class ServerTourTest(unittest.TestCase):
    """Phase 3: the raw client answering the real server's requests, recorded through the tap."""

    run_dir: Path

    @classmethod
    def setUpClass(cls) -> None:
        assert SERVER.is_file(), f"{SERVER} missing: run scripts/bootstrap.sh"
        cls.run_dir = record_client("test-server-tour", mode="server-tour")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.run_dir, ignore_errors=True)

    def test_server_tour_sees_every_server_initiated_method(self) -> None:
        # record_client already asserted exit status 0: record.sh passes on the client's status.
        recs = frames(self.run_dir)
        from_server = [r["json"] for r in recs if r.get("dir") == "s2c" and "json" in r]
        requests = [m for m in from_server if "method" in m and "id" in m]
        notes = {m["method"] for m in from_server if "method" in m and "id" not in m}
        self.assertEqual({m["method"] for m in requests}, SERVER_REQUESTS)
        self.assertTrue(SERVER_NOTES <= notes, SERVER_NOTES - notes)
        # every server request is answered, once, with its own id (order is not assumed)
        answers = [r["json"] for r in recs if r.get("dir") == "c2s" and "method" not in r["json"]]
        self.assertEqual(sorted(a["id"] for a in answers), sorted(m["id"] for m in requests))
        self.assertTrue(all("result" in a for a in answers), answers)
        sent = [r["json"] for r in recs if r.get("dir") == "c2s"]
        self.assertIn("notifications/roots/list_changed", {m.get("method") for m in sent})
        called = [m["params"]["name"] for m in sent if m.get("method") == "tools/call"]
        self.assertFalse([n for n in called if n.startswith("toggle-")], called)
        for tool in ("get-roots-list", "trigger-sampling-request", "trigger-elicitation-request",
                     "trigger-multi-step-elicitation", "trigger-url-elicitation",
                     "trigger-log-messages", "trigger-list-changed", "trigger-resource-update"):
            self.assertIn(tool, called)
        self.assertEqual((self.run_dir / "stderr.txt").read_text().count("client:"), 0)

    def test_capability_matrix(self) -> None:
        done = subprocess.run(
            [sys.executable, "-m", "client", "matrix", "--", "node", str(SERVER), "stdio"],
            cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        table: dict[str, tuple[set[str], set[str]]] = {}
        for line in done.stdout.splitlines()[2:]:
            name, tools, seen = (cell.strip() for cell in line.split("|"))
            table[name] = ({t.strip() for t in tools.split(",")} - {"-"},
                           {m.strip() for m in seen.split(",")} - {"-"})
        self.assertEqual({k: v[0] for k, v in table.items()}, MATRIX_EXPECTED)
        # a capability that unlocks a tool also makes the server speak first
        self.assertEqual(table["none"][1], set())
        self.assertIn("roots/list", table["roots"][1])
        self.assertIn("notifications/tools/list_changed", table["sampling"][1])
        self.assertNotIn("roots/list", table["sampling"][1])

    def test_server_tour_trace_checks_and_is_explained(self) -> None:
        trace = str(self.run_dir / "trace.jsonl")
        checked = subprocess.run(
            [sys.executable, "-m", "tap.check", trace, "--revision", "2025-11-25"],
            cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT,
        )
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertRegex(checked.stdout, r"check: ok \(\d+ frames\)")
        explained = subprocess.run(
            [sys.executable, "-m", "tap.show", trace, "--explain",
             str(ROOT / "docs/walkthrough/03-server-initiated.md")],
            cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT,
        )
        self.assertEqual(explained.returncode, 0, explained.stdout + explained.stderr)
        self.assertNotIn("(no note)", explained.stdout)
        self.assertNotIn("(no frame)", explained.stdout)
        self.assertIn("legacy shim", explained.stdout)


def tap_tool(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", module, *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=TIMEOUT)


class SdkClientTest(unittest.TestCase):
    """Phase 5: the SDK client against the real server, recorded through the tap."""

    runs: dict[str, Path]
    WALKTHROUGH = "docs/walkthrough/05-sdk-client.md"

    @classmethod
    def setUpClass(cls) -> None:
        assert SERVER.is_file(), f"{SERVER} missing: run scripts/bootstrap.sh"
        cls.runs = {
            "raw-tour": record_client("test-raw-tour", mode="tour"),
            "sdk-tour": record_client("test-sdk-tour", mode="sdk-tour"),
            "raw-server-tour": record_client("test-raw-server-tour", mode="server-tour"),
            "sdk-server-tour": record_client("test-sdk-server-tour", mode="sdk-server-tour"),
        }

    @classmethod
    def tearDownClass(cls) -> None:
        for run in cls.runs.values():
            shutil.rmtree(run, ignore_errors=True)

    def trace(self, name: str) -> str:
        return str(self.runs[name] / "trace.jsonl")

    def test_sdk_tour_runs_the_raw_tour_steps(self) -> None:
        # record_client already asserted exit status 0: record.sh passes on the client's status.
        recs = frames(self.runs["sdk-tour"])
        sent = [r["json"] for r in recs if r.get("dir") == "c2s"]
        self.assertEqual([m["method"] for m in sent], TOUR_METHODS)
        self.assertEqual([m["params"]["name"] for m in sent if m["method"] == "tools/call"],
                         ["echo", "get-sum", "trigger-long-running-operation",
                          "trigger-long-running-operation"])
        self.assertEqual([m["id"] for m in sent if "id" in m], list(range(17)))
        self.assertEqual(sent[0]["params"]["clientInfo"]["name"], "wire-lab-sdk")
        exits = [r for r in recs if r.get("dir") == "tap" and r.get("event") == "exit"]
        self.assertEqual([e.get("code") for e in exits], [0])
        # the only thing the SDK reports is the late progress of the cancelled call
        errors = [ln for ln in (self.runs["sdk-tour"] / "stderr.txt").read_text().splitlines()
                  if ln.startswith("sdk:")]
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("progress notification for an unknown token", errors[0])

    def test_sdk_traces_pass_schema_check(self) -> None:
        for name in ("sdk-tour", "sdk-server-tour"):
            done = tap_tool("tap.check", self.trace(name), "--revision", "2025-11-25")
            self.assertEqual(done.returncode, 0, name + done.stdout + done.stderr)
            self.assertRegex(done.stdout, r"check: ok \(\d+ frames\)")

    def test_sdk_server_tour_sees_every_server_initiated_method(self) -> None:
        recs = frames(self.runs["sdk-server-tour"])
        from_server = [r["json"] for r in recs if r.get("dir") == "s2c" and "json" in r]
        requests = [m for m in from_server if "method" in m and "id" in m]
        notes = {m["method"] for m in from_server if "method" in m and "id" not in m}
        self.assertEqual({m["method"] for m in requests}, SERVER_REQUESTS)
        self.assertTrue(SERVER_NOTES <= notes, SERVER_NOTES - notes)
        sent = [r["json"] for r in recs if r.get("dir") == "c2s"]
        answers = [m for m in sent if "method" not in m]
        self.assertEqual(sorted(a["id"] for a in answers), sorted(m["id"] for m in requests))
        self.assertTrue(all("result" in a for a in answers), answers)
        self.assertIn("notifications/roots/list_changed", {m.get("method") for m in sent})
        init = sent[0]["params"]
        self.assertEqual(init["clientInfo"]["name"], "wire-lab-sdk")
        self.assertEqual(init["capabilities"], {
            "roots": {"listChanged": True}, "sampling": {},
            "elicitation": {"form": {}, "url": {}}})
        # the handlers return phase 3 D1's values with the SDK's client name
        sampled = next(a for a in answers if "content" in a["result"])
        self.assertEqual(sampled["result"], {
            "role": "assistant",
            "content": {"type": "text", "text": "canned reply from wire-lab-sdk"},
            "model": "wire-lab-canned", "stopReason": "endTurn"})
        called = [m["params"]["name"] for m in sent if m.get("method") == "tools/call"]
        self.assertFalse([n for n in called if n.startswith("toggle-")], called)
        for tool in ("get-roots-list", "trigger-sampling-request", "trigger-elicitation-request",
                     "trigger-multi-step-elicitation", "trigger-url-elicitation",
                     "trigger-log-messages", "trigger-list-changed", "trigger-resource-update"):
            self.assertIn(tool, called)
        self.assertEqual((self.runs["sdk-server-tour"] / "stderr.txt").read_text().count("sdk:"), 0)

    def test_raw_walkthroughs_explain_sdk_traces(self) -> None:
        for name, walkthrough in (("sdk-tour", "02-raw-client-tour.md"),
                                  ("sdk-server-tour", "03-server-initiated.md")):
            done = tap_tool("tap.show", self.trace(name), "--explain",
                            str(ROOT / "docs/walkthrough" / walkthrough))
            self.assertEqual(done.returncode, 0, name + done.stdout + done.stderr)
            self.assertNotIn("(no note)", done.stdout)
            self.assertNotIn("(no frame)", done.stdout)

    def explained(self, raw: str, sdk: str, section: str) -> None:
        done = tap_tool("tap.diff", self.trace(raw), self.trace(sdk), "--explain",
                        f"{ROOT / self.WALKTHROUGH}#{section}")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("(no note)", done.stdout)
        self.assertNotIn("(no difference)", done.stdout)
        self.assertIn("~ c2s.initialize#0", done.stdout)  # the diff is not empty

    def test_tour_diff_is_explained(self) -> None:
        self.explained("raw-tour", "sdk-tour", "tour")

    def test_server_tour_diff_is_explained(self) -> None:
        self.explained("raw-server-tour", "sdk-server-tour", "server-tour")

    def test_record_sdk_client(self) -> None:
        # A secret in the caller's environment reaches neither the server nor the trace (D3).
        env = {**os.environ, "FAKE_SECRET_FOR_SDK": "leak"}
        run = record_client("test-sdk-env", env, mode="sdk-tour")
        try:
            text = (run / "trace.jsonl").read_text()
            self.assertNotIn("FAKE_SECRET_FOR_SDK", text)
            self.assertNotIn(os.environ["HOME"], text)
            spawn = next(r for r in frames(run) if r.get("event") == "spawn")
            argv = spawn["argv"]
            after_env = argv[argv.index("env") + 1 : argv.index("node")]
            self.assertEqual(after_env[0], "-i")
            self.assertEqual(sorted(a.split("=")[0] for a in after_env[1:]), sorted(ALLOWLIST))
            self.assertTrue((run / "stderr.txt").is_file())
        finally:
            shutil.rmtree(run, ignore_errors=True)
        # a client run's status is passed on: a server command that is not a server fails it
        bad = subprocess.run(["scripts/record.sh", "--client", "nope"], cwd=ROOT,
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("sdk-tour", bad.stderr)

    def test_record_without_install_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "scripts").mkdir()
            shutil.copy(ROOT / "scripts/record.sh", Path(tmp) / "scripts/record.sh")
            for mode in ("sdk-tour", "sdk-server-tour", "sdk-tour-2026"):
                done = subprocess.run(["scripts/record.sh", "--client", mode], cwd=tmp,
                                      capture_output=True, text=True, timeout=10)
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn("clients/sdk/node_modules missing (run scripts/bootstrap.sh)",
                              done.stderr)
                self.assertFalse((Path(tmp) / "runs").exists(), "no run folder is created")



# Phase 6: what the 2026 tour sends, in order (D6), and the walkthrough that explains it.
MODERN_WALKTHROUGH = ROOT / "docs/walkthrough/06-era-2026.md"
MODERN_TOUR_METHODS = [
    "server/discover", "tools/list", "tools/call", "tools/call", "resources/list",
    "resources/templates/list", "resources/read", "prompts/list", "prompts/get", "prompts/get",
    "completion/complete", "tools/call", "tools/call", "tools/call", "tools/call",
    "notifications/cancelled", "subscriptions/listen", *["tools/call"] * 14,
    "notifications/cancelled",
]
MODERN_TOUR_TOOLS = [
    "echo", "get-sum", "trigger-log-messages", "trigger-log-messages",
    "trigger-long-running-operation", "trigger-long-running-operation",
    "trigger-list-changed", "trigger-list-changed", "trigger-list-changed",
    "trigger-resource-update", "get-roots-list", "get-roots-list", "get-roots-list",
    "trigger-sampling-request", "trigger-sampling-request", "trigger-elicitation-request",
    "trigger-elicitation-request", "trigger-multi-step-elicitation",
    "trigger-multi-step-elicitation", "trigger-multi-step-elicitation",
]
ENVELOPE = "io.modelcontextprotocol/"


def run_tool(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *argv], cwd=ROOT, capture_output=True, text=True,
                          timeout=TIMEOUT)


class ModernTourTest(unittest.TestCase):
    """Phase 6 C8, C9, C10: the raw client in the 2026-07-28 era, recorded through the tap."""

    run_dir: Path

    @classmethod
    def setUpClass(cls) -> None:
        assert SERVER.is_file(), f"{SERVER} missing: run scripts/bootstrap.sh"
        cls.run_dir = record_client("test-tour-2026", mode="tour-2026")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.run_dir, ignore_errors=True)

    def test_tour_2026_runs_every_step(self) -> None:
        # record_client already asserted exit status 0: record.sh passes on the client's status.
        recs = frames(self.run_dir)
        sent = [r["json"] for r in recs if r.get("dir") == "c2s"]
        self.assertEqual([m["method"] for m in sent], MODERN_TOUR_METHODS)
        self.assertEqual([m["params"]["name"] for m in sent if m["method"] == "tools/call"],
                         MODERN_TOUR_TOOLS)
        self.assertNotIn("initialize", {m["method"] for m in sent})
        self.assertEqual([m["id"] for m in sent if "id" in m], list(range(30)))
        for message in sent:
            if "id" in message:  # every request carries the envelope; a notification does not
                meta = message["params"]["_meta"]
                self.assertEqual(meta[ENVELOPE + "protocolVersion"], "2026-07-28", message)
                self.assertIn(ENVELOPE + "clientInfo", meta)
                self.assertIn(ENVELOPE + "clientCapabilities", meta)
            else:
                self.assertNotIn("_meta", message.get("params", {}))
        exits = [r for r in recs if r.get("dir") == "tap" and r.get("event") == "exit"]
        self.assertEqual([e.get("code") for e in exits], [0])
        self.assertEqual((self.run_dir / "stderr.txt").read_text().count("client:"), 0)
        # all 21 methods of the schema: sent, received, or inside an input request
        from tools import atlas

        wanted = {m for m, per in atlas.schema_methods(ROOT).items() if "2026-07-28" in per}
        self.assertEqual(len(wanted), 21)
        seen: set[str] = set()
        for rec in recs:
            message = rec.get("json")
            if isinstance(message, dict):
                seen.add(message.get("method", ""))
                asked = (message.get("result") or {}).get("inputRequests") or {}
                seen.update(r["method"] for r in asked.values())
        self.assertEqual(wanted - seen, set())

    def test_record_tour_2026(self) -> None:
        env = {**os.environ, "FAKE_SECRET_FOR_C8": "leak"}
        run = record_client("test-c8-2026", env, mode="tour-2026")
        try:
            text = (run / "trace.jsonl").read_text()
            self.assertNotIn("FAKE_SECRET_FOR_C8", text)
            self.assertNotIn(os.environ["HOME"], text)
            spawn = next(r for r in frames(run) if r.get("event") == "spawn")
            argv = spawn["argv"]
            after_env = argv[argv.index("env") + 1 : argv.index("node")]
            self.assertEqual(sorted(a.split("=")[0] for a in after_env[1:]), sorted(ALLOWLIST))
            self.assertTrue((run / "stderr.txt").is_file())
            self.assertTrue(run.name.endswith("test-c8-2026"))
        finally:
            shutil.rmtree(run, ignore_errors=True)
        default = subprocess.run(["scripts/record.sh", "--client", "tour-2026"], cwd=ROOT,
                                 capture_output=True, text=True, timeout=TIMEOUT)
        self.assertEqual(default.returncode, 0, default.stderr)
        folder = ROOT / default.stdout.splitlines()[0].removeprefix("recorded: ").removesuffix(
            "/trace.jsonl")
        try:
            self.assertTrue(folder.name.endswith("-client-tour-2026"), folder.name)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_tour_2026_trace_passes_schema_check(self) -> None:
        done = run_tool("-m", "tap.check", str(self.run_dir / "trace.jsonl"),
                        "--revision", "2026-07-28")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"^check: ok \(\d+ frames\)\n$", "the output is unchanged")

    def test_tour_2026_walkthrough_explains_fresh_trace(self) -> None:
        done = run_tool("-m", "tap.show", str(self.run_dir / "trace.jsonl"), "--explain",
                        f"{MODERN_WALKTHROUGH}#tour")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("(no note)", done.stdout)
        self.assertNotIn("(no frame)", done.stdout)
        self.assertIn("there is no `initialize`", done.stdout)

    def test_era_diff_is_explained(self) -> None:
        old = record_client("test-era-2025")
        try:
            done = run_tool("-m", "tap.diff", str(old / "trace.jsonl"),
                            str(self.run_dir / "trace.jsonl"), "--explain",
                            f"{MODERN_WALKTHROUGH}#era-diff")
        finally:
            shutil.rmtree(old, ignore_errors=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("(no note)", done.stdout)
        self.assertNotIn("(no difference)", done.stdout)


class TasksTest(unittest.TestCase):
    """Phase 6 C11: the reduced tasks run and the SEP-2663 check of its trace."""

    run_dir: Path

    @classmethod
    def setUpClass(cls) -> None:
        assert SERVER.is_file(), f"{SERVER} missing: run scripts/bootstrap.sh"
        cls.run_dir = record_client("test-tasks-2026", mode="tasks-2026")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.run_dir, ignore_errors=True)

    def test_tasks_2026_runs_and_is_explained(self) -> None:
        recs = frames(self.run_dir)
        replies = {r["json"]["id"]: r["json"] for r in recs
                   if r.get("dir") == "s2c" and "id" in r["json"] and "method" not in r["json"]}
        self.assertEqual(replies[1]["error"]["code"], -32021)
        statuses = {i: replies[i]["result"].get("status") for i in (2, 4, 5, 6, 8)}
        self.assertEqual(statuses, {2: "input_required", 4: "completed", 5: "working",
                                    6: "working", 8: "cancelled"})
        self.assertIn("result", replies[4]["result"])
        self.assertEqual([r["json"]["method"] for r in recs if r.get("dir") == "c2s"], [
            "server/discover", "tools/call", "tools/call", "tasks/update", "tasks/get",
            "tools/call", "tasks/get", "tasks/cancel", "tasks/get"])
        done = run_tool("-m", "tap.show", str(self.run_dir / "trace.jsonl"), "--explain",
                        f"{MODERN_WALKTHROUGH}#tasks")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("(no note)", done.stdout)
        self.assertNotIn("(no frame)", done.stdout)

    def test_tasks_trace_passes_check_against_sep_2663(self) -> None:
        done = run_tool("-m", "tap.check", str(self.run_dir / "trace.jsonl"),
                        "--revision", "2026-07-28")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        # 10 tasks/* frames (five requests, five results) and the two task handles
        self.assertEqual(done.stdout.splitlines()[0], (
            "check: 12 of 18 frames checked against the SEP-2663 extension schema "
            "(tap/schemas/2026-07-28/sep-2663-tasks.json), not the pinned schema.json"))
        self.assertRegex(done.stdout.splitlines()[-1], r"^check: ok \(18 frames\)$")

    def test_tasks_trace_fails_pinned_only_check_on_extension_frames(self) -> None:
        done = run_tool("-m", "tap.check", str(self.run_dir / "trace.jsonl"),
                        "--revision", "2026-07-28", "--no-extensions")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        failing = [ln for ln in done.stdout.splitlines() if ln.startswith("seq ")]
        self.assertEqual(len(failing), 10, done.stdout)
        self.assertTrue(all("unknown method" in ln for ln in failing), done.stdout)
        self.assertEqual(sum("'tasks/" in ln for ln in failing), 5, "the five requests")
        self.assertNotIn("SEP-2663", done.stdout)


SDK_MODERN_WALKTHROUGH = ROOT / "docs/walkthrough/06-sdk-2026.md"


class SdkModernTourTest(unittest.TestCase):
    """Phase 6 Part B (C13-C15): the SDK client in the 2026-07-28 era, recorded through the tap."""

    runs: dict[str, Path]

    @classmethod
    def setUpClass(cls) -> None:
        assert SERVER.is_file(), f"{SERVER} missing: run scripts/bootstrap.sh"
        cls.runs = {
            "raw": record_client("test-raw-tour-2026", mode="tour-2026"),
            "sdk": record_client("test-sdk-tour-2026", mode="sdk-tour-2026"),
        }

    @classmethod
    def tearDownClass(cls) -> None:
        for run in cls.runs.values():
            shutil.rmtree(run, ignore_errors=True)

    def trace(self, name: str) -> str:
        return str(self.runs[name] / "trace.jsonl")

    def test_sdk_tour_2026_runs_and_starts_with_discover(self) -> None:
        # record_client already asserted exit status 0: record.sh passes on the client's status.
        recs = frames(self.runs["sdk"])
        spawns = [r for r in recs if r.get("event") == "spawn"]
        self.assertEqual(len(spawns), 1, "one process: the probe runs on the same connection")
        sent = [r["json"] for r in recs if r.get("dir") == "c2s"]
        self.assertEqual(sent[0]["method"], "server/discover")
        self.assertEqual([m["method"] for m in sent], MODERN_TOUR_METHODS)
        self.assertNotIn("initialize", {m["method"] for m in sent})
        self.assertEqual([m["params"]["name"] for m in sent if m["method"] == "tools/call"],
                         MODERN_TOUR_TOOLS)
        for message in sent:
            if "id" in message:
                meta = message["params"]["_meta"]
                self.assertEqual(meta[ENVELOPE + "protocolVersion"], "2026-07-28", message)
                self.assertEqual(meta[ENVELOPE + "clientInfo"]["name"], "wire-lab-sdk")
        exits = [r for r in recs if r.get("dir") == "tap" and r.get("event") == "exit"]
        self.assertEqual([e.get("code") for e in exits], [0])
        # the only thing the SDK reports is the late progress of the cancelled call
        errors = [ln for ln in (self.runs["sdk"] / "stderr.txt").read_text().splitlines()
                  if ln.startswith("sdk:")]
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("progress notification for an unknown token", errors[0])

    def test_sdk_era_option_usage_errors(self) -> None:
        main = str(ROOT / "clients/sdk/src/main.ts")
        for argv in (["server-tour", "--era", "2026-07-28"], ["tour", "--era", "2027-01-01"]):
            done = subprocess.run(["node", main, *argv, "--", "true"], cwd=ROOT,
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
            self.assertIn("usage: node clients/sdk/src/main.ts", done.stderr)

    def test_sdk_tour_2026_trace_passes_schema_check(self) -> None:
        done = run_tool("-m", "tap.check", self.trace("sdk"), "--revision", "2026-07-28")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"check: ok \(\d+ frames\)")

    def test_raw_vs_sdk_2026_diff_is_explained(self) -> None:
        done = run_tool("-m", "tap.diff", self.trace("raw"), self.trace("sdk"), "--explain",
                        str(SDK_MODERN_WALKTHROUGH))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("(no note)", done.stdout)
        self.assertNotIn("(no difference)", done.stdout)
        self.assertIn("~ c2s.server/discover#0", done.stdout)  # the diff is not empty


if __name__ == "__main__":
    unittest.main()
