"""C1, C2: the wire classifies lines by shape, correlates by id and type, frames cleanly."""

from __future__ import annotations

import io
import json
import sys
import threading
import time
import unittest
from typing import Any

from client import session, wire


class Sink(io.BytesIO):
    """A stdin stand-in that keeps what was written and does not close on `close()`."""

    def close(self) -> None:  # the tests read getvalue() afterwards
        pass

    def sent(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [json.loads(ln) for ln in self.getvalue().splitlines()]
        return out


class SlowSink(Sink):
    """Writes in small pieces and yields between them, so unlocked writers would interleave."""

    def write(self, data: bytes | bytearray | memoryview) -> int:  # type: ignore[override]
        view = bytes(data)
        for i in range(0, len(view), 4):
            super().write(view[i : i + 4])
            time.sleep(0)
        return len(view)


def make(sink: Sink | None = None) -> tuple[wire.Wire, Sink, list[str]]:
    reports: list[str] = []
    sink = sink if sink is not None else Sink()
    return wire.Wire(sink, io.BytesIO(), report=reports.append), sink, reports


def wait_for_lines(sink: Sink, count: int, timeout: float = 5.0) -> list[dict[str, Any]]:
    """The lines written so far, once there are `count` (refusals are sent off the reader)."""
    deadline = time.monotonic() + timeout
    while len(sink.getvalue().splitlines()) < count and time.monotonic() < deadline:
        time.sleep(0.005)
    return sink.sent()


def line(message: object) -> bytes:
    return json.dumps(message).encode() + b"\n"


class ClassifyTest(unittest.TestCase):
    def test_response_matches_same_id_and_type_only(self) -> None:
        w, _, reports = make()
        first = w.start_request("a")  # id 0
        self.assertEqual(first.id, 0)
        # "0" is not 0, and true is not 1: neither completes the request, both are reported.
        self.assertEqual(w.handle_line(line({"jsonrpc": "2.0", "id": "0", "result": {}})), "junk")
        self.assertFalse(first.done)
        second = w.start_request("b")  # id 1
        self.assertEqual(w.handle_line(line({"jsonrpc": "2.0", "id": True, "result": {}})), "junk")
        self.assertFalse(second.done)
        self.assertEqual(len(reports), 2, reports)
        # the right id completes only its own request, with the result
        self.assertEqual(
            w.handle_line(line({"jsonrpc": "2.0", "id": 1, "result": {"ok": 1}})), "response")
        self.assertTrue(second.done)
        self.assertFalse(first.done)
        self.assertEqual(second.wait(1), {"ok": 1})
        # an error reply raises with its error object
        w.handle_line(line({"jsonrpc": "2.0", "id": 0, "error": {"code": -1, "message": "m"}}))
        with self.assertRaises(wire.RpcError) as caught:
            first.wait(1)
        self.assertEqual(caught.exception.error, {"code": -1, "message": "m"})

    def test_server_request_with_overlapping_id_is_not_a_response(self) -> None:
        w, sink, _ = make()
        pending = w.start_request("tools/list")  # id 0, in flight
        kind = w.handle_line(line({"jsonrpc": "2.0", "id": 0, "method": "roots/list"}))
        self.assertEqual(kind, "request")
        self.assertFalse(pending.done)
        refusal = wait_for_lines(sink, 2)[-1]  # the request, then the refusal
        self.assertEqual(refusal["id"], 0)
        self.assertEqual(refusal["error"]["code"], -32601)
        self.assertNotIn("method", refusal)
        # a string id is answered with the string id, type included
        w.handle_line(line({"jsonrpc": "2.0", "id": "s-1", "method": "sampling/createMessage"}))
        self.assertEqual(wait_for_lines(sink, 3)[-1]["id"], "s-1")
        self.assertFalse(pending.done)

    def test_notification_is_queued(self) -> None:
        w, sink, _ = make()
        note = {"jsonrpc": "2.0", "method": "notifications/progress", "params": {"progress": 1}}
        self.assertEqual(w.handle_line(line(note)), "notification")
        self.assertEqual(w.notifications.get_nowait(), note)
        self.assertTrue(w.notifications.empty())
        self.assertEqual(sink.getvalue(), b"", "a notification is never answered")

    def test_junk_line_is_reported_and_ignored(self) -> None:
        w, sink, reports = make()
        pending = w.start_request("x")
        sent_before = sink.getvalue()
        junk = [
            b"not json\n",
            b"\xff\xfe\n",
            b"[1, 2]\n",
            b"42\n",
            line({"jsonrpc": "2.0"}),
            line({"jsonrpc": "2.0", "id": 0}),
            line({"jsonrpc": "2.0", "id": 99, "result": {}}),
            line({"jsonrpc": "2.0", "id": None, "result": {}}),
            line({"jsonrpc": "2.0", "id": 1.5, "method": "m"}),
            line({"jsonrpc": "2.0", "id": True, "method": "m"}),
            line({"jsonrpc": "2.0", "method": 5}),
        ]
        for raw in junk:
            self.assertEqual(w.handle_line(raw), "junk", raw)
        self.assertEqual(len(reports), len(junk), reports)
        self.assertFalse(pending.done)
        self.assertTrue(w.notifications.empty())
        self.assertEqual(sink.getvalue(), sent_before, "junk gets no reply")

    def test_classify_by_shape(self) -> None:
        cases: list[tuple[object, str]] = [
            ({"id": 1, "result": {}}, "response"),
            ({"id": "a", "error": {}}, "response"),
            ({"id": 1, "method": "m"}, "request"),
            ({"method": "m"}, "notification"),
            ({"id": 1, "method": "m", "result": {}}, "request"),
            ({"id": 1}, "junk"),
            ([], "junk"),
        ]
        for message, kind in cases:
            self.assertEqual(wire.classify(message), kind, message)

    def test_bad_id_or_deep_line_does_not_stop_reader(self) -> None:
        # P2-R1: an array id and a 100000-deep line are junk, and a good reply after them is
        # still delivered by the running reader thread.
        for bad in ({"jsonrpc": "2.0", "id": [0], "result": {}},
                    {"jsonrpc": "2.0", "id": {"a": 0}, "error": {}}):
            self.assertEqual(wire.classify(bad), "junk", bad)
        self.assertEqual(wire.classify({"id": None, "error": {}}), "response")
        stream = (line({"jsonrpc": "2.0", "id": [0], "result": {}})
                  + b"[" * 100000 + b"\n"
                  + line({"jsonrpc": "2.0", "id": {"a": 1}, "error": {"code": 1}})
                  + line({"jsonrpc": "2.0", "id": 0, "result": {"ok": True}}))
        reports: list[str] = []
        w = wire.Wire(Sink(), io.BytesIO(stream), report=reports.append)
        pending = w.start_request("x")
        w.start()
        self.assertEqual(pending.wait(5), {"ok": True})
        w.join(5)
        self.assertEqual(len(reports), 3, reports)
        self.assertEqual(w.handle_line(b"[" * 100000), "junk", "too deep is junk, not a crash")
        self.assertIn("not JSON", reports[-1])
        # a handler that raises is reported and does not end the loop (the guard per line)
        stream = line({"jsonrpc": "2.0", "id": 0, "result": {}}) + line(
            {"jsonrpc": "2.0", "id": 1, "result": {"second": 1}})
        reports2: list[str] = []
        w2 = wire.Wire(Sink(), io.BytesIO(stream), report=reports2.append)
        w2.start_request("a")
        second = w2.start_request("b")
        real = w2._complete
        calls: list[int] = []

        def flaky(message: dict[str, Any]) -> bool:
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return real(message)

        w2._complete = flaky  # type: ignore[method-assign]
        w2.start()
        self.assertEqual(second.wait(5), {"second": 1})
        self.assertTrue(any("boom" in r for r in reports2), reports2)
        # the reader ends at EOF: whatever is still pending fails at once, not after a timeout
        w3 = wire.Wire(Sink(), io.BytesIO(b""), report=lambda t: None)
        waiting = w3.start_request("y")
        w3.start()
        with self.assertRaises(ConnectionError):
            waiting.wait(5)
        # ... and so does a reader that dies on its stream (here: reading raises)

        class Broken:
            def __iter__(self) -> Broken:
                return self

            def __next__(self) -> bytes:
                raise OSError("read failed")

        w4 = wire.Wire(Sink(), Broken(), report=lambda t: None)  # type: ignore[arg-type]
        stuck = w4.start_request("z")
        quiet = threading.excepthook
        threading.excepthook = lambda args: None  # the thread's own traceback is not the point
        self.addCleanup(setattr, threading, "excepthook", quiet)
        w4.start()
        with self.assertRaises(ConnectionError):
            stuck.wait(5)


def notify_many(w: wire.Wire, tag: int, payload: str) -> None:
    for _ in range(25):
        w.notify("n", {"t": tag, "pad": payload})


def request_many(w: wire.Wire) -> None:
    for _ in range(10):
        w.start_request("r")


class FramingTest(unittest.TestCase):
    def test_one_compact_line_per_message(self) -> None:
        w, sink, _ = make()
        w.start_request("echo", {"text": "line one\nline two", "u": "caf\u00e9 \u2028 \u0085"})
        w.notify("notifications/initialized")
        w.notify("notifications/message", {"data": "\u2028"})
        w.send_line('{"typed": "as is" }')
        data = sink.getvalue()
        lines = data.split(b"\n")
        self.assertEqual(lines.pop(), b"", "every message ends in exactly one newline")
        self.assertEqual(len(lines), 4)
        self.assertEqual(
            lines[0],
            b'{"jsonrpc":"2.0","id":0,"method":"echo","params":'
            b'{"text":"line one\\nline two","u":"caf\\u00e9 \\u2028 \\u0085"}}',
        )
        self.assertEqual(lines[1], b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
        self.assertEqual(lines[2], b'{"jsonrpc":"2.0","method":"notifications/message",'
                                   b'"params":{"data":"\\u2028"}}', "notify is ASCII-only too")
        self.assertEqual(lines[3], b'{"typed": "as is" }', "a typed line is sent untouched")
        data.decode("utf-8")  # UTF-8 (here pure ASCII)

    def test_concurrent_sends_do_not_interleave(self) -> None:
        w, sink, _ = make(SlowSink())
        payload = "x" * 200
        threads = [
            threading.Thread(target=notify_many, args=(w, t, payload)) for t in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        sent = sink.sent()  # json.loads on every line: a torn line raises
        self.assertEqual(len(sent), 200)
        self.assertEqual(sorted({m["params"]["t"] for m in sent}), list(range(8)))
        # ids are allocated and written under the same lock: write order is id order
        w2, sink2, _ = make(SlowSink())
        workers = [threading.Thread(target=request_many, args=(w2,)) for _ in range(4)]
        for t in workers:
            t.start()
        for t in workers:
            t.join()
        self.assertEqual([m["id"] for m in sink2.sent()], list(range(40)))

    def test_large_write_does_not_block_reader(self) -> None:
        # P2-R2: a 1 MB write blocks on a full pipe while the server floods stdout and only
        # then reads stdin. The reader must keep draining (and a refusal must not be written
        # by the reader), or both sides wait on each other for ever.
        code = (
            "import sys, time\n"
            "sys.stdin.buffer.readline(); time.sleep(1.0)\n"
            "w = sys.stdout.buffer\n"
            "w.write(b'{\"jsonrpc\":\"2.0\",\"id\":\"s\",\"method\":\"roots/list\"}\\n')\n"
            "w.flush()\n"
            "pad = b'y' * 1000\n"
            "line = b'{\"jsonrpc\":\"2.0\",\"id\":0,\"result\":{\"pad\":\"' + pad + b'\"}}\\n'\n"
            "for _ in range(2000): w.write(line); w.flush()\n"
            "sys.stdin.buffer.read()\n"
        )
        sess = session.Session.open([sys.executable, "-c", code], report=lambda t: None)
        assert sess.process is not None
        self.addCleanup(sess.process.wait)
        self.addCleanup(sess.process.kill)
        sess.wire.start_request("a")
        big = threading.Thread(
            target=sess.wire.start_request, args=("big", {"blob": "x" * 1_000_000}), daemon=True)
        started = time.monotonic()
        big.start()
        big.join(8)
        self.assertFalse(big.is_alive(), "the large write is stuck: the reader stopped draining")
        self.assertLess(time.monotonic() - started, 9)


if __name__ == "__main__":
    unittest.main()
