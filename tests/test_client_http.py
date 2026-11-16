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
from unittest import mock

from client import __main__ as client_main
from client import http_wire, manual
from client.handlers import Handlers
from client.http_wire import (
    Carrier,
    HttpSession,
    HttpStatusError,
    HttpWire,
    SessionEnded,
    sse_data,
)
from client.modern_http import ModernHttpSession
from client.session import UnsupportedVersion
from client.wire import RpcError

Script = Callable[["Fake", http.server.BaseHTTPRequestHandler, bytes], None]
SESSION = "sess-1"
INIT_RESULT = {"protocolVersion": "2025-11-25", "capabilities": {},
               "serverInfo": {"name": "fake", "version": "0"}}


class Fake:
    """A loopback HTTP server whose answers a test scripts; `log` holds every request.

    `log` is in the order the handler threads read the requests; `ordered()` is in the order
    the connections were accepted, which is the client's write order (one POST per connection,
    each sent in full before the next opens; P8-FL-2).
    """

    def __init__(self, script: Script, *, sequential: bool = False) -> None:
        self.script = script
        self.log: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.events: dict[str, threading.Event] = {}
        self.accepted: dict[socket.socket, int] = {}
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
                        "conn": fake.accepted[self.connection],
                        "method": self.command, "path": self.path, "body": body,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                    })
                fake.script(fake, self, body)

            do_GET = do_POST = do_DELETE = serve

        base = http.server.HTTPServer if sequential else http.server.ThreadingHTTPServer

        class Server(base):  # type: ignore[valid-type,misc]
            def process_request(self, request: Any, client_address: Any) -> None:
                # The accepting thread numbers each connection before its handler starts.
                with fake.lock:
                    fake.accepted[request] = len(fake.accepted)
                super().process_request(request, client_address)

        self.server = Server(("127.0.0.1", 0), Handler)
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

    def ordered(self) -> list[dict[str, Any]]:
        """The log in connection order (stable within one connection)."""
        with self.lock:
            return sorted(self.log, key=lambda e: e["conn"])

    def posted(self) -> list[dict[str, Any]]:
        """The JSON bodies of the POSTs, in the client's write order."""
        return [{**json.loads(e["body"]), "_headers": e["headers"]}
                for e in self.ordered() if e["method"] == "POST" and e["body"]]


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


class FakeOrderTest(Case):
    def test_log_follows_connection_order(self) -> None:
        # C202 (P8-FL-2): the client opens one connection per POST and sends each in full before
        # opening the next, so its write order is the order the fake accepts connections in. The
        # handler threads read the bodies in any order; the log must not follow them. Here the
        # first connection's body is held back until the second's has been read.
        fake = self.serve(lambda fake, h, body: reply_json(h, 202, b""))
        port = int(fake.url.split(":")[2].split("/")[0])

        def post(body: bytes) -> bytes:
            return (b"POST /mcp HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\n\r\n%b"
                    % (len(body), body))

        first = socket.create_connection(("127.0.0.1", port))
        self.addCleanup(first.close)
        whole = post(b'{"n":1}')
        first.sendall(whole[:-3])
        time.sleep(0.2)  # the fake has accepted the first connection
        second = socket.create_connection(("127.0.0.1", port))
        self.addCleanup(second.close)
        second.sendall(post(b'{"n":2}'))
        self.assertTrue(fake.wait_for(lambda e: e["body"] == b'{"n":2}'))
        first.sendall(whole[-3:])
        self.assertTrue(fake.wait_for(lambda e: e["body"] == b'{"n":1}'))
        for sock in (first, second):
            sock.recv(1024)  # the 202, so neither connection closes with unread data
        self.assertEqual([m["n"] for m in fake.posted()], [1, 2])


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

    def test_protocol_version_header_is_the_negotiated_one(self) -> None:
        """P8-R7-10: the server answers `initialize` with an older version the client supports."""
        older = {**INIT_RESULT, "protocolVersion": "2025-06-18"}

        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body) if body else {}
            if message.get("method") == "initialize":
                stream_head(h, {"Mcp-Session-Id": SESSION})
                piece(h, event(result(message, older)))
                end_stream(h)
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        session, _ = self.session(fake)
        session.initialize({"roots": {}})
        session.request("ping")
        self.assertEqual(session.close(), 200)
        with fake.lock:
            later = fake.log[1:]  # everything after the initialize POST
        self.assertEqual({e["method"] for e in later}, {"GET", "POST", "DELETE"})
        for entry in later:
            self.assertEqual(entry["headers"]["mcp-protocol-version"], "2025-06-18",
                             entry["method"])

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

    def test_error_status_with_another_id_fails_the_request_at_once(self) -> None:
        """P8-R7-8: a body whose id is not the posted request's is not that request's reply."""
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            reply_json(h, 400, json.dumps({"jsonrpc": "2.0", "id": 999, "error": {
                "code": -32600, "message": "not yours"}}).encode())

        fake = self.serve(script)
        wire, _ = self.wire(fake)
        started = time.monotonic()
        with self.assertRaises(HttpStatusError) as caught:
            wire.request("ping", timeout=5)
        self.assertEqual(caught.exception.status, 400)
        self.assertIn("not yours", str(caught.exception))
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


    def test_next_post_waits_for_a_notifications_202(self) -> None:
        # C203 (P8-FL-3): separate POSTs are separate connections, and nothing orders them at
        # the server; the client knows a notification was taken only from its `202`. So the
        # next POST waits for it, and `ping` cannot overtake `initialized`. The fake holds the
        # `202` back; at that moment it must have seen no later POST.
        seen_at_202: list[int] = []

        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            if body and json.loads(body).get("method") == "notifications/initialized":
                time.sleep(0.3)
                with fake.lock:
                    seen_at_202.append(len(fake.log))
                reply_json(h, 202, b"")
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        session, _ = self.session(fake)
        session.initialize()
        self.assertEqual(session.request("ping"), {})
        deadline = time.monotonic() + 5
        while not seen_at_202 and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(seen_at_202, [2])  # initialize and initialized only
        self.assertEqual([m["method"] for m in fake.posted()],
                         ["initialize", "notifications/initialized", "ping"])

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
        with fake.lock:
            get = next(e for e in fake.log if e["method"] == "GET")
        self.assertEqual(get["headers"]["accept"], "text/event-stream")  # P8-R7-11

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

    def test_close_waits_for_the_receivers(self) -> None:
        # C205 (P8-FL-6): a receiver thread still printing what it read when the program exits
        # aborted the interpreter (exit 134, "could not acquire lock for <stdout> at interpreter
        # shutdown"). Here a receiver is held inside the observer while the session closes.
        entered, finished = threading.Event(), threading.Event()

        def observer(arrow: str, message: Any) -> None:
            if arrow == "<-" and isinstance(message, dict) and message.get("method") == "note":
                entered.set()
                time.sleep(0.5)
                finished.set()

        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            if body and json.loads(body).get("method") == "slow":
                stream_head(h)
                piece(h, event({"jsonrpc": "2.0", "method": "note"}))
                hung_up(h)
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        session, _ = self.session(fake, observer=observer)
        session.initialize()
        session.start_request("slow")
        self.assertTrue(entered.wait(5))
        session.close()
        self.assertTrue(finished.is_set(), "close returned while a receiver was still running")

    def test_unanswered_delete_is_bounded(self) -> None:
        """P8-R7-5: a DELETE the server never answers ends `close` after the grace, not never."""
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            if h.command == "DELETE":
                fake.event("delete-seen").set()
                fake.event("release").wait(10)  # never answers while the test is looking
                h.close_connection = True
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        session, reports = self.session(fake)
        self.addCleanup(fake.event("release").set)  # runs before `session.close`
        session.grace = 0.5
        session.initialize()
        statuses: list[int | None] = []
        closer = threading.Thread(target=lambda: statuses.append(session.close()), daemon=True)
        started = time.monotonic()
        closer.start()
        closer.join(5)
        self.assertFalse(closer.is_alive(), "close() is still waiting for the DELETE")
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertTrue(fake.event("delete-seen").is_set())
        self.assertEqual(statuses, [None])
        self.assertTrue(any("no answer to DELETE" in r for r in reports), reports)

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
        bodies = [e["body"].decode() for e in fake.ordered() if e["method"] == "POST"]
        self.assertEqual(bodies[2:4], [typed, junk])  # after initialize and initialized
        self.assertIn(f"-> {junk}", out.getvalue())
        refusal = [r for r in reports if "HTTP 400" in r]
        self.assertEqual(len(refusal), 1, reports)
        self.assertIn("Bad Request: junk", refusal[0])

    def test_manual_reports_a_late_refusal_before_closing(self) -> None:
        # C204 (P8-FL-4): lesson 07's junk-line block. The junk line is the last one, so
        # nothing is awaited; the refusal must still be read and reported before the session
        # closes, however late it comes.
        junk = '{"jsonrpc":"2.0","id":9,"method":"ping"'

        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            if body.decode() == junk:
                time.sleep(0.3)
                reply_json(h, 400, b'{"jsonrpc":"2.0","error":{"code":-32700,'
                                   b'"message":"Parse error"},"id":null}')
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        reports: list[str] = []
        status = manual.run_manual([], [junk, ":quit"], io.StringIO(), settle=0.5,
                                   report=reports.append, url=fake.url)
        self.assertEqual(status, 0)
        self.assertEqual(len([r for r in reports if "POST failed: HTTP 400" in r]), 1, reports)

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
        self.assertEqual(session.wire._pending, {}, "the refused request left no pending entry")

    def test_name_with_edge_whitespace_is_refused(self) -> None:
        """P8-R7-7: leading or trailing space or tab MUST be Base64 (out of scope), so refuse;
        a space inside a name is plain."""
        fake = self.serve(modern)
        session = self.modern(fake)
        before = len(fake.log)
        for name in (" echo", "echo ", " echo ", "\techo", "echo\t"):
            with self.assertRaises(ValueError, msg=repr(name)):
                session.call("tools/call", {"name": name, "arguments": {}})
        self.assertEqual(len(fake.log), before, "nothing was sent")
        self.assertEqual(session.wire._pending, {}, "the refused requests left no pending entry")
        session.call("tools/call", {"name": "my tool", "arguments": {}})
        with fake.lock:
            last = fake.log[-1]
        self.assertEqual(last["headers"]["mcp-name"], "my tool")

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


class SilentCarrier:
    """A stand-in for one HTTP connection: `getresponse` gives a scripted event stream whose
    reading hangs the carrier up (as `close_connections` does) just before it ends whole."""

    sock = None

    def __init__(self, lines: list[bytes]) -> None:
        self.lines = list(lines)
        self.carrier: Any = None
        self.status = 200

    def getheader(self, name: str) -> str | None:
        return "text/event-stream" if name.lower() == "content-type" else None

    def readline(self) -> bytes:
        if self.lines:
            return self.lines.pop(0)
        self.carrier.closed = True  # the client hung up as the stream ended: the end is whole
        return b""

    def getresponse(self) -> SilentCarrier:
        return self

    def close(self) -> None:
        pass


class HttpWireDetailTest(Case):
    """Phase 8 D9 (phase 7 C11-C15): the details of the raw client's HTTP transport that the
    first tests left to the mutation run (rows C181-C189)."""

    def test_a_404_to_a_request_with_no_session_ends_nothing(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body) if body else {}
            if message.get("method") == "gone":
                reply_json(h, 404, json.dumps({"jsonrpc": "2.0", "id": message["id"], "error": {
                    "code": -32001, "message": "Not found"}}).encode())
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        wire, _ = self.wire(fake)  # no `initialize`: the server gave no session id
        with self.assertRaises(RpcError):
            wire.request("gone", timeout=5)
        self.assertEqual(wire.request("ping", timeout=5), {})

    def test_an_error_status_other_than_404_does_not_end_the_session(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body) if body else {}
            if message.get("method", "").startswith("status"):
                reply_json(h, int(message["method"][6:]), b"no", "text/plain")
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        session, _ = self.session(fake)
        session.initialize()
        for status in (400, 403, 500):
            with self.subTest(status=status):
                with self.assertRaises(HttpStatusError):
                    session.request(f"status{status}")
                self.assertEqual(session.request("ping"), {})

    def test_a_404_hangs_up_every_other_open_stream(self) -> None:
        hung: list[bool] = []

        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body) if body else {}
            if message.get("method") == "gone":
                reply_json(h, 404, json.dumps({"jsonrpc": "2.0", "id": message["id"], "error": {
                    "code": -32001, "message": "Session not found"}}).encode())
            elif message.get("method") == "hang":
                stream_head(h)
                piece(h, b"id: p\ndata: \n\n")
                fake.event("hanging").set()
                hung.append(hung_up(h, 4.0))
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        session, _ = self.session(fake)
        session.initialize()
        session.start_request("hang")
        self.assertTrue(fake.event("hanging").wait(5))
        with self.assertRaises(RpcError):
            session.request("gone")
        deadline = time.monotonic() + 6
        while not hung and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(hung, [True], "the stream of the other request was left open")

    def test_a_failed_request_is_no_longer_pending(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            reply_json(h, 400, b"Bad Request", "text/plain")

        fake = self.serve(script)
        wire, _ = self.wire(fake)
        pending = wire.start_request("plain")
        with self.assertRaises(HttpStatusError):
            pending.wait(5)
        self.assertFalse(wire.abandon(pending), "the failed request was still in the table")

    def test_a_cancelled_request_is_not_reported_as_a_failed_post(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body) if body else {}
            if message.get("method") == "long":
                stream_head(h)
                piece(h, b"id: p\ndata: \n\n")
                fake.event("long-open").set()
                hung_up(h)
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        session, reports = self.session(fake)
        session.initialize()
        pending = session.start_request("long")
        self.assertTrue(fake.event("long-open").wait(5))
        self.assertTrue(session.cancel(pending, "test"))
        session.close()  # waits for the reader of the hung-up stream to end
        self.assertEqual([r for r in reports if "POST failed" in r], [])

    def test_a_connection_dropped_without_an_answer_fails_the_request_at_once(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            h.close_connection = True  # no status line, nothing

        fake = self.serve(script)
        wire, _ = self.wire(fake)
        started = time.monotonic()
        with self.assertRaises(OSError):
            wire.request("drop", timeout=5)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_a_line_that_cannot_be_handled_does_not_end_the_response(self) -> None:
        def on_request(message: dict[str, Any]) -> None:
            raise RuntimeError("the handler broke")

        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body)
            stream_head(h)
            piece(h, event({"jsonrpc": "2.0", "id": 41, "method": "roots/list"}))
            piece(h, event({"jsonrpc": "2.0", "id": 42, "method": "sampling/createMessage"}))
            piece(h, event(result(message, {"after": True})))
            end_stream(h)

        fake = self.serve(script)
        wire, reports = self.wire(fake, on_request=on_request)
        self.assertEqual(wire.request("go", timeout=5), {"after": True})
        self.assertTrue(any("the handler broke" in r for r in reports), reports)
        self.assertEqual(wire.server_request_ids("roots/list"), [41])
        self.assertEqual(wire.server_request_ids("sampling/createMessage"), [42])

    def test_nothing_is_posted_once_the_session_is_closed(self) -> None:
        fake = self.serve(standard)
        session, _ = self.session(fake)
        session.initialize()
        session.close()
        with fake.lock:
            before = len(fake.log)
        with self.assertRaises(OSError):
            session.wire.notify("notifications/late")
        with self.assertRaises(OSError):
            session.wire.send_line("{}")
        with fake.lock:
            self.assertEqual(len(fake.log), before)

    def test_open_stream_returns_the_status_once_the_head_has_arrived(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            if h.command == "GET":
                time.sleep(0.3)  # the head is late
                if fake.event("refuse").is_set():
                    return reply_json(h, 405, b"")
            standard(fake, h, body)

        fake = self.serve(script)
        self.addCleanup(fake.event("deleted").set)
        wire, reports = self.wire(fake)
        self.assertEqual(wire.open_stream(), 200)
        head = wire.wait_head("stream", "", timeout=0)
        self.assertIsNotNone(head)
        fake.event("refuse").set()
        wire2, reports2 = self.wire(fake)
        self.assertEqual(wire2.open_stream(), 405)
        self.assertTrue(any("405" in r for r in reports2), reports2)
        self.assertEqual(reports, [])

    def test_a_stream_the_client_closes_is_ended_by_the_client_and_not_reported(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            stream_head(h)
            piece(h, b": open\n\n")
            hung_up(h)

        fake = self.serve(script)
        wire, reports = self.wire(fake)
        self.assertEqual(wire.open_stream(), 200)
        wire.close_connections()
        wire.wait_stream_end(5)
        self.assertEqual(wire.stream_end, "client")
        self.assertEqual(reports, [])

    def test_a_stream_that_ends_whole_as_the_client_closes_it_is_ended_by_the_client(self) -> None:
        carrier = SilentCarrier([b": open\n", b"\n"])
        reports: list[str] = []
        wire = HttpWire("http://127.0.0.1:9/mcp", report=reports.append)
        carrier.carrier = Carrier(carrier)  # type: ignore[arg-type]
        wire._send = lambda method, headers, body=None: carrier.carrier  # type: ignore[method-assign]
        carrier.carrier.conn = carrier
        self.assertEqual(wire.open_stream(), 200)
        wire.wait_stream_end(5)
        self.assertEqual(wire.stream_end, "client")

    def test_a_stream_the_server_breaks_is_reported_and_ended_by_the_server(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            stream_head(h)
            piece(h, b": open\n\n")
            h.wfile.write(b"40\r\nda")  # a chunk that never finishes
            h.wfile.flush()
            h.close_connection = True

        fake = self.serve(script)
        wire, reports = self.wire(fake)
        self.assertEqual(wire.open_stream(), 200)
        wire.wait_stream_end(5)
        self.assertEqual(wire.stream_end, "server")
        self.assertTrue(any("the GET stream failed" in r for r in reports), reports)

    def test_closing_a_stream_before_its_head_arrives_is_no_failure(self) -> None:
        # The hang-up wakes a reader still waiting for the head with an error; the client caused
        # it, so it is neither reported nor taken for the server ending the stream.
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            fake.event("asked").set()
            hung_up(h, 3.0)  # the head never comes

        fake = self.serve(script)
        wire, reports = self.wire(fake)
        self.assertIsNone(wire.open_stream(timeout=0.3))
        self.assertTrue(fake.event("asked").wait(5))
        wire.close_connections()
        wire.wait_stream_end(5)
        self.assertEqual(wire.stream_end, "client")
        self.assertEqual(reports, [])

    def test_cancelling_a_request_before_its_head_arrives_is_no_failed_post(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            fake.event("asked").set()
            hung_up(h, 3.0)  # no head: the client has to hang up

        fake = self.serve(script)
        wire, reports = self.wire(fake)
        pending = wire.start_request("slowhead")
        self.assertTrue(fake.event("asked").wait(5))
        self.assertTrue(wire.abandon(pending))
        wire.join(5)
        self.assertEqual(reports, [])

    def test_a_later_initialize_carries_no_session_headers_either(self) -> None:
        fake = self.serve(standard)
        session, _ = self.session(fake)
        session.initialize()
        session.request("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                       "clientInfo": {"name": "x", "version": "0"}})
        with fake.lock:
            inits = [e for e in fake.log if e["method"] == "POST"
                     and json.loads(e["body"]).get("method") == "initialize"]
        self.assertEqual(len(inits), 2)
        for entry in inits:
            self.assertNotIn("mcp-session-id", entry["headers"])
            self.assertNotIn("mcp-protocol-version", entry["headers"])

    def test_stream_false_opens_no_stream(self) -> None:
        fake = self.serve(standard)
        session, _ = self.session(fake)
        session.initialize({"roots": {}}, stream=False)
        self.assertTrue(fake.wait_for(lambda e: b"notifications/initialized" in e["body"]))
        with fake.lock:
            self.assertNotIn("GET", [e["method"] for e in fake.log])

    def test_a_version_the_client_does_not_speak_is_refused(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            if not body:  # the cleanup's DELETE
                return reply_json(h, 200, b"")
            message = json.loads(body)
            stream_head(h, {"Mcp-Session-Id": SESSION})
            piece(h, event(result(message, {**INIT_RESULT, "protocolVersion": "1999-01-01"})))
            end_stream(h)

        fake = self.serve(script)
        session, _ = self.session(fake)
        with self.assertRaises(UnsupportedVersion):
            session.initialize()
        self.assertFalse(session.ready)

    def test_a_late_cancel_leaves_the_stream_of_an_answered_request_open(self) -> None:
        disconnected: list[bool] = []

        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body) if body else {}
            if message.get("method") == "slow":
                stream_head(h)
                piece(h, event(result(message, {"done": True})))  # answered; the stream stays
                fake.event("answered").set()
                disconnected.append(hung_up(h, 1.5))
                end_stream(h)
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        session, _ = self.session(fake)
        session.initialize()
        pending = session.start_request("slow")
        self.assertEqual(pending.wait(5), {"done": True})
        self.assertFalse(session.cancel(pending, "too late"))  # it was answered already
        deadline = time.monotonic() + 5
        while not disconnected and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(disconnected, [False])


class SseDataTest(unittest.TestCase):
    """Phase 8 D9 (C12): `sse_data`, the client's reading of an event stream, on its own."""

    def data(self, stream: bytes) -> list[bytes]:
        return list(sse_data(io.BytesIO(stream)))  # type: ignore[arg-type]

    def test_data_lines_of_one_event_are_joined_with_a_newline(self) -> None:
        self.assertEqual(self.data(b"data: a\ndata: b\ndata:\ndata: d\n\n"), [b"a\nb\n\nd"])

    def test_crlf_lines_end_without_their_cr(self) -> None:
        self.assertEqual(self.data(b"data: a\r\ndata: b\r\n\r\ndata: c\r\n\r\n"),
                         [b"a\nb", b"c"])

    def test_only_data_lines_count_and_comments_are_skipped(self) -> None:
        stream = b": comment\nevent: message\nid: 7\nretry: 5\ndata: x\n\n"
        self.assertEqual(self.data(stream), [b"x"])
        self.assertEqual(self.data(b"event: only\n\nid: 1\n\n"), [])

    def test_an_event_the_stream_ends_in_the_middle_of_is_not_dispatched(self) -> None:
        self.assertEqual(self.data(b"data: whole\n\ndata: cut"), [b"whole"])
        self.assertEqual(self.data(b"data: cut\n"), [])

    def test_one_space_after_the_colon_is_dropped_and_no_more(self) -> None:
        self.assertEqual(self.data(b"data:  two\ndata:none\n\n"), [b" two\nnone"])


class HttpWireDetailTwoTest(Case):
    """Phase 8 D9 (phase 7 C11-C15, C24, C203, C205), second part: rows C181-C189."""

    def init_script(self, versions: list[str], extra_first: list[dict[str, Any]] | None = None
                    ) -> Script:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            if not body:
                return standard(fake, h, body)
            message = json.loads(body)
            if message.get("method") != "initialize":
                return standard(fake, h, body)
            stream_head(h, {"Mcp-Session-Id": SESSION})
            for other in extra_first or []:
                piece(h, event(other))
            for version in versions:
                piece(h, event(result(message, {**INIT_RESULT, "protocolVersion": version})))
            end_stream(h)

        return script

    def versions_sent_later(self, fake: Fake) -> set[str | None]:
        with fake.lock:
            later = fake.log[1:]
        return {e["headers"].get("mcp-protocol-version") for e in later}

    def test_the_version_is_fixed_by_the_first_answer_to_initialize(self) -> None:
        # A second answer to the same id is dropped by the wire (and reported); it must not
        # replace the version the first one negotiated.
        fake = self.serve(self.init_script(["2025-11-25", "2025-06-18"]))
        session, _ = self.session(fake)
        session.initialize()
        session.wire.notify("notifications/x")
        self.assertTrue(fake.wait_for(lambda e: b"notifications/x" in e["body"]))
        self.assertEqual(self.versions_sent_later(fake) - {None}, {"2025-11-25"})

    def test_an_answer_to_another_request_does_not_fix_the_version(self) -> None:
        other = {"jsonrpc": "2.0", "id": 99, "result": {"protocolVersion": "2024-11-05"}}
        fake = self.serve(self.init_script(["2025-11-25"], [other]))
        session, _ = self.session(fake)
        session.initialize()
        session.wire.notify("notifications/x")
        self.assertTrue(fake.wait_for(lambda e: b"notifications/x" in e["body"]))
        self.assertEqual(self.versions_sent_later(fake) - {None}, {"2025-11-25"})

    def test_an_event_stream_is_known_by_its_type_whatever_the_case_or_parameters(self) -> None:
        for ctype in ("Text/Event-Stream", "text/event-stream; charset=utf-8"):
            with self.subTest(ctype=ctype):
                def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes,
                           ctype: str = ctype) -> None:
                    message = json.loads(body)
                    h.send_response(200)
                    h.send_header("Content-Type", ctype)
                    h.send_header("Transfer-Encoding", "chunked")
                    h.end_headers()
                    piece(h, b"id: p\ndata: \n\n")
                    piece(h, event(result(message, {"ok": True})))
                    end_stream(h)

                fake = self.serve(script)
                wire, _ = self.wire(fake)
                self.assertEqual(wire.request("go", timeout=5), {"ok": True})

    def test_a_blank_200_body_is_not_a_message(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            reply_json(h, 200, b" \n")

        fake = self.serve(script)
        wire, reports = self.wire(fake)
        wire.notify("notifications/x")
        self.assertIsNotNone(wire.wait_head("notification", "notifications/x"))
        wire.join(3)
        self.assertEqual(reports, [])

    def test_a_refused_post_that_carries_no_request_is_reported_whatever_the_body(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            reply_json(h, 400, json.dumps({"jsonrpc": "2.0", "id": 0, "error": {
                "code": -32600, "message": "no"}}).encode())

        fake = self.serve(script)
        wire, reports = self.wire(fake)
        wire.notify("notifications/x")
        wire.join(3)
        self.assertTrue(any("POST failed: HTTP 400" in r for r in reports), reports)

    def test_next_post_waits_for_an_unanswered_post_only_for_a_bound(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            fake.event("release").wait(8)  # a notification the server never answers
            with contextlib.suppress(OSError):
                reply_json(h, 202, b"")

        fake = self.serve(script)
        self.addCleanup(fake.event("release").set)
        wire, _ = self.wire(fake)
        with mock.patch.object(http_wire, "CONNECT_TIMEOUT", 0.3):
            wire.notify("notifications/a")
            started = time.monotonic()
            wire.notify("notifications/b")  # waits for a's answer, but only so long
            self.assertLess(time.monotonic() - started, 3.0)

    def hung_stream_script(self, hung: list[bool]) -> Script:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            message = json.loads(body) if body else {}
            if message.get("method") == "hang":
                stream_head(h)
                piece(h, b"id: p\ndata: \n\n")
                fake.event("hanging").set()
                hung.append(hung_up(h, 5.0))
            else:
                standard(fake, h, body)

        return script

    def test_close_hangs_up_the_open_streams_before_it_waits_for_their_readers(self) -> None:
        hung: list[bool] = []
        fake = self.serve(self.hung_stream_script(hung))
        session, _ = self.session(fake)
        session.grace = 2.0
        session.initialize()
        session.start_request("hang")
        self.assertTrue(fake.event("hanging").wait(5))
        started = time.monotonic()
        session.close()
        self.assertLess(time.monotonic() - started, 1.5, "close waited out its grace")
        deadline = time.monotonic() + 3
        while not hung and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(hung, [True], "the server never saw the stream hung up")

    def test_close_waits_for_the_server_to_end_the_get_stream(self) -> None:
        def script(fake: Fake, h: http.server.BaseHTTPRequestHandler, body: bytes) -> None:
            if h.command == "GET":
                stream_head(h)
                piece(h, b": open\n\n")
                fake.event("deleted").wait(5)
                time.sleep(0.4)  # the server ends the stream a moment after the DELETE
                end_stream(h)
            else:
                standard(fake, h, body)

        fake = self.serve(script)
        session, _ = self.session(fake)
        session.initialize({"roots": {}})
        session.close()
        self.assertEqual(session.http.stream_end, "server")

    def test_a_second_close_sends_no_second_delete(self) -> None:
        fake = self.serve(standard)
        session, _ = self.session(fake)
        session.initialize()
        self.assertEqual(session.close(), 200)
        self.assertEqual(session.close(), 200)
        with fake.lock:
            deletes = [e for e in fake.log if e["method"] == "DELETE"]
        self.assertEqual(len(deletes), 1)


class Era2026DetailTest(Case):
    """Phase 8 D9 (C24): the 2026-07-28 request headers, on the wire itself."""

    def wire2026(self, fake: Fake) -> HttpWire:
        wire, _ = self.wire(fake, era="2026-07-28")
        return wire

    def test_every_post_names_the_version_even_an_initialize(self) -> None:
        fake = self.serve(modern)
        wire = self.wire2026(fake)
        wire.request("initialize", {}, timeout=5)  # sent as it is: it is a POST all the same
        with fake.lock:
            headers = fake.log[0]["headers"]
        self.assertEqual(headers.get("mcp-protocol-version"), "2026-07-28")
        self.assertEqual(headers.get("mcp-method"), "initialize")

    def test_only_three_methods_carry_a_name(self) -> None:
        fake = self.serve(modern)
        wire = self.wire2026(fake)
        wire.request("resources/subscribe", {"uri": "demo://x"}, timeout=5)
        wire.request("tools/call", {"name": "echo"}, timeout=5)
        with fake.lock:
            names = [e["headers"].get("mcp-name") for e in fake.log]
        self.assertEqual(names, [None, "echo"])

    def test_a_control_character_in_a_name_is_refused(self) -> None:
        fake = self.serve(modern)
        wire = self.wire2026(fake)
        for name in ("a\x7fb", "a\x01b", "a\x00b", "a\nb"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                wire.request("tools/call", {"name": name}, timeout=5)
        self.assertEqual(len(fake.log), 0, "nothing was sent")


if __name__ == "__main__":
    unittest.main()
