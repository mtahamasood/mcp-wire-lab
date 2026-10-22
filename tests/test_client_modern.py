"""Phase 6 C1 to C6: the 2026-07-28 session, against the scripted fake server of
tests/fake_servers/modern.py (and `client.__main__` for the era option)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

from client import __main__ as cli
from client import modern
from client.handlers import Handlers, capability_object
from client.session import CLIENT_INFO, UnsupportedVersion
from client.wire import RpcError

ROOT = Path(__file__).resolve().parent.parent
FAKE = str(ROOT / "tests/fake_servers/modern.py")
META = "io.modelcontextprotocol/"
CAPS = capability_object(["roots", "sampling"])


@contextmanager
def server(
    *flags: str, caps: dict[str, Any] | None = None, discover: bool = True
) -> Iterator[tuple[modern.ModernSession, Path, list[str]]]:
    """A ModernSession on the fake server: the session, its log of received lines, reports."""
    reports: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "received.log"
        sess = modern.ModernSession.open_modern(
            [sys.executable, FAKE, str(log), *flags], capabilities=CAPS if caps is None else caps,
            report=reports.append, grace=2.0)
        try:
            if discover:
                sess.discover()
            yield sess, log, reports
        finally:
            sess.close()


def received(log: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [json.loads(ln) for ln in log.read_text().splitlines()]
    return out


def wait_for(condition: Any, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


class EnvelopeTest(unittest.TestCase):
    def test_every_request_carries_the_envelope(self) -> None:
        answer = modern.default_answer(Handlers(["roots", "sampling"]))
        with server() as (sess, log, _):
            sess.call("echo", {"x": 1})
            sess.request_with_input("mrtr", {"y": 2}, answer)  # a retry too
            sub = sess.listen({"toolsListChanged": True})
            sub.close()
            time.sleep(0.2)
            sent = [m for m in received(log) if "id" in m]
        self.assertEqual([m["method"] for m in sent],
                         ["server/discover", "echo", "mrtr", "mrtr", "subscriptions/listen"])
        for message in sent:
            meta = message["params"]["_meta"]
            self.assertEqual(meta[META + "protocolVersion"], "2026-07-28", message)
            self.assertEqual(meta[META + "clientInfo"], CLIENT_INFO, message)
            self.assertEqual(meta[META + "clientCapabilities"], CAPS, message)
            self.assertNotIn(META + "logLevel", meta)

    def test_caller_meta_kept_reserved_keys_set_by_client(self) -> None:
        params: dict[str, Any] = {"x": 1, "_meta": {
            "progressToken": "p1", META + "protocolVersion": "1999-01-01",
            META + "clientCapabilities": {"sampling": {}}}}
        built = modern.envelope(params, CAPS)
        self.assertEqual(built["_meta"]["progressToken"], "p1")
        self.assertEqual(built["_meta"][META + "protocolVersion"], "2026-07-28")
        self.assertEqual(built["_meta"][META + "clientCapabilities"], CAPS)
        self.assertEqual(params["_meta"][META + "protocolVersion"], "1999-01-01", "a copy")
        self.assertEqual(modern.envelope(None, {})["_meta"][META + "clientCapabilities"], {})

    def test_log_level_only_when_given(self) -> None:
        self.assertNotIn(META + "logLevel", modern.envelope({}, CAPS)["_meta"])
        built = modern.envelope({}, CAPS, log_level="warning")
        self.assertEqual(built["_meta"][META + "logLevel"], "warning")
        with server() as (sess, log, _):
            sess.call("echo", log_level="debug")
            sess.call("echo")
            sent = [m for m in received(log) if m.get("method") == "echo"]
        self.assertEqual([m["params"]["_meta"].get(META + "logLevel") for m in sent],
                         ["debug", None])

    def test_notifications_carry_no_envelope(self) -> None:
        with server() as (sess, log, _):
            sub = sess.listen({"toolsListChanged": True})
            sub.close()
            sess.call("echo")  # the server has seen the cancellation before this
            sent = received(log)
        cancelled = [m for m in sent if m.get("method") == "notifications/cancelled"]
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(set(cancelled[0]["params"]) - {"reason"}, {"requestId"})
        self.assertNotIn("_meta", cancelled[0]["params"])


class DiscoverTest(unittest.TestCase):
    def test_no_request_before_discover_reply(self) -> None:
        with server(discover=False) as (sess, log, _):
            with self.assertRaises(modern.NotDiscovered):
                sess.request("echo")
            with self.assertRaises(modern.NotDiscovered):
                sess.start_request("echo")
            self.assertEqual(log.read_text() if log.exists() else "", "", "nothing was sent")
            result = sess.discover()
            self.assertEqual(result["supportedVersions"], ["2026-07-28"])
            self.assertEqual(sess.call("echo")["params"]["_meta"][META + "protocolVersion"],
                             "2026-07-28")
            methods = [m.get("method") for m in received(log)]
        self.assertEqual(methods, ["server/discover", "echo"])

    def test_unsupported_version_stops(self) -> None:
        with server("--versions", "2025-11-25,2099-01-01", discover=False) as (sess, log, _):
            with self.assertRaises(UnsupportedVersion) as caught:
                sess.discover()
            self.assertIn("2025-11-25", str(caught.exception))
            self.assertIn("2099-01-01", str(caught.exception))
            with self.assertRaises(modern.NotDiscovered):
                sess.request("echo")
            self.assertEqual([m["method"] for m in received(log)], ["server/discover"])

    def test_unsupported_version_error_stops(self) -> None:
        with server("--discover-error", "-32022", discover=False) as (sess, _log, _):
            with self.assertRaises(UnsupportedVersion) as caught:
                sess.discover()
            self.assertIn("2025-11-25", str(caught.exception), "the versions the server offered")
            self.assertFalse(sess.ready)

    def test_other_error_suggests_2025_era(self) -> None:
        with server("--discover-error", "-32601", discover=False) as (sess, _log, _):
            with self.assertRaises(RuntimeError) as caught:
                sess.discover()
            self.assertNotIsInstance(caught.exception, UnsupportedVersion)
            self.assertIn("--era 2025-11-25", str(caught.exception))
            self.assertFalse(sess.ready)


class ResultTypeTest(unittest.TestCase):
    def test_complete_and_absent_are_results(self) -> None:
        with server() as (sess, _log, _):
            self.assertEqual(sess.request("echo")["resultType"], "complete")
            self.assertEqual(sess.request("legacy"), {"x": 1})

    def test_input_required_is_an_outcome(self) -> None:
        with server() as (sess, _log, _):
            outcome = sess.request("mrtr", {})
            self.assertIsInstance(outcome, modern.InputRequired)
            self.assertEqual(list(outcome.input_requests), ["a", "b"])
            with self.assertRaises(modern.InvalidResult):
                sess.call("mrtr", {})

    def test_task_only_with_tasks_extension(self) -> None:
        with server() as (sess, _log, _):
            with self.assertRaises(modern.InvalidResult):
                sess.request("task")
            declared = modern.with_tasks(CAPS)
            self.assertEqual(modern.TASKS_EXTENSION in declared["extensions"], True)
            handle = sess.request("task", capabilities=declared)
            self.assertEqual(handle["taskId"], "t1")
            self.assertNotIn("extensions", CAPS, "with_tasks copies")

    def test_unrecognized_result_type_is_invalid(self) -> None:
        with server() as (sess, _log, _):
            with self.assertRaises(modern.InvalidResult) as caught:
                sess.request("weird")
            self.assertIn("bogus", str(caught.exception))
        with self.assertRaises(modern.InvalidResult):
            modern.classify_result("not an object", False)

    def test_error_reply_still_raises_rpc_error(self) -> None:
        with server() as (sess, _log, _):
            with self.assertRaises(RpcError) as caught:
                sess.request("nonsense")
            self.assertEqual(caught.exception.error["code"], -32601)


class InputRequiredTest(unittest.TestCase):
    def answer(self) -> Any:
        return modern.default_answer(Handlers(["roots", "sampling"]))

    def test_retry_carries_responses_and_state_verbatim(self) -> None:
        first = {}
        with server() as (sess, log, _):
            first = sess.request("mrtr", {"y": 2})
            result = sess.request_with_input("mrtr", {"y": 2}, self.answer())
            sent = [m for m in received(log) if m.get("method") == "mrtr"]
        retry = sent[-1]["params"]
        self.assertEqual(set(retry["inputResponses"]), {"a", "b"})
        self.assertEqual(retry["inputResponses"]["a"], {"roots": [
            {"uri": "file:///wire-lab/project", "name": "wire-lab"}]})
        self.assertEqual(retry["inputResponses"]["b"]["role"], "assistant")
        self.assertEqual(retry["requestState"], first.request_state)
        self.assertEqual(retry["y"], 2)
        self.assertEqual(result["params"]["requestState"], first.request_state, "byte for byte")

    def test_retry_uses_fresh_id_and_full_envelope(self) -> None:
        lines: list[str] = []
        with server() as (sess, log, _):
            sess.request_with_input("mrtr", {"y": 2}, self.answer(), say=lines.append)
            sent = [m for m in received(log) if m.get("method") == "mrtr"]
        self.assertEqual(len(sent), 2)
        self.assertNotEqual(sent[0]["id"], sent[1]["id"])
        self.assertEqual(sent[0]["params"]["_meta"], sent[1]["params"]["_meta"])
        self.assertEqual(sent[1]["params"]["_meta"][META + "clientCapabilities"], CAPS)
        self.assertEqual(lines, ["round 1: a, b"])

    def test_round_limit(self) -> None:
        with server() as (sess, log, _):
            with self.assertRaises(modern.TooManyRounds):
                sess.request_with_input("forever", {}, self.answer(), max_rounds=3)
            self.assertEqual(len([m for m in received(log) if m.get("method") == "forever"]), 3)

    def test_unanswerable_request_raises(self) -> None:
        with server() as (sess, log, _):
            with self.assertRaises(modern.CannotAnswer):
                sess.request_with_input("unanswerable", {}, self.answer())
            self.assertEqual(len([m for m in received(log)
                                  if m.get("method") == "unanswerable"]), 1, "no retry")
            with self.assertRaises(modern.CannotAnswer):  # a capability not declared
                sess.request_with_input(
                    "mrtr", {}, modern.default_answer(Handlers([])))


class ListenTest(unittest.TestCase):
    def test_ack_matched_by_subscription_id_type_included(self) -> None:
        with server() as (sess, _log, _):
            outcome: list[modern.Subscription] = []
            thread = threading.Thread(
                target=lambda: outcome.append(sess.listen({"hold": True})), daemon=True)
            thread.start()
            time.sleep(0.5)  # the decoy acknowledgment (id as a string) is long here
            self.assertEqual(outcome, [], "an ack under the id as a string must not count")
            sess.call("release")
            thread.join(3)
            self.assertEqual(len(outcome), 1)
            self.assertEqual(outcome[0].filter, {"hold": True})
            self.assertIsInstance(outcome[0].id, int)

    def test_notifications_routed_by_subscription_id(self) -> None:
        with server() as (sess, _log, _):
            first = sess.listen({"toolsListChanged": True})
            second = sess.listen({"toolsListChanged": True})
            self.assertNotEqual(first.id, second.id)
            sess.call("emit", {"sub": second.id})
            sess.call("emit", {"sub": str(first.id)})  # the wrong type: nobody's
            sess.call("emit", {"sub": first.id})
            first.wait_for("notifications/tools/list_changed", 3)
            second.wait_for("notifications/tools/list_changed", 3)
            with self.assertRaises(TimeoutError):  # each had exactly one
                first.wait_for("notifications/tools/list_changed", 0.3)
            with self.assertRaises(TimeoutError):
                second.wait_for("notifications/tools/list_changed", 0.3)
            # the request-scoped notification carries no id: it stays on the wire's queue
            methods = []
            while not sess.wire.notifications.empty():
                methods.append(sess.wire.notifications.get_nowait()["method"])
            self.assertIn("notifications/message", methods)
            self.assertEqual([m["method"] for m in first.seen() + second.seen()], [])

    def test_close_sends_cancelled_with_listen_id(self) -> None:
        with server("--late") as (sess, log, reports):
            sub = sess.listen({"toolsListChanged": True})
            self.assertTrue(sub.close())
            self.assertFalse(sub.close(), "a closed stream is closed once")
            self.assertTrue(wait_for(lambda: any("late reply" in r for r in reports)), reports)
            sent = received(log)
        cancelled = [m for m in sent if m.get("method") == "notifications/cancelled"]
        self.assertEqual([m["params"]["requestId"] for m in cancelled], [sub.id])


class CliTest(unittest.TestCase):
    def run_main(self, *argv: str) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(list(argv))
        return code, err.getvalue()

    def test_era_option_parsing(self) -> None:
        self.assertEqual(cli.parse_options([]), (None, "2025-11-25"))
        self.assertEqual(cli.parse_options(["--era", "2026-07-28", "--caps", "roots"]),
                         ("roots", "2026-07-28"))
        self.assertEqual(cli.parse_options(["--caps", "none", "--era", "2025-11-25"]),
                         ("none", "2025-11-25"))
        for bad in (["--era"], ["--era", "2099-01-01"], ["--era", "2026-07-28", "--era",
                                                         "2026-07-28"], ["--nope", "x"]):
            self.assertIsNone(cli.parse_options(bad), bad)
        with (mock.patch.object(cli, "run_tour", return_value=0) as old,
              mock.patch.object(cli, "run_modern_tour", return_value=0) as new):
            self.assertEqual(self.run_main("tour", "--", "srv")[0], 0)
            self.assertEqual((old.call_count, new.call_count), (1, 0), "the default era")
            self.assertEqual(self.run_main("tour", "--era", "2026-07-28", "--", "srv")[0], 0)
            self.assertEqual((old.call_count, new.call_count), (1, 1))
            self.assertEqual(new.call_args.kwargs["caps"], ("roots", "sampling", "elicitation"))
            self.run_main("tour", "--caps", "none", "--era", "2026-07-28", "--", "srv")
            self.assertEqual(new.call_args.kwargs["caps"], ())
        with mock.patch.object(cli, "run_tasks", return_value=0) as tasks:
            self.assertEqual(self.run_main("tasks", "--era", "2026-07-28", "--", "srv")[0], 0)
            self.assertEqual(tasks.call_count, 1)
        with mock.patch.object(cli, "run_manual", return_value=0) as manual:
            self.run_main("manual", "--era", "2026-07-28", "--", "srv")
            self.assertEqual(manual.call_args.kwargs["era"], "2026-07-28")
            self.run_main("manual", "--", "srv")
            self.assertEqual(manual.call_args.kwargs["era"], "2025-11-25")

    def test_modes_without_a_2026_form_are_usage_errors(self) -> None:
        for argv in (["server-tour", "--era", "2026-07-28", "--", "srv"],
                     ["matrix", "--era", "2026-07-28", "--", "srv"],
                     ["tasks", "--", "srv"],
                     ["tasks", "--era", "2025-11-25", "--", "srv"],
                     ["tour", "--era", "2099-01-01", "--", "srv"]):
            code, err = self.run_main(*argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("usage:", err)


if __name__ == "__main__":
    unittest.main()
