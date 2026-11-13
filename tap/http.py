"""The wire tap's HTTP mode (phase 7 D1-D5): a recording reverse proxy for Streamable HTTP.

Usage:
  python3 -m tap --trace <file> --http <listen-port> -- <server command...>

Starts the server command as a child with `PORT=<private dir>/server.sock`, so the pinned
server listens on that Unix socket and on no network interface. When the socket accepts, the
tap listens on 127.0.0.1:<listen-port> and relays every HTTP exchange to the socket: the request
heads, bodies and response heads, bodies and event-stream events are written to the trace as
`tap` records and `c2s`/`s2c` frames (D1), and every byte is forwarded as soon as it is read (D3).
"""

from __future__ import annotations

import http.client
import http.server
import os
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any

from tap.__main__ import (
    FORWARDED_SIGNALS,
    Trace,
    exit_code,
    frame_fields,
    read_some,
    say,
    write_all,
)

HOST = "127.0.0.1"
UPSTREAM_HOST = "localhost"
SOCKET_NAME = "server.sock"
MAX_SOCKET_PATH = 100
READY_TIMEOUT = 15.0
READY_POLL = 0.05
DRAIN_SECONDS = 2.0
CHUNK = 65536
WATCH_PERIOD = 0.2  # seconds between checks that a finished exchange's watch can stop
HANG_UP = getattr(select, "POLLRDHUP", 0)  # the peer's hang-up, even behind unread bytes
LINE_END = re.compile(rb"[\r\n]")
HOP_BY_HOP = frozenset(
    {"connection", "keep-alive", "te", "trailer", "transfer-encoding", "upgrade"}
)
RECORDED_HEADERS = frozenset({"accept", "content-type", "last-event-id"})
NO_BODY_STATUS = frozenset({204, 304})


def is_hop_by_hop(name: str) -> bool:
    """A header the tap does not forward (D3): hop-by-hop, or `Proxy-*`."""
    lowered = name.lower()
    return lowered in HOP_BY_HOP or lowered.startswith("proxy-")


def recorded_headers(pairs: list[tuple[str, str]]) -> dict[str, str]:
    """The headers that matter (D5): lowercased names, a repeated header joined with `, `."""
    out: dict[str, str] = {}
    for name, value in pairs:
        lowered = name.lower()
        if lowered in RECORDED_HEADERS or lowered.startswith("mcp-"):
            out[lowered] = f"{out[lowered]}, {value}" if lowered in out else value
    return out


# -- the SSE reader (D4) ----------------------------------------------------------------


@dataclass
class SseEvent:
    """One dispatched event; `data` is the data lines joined with a newline (maybe empty)."""

    data: bytes
    id: str | None = None
    event: str | None = None
    retry: int | None = None
    partial: bool = False


class SseParser:
    """The event-stream interpretation of the SSE standard, over bytes, chunk by chunk (D4).

    `feed` returns the events a chunk completed; `finish` returns the event the stream's end cut
    off (with `partial` set), if it has any field. `comments` counts the comment lines seen.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self._scanned = 0  # the bytes of `_buf` known to hold no line end
        self.comments = 0
        self._reset()

    def _reset(self) -> None:
        self._data: list[bytes] = []
        self._id: str | None = None
        self._event: str | None = None
        self._retry: int | None = None
        self._touched = False

    def feed(self, chunk: bytes) -> list[SseEvent]:
        """Parse a chunk in time linear in its size (P8-R7-1): a scan resumes where the last
        one stopped, a line end is found at C speed, and the buffer is trimmed once per call."""
        buf = self._buf
        buf += chunk
        events: list[SseEvent] = []
        pos = 0  # the start of the first unconsumed line
        scan = self._scanned
        while True:
            found = LINE_END.search(buf, scan)
            if found is None:
                scan = len(buf)
                break
            end = found.start()
            if buf[end] == 13:  # CR
                if end + 1 == len(buf):
                    scan = end  # a CR may be the first half of CRLF; wait for the next byte
                    break
                stop = end + 2 if buf[end + 1] == 10 else end + 1
            else:
                stop = end + 1
            line = bytes(buf[pos:end])
            pos = scan = stop
            event = self._line(line)
            if event is not None:
                events.append(event)
        del buf[:pos]
        self._scanned = scan - pos
        return events

    def finish(self) -> SseEvent | None:
        """The stream's end: an unterminated last line counts; a missing blank line does not.

        A last CR, which `feed` held back as a possible half of CRLF, ends its line: no LF can
        follow it now, so `data: x` CR CR dispatches its event whole (P8-R7-9).
        """
        line = bytes(self._buf)
        self._buf.clear()
        self._scanned = 0
        if line.endswith(b"\r"):
            event = self._line(line[:-1])
            if event is not None:
                return event
        elif line:
            self._line(line)
        if not self._touched:
            return None
        event = self._event_now()
        event.partial = True
        self._reset()
        return event

    def _event_now(self) -> SseEvent:
        return SseEvent(b"\n".join(self._data), self._id, self._event, self._retry)

    def _line(self, line: bytes) -> SseEvent | None:
        if not line:
            if not self._touched:
                return None
            event = self._event_now()
            self._reset()
            return event
        if line.startswith(b":"):
            self.comments += 1
            return None
        name, colon, value = line.partition(b":")
        if colon and value.startswith(b" "):
            value = value[1:]
        field = name.decode("latin-1")
        if field == "data":
            self._data.append(value)
        elif field == "id":
            self._id = value.decode("utf-8", "replace")
        elif field == "event":
            self._event = value.decode("utf-8", "replace")
        elif field == "retry":
            if not (value.isascii() and value.isdigit()):
                return None
            self._retry = int(value)
        else:
            return None
        self._touched = True
        return None


# -- upstream -----------------------------------------------------------------------------


class UnixHTTPConnection(http.client.HTTPConnection):
    """An HTTP connection whose transport is a Unix-domain socket (D2)."""

    def __init__(self, path: str) -> None:
        super().__init__(UPSTREAM_HOST)
        self.socket_path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self.socket_path)
        except OSError:
            sock.close()
            raise
        self.sock = sock


def socket_accepts(path: str) -> bool:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
        return True
    except OSError:
        return False
    finally:
        sock.close()


class ClientWatch:
    """Passes a client's hang-up on to the server for one exchange (D3; P8-R7-2, P8-R7-13).

    It runs from the moment the request has been sent upstream until the exchange ends, for
    every kind of response: when the client hangs up it shuts the upstream socket down, which
    wakes a `getresponse()` or `read1()` waiting on it, and the server sees the disconnect as
    it would without the tap. Where the platform has `POLLRDHUP` (Linux) it waits for the
    client's hang-up only, so a request the client has queued behind the open exchange (HTTP/1.1
    pipelining) does not end the watch; elsewhere the first queued byte ends it.
    """

    def __init__(self, client: socket.socket) -> None:
        self.client = client
        self.gone = threading.Event()
        self._upstream: socket.socket | None = None
        self._lock = threading.Lock()
        self._done = False

    def start(self, upstream: socket.socket) -> None:
        self._upstream = upstream
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self) -> None:
        """The exchange is over: the watch touches the upstream no more."""
        with self._lock:
            self._done = True

    def client_left(self) -> None:
        """The client has gone (seen by the watch, or by a failed write): close the upstream."""
        self.gone.set()
        with self._lock:
            if self._done or self._upstream is None:
                return
            try:
                self._upstream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _run(self) -> None:
        if HANG_UP:
            poller = select.poll()
            poller.register(self.client, HANG_UP)
            while not self._done:
                try:
                    if not poller.poll(WATCH_PERIOD * 1000):
                        continue
                except OSError:
                    pass
                break
        else:
            while not self._done:
                try:
                    ready, _, _ = select.select([self.client], [], [], WATCH_PERIOD)
                    if not ready:
                        continue
                    if self.client.recv(1, socket.MSG_PEEK) != b"":
                        return  # the client's next request is queued; no hang-up can be seen
                except (OSError, ValueError):
                    pass
                break
        if not self._done:
            self.client_left()


# -- the proxy ------------------------------------------------------------------------------


def body_frame(
    trace: Trace, direction: str, data: bytes, http: dict[str, Any], partial: bool = False
) -> None:
    """One `c2s` or `s2c` frame for a body or an event's data, with its `http` object (D1)."""
    try:
        fields = frame_fields(data)
    except Exception as exc:  # describing a body must never stop the proxy (phase 1 D2)
        fields = {"bytes": len(data), "json": None, "parse_error": f"tap could not describe: {exc}"}
    if partial:
        fields["partial"] = True
    trace.record(direction, {**fields, "http": http})


class Proxy(http.server.ThreadingHTTPServer):
    """The listening side: 127.0.0.1 only, one thread per connection."""

    daemon_threads = True
    allow_reuse_address = True
    # socketserver's default backlog of 5 reset bursts of 40 or more connections that the
    # pinned server (backlog 511) would accept (D3; P8-R7-12).
    request_queue_size = 128

    def __init__(self, port: int, socket_path: str, trace: Trace) -> None:
        super().__init__((HOST, port), ProxyHandler)
        self.socket_path = socket_path
        self.trace = trace
        self._numbers = threading.Lock()
        self._next_exchange = 0
        self._active = 0
        self._idle = threading.Condition()

    def begin(self, make: Callable[[int], None]) -> int:
        """Number an exchange and run `make(number)` (its first record) in one step."""
        with self._numbers:
            number = self._next_exchange
            self._next_exchange += 1
            make(number)
        with self._idle:
            self._active += 1
        return number

    def end(self) -> None:
        with self._idle:
            self._active -= 1
            self._idle.notify_all()

    def drain(self, seconds: float) -> None:
        """Wait up to `seconds` for open exchanges to end."""
        deadline = time.monotonic() + seconds
        with self._idle:
            while self._active > 0 and (left := deadline - time.monotonic()) > 0:
                self._idle.wait(left)


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: Proxy

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def setup(self) -> None:
        super().setup()
        try:
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

    def do_GET(self) -> None:
        self.proxy()

    do_POST = do_DELETE = do_PUT = do_PATCH = do_OPTIONS = do_HEAD = do_GET

    # -- one exchange (D1, D3) ----------------------------------------------------------

    def read_body(self) -> bytes:
        """The request body, whole: by Content-Length, or de-chunked."""
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            parts: list[bytes] = []
            while True:
                size = int(self.rfile.readline(1024).split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    while self.rfile.readline(65536) not in (b"\r\n", b"\n", b""):
                        pass  # trailers
                    return b"".join(parts)
                parts.append(self.rfile.read(size))
                self.rfile.readline(8)
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def proxy(self) -> None:
        trace = self.server.trace
        try:
            body = self.read_body()
        except (ValueError, OSError):
            self.close_connection = True
            return
        pairs = list(self.headers.items())

        def first_record(number: int) -> None:
            trace.event(
                "http-request",
                http={
                    "exchange": number, "method": self.command, "path": self.path,
                    "headers": recorded_headers(pairs), "body_bytes": len(body),
                },
            )
            if body:
                body_frame(trace, "c2s", body, {"exchange": number})

        number = self.server.begin(first_record)
        try:
            self.exchange(number, body, pairs)
        except Exception as exc:  # one exchange never takes the proxy down
            say(f"tap: exchange {number} failed: {type(exc).__name__}: {exc}")
            self.close_connection = True
        finally:
            self.server.end()

    def open_upstream(
        self, body: bytes, pairs: list[tuple[str, str]], watch: ClientWatch
    ) -> tuple[UnixHTTPConnection, http.client.HTTPResponse] | None:
        """Send the request to the socket, start the watch, and wait for the response head.

        The connection and the head, or None if the upstream failed or the client left first.
        """
        conn = UnixHTTPConnection(self.server.socket_path)
        try:
            conn.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", UPSTREAM_HOST)
            for name, value in pairs:
                if name.lower() in ("host", "content-length", "expect") or is_hop_by_hop(name):
                    continue
                conn.putheader(name, value)
            if body or self.command in ("POST", "PUT", "PATCH"):
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body)
            if conn.sock is not None:
                watch.start(conn.sock)
            response = conn.getresponse()
        except (OSError, http.client.HTTPException):
            watch.stop()
            conn.close()
            return None
        return conn, response

    def answer_502(self, number: int) -> None:
        self.server.trace.event(
            "http-response", http={"exchange": number, "status": 502, "headers": {}, "by": "tap"}
        )
        self.send_response_only(502, "Bad Gateway")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def exchange(self, number: int, body: bytes, pairs: list[tuple[str, str]]) -> None:
        """Relay one exchange. A client that leaves it, at any point, is passed on to the server
        (the watch) and ends it with `http-end` by `client` (D1, D3; P8-R7-2)."""
        watch = ClientWatch(self.connection)
        try:
            ended = self.relay(number, body, pairs, watch)
        finally:
            watch.stop()
        if watch.gone.is_set():
            self.close_connection = True
            if not ended:
                self.server.trace.event(
                    "http-end", http={"exchange": number, "by": "client", "comments": 0})

    def relay(self, number: int, body: bytes, pairs: list[tuple[str, str]],
              watch: ClientWatch) -> bool:
        """Send the request, relay the response; True if an event stream's `http-end` is written."""
        trace = self.server.trace
        opened = self.open_upstream(body, pairs, watch)
        if opened is None:
            if not watch.gone.is_set():
                self.answer_502(number)
            return False
        conn, resp = opened
        try:
            kind = (resp.getheader("Content-Type") or "").split(";")[0].strip().lower()
            trace.event(
                "http-response",
                http={"exchange": number, "status": resp.status,
                      "headers": recorded_headers(resp.getheaders())},
            )
            has_body = self.command != "HEAD" and resp.status not in NO_BODY_STATUS
            length = resp.getheader("Content-Length")
            chunked = has_body and length is None
            try:
                self.send_response_only(resp.status, resp.reason)
                for name, value in resp.getheaders():
                    if not is_hop_by_hop(name):
                        self.send_header(name, value)
                if chunked:
                    self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
            except OSError:
                watch.client_left()
                return False
            if not has_body:
                return False
            if kind == "text/event-stream":
                self.pump_stream(number, resp, chunked, watch)
                return True
            self.pump_body(number, resp, chunked, int(length) if length else None, watch)
            return False
        finally:
            watch.stop()
            conn.close()

    def send_piece(self, data: bytes, chunked: bool) -> None:
        self.wfile.write(b"%x\r\n%b\r\n" % (len(data), data) if chunked else data)

    def pump_body(self, number: int, resp: http.client.HTTPResponse, chunked: bool,
                  length: int | None, watch: ClientWatch) -> None:
        """A body that is not an event stream: forwarded piece by piece, recorded as one frame.

        The frame is written before the piece that completes the body is forwarded. A body cut
        off (the upstream failed, or the client left) is recorded as far as it was read, with
        `partial` set.
        """
        trace = self.server.trace
        got: list[bytes] = []
        total = 0
        recorded = False
        ended = False  # the upstream ended the body (read1 gave b""), not an error or the client

        def whole() -> bool:
            return total >= length if length is not None else ended

        def record() -> None:
            nonlocal recorded
            recorded = True
            if total:
                body_frame(trace, "s2c", b"".join(got), {"exchange": number},
                           partial=not whole())

        try:
            while True:
                piece = resp.read1(CHUNK)
                if not piece:
                    ended = True
                    break
                got.append(piece)
                total += len(piece)
                if length is not None and total >= length and not recorded:
                    record()
                try:
                    self.send_piece(piece, chunked)
                except OSError:
                    watch.client_left()
                    break
        except (OSError, http.client.HTTPException):
            pass
        if not recorded:
            record()
        if not (ended and whole()):
            self.close_connection = True
        elif chunked:
            try:
                self.send_piece(b"", True)
            except OSError:
                watch.client_left()

    def pump_stream(self, number: int, resp: http.client.HTTPResponse, chunked: bool,
                    watch: ClientWatch) -> None:
        """An event stream: each event recorded, then its bytes forwarded at once (D3, D4)."""
        trace = self.server.trace
        parser = SseParser()

        def record_event(event: SseEvent) -> None:
            if event.data:
                http: dict[str, Any] = {"exchange": number}
                sse = {k: v for k, v in (("id", event.id), ("event", event.event)) if v is not None}
                if sse:
                    http["sse"] = sse
                body_frame(trace, "s2c", event.data, http, partial=event.partial)
            elif not event.partial:
                http = {"exchange": number}
                if event.id is not None:
                    http["id"] = event.id
                if event.retry is not None:
                    http["retry"] = event.retry
                trace.event("sse-event", http=http)

        clean = False
        while True:
            try:
                piece = resp.read1(CHUNK)
            except (OSError, http.client.HTTPException):
                break
            if not piece:
                clean = True
                break
            for event in parser.feed(piece):
                record_event(event)
            try:
                self.send_piece(piece, chunked)
            except OSError:
                watch.client_left()
                break
        tail = parser.finish()
        if tail is not None:
            record_event(tail)
        by = "client" if watch.gone.is_set() else "server"
        trace.event("http-end", http={"exchange": number, "by": by, "comments": parser.comments})
        if by == "client" or not clean:
            self.close_connection = True
        elif chunked:
            try:
                self.send_piece(b"", True)
            except OSError:
                watch.client_left()


# -- the mode's lifecycle (D2) ---------------------------------------------------------------


def relay_log(src: int, stream: str, trace: Trace) -> None:
    """Copy the child's stdout or stderr to the tap's stderr; record each line as a stderr frame."""
    pending = b""
    forwarding = True

    def record(frame: bytes, partial: bool = False) -> None:
        fields = frame_fields(frame)
        if partial:
            fields["partial"] = True
        if stream == "stdout":
            fields["stream"] = "stdout"
        trace.record("stderr", fields)

    while True:
        try:
            chunk = read_some(src)
        except OSError:
            break
        if not chunk:
            break
        pending += chunk
        while (end := pending.find(b"\n")) >= 0:
            frame, pending = pending[: end + 1], pending[end + 1 :]
            record(frame)
        if forwarding:
            try:
                write_all(2, chunk)
            except OSError:
                forwarding = False
    if pending:
        record(pending, partial=True)


def run_http(trace_path: Path, port: int, command: list[str]) -> int:
    """HTTP mode: start the server on a private socket and proxy `127.0.0.1:<port>` to it."""
    try:
        directory = tempfile.mkdtemp()
    except OSError as exc:
        say(f"tap: cannot make a private directory: {exc}")
        return 1
    socket_path = os.path.join(directory, SOCKET_NAME)
    if len(os.fsencode(socket_path)) > MAX_SOCKET_PATH:
        say(f"tap: the socket path is longer than {MAX_SOCKET_PATH} bytes: {socket_path}")
        shutil.rmtree(directory, ignore_errors=True)
        return 1
    try:
        trace = Trace(trace_path)
    except OSError as exc:
        say(f"tap: cannot write trace: {exc}")
        shutil.rmtree(directory, ignore_errors=True)
        return 2

    child: subprocess.Popen[bytes] | None = None
    early: list[int] = []

    def forward(signum: int, _frame: FrameType | None) -> None:
        if child is None:
            early.append(signum)
        else:
            child.send_signal(signum)

    for sig in FORWARDED_SIGNALS:
        signal.signal(sig, forward)

    trace.event("spawn", argv=command)
    try:
        child = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            env={**os.environ, "PORT": socket_path},
            process_group=0,
        )
    except OSError as exc:
        say(f"tap: cannot start {command[0]}: {exc}")
        trace.finish(code=127, error=str(exc))
        shutil.rmtree(directory, ignore_errors=True)
        return 127
    for signum in early:
        child.send_signal(signum)

    assert child.stdout and child.stderr
    relays = [
        threading.Thread(target=relay_log, args=(child.stdout.fileno(), "stdout", trace)),
        threading.Thread(target=relay_log, args=(child.stderr.fileno(), "stderr", trace)),
    ]
    for thread in relays:
        thread.start()

    def finish(returncode: int) -> int:
        for thread in relays:
            thread.join(5)
        code = exit_code(returncode)
        if returncode < 0:
            trace.finish(code=code, signal=-returncode)
        else:
            trace.finish(code=code)
        shutil.rmtree(directory, ignore_errors=True)
        return code

    def give_up(message: str) -> int:
        """Ready failed: say why, stop a child still running, exit with its code (1 if 0)."""
        say(f"tap: {message}")
        if child.poll() is None:
            child.send_signal(signal.SIGINT)
        try:
            returncode = child.wait(5)
        except subprocess.TimeoutExpired:
            child.kill()
            returncode = child.wait()
        return finish(returncode) or 1

    deadline = time.monotonic() + READY_TIMEOUT
    while not socket_accepts(socket_path):
        gone = child.poll()
        if gone is not None:
            return give_up(f"the server exited before it listened (code {exit_code(gone)})")
        if time.monotonic() > deadline:
            return give_up(f"the server did not listen on {socket_path} within {READY_TIMEOUT:g} s")
        time.sleep(READY_POLL)
    try:
        proxy = Proxy(port, socket_path, trace)
    except OSError as exc:
        return give_up(f"cannot listen on {HOST}:{port}: {exc}")
    trace.event("listen", listen=f"{HOST}:{port}", upstream=f"unix:{socket_path}")
    say(f"tap: listening on http://{HOST}:{port}")
    threading.Thread(target=proxy.serve_forever, daemon=True).start()

    returncode = child.wait()
    proxy.shutdown()
    proxy.drain(DRAIN_SECONDS)
    proxy.server_close()
    return finish(returncode)


if __name__ == "__main__":
    print("run it as: python3 -m tap --trace <file> --http <port> -- <server command...>",
          file=sys.stderr)
    sys.exit(2)
