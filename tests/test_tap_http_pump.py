"""The tap's HTTP forwarder, called in-process (phase 8 D9, phase 7 C4, C5, C120).

`ProxyHandler.relay` runs against a scripted upstream response and a recording `wfile`, with no
socket to a client and no subprocess. That makes the order of two steps testable that a real
connection only shows by racing: a record written before the bytes it describes are forwarded,
and a client that hangs up at the very moment it receives the last bytes of an answer.
"""

from __future__ import annotations

import socket
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from tap.http import ClientWatch, Proxy, ProxyHandler

Hook = Callable[[bytes], None]


class FakeTrace:
    """Records what the tap writes, in order: `("event", name, fields)` or `("record", dir, f)`."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str, dict[str, Any]]] = []

    def event(self, name: str, **fields: Any) -> None:
        self.items.append(("event", name, fields))

    def record(self, direction: str, fields: dict[str, Any]) -> None:
        self.items.append(("record", direction, fields))

    def frames(self) -> list[dict[str, Any]]:
        return [f for kind, name, f in self.items if kind == "record" and name == "s2c"]

    def events(self, name: str) -> list[dict[str, Any]]:
        return [f for kind, n, f in self.items if kind == "event" and n == name]


class FakeResponse:
    """An upstream response: `read1` gives the scripted pieces, then b"" (the end).

    A piece that is an exception is raised instead (the upstream failed).
    """

    def __init__(self, pieces: list[bytes | Exception], status: int = 200,
                 headers: list[tuple[str, str]] | None = None) -> None:
        self.pieces = list(pieces)
        self.status = status
        self.reason = "OK"
        self.headers = headers or []

    def getheader(self, name: str) -> str | None:
        for key, value in self.headers:
            if key.lower() == name.lower():
                return value
        return None

    def getheaders(self) -> list[tuple[str, str]]:
        return list(self.headers)

    def read1(self, size: int) -> bytes:
        if not self.pieces:
            return b""
        piece = self.pieces.pop(0)
        if isinstance(piece, Exception):
            raise piece
        return piece


class FakeUpstream:
    def close(self) -> None:
        pass


class Wfile:
    """What the client is sent; `on_write` runs before each write is taken."""

    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.on_write: Hook | None = None

    def write(self, data: bytes) -> int:
        if self.on_write is not None:
            self.on_write(data)
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        pass


class Exchange:
    """One exchange through `ProxyHandler.exchange`, the upstream and the client both faked."""

    def __init__(self, case: unittest.TestCase, response: FakeResponse,
                 command: str = "GET") -> None:
        client, peer = socket.socketpair()
        case.addCleanup(client.close)
        case.addCleanup(peer.close)
        self.trace = FakeTrace()
        self.wfile = Wfile()
        self.watch: ClientWatch | None = None
        handler = ProxyHandler.__new__(ProxyHandler)
        handler.server = SimpleNamespace(trace=self.trace)  # type: ignore[assignment]
        handler.wfile = self.wfile  # type: ignore[assignment]
        handler.connection = client
        handler.command = command
        handler.path = "/mcp"
        handler.request_version = "HTTP/1.1"
        handler.close_connection = False
        self.handler = handler
        handler.open_upstream = self._open  # type: ignore[method-assign,assignment]
        self.response = response

    def _open(self, body: bytes, pairs: list[tuple[str, str]],
              watch: ClientWatch) -> tuple[FakeUpstream, FakeResponse]:
        self.watch = watch
        return FakeUpstream(), self.response

    def run(self) -> None:
        self.handler.exchange(0, b"", [])

    @property
    def sent(self) -> bytes:
        return b"".join(self.wfile.writes)

    def client_leaves_when(self, marker: bytes, *, write_fails: bool = False) -> None:
        """The client hangs up as it is sent the write that holds `marker` (the write then
        fails, if `write_fails`: the bytes did not reach it)."""
        def hook(data: bytes) -> None:
            if marker in data:
                assert self.watch is not None
                self.watch.client_left()
                if write_fails:
                    raise BrokenPipeError("the client is gone")

        self.wfile.on_write = hook


    def write_fails_when(self, marker: bytes) -> None:
        """The write that holds `marker` fails as a write to a client that has gone does."""
        def hook(data: bytes) -> None:
            if marker in data:
                raise BrokenPipeError("the client is gone")

        self.wfile.on_write = hook


STREAM = [("Content-Type", "text/event-stream")]
EVENT = b'data: {"jsonrpc":"2.0","id":1,"result":{}}\n\n'


class RecordBeforeForwardTest(unittest.TestCase):
    """D3: what is recorded is on the trace before the client is sent the bytes it describes."""

    def test_an_event_is_recorded_before_its_bytes_are_forwarded(self) -> None:
        ex = Exchange(self, FakeResponse([EVENT, EVENT.replace(b'"id":1', b'"id":2')],
                                         headers=STREAM))
        seen: list[int] = []
        ex.wfile.on_write = lambda data: (
            seen.append(len(ex.trace.frames())) if b"jsonrpc" in data else None)
        ex.run()
        self.assertEqual(seen, [1, 2])  # the frame of each event exists when its bytes go out

    def test_a_body_is_recorded_before_the_piece_that_completes_it(self) -> None:
        ex = Exchange(self, FakeResponse([b"abc", b"def"], headers=[("Content-Length", "6")]))
        seen: list[int] = []

        def hook(data: bytes) -> None:
            if data == b"def":
                seen.append(len(ex.trace.frames()))

        ex.wfile.on_write = hook
        ex.run()
        self.assertEqual(seen, [1])
        (frame,) = ex.trace.frames()
        self.assertEqual(frame["raw"], "abcdef")
        self.assertNotIn("partial", frame)


class ContentTypeTest(unittest.TestCase):
    def test_an_event_stream_is_known_by_its_type_whatever_the_case_or_parameters(self) -> None:
        for value in ("Text/Event-Stream", "text/event-stream; charset=utf-8",
                      "TEXT/EVENT-STREAM ;charset=utf-8"):
            with self.subTest(value=value):
                ex = Exchange(self, FakeResponse([EVENT], headers=[("Content-Type", value)]))
                ex.run()
                self.assertEqual(len(ex.trace.frames()), 1)
                self.assertEqual(len(ex.trace.events("http-end")), 1)  # only a stream has one

    def test_another_type_is_a_body_not_a_stream(self) -> None:
        ex = Exchange(self, FakeResponse([EVENT], headers=[("Content-Type", "text/plain")]))
        ex.run()
        self.assertEqual(ex.trace.events("http-end"), [])


class EndOfAnswerTest(unittest.TestCase):
    """C5: how an answer ends decides what the client is told and whether the connection stays."""

    def test_a_body_with_no_length_ends_with_the_last_chunk(self) -> None:
        ex = Exchange(self, FakeResponse([b"abc"]))
        ex.run()
        self.assertTrue(ex.sent.endswith(b"3\r\nabc\r\n0\r\n\r\n"), ex.sent)
        self.assertFalse(ex.handler.close_connection)

    def test_a_body_the_upstream_cut_off_is_not_ended_as_whole(self) -> None:
        ex = Exchange(self, FakeResponse([b"abc", OSError("reset")]))
        ex.run()
        self.assertFalse(ex.sent.endswith(b"0\r\n\r\n"), ex.sent)
        self.assertTrue(ex.handler.close_connection)
        self.assertTrue(ex.trace.frames()[0]["partial"])

    def test_a_stream_the_upstream_cut_off_is_not_ended_as_whole(self) -> None:
        ex = Exchange(self, FakeResponse([EVENT, OSError("reset")], headers=STREAM))
        ex.run()
        self.assertFalse(ex.sent.endswith(b"0\r\n\r\n"), ex.sent)
        self.assertTrue(ex.handler.close_connection)
        (end,) = ex.trace.events("http-end")
        self.assertEqual(end["http"]["by"], "server")

    def test_a_stream_the_upstream_ended_ends_with_the_last_chunk(self) -> None:
        ex = Exchange(self, FakeResponse([EVENT], headers=STREAM))
        ex.run()
        self.assertTrue(ex.sent.endswith(b"0\r\n\r\n"), ex.sent)
        self.assertFalse(ex.handler.close_connection)


class LeavingWithTheLastBytesTest(unittest.TestCase):
    """C120: a client that hangs up as it is sent the end of a whole answer has hung up on
    nothing. The hang-up is placed here, deterministically, between the last write and the
    moment the tap notices the upstream has ended; a real client can only race for it."""

    def test_a_stream_the_client_leaves_as_it_ends_is_ended_by_the_server(self) -> None:
        ex = Exchange(self, FakeResponse([EVENT], headers=STREAM))
        ex.client_leaves_when(b"jsonrpc")
        ex.run()
        (end,) = ex.trace.events("http-end")
        self.assertEqual(end["http"]["by"], "server")

    def test_a_body_the_client_leaves_as_it_ends_has_no_end_by_client(self) -> None:
        ex = Exchange(self, FakeResponse([b"{}"], headers=[("Content-Length", "2")]))
        ex.client_leaves_when(b"{}")
        ex.run()
        self.assertEqual(ex.trace.events("http-end"), [])
        self.assertNotIn("partial", ex.trace.frames()[0])

    def test_an_answer_with_no_body_the_client_leaves_as_it_ends_has_no_end_by_client(self) -> None:
        ex = Exchange(self, FakeResponse([], status=304))
        ex.client_leaves_when(b"304")
        ex.run()
        self.assertEqual(ex.trace.events("http-end"), [])

    def test_a_client_that_leaves_before_the_end_is_ended_by_the_client(self) -> None:
        ex = Exchange(self, FakeResponse([b"ab", b"cd"], headers=[("Content-Length", "4")]))
        ex.client_leaves_when(b"ab", write_fails=True)
        ex.run()
        (end,) = ex.trace.events("http-end")
        self.assertEqual(end["http"]["by"], "client")


class NoBodyTest(unittest.TestCase):
    """C4: a HEAD answer and a 204 or 304 have no body, whatever their headers say."""

    def test_head_and_304_are_not_read_for_a_body(self) -> None:
        for command, status in (("HEAD", 200), ("GET", 304), ("GET", 204)):
            with self.subTest(command=command, status=status):
                ex = Exchange(self, FakeResponse([], status=status,
                                                 headers=[("Content-Length", "5")]), command)
                ex.run()
                self.assertFalse(ex.handler.close_connection)  # a cut-off body would close it
                self.assertEqual(ex.trace.frames(), [])
                self.assertEqual(ex.trace.events("http-end"), [])


class WriteFailureTest(unittest.TestCase):
    """C120: a write to the client that fails means the client has gone: it is passed on."""

    def test_a_failed_write_of_the_response_head_is_a_hang_up(self) -> None:
        ex = Exchange(self, FakeResponse([b"{}"], headers=[("Content-Length", "2")]))
        ex.write_fails_when(b"HTTP/1.1 200")
        ex.run()
        assert ex.watch is not None
        self.assertTrue(ex.watch.gone.is_set())
        self.assertTrue(ex.handler.close_connection)
        (end,) = ex.trace.events("http-end")
        self.assertEqual(end["http"]["by"], "client")

    def test_a_failed_write_of_a_body_piece_is_a_hang_up(self) -> None:
        ex = Exchange(self, FakeResponse([b"ab", b"cd"], headers=[("Content-Length", "4")]))
        ex.write_fails_when(b"ab")
        ex.run()
        assert ex.watch is not None
        self.assertTrue(ex.watch.gone.is_set())
        (end,) = ex.trace.events("http-end")
        self.assertEqual(end["http"]["by"], "client")
        self.assertTrue(ex.handler.close_connection)

    def test_a_failed_write_of_an_event_is_a_hang_up(self) -> None:
        ex = Exchange(self, FakeResponse([EVENT, EVENT], headers=STREAM))
        ex.write_fails_when(b"jsonrpc")
        ex.run()
        assert ex.watch is not None
        self.assertTrue(ex.watch.gone.is_set())
        (end,) = ex.trace.events("http-end")
        self.assertEqual(end["http"]["by"], "client")
        self.assertTrue(ex.handler.close_connection)

    def test_the_connection_of_a_client_that_left_is_not_served_again(self) -> None:
        ex = Exchange(self, FakeResponse([EVENT, EVENT], headers=STREAM))
        ex.client_leaves_when(b"jsonrpc", write_fails=True)
        ex.run()
        self.assertTrue(ex.handler.close_connection)


class ClientWatchTest(unittest.TestCase):
    """D3: the watch, on real sockets. `client` is the tap's side of the client's connection."""

    def pair(self) -> tuple[socket.socket, socket.socket]:
        client, peer = socket.socketpair()
        self.addCleanup(client.close)
        self.addCleanup(peer.close)
        return client, peer

    def started(self, client: socket.socket) -> tuple[ClientWatch, socket.socket]:
        upstream, server = self.pair()
        watch = ClientWatch(client)
        self.addCleanup(watch.stop)
        watch.start(upstream)
        return watch, server

    def test_a_client_that_leaves_after_the_exchange_is_over_has_left_nothing(self) -> None:
        client, peer = self.pair()
        watch, _ = self.started(client)
        watch.stop()
        watch.client_left()
        self.assertFalse(watch.gone.is_set())

    def test_leaving_wakes_the_reader_and_the_server_sees_the_disconnect(self) -> None:
        client, peer = self.pair()
        upstream, server = self.pair()
        woken = threading.Event()

        def read() -> None:
            upstream.recv(1)  # what `getresponse()` waits in
            woken.set()

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        watch = ClientWatch(client)
        self.addCleanup(watch.stop)
        watch.start(upstream)
        peer.close()
        self.assertTrue(woken.wait(3), "the reader waiting on the upstream was not woken")
        server.settimeout(3)
        self.assertEqual(server.recv(1), b"", "the server did not see the disconnect")
        self.assertTrue(watch.gone.is_set())

    def test_a_request_queued_behind_the_exchange_is_not_a_hang_up(self) -> None:
        client, peer = self.pair()
        watch, server = self.started(client)
        peer.sendall(b"POST /next HTTP/1.1\r\n")
        time.sleep(0.5)
        self.assertFalse(watch.gone.is_set())
        peer.close()  # behind the queued bytes: the hang-up is still seen
        self.assertTrue(watch.gone.wait(3))

    def test_without_pollrdhup_a_queued_request_ends_the_watch_and_eof_is_a_hang_up(self) -> None:
        with mock.patch("tap.http.HANG_UP", 0), mock.patch("tap.http.WATCH_PERIOD", 0.05):
            client, peer = self.pair()
            watch, _ = self.started(client)
            peer.sendall(b"x")
            time.sleep(0.5)
            self.assertFalse(watch.gone.is_set())  # no hang-up can be seen behind it
            client2, peer2 = self.pair()
            watch2, _ = self.started(client2)
            peer2.close()
            self.assertTrue(watch2.gone.wait(3))


class NoDelayTest(unittest.TestCase):
    def test_small_pieces_are_not_held_for_the_nagle_timer(self) -> None:
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        outside = socket.create_connection(listener.getsockname())
        self.addCleanup(outside.close)
        inside, _ = listener.accept()
        self.addCleanup(inside.close)
        handler = ProxyHandler.__new__(ProxyHandler)
        handler.request = inside
        handler.setup()
        self.assertTrue(inside.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY))


class DrainTest(unittest.TestCase):
    """D2: the tap waits, up to a bound, for the exchanges still open when its child exits."""

    def proxy(self) -> Proxy:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        proxy = Proxy(0, str(Path(scratch.name) / "s"), SimpleNamespace())  # type: ignore[arg-type]
        self.addCleanup(proxy.server_close)
        return proxy

    def test_drain_waits_for_an_open_exchange_and_no_longer(self) -> None:
        proxy = self.proxy()
        started = time.monotonic()
        proxy.drain(5)
        self.assertLess(time.monotonic() - started, 0.5)  # nothing open: no wait
        proxy.begin(lambda number: None)
        threading.Timer(0.4, proxy.end).start()
        started = time.monotonic()
        proxy.drain(5)
        self.assertGreaterEqual(time.monotonic() - started, 0.35)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_drain_gives_up_after_its_bound(self) -> None:
        proxy = self.proxy()
        proxy.begin(lambda number: None)  # never ends
        started = time.monotonic()
        proxy.drain(0.3)
        self.assertGreaterEqual(time.monotonic() - started, 0.25)
        self.assertLess(time.monotonic() - started, 2.0)


if __name__ == "__main__":
    unittest.main()
