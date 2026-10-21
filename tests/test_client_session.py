"""C3, C4, C5: the 2025 lifecycle, shutdown, and cancellation, against scripted fake servers."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from client import session, wire

ROOT = Path(__file__).resolve().parent.parent
FAKE = str(ROOT / "tests/fake_servers/scripted.py")


@contextmanager
def server(*flags: str, grace: float = 2.0) -> Iterator[tuple[session.Session, Path, list[str]]]:
    """A session on the scripted server; yields it, the server's log of received lines, reports."""
    reports: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "received.log"
        sess = session.Session.open(
            [sys.executable, FAKE, str(log), *flags], report=reports.append, grace=grace
        )
        try:
            yield sess, log, reports
        finally:
            sess.close()


def received(log: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [json.loads(ln) for ln in log.read_text().splitlines()]
    return out


class LifecycleTest(unittest.TestCase):
    def test_request_before_initialized_raises_without_sending(self) -> None:
        with server() as (sess, log, _):
            with self.assertRaises(session.NotInitialized):
                sess.request("ping")
            with self.assertRaises(session.NotInitialized):
                sess.start_request("ping")
            self.assertEqual(log.read_text() if log.exists() else "", "", "nothing was sent")
            sess.initialize()
            self.assertEqual(sess.request("ping"), {}, "after initialized, requests flow")
            sent = received(log)
            self.assertEqual([m.get("method") for m in sent],
                             ["initialize", "notifications/initialized", "ping"])

    def test_initialize_message_is_what_d2_says(self) -> None:
        with server() as (sess, log, _):
            result = sess.initialize()
            self.assertEqual(result["serverInfo"]["name"], "scripted")
            sess.request("ping")  # its reply shows the server has logged the lines before it
            first, second = received(log)[:2]
            self.assertEqual(first, {
                "jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
                    "protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": {"name": "wire-lab-raw", "version": "0.2.0"}}})
            self.assertEqual(second, {"jsonrpc": "2.0", "method": "notifications/initialized"})

    def test_older_supported_version_is_accepted(self) -> None:
        for version in session.SUPPORTED_VERSIONS:
            with server("--version", version) as (sess, _, _):
                self.assertEqual(sess.initialize()["protocolVersion"], version)

    def test_unsupported_version_stops(self) -> None:
        with server("--version", "1999-01-01") as (sess, log, _):
            with self.assertRaises(session.UnsupportedVersion) as caught:
                sess.initialize()
            self.assertIn("1999-01-01", str(caught.exception))
            with self.assertRaises(session.NotInitialized):
                sess.request("ping")
            self.assertEqual([m.get("method") for m in received(log)], ["initialize"])

    def test_error_reply_raises_with_error_object(self) -> None:
        with server() as (sess, _, _):
            sess.initialize()
            with self.assertRaises(wire.RpcError) as caught:
                sess.request("boom")
            self.assertEqual(caught.exception.error,
                             {"code": -32000, "message": "boom", "data": {"x": 1}})
            self.assertEqual(sess.request("echo", {"a": 1}), {"a": 1}, "still usable")

    def test_timeout_raises(self) -> None:
        with server() as (sess, _, _):
            sess.initialize()
            with self.assertRaises(TimeoutError):
                sess.request("hang", timeout=0.2)


class ShutdownTest(unittest.TestCase):
    def test_close_then_escalate(self) -> None:
        grace = 0.4
        for flags, status, name in (
            ((), 0, "closing stdin is enough"),
            (("--ignore-eof",), -15, "SIGTERM after the grace period"),
            (("--ignore-eof", "--ignore-term"), -9, "SIGKILL after SIGTERM was ignored"),
        ):
            with server(*flags, grace=grace) as (sess, _, _):
                sess.initialize()  # the reply proves the child has installed its handlers
                started = time.monotonic()
                self.assertEqual(sess.close(), status, name)
                took = time.monotonic() - started
                if status == 0:
                    self.assertLess(took, grace, name)
                else:
                    self.assertGreaterEqual(took, grace, name)
                self.assertLess(took, 4 * grace + 2, name)
                self.assertEqual(sess.close(), status, "closing twice returns the same status")


class CancelTest(unittest.TestCase):
    def test_cancel_sends_notification_and_drops_late_reply(self) -> None:
        with server("--late") as (sess, log, reports):
            sess.initialize()
            pending = sess.start_request("hang")
            self.assertTrue(sess.cancel(pending, "no longer needed"))
            with self.assertRaises(wire.Cancelled):
                pending.wait(1)
            # the server replies to the cancelled request; the client drops and reports it
            deadline = time.monotonic() + 5
            while not reports and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(len(reports), 1, reports)
            self.assertIn("late reply", reports[0])
            self.assertIn(f"id {pending.id}", reports[0])
            self.assertEqual(sess.request("ping"), {}, "the session carries on")
            sent = [m for m in received(log) if m.get("method") == "notifications/cancelled"]
            self.assertEqual(sent, [{
                "jsonrpc": "2.0", "method": "notifications/cancelled",
                "params": {"requestId": pending.id, "reason": "no longer needed"}}])

    def test_cancel_without_reason_and_finished_request(self) -> None:
        with server() as (sess, log, _):
            sess.initialize()
            done = sess.start_request("ping")
            done.wait(2)
            self.assertFalse(sess.cancel(done), "a finished request is not cancelled")
            hung = sess.start_request("hang")
            self.assertTrue(sess.cancel(hung))
            time.sleep(0.2)  # let the server log the notification
            cancel = [m for m in received(log) if m.get("method") == "notifications/cancelled"]
            self.assertEqual(cancel[0]["params"], {"requestId": hung.id})
            with self.assertRaises(ValueError):
                sess.cancel(wire.Pending(0, "initialize"))


class OverlapTest(unittest.TestCase):
    def test_server_request_id_overlapping_a_pending_client_id(self) -> None:
        with server() as (sess, _, _):
            sess.initialize()
            result = sess.request("overlap", timeout=5)  # id 1; the server asks with id 0
            self.assertEqual(result["error"]["code"], -32601)
            self.assertEqual(result["id"], 0)


if __name__ == "__main__":
    unittest.main()
