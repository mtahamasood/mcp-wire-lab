"""Phase 7 part A, C1-C8 and C28: the tap's HTTP mode against a scripted Unix-socket upstream."""

from __future__ import annotations

import base64
import http.client
import json
import os
import resource
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any

from tap.http import SseParser

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "tests/fake_servers/http_upstream.py"
TIMEOUT = 20
Record = dict[str, Any]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def tcp_listeners() -> dict[int, str]:
    """Listening TCP ports on this machine -> local address (Linux /proc/net/tcp and tcp6)."""
    found: dict[int, str] = {}
    for name in ("tcp", "tcp6"):
        try:
            lines = Path(f"/proc/net/{name}").read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if fields[3] == "0A":
                address, port = fields[1].split(":")
                found[int(port, 16)] = address
    return found


class Tap:
    """One running `python3 -m tap --http` in front of the scripted upstream."""

    def __init__(self, case: unittest.TestCase, *upstream_args: str,
                 command: list[str] | None = None, env: dict[str, str] | None = None,
                 limit_trace: int | None = None) -> None:
        self.case = case
        self.dir = tempfile.TemporaryDirectory()
        case.addCleanup(self.dir.cleanup)
        self.trace = Path(self.dir.name) / "trace.jsonl"
        self.log = Path(self.dir.name) / "upstream.jsonl"
        self.port = free_port()
        self.stderr_lines: list[str] = []
        self.listening = threading.Event()
        child = command or [sys.executable, str(UPSTREAM), str(self.log), *upstream_args]

        def limit() -> None:
            resource.setrlimit(resource.RLIMIT_FSIZE, (limit_trace or 0, resource.RLIM_INFINITY))
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)

        self.proc = subprocess.Popen(
            [sys.executable, "-m", "tap", "--trace", str(self.trace), "--http", str(self.port),
             "--", *child],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "TRACE_PEEK": str(self.trace), **(env or {})},
            preexec_fn=limit if limit_trace else None,
        )
        threading.Thread(target=self._read_stderr, daemon=True).start()
        case.addCleanup(self._kill)

    def _read_stderr(self) -> None:
        assert self.proc.stderr
        for line in self.proc.stderr:
            self.stderr_lines.append(line.rstrip("\n"))
            if line.startswith("tap: listening"):
                self.listening.set()

    def _kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()

    def wait_listening(self) -> Tap:
        self.case.assertTrue(self.listening.wait(TIMEOUT), "\n".join(self.stderr_lines))
        return self

    def conn(self) -> http.client.HTTPConnection:
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=TIMEOUT)

    def request(
        self, method: str, path: str, body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, http.client.HTTPMessage, bytes]:
        conn = self.conn()
        try:
            conn.request(method, path, body, headers or {})
            resp = conn.getresponse()
            return resp.status, resp.msg, resp.read()
        finally:
            conn.close()

    def stop(self) -> list[Record]:
        """SIGINT, wait for the exit, and return the trace."""
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
        self.proc.wait(TIMEOUT)
        return self.records()

    def records(self) -> list[Record]:
        return [json.loads(line) for line in self.trace.read_text().splitlines()]

    def upstream_log(self) -> list[Record]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]


def started(case: unittest.TestCase, *args: str, **kwargs: Any) -> Tap:
    return Tap(case, *args, **kwargs).wait_listening()


def tap_records(records: list[Record], event: str) -> list[Record]:
    return [r for r in records if r["dir"] == "tap" and r.get("event") == event]


def frames(records: list[Record], direction: str) -> list[Record]:
    return [r for r in records if r["dir"] == direction and "http" in r]


def sse_get(case: unittest.TestCase, payload: bytes, route: str = "raw") -> list[Record]:
    """Serve `payload` as an event stream through the tap; return the trace."""
    tap = started(case)
    status, _, body = tap.request("GET", f"/{route}?hex={payload.hex()}")
    case.assertEqual(status, 200)
    case.assertEqual(body, payload, "the client must get the stream's bytes unchanged")
    return tap.stop()


class HttpRecordTest(unittest.TestCase):
    def test_post_body_is_one_c2s_frame_after_its_request_head(self) -> None:
        body = b'{ "jsonrpc" : "2.0",\n "id":1, "method":"ping" }'
        tap = started(self)
        tap.request("POST", "/json", body, {"Content-Type": "application/json"})
        records = tap.stop()
        head = tap_records(records, "http-request")[0]
        self.assertEqual(head["http"]["exchange"], 0)
        self.assertEqual(head["http"]["method"], "POST")
        self.assertEqual(head["http"]["path"], "/json")
        self.assertEqual(head["http"]["body_bytes"], len(body))
        (frame,) = frames(records, "c2s")
        self.assertEqual(frame["seq"], head["seq"] + 1)
        self.assertEqual(frame["raw"], body.decode())
        self.assertEqual(frame["bytes"], len(body))
        self.assertEqual(frame["json"]["method"], "ping")
        self.assertEqual(frame["http"], {"exchange": 0})

    def test_json_response_is_one_s2c_frame_after_its_response_head(self) -> None:
        tap = started(self)
        tap.request("POST", "/json", b"{}")
        records = tap.stop()
        head = tap_records(records, "http-response")[0]
        self.assertEqual(head["http"]["status"], 200)
        self.assertEqual(head["http"]["headers"], {"content-type": "application/json"})
        (frame,) = frames(records, "s2c")
        self.assertEqual(frame["seq"], head["seq"] + 1)
        self.assertEqual(frame["json"]["result"], {})
        self.assertEqual(frame["http"], {"exchange": 0})

    def test_bodiless_request_and_202_have_no_frames(self) -> None:
        tap = started(self)
        self.assertEqual(tap.request("GET", "/accepted")[0], 202)
        self.assertEqual(tap.request("DELETE", "/anything")[0], 200)
        records = tap.stop()
        self.assertEqual([r for r in records if r["dir"] in ("c2s", "s2c")], [])
        statuses = [r["http"]["status"] for r in tap_records(records, "http-response")]
        self.assertEqual(statuses, [202, 200])

    def test_exchange_numbers_follow_arrival_order(self) -> None:
        tap = started(self)
        for path in ("/json", "/accepted", "/status?code=404"):
            tap.request("GET", path)
        records = tap.stop()
        heads = tap_records(records, "http-request")
        self.assertEqual([h["http"]["exchange"] for h in heads], [0, 1, 2])
        self.assertEqual([h["http"]["path"] for h in heads],
                         ["/json", "/accepted", "/status?code=404"])
        self.assertEqual([r["http"]["exchange"] for r in tap_records(records, "http-response")],
                         [0, 1, 2])

    def test_only_the_headers_that_matter_are_recorded(self) -> None:
        tap = started(self)
        conn = tap.conn()
        conn.putrequest("POST", "/hop")
        for name, value in (
            ("Accept", "application/json"), ("Accept", "text/event-stream"),
            ("Content-Type", "application/json"), ("Last-Event-ID", "e9"),
            ("MCP-Protocol-Version", "2025-11-25"), ("Mcp-Session-Id", "abc"),
            ("X-Other", "dropped"), ("Content-Length", "2"),
        ):
            conn.putheader(name, value)
        conn.endheaders(b"{}")
        conn.getresponse().read()
        conn.close()
        records = tap.stop()
        self.assertEqual(tap_records(records, "http-request")[0]["http"]["headers"], {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json", "last-event-id": "e9",
            "mcp-protocol-version": "2025-11-25", "mcp-session-id": "abc",
        })
        self.assertEqual(tap_records(records, "http-response")[0]["http"]["headers"],
                         {"content-type": "application/json", "mcp-session-id": "fake-session"})

    def test_trace_loads_in_show_and_check_unchanged(self) -> None:
        event = b'id: 1\ndata: {"jsonrpc":"2.0","id":0,"result":{}}\n\n'
        tap = started(self)
        tap.request("POST", f"/raw?hex={event.hex()}", b'{"jsonrpc":"2.0","id":0,"method":"ping"}')
        tap.stop()
        shown = subprocess.run([sys.executable, "-m", "tap.show", str(tap.trace)],
                               cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        checked = subprocess.run(
            [sys.executable, "-m", "tap.check", str(tap.trace), "--revision", "2025-11-25"],
            cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        sys.path.insert(0, str(ROOT))
        from tap import show

        anchors = [i["anchor"] for i in show.annotate(show.load(tap.trace))]
        for anchor in ("tap.spawn.0", "tap.listen.0", "tap.http-request.0", "c2s.ping.0",
                       "tap.http-response.0", "s2c.response.0",
                       "tap.http-end.0", "tap.exit.0"):
            self.assertIn(anchor, anchors)


class SseTest(unittest.TestCase):
    def test_event_data_becomes_one_frame(self) -> None:
        records = sse_get(self, b'event: message\nid: 7\ndata: {"a":1}\n\n')
        (frame,) = frames(records, "s2c")
        self.assertEqual(frame["raw"], '{"a":1}')
        self.assertEqual(frame["json"], {"a": 1})
        self.assertEqual(frame["http"], {"exchange": 0, "sse": {"id": "7", "event": "message"}})

    def test_line_endings_and_multiline_data(self) -> None:
        payload = (b"data: a\r\ndata: b\r\n\r\n"  # CRLF
                   b"data: c\rdata: d\r\r"  # CR
                   b"data:  e\ndata\ndata: f\n\n")  # LF, a second space kept, a line without colon
        for route in ("raw", "split"):
            with self.subTest(route=route):
                records = sse_get(self, payload, route)
                self.assertEqual([f["raw"] for f in frames(records, "s2c")],
                                 ["a\nb", "c\nd", " e\n\nf"])

    def test_empty_data_is_a_tap_record(self) -> None:
        records = sse_get(self, b"id: p1\ndata: \n\nretry: 1500\n\n")
        self.assertEqual(frames(records, "s2c"), [])
        events = tap_records(records, "sse-event")
        self.assertEqual([e["http"] for e in events],
                         [{"exchange": 0, "id": "p1"}, {"exchange": 0, "retry": 1500}])

    def test_comments_are_counted_not_recorded(self) -> None:
        records = sse_get(self, b": ping\n\n: again\ndata: {}\n\n")
        self.assertEqual([f["raw"] for f in frames(records, "s2c")], ["{}"])
        self.assertEqual(tap_records(records, "sse-event"), [])
        end = tap_records(records, "http-end")[0]["http"]
        self.assertEqual(end, {"exchange": 0, "by": "server", "comments": 2})
        self.assertNotIn("ping", json.dumps(records[3:]))

    def test_unterminated_event_is_partial(self) -> None:
        records = sse_get(self, b'data: {"x":1}\n\nid: 5\ndata: {"y":2}')
        got = frames(records, "s2c")
        self.assertEqual([f["raw"] for f in got], ['{"x":1}', '{"y":2}'])
        self.assertNotIn("partial", got[0])
        self.assertTrue(got[1]["partial"])
        records = sse_get(self, b"id: 5\n")  # no data: nothing to record
        self.assertEqual(frames(records, "s2c"), [])
        self.assertEqual(tap_records(records, "sse-event"), [])

    def test_non_utf8_data_is_base64(self) -> None:
        records = sse_get(self, b"data: \xff\xfe\n\n")
        (frame,) = frames(records, "s2c")
        self.assertEqual(base64.b64decode(frame["raw_b64"]), b"\xff\xfe")
        self.assertNotIn("raw", frame)
        self.assertIsNone(frame["json"])
        self.assertIn("UTF-8", frame["parse_error"])

    def test_parser_alone(self) -> None:
        parser = SseParser()
        self.assertEqual(parser.feed(b"data: a\r"), [])  # a CR may start a CRLF
        (event,) = parser.feed(b"\n\r\n")
        self.assertEqual(event.data, b"a")
        self.assertEqual(parser.feed(b"unknown: x\n\n"), [])  # other fields are ignored


class HttpForwardTest(unittest.TestCase):
    def test_bodies_status_and_headers_forwarded_unchanged(self) -> None:
        body = b'{"z": 1,  "a": 2}\n'
        tap = started(self)
        status, headers, answer = tap.request(
            "POST", "/echo?a=b&c=d%20e", body, {"X-Custom": "v 1", "Content-Type": "text/x"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/json")
        sent = tap.upstream_log()[-1]
        self.assertEqual(json.loads(answer)["path"], "/echo?a=b&c=d%20e")
        self.assertEqual(sent["method"], "POST")
        self.assertEqual(base64.b64decode(sent["body_b64"]), body)
        upstream_headers = {k.lower(): v for k, v in sent["headers"]}
        self.assertEqual(upstream_headers["x-custom"], "v 1")
        self.assertEqual(upstream_headers["content-type"], "text/x")
        self.assertEqual(upstream_headers["content-length"], str(len(body)))
        self.assertEqual(tap.request("GET", "/status?code=418")[0], 418)

    def test_hop_by_hop_headers_not_forwarded(self) -> None:
        tap = started(self)
        _, headers, _ = tap.request(
            "GET", "/hop", headers={"Keep-Alive": "5", "Proxy-Authorization": "x", "TE": "trailers",
                                    "X-Kept": "yes"})
        sent = {k.lower() for k, _ in tap.upstream_log()[-1]["headers"]}
        self.assertIn("x-kept", sent)
        for name in ("keep-alive", "proxy-authorization", "te", "upgrade", "transfer-encoding"):
            self.assertNotIn(name, sent)
        self.assertIsNone(headers["Keep-Alive"])
        self.assertIsNone(headers["Proxy-Authenticate"])
        self.assertEqual(headers["X-Fake"], "kept")

    def test_upstream_host_is_localhost(self) -> None:
        tap = started(self)
        tap.request("GET", "/echo", headers={"Host": "example.test:9"})
        sent = {k.lower(): v for k, v in tap.upstream_log()[-1]["headers"]}
        self.assertEqual(sent["host"], "localhost")

    def test_records_precede_forwarding(self) -> None:
        tap = started(self)
        # The request's records are on the trace before the upstream is asked: the upstream reads
        # the trace file while it handles the request.
        _, _, answer = tap.request("POST", "/peek", b'{"id":3}')
        seen = [json.loads(line) for line in json.loads(answer)["lines"]]
        self.assertEqual([r.get("event") or r["dir"] for r in seen][-2:], ["http-request", "c2s"])
        # An event's frame is on the trace before the client gets its bytes.
        conn = tap.conn()
        conn.request("GET", "/slow")
        resp = conn.getresponse()
        while resp.readline().strip() != b"":
            pass  # up to the end of the first event
        mine = [r for r in tap.records() if r["dir"] == "s2c" and r["http"]["exchange"] == 1]
        self.assertEqual([r["json"].get("result") for r in mine], [{}])
        conn.close()

    def test_events_reach_client_before_stream_ends(self) -> None:
        tap = started(self)
        conn = tap.conn()
        started_at = time.monotonic()
        conn.request("GET", "/slow")
        resp = conn.getresponse()
        first = None
        while True:
            line = resp.readline()
            if line.startswith(b"data:") and first is None:
                first = time.monotonic() - started_at
            if not line:
                break
        total = time.monotonic() - started_at
        assert first is not None
        self.assertLess(first, 0.6)
        self.assertGreater(total, 0.9)
        conn.close()

    def test_server_request_round_trip_does_not_deadlock(self) -> None:
        tap = started(self)
        conn = tap.conn()
        conn.request("POST", "/roundtrip", b"{}")
        resp = conn.getresponse()
        first = b""
        while not first.startswith(b"data:"):
            first = resp.readline()
        self.assertIn(b'"method":"ping"', first)
        self.assertEqual(tap.request("POST", "/reply", b"{}")[0], 202)
        rest = resp.read()
        self.assertIn(b'"result":{}', rest)
        conn.close()
        records = tap.stop()
        self.assertEqual([f["http"]["exchange"] for f in frames(records, "s2c")], [0, 0])

    def test_client_disconnect_closes_upstream(self) -> None:
        tap = started(self)
        conn = tap.conn()
        conn.request("GET", "/hold")
        resp = conn.getresponse()
        while resp.readline().strip() != b"":
            pass
        conn.sock.shutdown(socket.SHUT_RDWR)
        conn.close()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            ends = tap_records(tap.records(), "http-end")
            if ends and any(e.get("event") == "disconnect" for e in tap.upstream_log()):
                break
            time.sleep(0.05)
        (end,) = tap_records(tap.records(), "http-end")
        self.assertEqual(end["http"]["by"], "client")
        self.assertTrue([e for e in tap.upstream_log() if e.get("event") == "disconnect"])

    def test_upstream_down_gives_502(self) -> None:
        tap = started(self)
        tap.request("GET", "/unlisten")
        status, _, body = tap.request("GET", "/json")
        self.assertEqual((status, body), (502, b""))
        records = tap.stop()
        last = tap_records(records, "http-response")[-1]["http"]
        self.assertEqual((last["exchange"], last["status"], last["by"]), (1, 502, "tap"))

    def test_trace_write_failure_keeps_proxying(self) -> None:
        tap = started(self, limit_trace=1500)
        for _ in range(6):
            status, _, _ = tap.request("POST", "/json", b'{"filler":"' + b"x" * 400 + b'"}')
            self.assertEqual(status, 200)
        code = tap.proc.poll()
        self.assertIsNone(code)
        tap.proc.send_signal(signal.SIGINT)
        self.assertEqual(tap.proc.wait(TIMEOUT), 0)
        self.assertTrue(any("recording stopped" in line for line in tap.stderr_lines))


class HttpLifecycleTest(unittest.TestCase):
    def test_listens_on_loopback_only_after_upstream_accepts(self) -> None:
        tap = Tap(self, "1.0")  # the upstream waits 1 s before it listens
        time.sleep(0.4)
        self.assertFalse(tap.listening.is_set())
        with socket.socket() as probe:
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", tap.port)), 0)
        tap.wait_listening()
        self.assertEqual(tcp_listeners().get(tap.port), "0100007F")
        records = tap.stop()
        listen = tap_records(records, "listen")[0]
        self.assertEqual(listen["listen"], f"127.0.0.1:{tap.port}")
        self.assertTrue(listen["upstream"].startswith("unix:"))
        spawn_at = tap_records(records, "spawn")[0]["seq"]
        self.assertLess(spawn_at, listen["seq"])

    def test_child_exit_before_ready_gives_its_code(self) -> None:
        for child_code, want in ((3, 3), (0, 1)):
            with self.subTest(child_code=child_code):
                code = f"import sys; sys.exit({child_code})"
                tap = Tap(self, command=[sys.executable, "-c", code])
                self.assertEqual(tap.proc.wait(TIMEOUT), want)
                records = tap.records()
                self.assertEqual(tap_records(records, "listen"), [])
                self.assertEqual(records[-1]["event"], "exit")
                self.assertEqual(records[-1]["code"], child_code)
                self.assertTrue(any(line.startswith("tap:") for line in tap.stderr_lines))

    def test_sigint_forwarded_and_exit_is_last(self) -> None:
        tap = started(self)
        tap.request("GET", "/json")
        records = tap.stop()
        self.assertEqual(tap.proc.returncode, 0)
        self.assertEqual(records[0]["event"], "spawn")
        self.assertEqual(records[-1]["event"], "exit")
        self.assertEqual(records[-1]["code"], 0)
        self.assertEqual(len(tap_records(records, "exit")), 1)
        self.assertEqual([r["seq"] for r in records], list(range(len(records))))

    def test_child_output_is_recorded_as_stderr(self) -> None:
        tap = started(self)
        tap.request("GET", "/log")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not any(
            r.get("raw") == "fake stdout line\n" for r in tap.records()
        ):
            time.sleep(0.05)
        records = tap.stop()
        err = [r for r in records if r["dir"] == "stderr"]
        out = next(r for r in err if r["raw"] == "fake stdout line\n")
        self.assertEqual(out["stream"], "stdout")
        plain = next(r for r in err if r["raw"] == "fake stderr line\n")
        self.assertNotIn("stream", plain)
        self.assertIn("fake stdout line", tap.stderr_lines)
        self.assertIn("fake stderr line", tap.stderr_lines)

    def test_usage_errors_start_nothing(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        marker = Path(scratch.name) / "started"
        child = [sys.executable, "-c", f"open({str(marker)!r}, 'w')"]
        trace = marker.parent / "t.jsonl"
        for extra in (["--http", "0"], ["--http", "abc"], ["--http", "70000"], ["--http"],
                      ["--http", "5000", "--delay", "c2s:5"],
                      ["--http", "5000", "--drop", "c2s:x"]):
            with self.subTest(extra=extra):
                done = subprocess.run(
                    [sys.executable, "-m", "tap", "--trace", str(trace), *extra, "--", *child],
                    cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn("usage:", done.stderr)
                self.assertFalse(marker.exists())
                self.assertFalse(trace.exists())


class HttpUpstreamTest(unittest.TestCase):
    def test_child_gets_port_as_a_socket_in_a_private_dir(self) -> None:
        tap = started(self)
        port_env = json.loads(tap.request("GET", "/env")[2])["PORT"]
        directory = os.path.dirname(port_env)
        self.assertEqual(os.path.basename(port_env), "server.sock")
        self.assertEqual(stat.S_IMODE(os.stat(directory).st_mode), 0o700)
        self.assertTrue(stat.S_ISSOCK(os.stat(port_env).st_mode))
        records = tap.stop()
        self.assertEqual(tap_records(records, "listen")[0]["upstream"], f"unix:{port_env}")

    def test_upstream_is_the_socket_and_dir_removed_after_exit(self) -> None:
        tap = started(self)
        port_env = json.loads(tap.request("GET", "/env")[2])["PORT"]
        tap.stop()
        self.assertFalse(os.path.exists(os.path.dirname(port_env)))

    def test_overlong_socket_path_starts_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            long_dir = Path(tmp) / ("d" * 60) / ("e" * 60)
            long_dir.mkdir(parents=True)
            marker = Path(tmp) / "started"
            trace = Path(tmp) / "t.jsonl"
            done = subprocess.run(
                [sys.executable, "-m", "tap", "--trace", str(trace), "--http", str(free_port()),
                 "--", sys.executable, "-c", f"open({str(marker)!r}, 'w')"],
                cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT,
                env={**os.environ, "TMPDIR": str(long_dir)},
            )
            self.assertEqual(done.returncode, 1, done.stderr)
            self.assertEqual(len(done.stderr.splitlines()), 1)
            self.assertTrue(done.stderr.startswith("tap:"))
            self.assertFalse(marker.exists())
            self.assertEqual(list(long_dir.iterdir()), [], "the private directory is removed")


if __name__ == "__main__":
    unittest.main()
