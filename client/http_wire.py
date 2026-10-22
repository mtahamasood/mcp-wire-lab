"""The raw client over Streamable HTTP (phase 7 D8): the same wire and session, another transport.

`HttpWire` is a `Wire` whose lines travel by HTTP: every message the wire writes is one POST, and
every response body (a JSON body, or the data of each event of an event stream) goes to the
phase 2 line handler as one incoming line. Classification, id correlation, the pending table,
cancellation bookkeeping, the handlers and the notification queue are `client/wire.py`'s code,
reused unchanged. `HttpSession` is a `Session` that opens the GET stream between `initialize` and
`notifications/initialized`, and closes with a DELETE. Standard library only (P4): the
connection and header steps are `http.client`'s, in plain view.

Out of scope (D14): reconnection, `Last-Event-ID`, re-initialising after a 404, TLS, batches.
"""

from __future__ import annotations

import http.client
import io
import json
import socket
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from client.session import (
    CLIENT_INFO,
    PROTOCOL_VERSION,
    SUPPORTED_VERSIONS,
    Session,
    UnsupportedVersion,
)
from client.wire import (
    DEFAULT_TIMEOUT,
    Key,
    Message,
    Pending,
    Wire,
    classify,
    key_of,
    stderr_report,
)

EVENT_STREAM = "text/event-stream"
ACCEPT = f"application/json, {EVENT_STREAM}"
CONNECT_TIMEOUT = 10.0
ERROR_BODY_LIMIT = 65536


class HttpStatusError(Exception):
    """The server answered a POST with a status that carries no JSON-RPC reply to its request."""

    def __init__(self, status: int, body: str = "") -> None:
        super().__init__(f"HTTP {status}" + (f": {body}" if body else ""))
        self.status = status
        self.body = body


class SessionEnded(ConnectionError):
    """The server no longer knows the session (404 to a request that carried its id)."""


@dataclass
class Head:
    """What came back for one HTTP request: its status and content type."""

    status: int
    content_type: str


class Carrier:
    """One HTTP connection carrying one request and its response; `close` ends it from outside."""

    def __init__(self, conn: http.client.HTTPConnection) -> None:
        self.conn = conn
        self.closed = False

    def hang_up(self) -> None:
        """Hang up from outside: the blocked reader wakes with an error, the server sees the
        disconnect. The reader's own thread then closes the connection object (`close`)."""
        self.closed = True
        sock = self.conn.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def close(self) -> None:
        self.closed = True
        self.conn.close()


def sse_data(resp: http.client.HTTPResponse) -> Iterator[bytes]:
    """The data of each event of an event stream, in order, until the stream ends.

    A line ends with LF or CRLF; `:` lines are comments; one space after the colon is dropped;
    `data` lines of one event are joined with a newline; a blank line dispatches. An empty-data
    event (the priming event) yields b"". An event cut off by the stream's end is not dispatched.

    `spec:docs/specification/2025-11-25/basic/transports.mdx:102`
    "to initiate an SSE stream"
    """
    data: list[bytes] = []
    while True:
        line = resp.readline()  # http.client reads a chunked stream line by line (M14)
        if not line:
            return
        line = line.rstrip(b"\r\n")
        if not line:
            if data:
                yield b"\n".join(data)
                data = []
        elif not line.startswith(b":"):
            name, _, value = line.partition(b":")
            if name == b"data":
                data.append(value[1:] if value.startswith(b" ") else value)


class HttpWire(Wire):
    """A `Wire` that posts each written line and reads each response on its own thread (D8)."""

    def __init__(
        self,
        url: str,
        *,
        report: Callable[[str], None] = stderr_report,
        observer: Callable[[str, Any], None] | None = None,
        on_request: Callable[[Message], None] | None = None,
        on_notification: Callable[[Message], None] | None = None,
    ) -> None:
        super().__init__(io.BytesIO(), io.BytesIO(), report=report, observer=observer,
                         on_request=on_request, on_notification=on_notification)
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "http" or not parts.hostname:
            raise ValueError(f"the raw client speaks plain http only, got {url!r}")
        self._host = parts.hostname
        self._port = parts.port or 80
        self._target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        self.session_id: str | None = None
        self.protocol_version: str | None = None
        self.server_requests: list[tuple[str, Any]] = []  # (method, id) of each, in order
        self.stream_end: str | None = None  # "server" or "client", once the GET stream is over
        self._init_key: Key | None = None
        self._carriers: set[Carrier] = set()
        self._by_request: dict[Key, Carrier] = {}
        self._stream_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._heads: dict[tuple[str, Any], Head] = {}
        self._heads_changed = threading.Condition()

    # -- building and sending ----------------------------------------------------------

    def _headers(self, *, session: bool, extra: dict[str, str]) -> dict[str, str]:
        """The headers of one request: the given ones, then (after `initialize`) the session's.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:265`
        "MCP-Protocol-Version:"
        `spec:docs/specification/2025-11-25/basic/transports.mdx:207`
        "include it in the `MCP-Session-Id`"
        """
        headers = dict(extra)
        if session:
            if self.session_id is not None:
                headers["Mcp-Session-Id"] = self.session_id
            if self.protocol_version is not None:
                headers["MCP-Protocol-Version"] = self.protocol_version
        return headers

    def _send(self, method: str, headers: dict[str, str], body: bytes | None = None) -> Carrier:
        """Open a connection, send one request in full, and return the carrier (not yet read).

        `spec:docs/specification/2025-11-25/basic/transports.mdx:91`
        "MUST** use HTTP POST"
        """
        conn = http.client.HTTPConnection(self._host, self._port, timeout=CONNECT_TIMEOUT)
        try:
            conn.putrequest(method, self._target, skip_accept_encoding=True)
            for name, value in headers.items():
                conn.putheader(name, value)
            if body is not None:
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body)
            if conn.sock is not None:
                conn.sock.settimeout(None)  # a stream is quiet between keepalives (M7)
        except (OSError, http.client.HTTPException) as exc:
            conn.close()
            raise OSError(f"cannot send {method} to {self._host}:{self._port}: {exc}") from exc
        carrier = Carrier(conn)
        with self._lock:
            self._carriers.add(carrier)
        return carrier

    def _write(self, text: str) -> None:
        """Post one message as it is written (the caller holds the write lock, so POSTs leave in
        write order); its response is read on a new thread, so a long one never blocks the next.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:94`
        "body of the POST request **MUST** be"
        """
        if self._closed is not None:
            raise self._closed
        try:
            message: Any = json.loads(text)
        except ValueError:
            message = None  # manual mode may send junk; it is posted as typed
        is_init = isinstance(message, dict) and message.get("method") == "initialize"
        carrier = self._send(
            "POST",
            self._headers(session=not is_init, extra={
                "Content-Type": "application/json", "Accept": ACCEPT}),
            text.encode("utf-8"),
        )
        kind = classify(message)
        with self._lock:
            if kind == "request":
                self._by_request[key_of(message["id"])] = carrier
                if is_init:
                    self._init_key = key_of(message["id"])
        threading.Thread(target=self._receive, args=(carrier, message, kind, is_init),
                         daemon=True).start()

    # -- receiving ---------------------------------------------------------------------

    def _note_head(self, kind: str, ident: Any, resp: http.client.HTTPResponse) -> None:
        content_type = (resp.getheader("Content-Type") or "").split(";")[0].strip().lower()
        with self._heads_changed:
            self._heads[(kind, ident)] = Head(resp.status, content_type)
            self._heads_changed.notify_all()

    def wait_head(self, kind: str, ident: Any, timeout: float = 5.0) -> Head | None:
        """The status and content type of the response to one of our HTTP requests, once seen.

        `kind` is `request` (ident: the id), `notification` (the method), `response` (the id of
        the server request we answered), `stream` (GET) or `delete`.
        """
        deadline = time.monotonic() + timeout
        with self._heads_changed:
            while (kind, ident) not in self._heads:
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self._heads_changed.wait(left)
            return self._heads[(kind, ident)]

    def _line(self, raw: bytes) -> None:
        """Give one incoming message to the phase 2 line handler.

        `initialize`'s result also fixes the version that later requests name in a header.
        """
        try:
            message = json.loads(raw.decode("utf-8"))
        except ValueError:
            message = None
        kind = classify(message)
        if kind == "request":
            self.server_requests.append((message["method"], message["id"]))
        elif (kind == "response" and self._init_key is not None
              and self.protocol_version is None and key_of(message["id"]) == self._init_key
              and "result" in message):
            version = message["result"].get("protocolVersion")
            self.protocol_version = version if isinstance(version, str) else None
        try:
            self.handle_line(raw)
        except Exception as exc:  # one bad line never ends a response
            self._report(f"error while handling a line ({type(exc).__name__}: {exc}): {raw[:80]!r}")

    def _deliver(self, resp: http.client.HTTPResponse) -> None:
        """Hand over a 200 response: one JSON body, or each event's data in order.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:102`
        "to initiate an SSE stream"
        """
        content_type = (resp.getheader("Content-Type") or "").split(";")[0].strip().lower()
        if content_type == EVENT_STREAM:
            for data in sse_data(resp):
                if data:  # the priming event has none
                    self._line(data)
        else:
            body = resp.read()
            if body.strip():
                self._line(body)

    def _receive(self, carrier: Carrier, message: Any, kind: str, is_init: bool) -> None:
        """Read the response to one POST (its own thread) and act on its status.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:96`
        "return HTTP status code 202"
        """
        ident = (message["id"] if kind in ("request", "response") else
                 message.get("method") if kind == "notification" else None)
        try:
            resp = carrier.conn.getresponse()
            self._note_head(kind, ident, resp)
            if is_init and resp.status == 200:
                self.session_id = resp.getheader("Mcp-Session-Id")
            if resp.status == 202:
                resp.read()
            elif resp.status == 200:
                self._deliver(resp)
            else:
                self._refused(resp, message, kind)
        except (OSError, http.client.HTTPException, ValueError, AttributeError) as exc:
            if not carrier.closed:
                self._fail_post(message, kind, exc)
        finally:
            carrier.close()
            with self._lock:
                self._carriers.discard(carrier)
                if kind == "request" and self._by_request.get(key_of(message["id"])) is carrier:
                    del self._by_request[key_of(message["id"])]

    def _refused(self, resp: http.client.HTTPResponse, message: Any, kind: str) -> None:
        """Any status but 200 and 202: a JSON-RPC body with an id is a reply; else the post fails.

        A 404 to a request that carried the session id ends the session.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:212`
        "with HTTP 404 Not Found"
        """
        body = resp.read(ERROR_BODY_LIMIT)
        text = body.decode("utf-8", "replace")
        try:
            decoded = json.loads(text)
        except ValueError:
            decoded = None
        if (classify(decoded) == "response" and decoded.get("id") is not None):
            self._line(body)
        else:
            self._fail_post(message, kind, HttpStatusError(resp.status, text[:200]))
        if resp.status == 404 and self.session_id is not None:
            self._end_session()

    def _fail_post(self, message: Any, kind: str, failure: Exception) -> None:
        """The request this POST carried fails at once; a POST with no request is reported."""
        if kind == "request":
            with self._table_lock:
                pending = self._pending.pop(key_of(message["id"]), None)
            if pending is not None:
                pending.complete(failure=failure)
                return
        self._report(f"POST failed: {failure}")

    def _end_session(self) -> None:
        """The session is over: pending and later requests fail with SessionEnded."""
        self._fail_all(SessionEnded("the server ended the session (404); not re-initializing"))
        self.close_connections()

    # -- the GET stream ----------------------------------------------------------------

    def open_stream(self, timeout: float = 10.0) -> int | None:
        """GET the server's stream and read it on its own thread; returns once the head arrived.

        Returns the status (200 means the stream is open); a refusal is reported and the session
        goes on without it.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:140`
        "either return `Content-Type: text/event-stream`"
        """
        carrier = self._send("GET", self._headers(session=True, extra={"Accept": EVENT_STREAM}))
        ready = threading.Event()
        status: list[int] = []

        def run() -> None:
            try:
                resp = carrier.conn.getresponse()
                self._note_head("stream", "", resp)
                status.append(resp.status)
                ready.set()
                if resp.status == 200:
                    self._deliver(resp)
                    self.stream_end = "client" if carrier.closed else "server"
                else:
                    self._report(f"the server refused the GET stream: HTTP {resp.status}")
            except (OSError, http.client.HTTPException, ValueError, AttributeError) as exc:
                if not carrier.closed:
                    self._report(f"the GET stream failed: {exc}")
                self.stream_end = "client" if carrier.closed else "server"
            finally:
                ready.set()
                carrier.close()
                with self._lock:
                    self._carriers.discard(carrier)

        self._stream_thread = threading.Thread(target=run, daemon=True)
        self._stream_thread.start()
        ready.wait(timeout)
        return status[0] if status else None

    def server_request_ids(self, method: str) -> list[Any]:
        """The ids of the server's requests of one method, in the order they arrived."""
        return [i for m, i in list(self.server_requests) if m == method]

    def wait_stream_end(self, timeout: float) -> None:
        if self._stream_thread is not None:
            self._stream_thread.join(timeout)

    # -- cancelling and closing --------------------------------------------------------

    def abandon(self, pending: Pending) -> bool:
        """Stop waiting for a request and hang up the connection carrying its stream.

        Without the hang-up the server's stream for it never ends (M10).

        `spec:docs/specification/2025-11-25/basic/transports.mdx:154`
        "client **MAY** close the SSE stream"
        """
        done = super().abandon(pending)
        if done:
            with self._lock:
                carrier = self._by_request.pop(key_of(pending.id), None)
            if carrier is not None:
                carrier.hang_up()
        return done

    def terminate(self) -> int | None:
        """DELETE the session; returns the status, or None if there is no session (or no answer).

        `spec:docs/specification/2025-11-25/basic/transports.mdx:217`
        "send an HTTP DELETE to the MCP endpoint"
        """
        if self.session_id is None:
            return None
        try:
            carrier = self._send("DELETE", self._headers(session=True, extra={}))
        except OSError as exc:
            self._report(str(exc))
            return None
        try:
            resp = carrier.conn.getresponse()
            self._note_head("delete", "", resp)
            resp.read()
            return resp.status
        except (OSError, http.client.HTTPException) as exc:
            self._report(f"no answer to DELETE: {exc}")
            return None
        finally:
            carrier.close()
            with self._lock:
                self._carriers.discard(carrier)

    def close_connections(self) -> None:
        with self._lock:
            carriers = list(self._carriers)
        for carrier in carriers:
            carrier.hang_up()

    # -- the stdio parts of Wire that HTTP does not have -------------------------------

    def start(self) -> None:
        """There is no reader thread: each response has its own."""

    def join(self, timeout: float) -> None:
        """Nothing to join."""


class HttpSession(Session):
    """A session over HTTP: no process, a GET stream before `initialized`, DELETE to close."""

    def __init__(self, wire: HttpWire, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        super().__init__(wire, None, timeout=timeout)
        self.http = wire
        self._closed_with: tuple[int | None] | None = None

    @classmethod
    def connect(
        cls, url: str, *, report: Callable[[str], None] = stderr_report,
        observer: Callable[[str, Any], None] | None = None,
        on_request: Callable[[Message], None] | None = None,
        on_notification: Callable[[Message], None] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> HttpSession:
        wire = HttpWire(url, report=report, observer=observer, on_request=on_request,
                        on_notification=on_notification)
        return cls(wire, timeout=timeout)

    def initialize(self, capabilities: Message | None = None, *, stream: bool = True) -> Message:
        """`initialize`; with capabilities declared, the GET stream; then `initialized`.

        `stream=False` skips the stream (the lesson's experiment).

        The stream must be open before `notifications/initialized`: the server sends its
        `roots/list` sync and list-change notifications right after it, and with no stream open
        they are dropped (M8).

        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:47`
        "MUST** initiate this phase"
        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:147`
        "MUST** send an `initialized` notification"
        """
        params: Message = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {} if capabilities is None else capabilities,
            "clientInfo": dict(CLIENT_INFO),
        }
        result: Message = self.wire.request("initialize", params, self.timeout)
        version = result.get("protocolVersion")
        if version not in SUPPORTED_VERSIONS:
            raise UnsupportedVersion(
                f"the server chose protocol version {version!r}; this client speaks "
                f"{', '.join(SUPPORTED_VERSIONS)}"
            )
        if capabilities and stream:
            self.http.open_stream()
        self.wire.notify("notifications/initialized")
        self.ready = True
        return result

    def close(self) -> int | None:
        """DELETE the session, let the server end the GET stream, then hang up everything.

        Returns the DELETE status, or None when there was no session. Safe to call twice.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:217`
        "send an HTTP DELETE to the MCP endpoint"
        """
        with self._close_lock:
            if self._closed_with is not None:
                return self._closed_with[0]
            status = self.http.terminate()
            self.http.wait_stream_end(self.grace)  # the server ends it on DELETE (M11)
            self.wire.close_input()  # fails what is still pending
            self.http.close_connections()
            self._closed_with = (status,)
            return status
