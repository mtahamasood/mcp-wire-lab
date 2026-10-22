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
        self._buf = b""
        self.comments = 0
        self._reset()

    def _reset(self) -> None:
        self._data: list[bytes] = []
        self._id: str | None = None
        self._event: str | None = None
        self._retry: int | None = None
        self._touched = False

    def feed(self, chunk: bytes) -> list[SseEvent]:
        self._buf += chunk
        events: list[SseEvent] = []
        while True:
            end = next((i for i, b in enumerate(self._buf) if b in b"\r\n"), None)
            if end is None:
                break
            if self._buf[end : end + 1] == b"\r":
                if end + 1 == len(self._buf):
                    break  # a CR may be the first half of CRLF; wait for the next byte
                stop = end + 2 if self._buf[end + 1 : end + 2] == b"\n" else end + 1
            else:
                stop = end + 1
            line, self._buf = self._buf[:end], self._buf[stop:]
            event = self._line(line)
            if event is not None:
                events.append(event)
        return events

    def finish(self) -> SseEvent | None:
        """The end of the stream: an unterminated last line counts, a missing blank line does not."""
        line, self._buf = self._buf, b""
        if line.endswith(b"\r"):
            line = line[:-1]
        if line:
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
        self, body: bytes, pairs: list[tuple[str, str]]
    ) -> tuple[UnixHTTPConnection, http.client.HTTPResponse] | None:
        """Send the request to the socket; the connection and the response head, or None."""
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
            response = conn.getresponse()
        except (OSError, http.client.HTTPException):
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
        trace = self.server.trace
        opened = self.open_upstream(body, pairs)
        if opened is None:
            self.answer_502(number)
            return
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
            self.send_response_only(resp.status, resp.reason)
            for name, value in resp.getheaders():
                if not is_hop_by_hop(name):
                    self.send_header(name, value)
            if chunked:
                self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            if not has_body:
                return
            if kind == "text/event-stream":
                self.pump_stream(number, conn, resp, chunked)
            else:
                self.pump_body(number, resp, chunked, int(length) if length else None)
        finally:
            conn.close()

    def send_piece(self, data: bytes, chunked: bool) -> None:
        self.wfile.write(b"%x\r\n%b\r\n" % (len(data), data) if chunked else data)

    def pump_body(self, number: int, resp: http.client.HTTPResponse, chunked: bool,
                  length: int | None) -> None:
        """A body that is not an event stream: forwarded piece by piece, recorded as one frame.

        The frame is written before the piece that completes the body is forwarded.
        """
        trace = self.server.trace
        got: list[bytes] = []
        total = 0
        recorded = False

        def record() -> None:
            nonlocal recorded
            recorded = True
            if total:
                body_frame(trace, "s2c", b"".join(got), {"exchange": number})

        try:
            while True:
                piece = resp.read1(CHUNK)
                if not piece:
                    break
                got.append(piece)
                total += len(piece)
                if length is not None and total >= length and not recorded:
                    record()
                self.send_piece(piece, chunked)
        except (OSError, http.client.HTTPException):
            self.close_connection = True
        if not recorded:
            record()
        if chunked and not self.close_connection:
            self.send_piece(b"", True)

    def pump_stream(self, number: int, conn: UnixHTTPConnection, resp: http.client.HTTPResponse,
                    chunked: bool) -> None:
        """An event stream: each event recorded, then its bytes forwarded at once (D3, D4)."""
        trace = self.server.trace
        parser = SseParser()
        client_gone = threading.Event()
        done = threading.Event()

        def watch() -> None:
            """A client that hangs up closes the upstream connection (D3)."""
            sock = self.connection
            while not done.is_set():
                try:
                    ready, _, _ = select.select([sock], [], [], 0.2)
                    if not ready:
                        continue
                    gone = sock.recv(1, socket.MSG_PEEK) == b""
                except OSError:
                    gone = True
                if not gone:
                    return  # the client's next request is already queued; stop watching
                client_gone.set()
                if conn.sock is not None:
                    try:
                        conn.sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                return

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

        threading.Thread(target=watch, daemon=True).start()
        clean = False
        try:
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
                    client_gone.set()
                    break
            tail = parser.finish()
            if tail is not None:
                record_event(tail)
        finally:
            done.set()
        by = "client" if client_gone.is_set() else "server"
        trace.event("http-end", http={"exchange": number, "by": by, "comments": parser.comments})
        if by == "client" or not clean:
            self.close_connection = True
        elif chunked:
            try:
                self.send_piece(b"", True)
            except OSError:
                self.close_connection = True


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
        if child.poll() is not None:
            return give_up(f"the server exited before it listened (code {exit_code(child.poll())})")
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
