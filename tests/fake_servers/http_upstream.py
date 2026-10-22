"""A scripted Streamable-HTTP-shaped upstream for the tap's HTTP tests (phase 7, part A).

Started by the tap as its child: it listens on the Unix socket that `PORT` names (the way the
pinned server does under the tap) and answers by path:

  /echo      200 JSON describing the request it got (method, path, query, headers, body_b64)
  /json      200 `application/json`, the body {"jsonrpc":"2.0","id":1,"result":{}}
  /accepted  202, empty body
  /hop       200 JSON with hop-by-hop headers (Keep-Alive, Proxy-Authenticate) and X-Fake
  /sse       200 event stream: a priming event, one message event, then the end
  /raw       200 event stream whose body is the bytes of ?hex=<hex>, sent whole, then the end
  /split     like /raw, but one byte per write with a short pause (chunk-boundary robustness)
  /slow      an event, a 1 s pause, a second event, the end
  /roundtrip an event (a server request), then waits for a POST to /reply, then the final event
  /reply     202, and releases /roundtrip
  /hold      an event, then silence until a DELETE of any path, then the end
  /status    the status in ?code=, empty body
  /log       200 JSON; writes one line to stdout and one to stderr first
  /pid       200 JSON: this process's number
  /env       200 JSON: the PORT variable this process was started with
  /peek      200 JSON: the lines of the trace file named by TRACE_PEEK, as they are right now
  /unlisten  200, then removes the socket file, so the next connection is refused

With a second argument (seconds) it waits that long before it listens.

Every request is also appended to LOG (the first argument), one JSON object per line, so a test
can check what reached the upstream and when.
"""

from __future__ import annotations

import base64
import http.server
import json
import os
import resource
import select
import socket
import socketserver
import sys
import threading
import time
import urllib.parse
from typing import Any

LOG = sys.argv[1] if len(sys.argv) > 1 else os.devnull
RELEASE = threading.Event()  # set by POST /reply
DELETED = threading.Event()  # set by DELETE
LOG_LOCK = threading.Lock()
EVENT = b'event: message\nid: e1\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n'


def note(entry: dict[str, Any]) -> None:
    with LOG_LOCK, open(LOG, "a", encoding="utf-8") as log:
        log.write(json.dumps(entry) + "\n")


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def address_string(self) -> str:
        return "unix"

    # -- helpers ----------------------------------------------------------------------

    def body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def stream_head(self, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

    def piece(self, data: bytes) -> None:
        self.wfile.write(b"%x\r\n%b\r\n" % (len(data), data))
        self.wfile.flush()

    def end_stream(self) -> None:
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def reply(self, status: int, body: bytes = b"", ctype: str = "application/json",
              extra: tuple[tuple[str, str], ...] = ()) -> None:
        self.send_response(status)
        if body:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    # -- one request ------------------------------------------------------------------

    def handle_any(self) -> None:
        parts = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parts.query)
        data = self.body()
        record = {
            "method": self.command, "path": self.path, "headers": self.headers.items(),
            "body_b64": base64.b64encode(data).decode(), "t": time.monotonic(),
        }
        note(record)
        if self.command == "DELETE":
            DELETED.set()
            self.reply(200)
            return
        route = parts.path
        if route == "/echo":
            self.reply(200, json.dumps(record).encode())
        elif route == "/json":
            self.reply(200, b'{"jsonrpc":"2.0","id":1,"result":{}}')
        elif route == "/accepted":
            self.reply(202)
        elif route == "/hop":
            self.reply(200, b"{}", extra=(
                ("Keep-Alive", "timeout=5"), ("Proxy-Authenticate", "Basic"),
                ("X-Fake", "kept"), ("Mcp-Session-Id", "fake-session"),
            ))
        elif route == "/sse":
            self.stream_head()
            self.piece(b"id: p1\ndata: \n\n")
            self.piece(EVENT)
            self.end_stream()
        elif route in ("/raw", "/split"):
            payload = bytes.fromhex(query.get("hex", [""])[0])
            self.stream_head()
            if route == "/raw":
                self.piece(payload)
            else:
                for i in range(len(payload)):
                    self.piece(payload[i : i + 1])
                    time.sleep(0.005)
            self.end_stream()
        elif route == "/slow":
            self.stream_head()
            self.piece(EVENT)
            time.sleep(1.0)
            self.piece(EVENT.replace(b"e1", b"e2").replace(b"{}", b'{"n":2}'))
            self.end_stream()
        elif route == "/roundtrip":
            self.stream_head()
            self.piece(b'id: s1\ndata: {"jsonrpc":"2.0","id":0,"method":"ping"}\n\n')
            RELEASE.wait(10)
            self.piece(b'id: s2\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n')
            self.end_stream()
        elif route == "/reply":
            self.reply(202)
            RELEASE.set()
        elif route == "/hold":
            self.stream_head()
            self.piece(b": hello\n\n" + EVENT)
            deadline = time.monotonic() + 10
            while not DELETED.is_set() and time.monotonic() < deadline:
                ready, _, _ = select.select([self.connection], [], [], 0.05)
                if ready and self.connection.recv(1, socket.MSG_PEEK) == b"":
                    note({"event": "disconnect", "path": self.path})
                    self.close_connection = True
                    return
            self.end_stream()
        elif route == "/status":
            self.reply(int(query.get("code", ["200"])[0]))
        elif route == "/log":
            print("fake stdout line", flush=True)
            print("fake stderr line", file=sys.stderr, flush=True)
            self.reply(200, b"{}")
        elif route == "/env":
            self.reply(200, json.dumps({"PORT": os.environ.get("PORT")}).encode())
        elif route == "/peek":
            with open(os.environ["TRACE_PEEK"], encoding="utf-8") as trace:
                self.reply(200, json.dumps({"lines": trace.read().splitlines()}).encode())
        elif route == "/unlisten":
            self.reply(200, b"{}")
            os.unlink(os.environ["PORT"])
        elif route == "/pid":
            self.reply(200, json.dumps({"pid": os.getpid()}).encode())
        else:
            self.reply(404)

    do_GET = do_POST = do_DELETE = do_PUT = do_HEAD = handle_any


def main() -> int:
    path = os.environ["PORT"]
    _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)  # a test may limit the tap's file size
    resource.setrlimit(resource.RLIMIT_FSIZE, (hard, hard))
    if len(sys.argv) > 2:
        time.sleep(float(sys.argv[2]))
    server = Server(path, Handler)
    print(f"fake upstream listening on {path}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
