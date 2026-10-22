"""Phase 7 parts B1, B2, D, C11-C15, C23-C25: the raw client's HTTP transport against an
in-process fake server."""

from __future__ import annotations

import contextlib
import http.server
import io
import json
import select
import socket
import threading
import time
import unittest
from collections.abc import Callable
from typing import Any

from client import __main__ as client_main
from client import manual
from client.handlers import Handlers
from client.http_wire import HttpSession, HttpStatusError, HttpWire, SessionEnded
from client.modern_http import ModernHttpSession
from client.wire import RpcError

Script = Callable[["Fake", http.server.BaseHTTPRequestHandler, bytes], None]
SESSION = "sess-1"
INIT_RESULT = {"protocolVersion": "2025-11-25", "capabilities": {},
               "serverInfo": {"name": "fake", "version": "0"}}


class Fake:
    """A loopback HTTP server whose answers a test scripts; `log` holds every request."""

    def __init__(self, script: Script, *, sequential: bool = False) -> None:
        self.script = script
        self.log: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.events: dict[str, threading.Event] = {}
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass

            def serve(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                with fake.lock:
                    fake.log.append({
                        "method": self.command, "path": self.path, "body": body,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                    })
                fake.script(fake, self, body)

            do_GET = do_POST = do_DELETE = serve

        base = http.server.HTTPServer if sequential else http.server.ThreadingHTTPServer
        self.server = base(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/mcp"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def event(self, name: str) -> threading.Event:
        with self.lock:
            return self.events.setdefault(name, threading.Event())

    def wait_for(self, predicate: Callable[[dict[str, Any]], bool], timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if any(predicate(e) for e in self.log):
                    return True
            time.sleep(0.02)
        return False

    def posted(self) -> list[dict[str, Any]]:
        """The JSON bodies of the POSTs, in arrival order."""
        with self.lock:
            return [{**json.loads(e["body"]), "_headers": e["headers"]}
                    for e in self.log if e["method"] == "POST" and e["body"]]


def reply_json(h: http.server.BaseHTTPRequestHandler, status: int, body: bytes,
               ctype: str = "application/json", extra: dict[str, str] | None = None) -> None:
    h.send_response(status)
    if body:
        h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    for name, value in (extra or {}).items():
        h.send_header(name, value)
    h.end_headers()
    h.wfile.write(body)


def stream_head(h: http.server.BaseHTTPRequestHandler, extra: dict[str, str] | None = None) -> None:
    h.send_response(200)
    h.send_header("Content-Type", "text/event-stream")
    h.send_header("Transfer-Encoding", "chunked")
    for name, value in (extra or {}).items():
        h.send_header(name, value)
    h.end_headers()


def piece(h: http.server.BaseHTTPRequestHandler, data: bytes) -> None:
    h.wfile.write(b"%x\r\n%b\r\n" % (len(data), data))
    h.wfile.flush()


def end_stream(h: http.server.BaseHTTPRequestHandler) -> None:
    h.wfile.write(b"0\r\n\r\n")
    h.wfile.flush()


def event(message: dict[str, Any]) -> bytes:
    return b"id: x\ndata: " + json.dumps(message).encode() + b"\n\n"


def result(request: dict[str, Any], value: Any = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request["id"], "result": {} if value is None else value}


def hung_up(h: http.server.BaseHTTPRequestHandler, deadline: float = 5.0) -> bool:
    """Wait until the client closes the connection under a stream the fake is holding open."""
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        ready, _, _ = select.select([h.connection], [], [], 0.05)
        if ready and h.connection.recv(1, socket.MSG_PEEK) == b"":
            return True
    return False


def standard(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
    """A well-behaved server: a session at initialize, SSE replies to requests, 202 to the rest."""
    if h.command == "DELETE":
        fake.event("deleted").set()
        reply_json(h, 200, b"")
        return
    if h.command == "GET":
        stream_head(h)
        piece(h, b": open\n\n")
        fake.event("deleted").wait(5)
        end_stream(h)
        return
    message = json.loads(body)
    if "method" in message and "id" in message:
        stream_head(h, {"Mcp-Session-Id": SESSION} if message["method"] == "initialize" else None)
        piece(h, b"id: p\ndata: \n\n")
        piece(h, event(result(message, INIT_RESULT if message["method"] == "initialize" else None)))
        end_stream(h)
    else:
        reply_json(h, 202, b"")


class Case(unittest.TestCase):
    def serve(self, script: Script, *, sequential: bool = False) -> Fake:
        fake = Fake(script, sequential=sequential)
        self.addCleanup(fake.stop)
        return fake

    def session(self, fake: Fake, **kwargs: Any) -> tuple[HttpSession, list[str]]:
        reports: list[str] = []
        session = HttpSession.connect(fake.url, report=reports.append, timeout=5, **kwargs)
        self.addCleanup(session.close)
        return session, reports

    def wire(self, fake: Fake, **kwargs: Any) -> tuple[HttpWire, list[str]]:
        reports: list[str] = []
        wire = HttpWire(fake.url, report=reports.append, **kwargs)
        self.addCleanup(wire.close_connections)
        return wire, reports


class HttpWireTest(Case):
    def test_each_message_is_one_post_with_accept_and_content_type(self) -> None:
        fake = self.serve(standard)
        wire, _ = self.wire(fake)
        wire.request("ping", timeout=5)
        wire.notify("notifications/x")
        self.assertTrue(fake.wait_for(lambda e: b"notifications/x" in e["body"]))
        with fake.lock:
            log = list(fake.log)
        self.assertEqual([e["method"] for e in log], ["POST", "POST"])
        for entry in log:
            self.assertEqual(entry["headers"]["content-type"], "application/json")
            accept = entry["headers"]["accept"]
            self.assertIn("application/json", accept)
            self.assertIn("text/event-stream", accept)
            self.assertEqual(entry["path"], "/mcp")

    def test_session_and_version_headers_after_initialize_only(self) -> None:
        fake = self.serve(standard)
        session, _ = self.session(fake)
        session.initialize({"roots": {}})
        session.request("ping")
        self.assertEqual(session.close(), 200)
        with fake.lock:
            log = list(fake.log)
        init = log[0]
        self.assertNotIn("mcp-session-id", init["headers"])
        self.assertNotIn("mcp-protocol-version", init["headers"])
        later = log[1:]
        self.assertEqual({e["method"] for e in later}, {"GET", "POST", "DELETE"})
        for entry in later:
            self.assertEqual(entry["headers"]["mcp-session-id"], SESSION, entry["method"])
            self.assertEqual(entry["headers"]["mcp-protocol-version"], "2025-11-25")

    def test_json_and_sse_bodies_reach_the_line_handler(self) -> None:
        asked: list[dict[str, Any]] = []

        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body)
            if "method" not in message:  # the client's refusal of the server's request
                reply_json(h, 202, b"")
            elif message["method"] == "json":
                reply_json(h, 200, json.dumps(result(message, {"how": "json"})).encode())
            else:
                stream_head(h)
                piece(h, event({"jsonrpc": "2.0", "method": "notifications/progress",
                                "params": {"progress": 1}}))
                piece(h, event({"jsonrpc": "2.0", "id": 41, "method": "roots/list"}))
                piece(h, event(result(message, {"how": "sse"})))
                end_stream(h)

        fake = self.serve(script)
        wire, _ = self.wire(fake, on_request=asked.append)
        self.assertEqual(wire.request("json", timeout=5), {"how": "json"})
        self.assertEqual(wire.request("sse", timeout=5), {"how": "sse"})
        self.assertEqual(wire.notifications.get(timeout=1)["method"], "notifications/progress")
        self.assertEqual([m["method"] for m in asked], ["roots/list"])

    def test_202_and_empty_events_are_skipped(self) -> None:
        fake = self.serve(standard)
        wire, reports = self.wire(fake)
        wire.notify("notifications/x")
        wire.request("ping", timeout=5)  # its stream opens with an empty-data event
        head = wire.wait_head("notification", "notifications/x")
        self.assertIsNotNone(head)
        assert head is not None
        self.assertEqual(head.status, 202)
        self.assertEqual(reports, [])
        self.assertTrue(wire.notifications.empty())

    def test_error_status_fails_the_request_at_once(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body)
            if message["method"] == "plain":
                reply_json(h, 400, b"Bad Request: nope", "text/plain")
            else:
                reply_json(h, 400, json.dumps({"jsonrpc": "2.0", "id": message["id"],
                                               "error": {"code": -32600, "message": "x"}}).encode())

        fake = self.serve(script)
        wire, _ = self.wire(fake)
        started = time.monotonic()
        with self.assertRaises(HttpStatusError) as caught:
            wire.request("plain", timeout=5)
        self.assertEqual(caught.exception.status, 400)
        self.assertIn("nope", str(caught.exception))
        with self.assertRaises(RpcError) as rpc:
            wire.request("typed", timeout=5)
        self.assertEqual(rpc.exception.error["code"], -32600)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_404_ends_the_session(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            if not body:
                return standard(fake, h, body)
            message = json.loads(body)
            if message["method"] == "gone":
                reply_json(h, 404, json.dumps({"jsonrpc": "2.0", "id": message["id"], "error": {
                    "code": -32001, "message": "Session not found"}}).encode())
            elif message["method"] == "hang":
                fake.event("hanging").set()
                hung_up(h)
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        session, _ = self.session(fake)
        session.initialize()
        stuck = session.start_request("hang")
        self.assertTrue(fake.event("hanging").wait(5))
        with self.assertRaises(RpcError):
            session.request("gone")
        with self.assertRaises(SessionEnded):
            stuck.wait(5)
        with self.assertRaises(SessionEnded):
            session.request("ping")


    def test_posts_leave_in_write_order(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            reply_json(h, 202, b"")

        fake = self.serve(script, sequential=True)  # one request at a time, in connection order
        wire, _ = self.wire(fake)
        for n in range(8):
            wire.notify(f"notifications/n{n}")
        self.assertTrue(fake.wait_for(lambda e: b"notifications/n7" in e["body"]))
        self.assertEqual([m["method"] for m in fake.posted()],
                         [f"notifications/n{n}" for n in range(8)])


    def test_reply_to_server_request_while_its_stream_is_open(self) -> None:
        stream_open_at_reply: list[bool] = []

        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body)
            if message.get("method") == "slow":
                stream_head(h)
                piece(h, event({"jsonrpc": "2.0", "id": 5, "method": "ping"}))
                stream_open_at_reply.append(fake.event("replied").wait(5))
                piece(h, event(result(message, {"done": True})))
                end_stream(h)
            else:  # the client's reply to the server's ping
                fake.event("replied").set()
                reply_json(h, 202, b"")

        fake = self.serve(script)
        handlers = Handlers(())
        wire, _ = self.wire(fake, on_request=handlers.handle_request)
        handlers.attach(wire)
        self.assertEqual(wire.request("slow", timeout=5), {"done": True})
        self.assertEqual(stream_open_at_reply, [True])
        replies = [m for m in fake.posted() if m.get("id") == 5]
        self.assertEqual(replies[0]["result"], {})


class HttpStreamTest(Case):
    def test_stream_opens_before_initialized(self) -> None:
        fake = self.serve(standard)
        session, _ = self.session(fake)
        session.initialize({"roots": {}})
        self.assertTrue(fake.wait_for(lambda e: b"notifications/initialized" in e["body"]))
        with fake.lock:
            order = [e["method"] + ":" + (json.loads(e["body"]).get("method", "") if e["body"]
                                          else "") for e in fake.log]
        self.assertEqual(order[:3], ["POST:initialize", "GET:", "POST:notifications/initialized"])

    def test_get_stream_delivers_requests_and_notifications(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            if h.command == "GET":
                stream_head(h)
                piece(h, event({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}))
                piece(h, event({"jsonrpc": "2.0", "id": 0, "method": "roots/list"}))
                fake.event("deleted").wait(5)
                end_stream(h)
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        handlers = Handlers(("roots",), debounce=0.01)
        session, _ = self.session(fake, on_request=handlers.handle_request,
                                  on_notification=handlers.handle_notification)
        handlers.attach(session.wire)
        session.initialize(handlers.capabilities)
        self.assertTrue(handlers.wait_count("roots/list", 1, 5))
        self.assertTrue(handlers.wait_count("notifications/tools/list_changed", 1, 5))
        self.assertTrue(fake.wait_for(lambda e: b'"roots"' in e["body"] and b'"id": 0' in e["body"]
                                      or b'"id":0' in e["body"] and b'"roots":' in e["body"]))
        self.assertEqual(session.wire.notifications.get(timeout=1)["method"],
                         "notifications/tools/list_changed")

    def test_refused_stream_is_reported(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            if h.command == "GET":
                reply_json(h, 405, b"")
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        session, reports = self.session(fake)
        session.initialize({"roots": {}})
        self.assertEqual(session.request("ping"), {})
        self.assertTrue(any("405" in r for r in reports), reports)

    def test_cancel_closes_the_response_stream(self) -> None:
        disconnected: list[bool] = []

        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body) if body else {}
            if message.get("method") == "long":
                stream_head(h)
                piece(h, b"id: p\ndata: \n\n")
                fake.event("long-open").set()
                disconnected.append(hung_up(h))
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        session, _ = self.session(fake)
        session.initialize()
        pending = session.start_request("long")
        self.assertTrue(fake.event("long-open").wait(5))
        self.assertTrue(session.cancel(pending, "test"))
        self.assertTrue(fake.wait_for(lambda e: b"notifications/cancelled" in e["body"]))
        deadline = time.monotonic() + 5
        while not disconnected and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(disconnected, [True])

    def test_close_sends_delete_and_ends_streams(self) -> None:
        fake = self.serve(standard)
        session, _ = self.session(fake)
        session.initialize({"roots": {}})
        self.assertEqual(session.close(), 200)
        self.assertEqual(session.http.stream_end, "server")
        with fake.lock:
            deletes = [e for e in fake.log if e["method"] == "DELETE"]
        self.assertEqual(len(deletes), 1)
        self.assertEqual(deletes[0]["headers"]["mcp-session-id"], SESSION)
        with self.assertRaises(OSError):
            session.wire.request("ping")
        self.assertEqual(session.close(), 200)  # safe twice

    def test_close_without_a_session_returns_none(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body)
            if "id" not in message:
                return reply_json(h, 202, b"")
            stream_head(h)
            piece(h, event(result(message, INIT_RESULT)))
            end_stream(h)

        fake = self.serve(script)
        session, _ = self.session(fake)
        session.initialize()
        self.assertIsNone(session.close())
        self.assertTrue(fake.wait_for(lambda e: b"notifications/initialized" in e["body"]))
        self.assertEqual([e["method"] for e in fake.log], ["POST", "POST"])  # and no DELETE


class HttpModesTest(Case):
    """C23 (part B2, D10): manual over HTTP, and `--url` against `-- <command>`."""

    def test_manual_posts_typed_line_verbatim(self) -> None:
        junk = "{not json at all"
        typed = '{"id":7,  "method":"ping" }'  # no jsonrpc, odd spacing

        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            if body.decode() == junk:
                reply_json(h, 400, b'{"error":"Bad Request: junk"}')
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        reports: list[str] = []
        out = io.StringIO()
        status = manual.run_manual([], [typed, junk], out, settle=0.5, report=reports.append,
                                   url=fake.url)
        self.assertEqual(status, 0)
        with fake.lock:
            bodies = [e["body"].decode() for e in fake.log if e["method"] == "POST"]
        self.assertEqual(bodies[2:4], [typed, junk])  # after initialize and initialized
        self.assertIn(f"-> {junk}", out.getvalue())
        refusal = [r for r in reports if "HTTP 400" in r]
        self.assertEqual(len(refusal), 1, reports)
        self.assertIn("Bad Request: junk", refusal[0])

    def test_url_and_command_are_exclusive(self) -> None:
        url = "http://127.0.0.1:9/mcp"
        for argv in (["tour", "--url", url, "--", "cmd"], ["tour", "--", "cmd", "--url", url],
                     ["tour", "--url"], ["tour", "--url", url, "extra"], ["tour"],
                     ["matrix", "--url", url], ["tasks", "--era", "2026-07-28", "--url", url]):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(client_main.main(argv), 2, argv)
            self.assertIn("usage:", err.getvalue())


DISCOVER = {"supportedVersions": ["2026-07-28"], "capabilities": {},
            "serverInfo": {"name": "fake", "version": "0"}}


def modern(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
    """A 2026-07-28 server: JSON for discover, an event stream for everything else."""
    message = json.loads(body)
    if message["method"] == "server/discover":
        reply_json(h, 200, json.dumps(result(message, DISCOVER)).encode())
    elif message["method"] == "long":
        stream_head(h)
        piece(h, event({"jsonrpc": "2.0", "method": "notifications/progress",
                        "params": {"progressToken": "t", "progress": 1}}))
        fake.event("long-open").set()
        if hung_up(h):
            fake.event("hung-up").set()
    else:
        stream_head(h)
        piece(h, event(result(message)))
        end_stream(h)


class Era2026Test(Case):
    """C24, C25 (part D, D11): the 2026-07-28 era over HTTP."""

    def modern(self, fake: Fake) -> ModernHttpSession:
        session = ModernHttpSession.open_http(fake.url, report=lambda _text: None, timeout=5)
        self.addCleanup(session.close)
        session.discover()
        return session

    def test_every_post_carries_the_request_headers(self) -> None:
        fake = self.serve(modern)
        session = self.modern(fake)
        session.call("tools/call", {"name": "echo", "arguments": {}})
        session.call("resources/read", {"uri": "demo://x"})
        session.call("prompts/get", {"name": "simple-prompt"})
        session.call("tools/list")
        with fake.lock:
            log = [e for e in fake.log if e["method"] == "POST"]
        seen = [(json.loads(e["body"])["method"], e["headers"].get("mcp-method"),
                 e["headers"].get("mcp-name"), e["headers"].get("mcp-protocol-version"))
                for e in log]
        self.assertEqual(seen, [
            ("server/discover", "server/discover", None, "2026-07-28"),
            ("tools/call", "tools/call", "echo", "2026-07-28"),
            ("resources/read", "resources/read", "demo://x", "2026-07-28"),
            ("prompts/get", "prompts/get", "simple-prompt", "2026-07-28"),
            ("tools/list", "tools/list", None, "2026-07-28"),
        ])

    def test_no_session_stream_or_delete(self) -> None:
        fake = self.serve(modern)
        session = self.modern(fake)
        session.call("tools/list")
        self.assertIsNone(session.close())
        with fake.lock:
            log = list(fake.log)
        self.assertEqual({e["method"] for e in log}, {"POST"})
        for entry in log:
            self.assertNotIn("mcp-session-id", entry["headers"])

    def test_non_ascii_name_is_refused(self) -> None:
        fake = self.serve(modern)
        session = self.modern(fake)
        before = len(fake.log)
        with self.assertRaises(ValueError) as caught:
            session.call("tools/call", {"name": "écho", "arguments": {}})
        self.assertIn("plain ASCII", str(caught.exception))
        self.assertEqual(len(fake.log), before, "nothing was sent")

    def test_cancel_closes_stream_without_notification(self) -> None:
        fake = self.serve(modern)
        session = self.modern(fake)
        pending = session.start_request("long")
        self.assertTrue(fake.event("long-open").wait(5))
        self.assertTrue(session.cancel(pending, "test"))
        self.assertTrue(fake.event("hung-up").wait(5), "the stream's connection was closed")
        with fake.lock:
            methods = [json.loads(e["body"])["method"] for e in fake.log if e["body"]]
        self.assertNotIn("notifications/cancelled", methods)


if __name__ == "__main__":
    unittest.main()
