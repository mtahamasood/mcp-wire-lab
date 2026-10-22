"""Phase 7 parts A, B1, B2, D, E (G5): `record.sh --http` and the HTTP modes against the real
server.

C10 (record.sh), C28 (no TCP listener), C16-C18 (the tour's trace), C20 (the walkthrough), C22
(the earlier tours), C26 (the 2026-07-28 tour).
Each test class records the tour once and checks facts about that run.
"""

from __future__ import annotations

import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from tests.test_e2e import (
    MODERN_TOUR_METHODS,
    MODERN_TOUR_TOOLS,
    SERVER_NOTES,
    SERVER_REQUESTS,
    TOUR_METHODS,
)
from tests.test_tap_http import free_port

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "vendor/servers/src/everything/dist/index.js"
TIMEOUT = 120
# record.sh's environment allowlist (D14), and PORT, which the tap adds for HTTP runs (D7).
ALLOWLIST = {"PATH", "HOME", "LANG", "MCP_WIRE_LAB"}
WALKTHROUGH = ROOT / "docs/walkthrough/07-streamable-http.md"
Record = dict[str, Any]


def records(run: Path) -> list[Record]:
    return [json.loads(line) for line in (run / "trace.jsonl").read_text().splitlines()]


def run_dir(stdout: str) -> Path:
    first = stdout.splitlines()[0]
    return ROOT / first.removeprefix("recorded: ").removesuffix("/trace.jsonl")


def tap_events(trace: list[Record], event: str) -> list[Record]:
    return [r for r in trace if r["dir"] == "tap" and r.get("event") == event]


def proc_children(parent: int) -> list[int]:
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            stat_fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
        except OSError:
            continue
        if int(stat_fields[1]) == parent:
            found.append(int(entry.name))
    return found


def proc_cmdline(pid: int) -> list[str]:
    try:
        return (Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0"))[:-1]
    except OSError:
        return []


def find_server(name: str, deadline: float) -> int | None:
    """The pid of the pinned server started by the tap of the run named `name`."""
    while time.monotonic() < deadline:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            cmd = proc_cmdline(int(entry.name))
            if "tap" in cmd and any(a.endswith(f"-{name}/trace.jsonl") for a in cmd):
                for child in proc_children(int(entry.name)):
                    if proc_cmdline(child)[-1:] == ["streamableHttp"]:
                        return child
        time.sleep(0.05)
    return None


def listening_inodes() -> tuple[set[int], dict[int, str]]:
    """(inodes of TCP sockets in LISTEN, inode -> path of listening Unix sockets), from /proc."""
    tcp: set[int] = set()
    for name in ("tcp", "tcp6"):
        for line in Path(f"/proc/net/{name}").read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] == "0A":
                tcp.add(int(fields[9]))
    unix: dict[int, str] = {}
    for line in Path("/proc/net/unix").read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 8 and int(fields[3], 16) & 0x10000:  # __SO_ACCEPTCON
            unix[int(fields[6])] = fields[7]
    return tcp, unix


def socket_inodes(pid: int) -> set[int]:
    found = set()
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        match = re.fullmatch(r"socket:\[(\d+)\]", target)
        if match:
            found.add(int(match.group(1)))
    return found


class RecordHttpTest(unittest.TestCase):
    """One recording, sampled while it runs: C10 and C28."""

    recording: Path
    server_env: dict[str, str]
    tcp_overlap: set[int]
    unix_listeners: list[str]
    done: subprocess.CompletedProcess[str]

    @classmethod
    def setUpClass(cls) -> None:
        assert SERVER.is_file(), f"{SERVER} missing: run scripts/bootstrap.sh"
        name = f"test-http-record-{os.getpid()}"
        proc = subprocess.Popen(["scripts/record.sh", "--http", "--client", "http-tour", name],
                                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        pid = find_server(name, time.monotonic() + 30)
        assert pid is not None, "the server never started"
        cls.server_env = {}
        for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
            if item:
                key, _, value = item.decode().partition("=")
                cls.server_env[key] = value
        deadline = time.monotonic() + 15
        while True:  # the server is up once its socket listens; the TCP check follows
            tcp, unix = listening_inodes()
            mine = socket_inodes(pid)
            cls.tcp_overlap = mine & tcp
            cls.unix_listeners = [path for inode, path in unix.items() if inode in mine]
            if cls.unix_listeners or time.monotonic() > deadline:
                break
            time.sleep(0.05)
        out, err = proc.communicate(timeout=TIMEOUT)
        cls.done = subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
        if proc.returncode == 0:
            cls.recording = run_dir(out)

    def test_record_http_tour_writes_a_run_folder(self) -> None:
        self.assertEqual(self.done.returncode, 0, self.done.stderr)
        lines = self.done.stdout.splitlines()
        self.assertRegex(
            lines[0], r"^recorded: runs/\d{8}T\d{6}Z-test-http-record-\d+/trace\.jsonl$")
        self.assertRegex(lines[1], r"^read it:  python3 -m tap\.show runs/\S+/trace\.jsonl$")
        trace = self.recording / "trace.jsonl"
        self.assertEqual(stat.S_IMODE(trace.stat().st_mode), 0o600)
        stderr = (self.recording / "stderr.txt").read_text()
        self.assertIn("tap: listening on http://127.0.0.1:", stderr)
        self.assertTrue((self.recording / "bin/python3").is_symlink())
        self.assertTrue((self.recording / "bin/node").is_symlink())
        recs = records(self.recording)
        self.assertEqual(recs[0]["event"], "spawn")
        self.assertEqual(recs[0]["argv"], ["node", "vendor/servers/src/everything/dist/index.js",
                                           "streamableHttp"])
        self.assertEqual(recs[-1]["event"], "exit")

    def test_server_env_is_the_allowlist_plus_port(self) -> None:
        self.assertEqual(set(self.server_env), ALLOWLIST | {"PORT"})
        port = self.server_env["PORT"]
        self.assertTrue(port.endswith("/server.sock"), port)
        self.assertEqual(self.server_env["PATH"].split(":")[1:], ["/usr/bin", "/bin"])
        self.assertNotIn(os.environ["HOME"], json.dumps(self.server_env))

    def test_server_has_no_tcp_listener(self) -> None:
        self.assertEqual(self.tcp_overlap, set(), "the server listens on a TCP port")
        self.assertEqual(self.unix_listeners, [self.server_env["PORT"]])

    def test_http_with_a_fixture_is_a_usage_error(self) -> None:
        before = set((ROOT / "runs").glob("*"))
        done = subprocess.run(
            ["scripts/record.sh", "--http", "tests/fixtures/handshake-2025.ndjson"],
            cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(done.returncode, 1)
        self.assertIn("record: --http needs --client http-tour", done.stderr)
        self.assertEqual(set((ROOT / "runs").glob("*")), before, "a run folder was made")
        other = subprocess.run(
            ["scripts/record.sh", "--http", "--client", "tasks-2026"],
            cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(other.returncode, 1)
        self.assertIn("tasks-2026 runs only on stdio", other.stderr)


class HttpTourTest(unittest.TestCase):
    recording: Path
    trace: list[Record]

    @classmethod
    def setUpClass(cls) -> None:
        assert SERVER.is_file(), f"{SERVER} missing: run scripts/bootstrap.sh"
        done = subprocess.run(
            ["scripts/record.sh", "--http", "--client", "http-tour", "test-http-tour"],
            cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
        assert done.returncode == 0, done.stderr
        cls.recording = run_dir(done.stdout)
        cls.trace = records(cls.recording)

    def exchanges(self) -> dict[int, dict[str, Any]]:
        """exchange number -> {method, path, status, content_type, frames: [(dir, json)], end}"""
        out: dict[int, dict[str, Any]] = {}
        for rec in self.trace:
            http: dict[str, Any] = rec.get("http") or {}
            if rec["dir"] == "tap" and rec.get("event") == "http-request":
                out[http["exchange"]] = {"method": http["method"], "path": http["path"],
                                         "request_headers": http["headers"], "frames": [],
                                         "events": [], "request_seq": rec["seq"]}
            elif rec["dir"] == "tap" and rec.get("event") == "http-response":
                out[http["exchange"]].update(
                    status=http["status"], response_headers=http["headers"])
            elif rec["dir"] == "tap" and rec.get("event") == "sse-event":
                out[http["exchange"]]["events"].append(rec)
            elif rec["dir"] == "tap" and rec.get("event") == "http-end":
                out[http["exchange"]]["end"] = http["by"]
            elif rec["dir"] in ("c2s", "s2c") and http:
                out[http["exchange"]]["frames"].append((rec["dir"], rec["json"], rec["seq"]))
        return out

    def test_http_tour_runs_and_its_trace_checks(self) -> None:
        sent = [r["json"]["method"] for r in self.trace if r["dir"] == "c2s" and r["json"]
                and "method" in r["json"]]
        for method in ("initialize", "notifications/initialized", "tools/call",
                       "notifications/cancelled"):
            self.assertIn(method, sent)
        received = [r["json"]["method"] for r in self.trace if r["dir"] == "s2c" and r["json"]
                    and "method" in r["json"]]
        for method in ("roots/list", "sampling/createMessage", "notifications/progress",
                       "notifications/tools/list_changed"):
            self.assertIn(method, received)
        done = subprocess.run(
            [sys.executable, "-m", "tap.check", str(self.recording / "trace.jsonl"), "--revision",
             "2025-11-25"], cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_fresh_trace_shows_what_http_adds(self) -> None:
        ex = self.exchanges()

        def of(direction: str, **match: Any) -> tuple[int, dict[str, Any], int]:
            """(exchange, message, seq) of the one frame whose message has these fields."""
            found = [(n, m, s) for n, e in ex.items() for d, m, s in e["frames"]
                     if d == direction and all(m.get(k) == v for k, v in match.items())]
            self.assertEqual(len(found), 1, f"{direction} {match}: {len(found)} frames")
            return found[0]

        # M3, M5: the initialize reply is an event stream with a priming event and a session id.
        n, _, _ = of("c2s", method="initialize")
        first = ex[n]
        self.assertEqual((first["status"], first["response_headers"]["content-type"]),
                         (200, "text/event-stream"))
        self.assertRegex(first["response_headers"]["mcp-session-id"], r"^[0-9a-f-]{36}$")
        self.assertEqual(len(first["events"]), 1, "one priming event")
        self.assertLess(first["events"][0]["seq"], first["frames"][1][2])
        self.assertNotIn("mcp-session-id", first["request_headers"])
        # M4: a notification and a client reply are answered 202 with no frame of their own.
        _, _, _ = of("c2s", method="notifications/initialized")
        for _, e in ex.items():
            if e["method"] == "POST" and e["frames"] and e["frames"][0][0] == "c2s" and (
                    "method" not in e["frames"][0][1] or "id" not in e["frames"][0][1]):
                self.assertEqual(e["status"], 202, e["frames"][0][1])
                self.assertEqual(len(e["frames"]), 1)
        # M8: the server's roots/list is a frame of the GET exchange.
        n, _, _ = of("s2c", method="roots/list")
        self.assertEqual(ex[n]["method"], "GET")
        self.assertEqual(ex[n]["request_headers"]["accept"], "text/event-stream")
        self.assertEqual(ex[n]["status"], 200)
        get_exchange = n
        # M9: sampling/createMessage is a frame of its tools/call exchange, before the response.
        n, _, request_seq = of("s2c", method="sampling/createMessage")
        _, call, _ = of("c2s", method="tools/call", params={
            "name": "trigger-sampling-request", "arguments": {"prompt": "hello over http"}})
        self.assertEqual(ex[n]["frames"][0][1]["method"], "tools/call")
        _, _, response_seq = of("s2c", id=call["id"])
        self.assertLess(request_seq, response_seq)
        # M10: the cancelled call has no response and its stream ends by the client.
        cancelled = [e for e in ex.values() if e["frames"] and e["frames"][0][0] == "c2s"
                     and e["frames"][0][1].get("params", {}).get("name")
                     == "trigger-long-running-operation"]
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0]["end"], "client")
        self.assertEqual([d for d, _, _ in cancelled[0]["frames"]], ["c2s", "s2c"])  # a progress
        self.assertEqual(cancelled[0]["frames"][1][1]["method"], "notifications/progress")
        # M11: DELETE gets 200 and the GET exchange then ends by the server.
        deletes = [e for e in ex.values() if e["method"] == "DELETE"]
        self.assertEqual([d["status"] for d in deletes], [200])
        self.assertEqual(ex[get_exchange]["end"], "server")
        self.assertEqual(deletes[0]["request_headers"]["mcp-session-id"],
                         first["response_headers"]["mcp-session-id"])
        self.assertEqual(deletes[0]["request_headers"]["mcp-protocol-version"], "2025-11-25")

    def test_walkthrough_explains_fresh_trace(self) -> None:
        done = subprocess.run(
            [sys.executable, "-m", "tap.show", str(self.recording / "trace.jsonl"), "--explain",
             str(WALKTHROUGH)], cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("(no note)", done.stdout)
        self.assertNotIn("(no frame)", done.stdout)


    def test_without_the_stream_roots_list_never_arrives(self) -> None:
        assert SERVER.is_file(), f"{SERVER} missing: run scripts/bootstrap.sh"
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            tap = subprocess.Popen(
                [sys.executable, "-m", "tap", "--trace", str(trace), "--http", str(port), "--",
                 "node", str(SERVER), "streamableHttp"],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            try:
                assert tap.stderr is not None
                deadline = time.monotonic() + 30
                for line in tap.stderr:
                    if line.startswith("tap: listening"):
                        break
                    self.assertLess(time.monotonic(), deadline, "the tap never listened")
                done = subprocess.run(
                    [sys.executable, "-m", "client.http_tour", "--url",
                     f"http://127.0.0.1:{port}/mcp", "--no-stream"],
                    cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn("never arrived", done.stdout)
            finally:
                tap.send_signal(signal.SIGINT)
                tap.wait(30)
            trace_records = [json.loads(line) for line in trace.read_text().splitlines()]
        methods = [r["json"].get("method") for r in trace_records
                   if r["dir"] == "s2c" and isinstance(r.get("json"), dict)]
        self.assertNotIn("roots/list", methods)
        self.assertEqual([r for r in trace_records if r["dir"] == "tap"
                          and r.get("event") == "http-request"
                          and r["http"]["method"] == "GET"], [])


class SdkHttpTest(unittest.TestCase):
    """C27 (part C, D12): the SDK client's tour over its Streamable HTTP transport."""

    def test_sdk_tour_over_http_checks_and_deletes(self) -> None:
        assert SERVER.is_file(), f"{SERVER} missing: run scripts/bootstrap.sh"
        done = subprocess.run(
            ["scripts/record.sh", "--http", "--client", "sdk-tour", "test-sdk-http"],
            cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
        self.assertEqual(done.returncode, 0, done.stderr)
        recording = run_dir(done.stdout)
        trace = records(recording)
        checked = subprocess.run(
            [sys.executable, "-m", "tap.check", str(recording / "trace.jsonl"), "--revision",
             "2025-11-25"], cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        requests = [r["http"] for r in trace
                    if r["dir"] == "tap" and r.get("event") == "http-request"]
        deletes = [h for h in requests if h["method"] == "DELETE"]
        self.assertEqual(len(deletes), 1)
        self.assertEqual(requests[-1]["method"], "DELETE", "DELETE is the last request")
        responses = {r["http"]["exchange"]: r["http"] for r in trace
                     if r["dir"] == "tap" and r.get("event") == "http-response"}
        self.assertEqual(responses[deletes[0]["exchange"]]["status"], 200)
        sent = [r["json"]["method"] for r in trace if r["dir"] == "c2s" and r["json"]
                and "method" in r["json"]]
        self.assertIn("initialize", sent)
        self.assertIn("notifications/initialized", sent)


def record_http(name: str, mode: str) -> Path:
    """`record.sh --http --client <mode>`; the run folder, after asserting the client's exit 0."""
    done = subprocess.run(["scripts/record.sh", "--http", "--client", mode, name], cwd=ROOT,
                          capture_output=True, text=True, timeout=TIMEOUT)
    assert done.returncode == 0, done.stderr
    return run_dir(done.stdout)


def checked(recording: Path, revision: str) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "tap.check", str(recording / "trace.jsonl"), "--revision", revision],
        cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
    assert done.returncode == 0, done.stdout + done.stderr


def sent_frames(trace: list[Record]) -> list[Record]:
    return [r["json"] for r in trace if r["dir"] == "c2s" and r["json"]]


class HttpModesTest(unittest.TestCase):
    """C22 (part B2, D10): the phase 2 and 3 tours over HTTP, through the tap."""

    def test_tour_over_http(self) -> None:
        recording = record_http("test-http-tour-2025", "tour")
        trace = records(recording)
        self.assertEqual([m["method"] for m in sent_frames(trace)], TOUR_METHODS)
        checked(recording, "2025-11-25")
        requests = [r["http"] for r in tap_events(trace, "http-request")]
        self.assertEqual(requests[-1]["method"], "DELETE")

    def test_server_tour_over_http(self) -> None:
        recording = record_http("test-http-server-tour", "server-tour")
        trace = records(recording)
        from_server = [r["json"] for r in trace if r["dir"] == "s2c" and r["json"]]
        asked = [m for m in from_server if "method" in m and "id" in m]
        self.assertEqual({m["method"] for m in asked}, SERVER_REQUESTS)
        notes = {m["method"] for m in from_server if "method" in m and "id" not in m}
        self.assertTrue(SERVER_NOTES <= notes, SERVER_NOTES - notes)
        sent = sent_frames(trace)
        answers = [m for m in sent if "method" not in m]
        self.assertEqual(sorted(a["id"] for a in answers), sorted(m["id"] for m in asked))
        self.assertIn("notifications/roots/list_changed", {m.get("method") for m in sent})
        called = {m["params"]["name"] for m in sent if m.get("method") == "tools/call"}
        for tool in ("get-roots-list", "trigger-sampling-request", "trigger-elicitation-request",
                     "trigger-multi-step-elicitation", "trigger-url-elicitation",
                     "trigger-log-messages", "trigger-list-changed", "trigger-resource-update"):
            self.assertIn(tool, called)
        checked(recording, "2025-11-25")


class Era2026HttpTest(unittest.TestCase):
    """C26 (part D, D11): phase 6's 2026-07-28 tour over HTTP, through the tap."""

    def test_2026_tour_over_http_checks(self) -> None:
        recording = record_http("test-http-tour-2026", "tour-2026")
        trace = records(recording)
        sent = sent_frames(trace)
        # the two `notifications/cancelled` of the stdio tour are closed streams here (D11)
        expected = [m for m in MODERN_TOUR_METHODS if m != "notifications/cancelled"]
        self.assertEqual([m["method"] for m in sent], expected)
        self.assertEqual([m["params"]["name"] for m in sent if m["method"] == "tools/call"],
                         MODERN_TOUR_TOOLS)
        requests = [r["http"] for r in tap_events(trace, "http-request")]
        self.assertEqual({h["method"] for h in requests}, {"POST"}, "no GET and no DELETE")
        for http in requests:
            headers = http["headers"]
            self.assertEqual(headers["mcp-protocol-version"], "2026-07-28")
            self.assertNotIn("mcp-session-id", headers)
        named = [h["headers"].get("mcp-name") for h in requests
                 if h["headers"]["mcp-method"] in ("tools/call", "resources/read", "prompts/get")]
        self.assertTrue(all(named), named)
        cancelled = [h for h in tap_events(trace, "http-end") if h["http"]["by"] == "client"]
        self.assertGreaterEqual(len(cancelled), 2, "the cancelled call and the subscription")
        checked(recording, "2026-07-28")


class SdkEra2026HttpTest(unittest.TestCase):
    """Part D with the SDK client (D11, D12): its 2026-07-28 tour over its HTTP transport."""

    def test_sdk_tour_2026_over_http_checks(self) -> None:
        recording = record_http("test-sdk-http-2026", "sdk-tour-2026")
        trace = records(recording)
        requests = [r["http"] for r in tap_events(trace, "http-request")]
        self.assertEqual({h["method"] for h in requests}, {"POST"}, "no GET and no DELETE")
        for http in requests:
            self.assertEqual(http["headers"]["mcp-protocol-version"], "2026-07-28")
        # The SDK 2.3.1 posts `notifications/cancelled` when it closes its subscription, with no
        # `Mcp-Method` header, though the 2026-07-28 transport sends no notifications (measured;
        # sdk-client/dist/index.mjs, listed in the walkthrough's accepted differences).
        bare = [h for h in requests if "mcp-method" not in h["headers"]]
        self.assertEqual(len(bare), 1, bare)
        self.assertEqual(sent_frames(trace)[0]["method"], "server/discover")
        self.assertEqual(sent_frames(trace)[-1]["method"], "notifications/cancelled")
        checked(recording, "2026-07-28")


class RecordHttpRefusalsTest(unittest.TestCase):
    """The modes `record.sh --http` refuses, and why (usage errors: nothing is started)."""

    def refused(self, mode: str) -> str:
        done = subprocess.run(["scripts/record.sh", "--http", "--client", mode, "test-refused"],
                              cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        return done.stderr

    def test_sdk_server_tour_is_refused_with_the_measured_reason(self) -> None:
        self.assertIn("burst is dropped", self.refused("sdk-server-tour"))

    def test_tasks_stays_on_stdio(self) -> None:
        self.assertIn("only on stdio", self.refused("tasks-2026"))


if __name__ == "__main__":
    unittest.main()
