"""C1-C4: answering the server's requests and reacting to its notifications (D1, D2).

The handlers run on a real `Wire` over pipes against a test-controlled "server" end, so what is
checked is what a server would see: lines on its stdin, in the order the client wrote them.
"""

from __future__ import annotations

import json
import os
import threading
import time
import unittest
from typing import Any

from client import handlers, wire

ALL = ("roots", "sampling", "elicitation", "elicitation-url")
URI = "file:///wire-lab/project"


class Rig:
    """A Wire whose server side is this test: `say()` is the server talking, `read()` listens."""

    def __init__(self, caps: tuple[str, ...] = ALL, **kwargs: Any) -> None:
        to_server_r, to_server_w = os.pipe()
        from_server_r, from_server_w = os.pipe()
        self.said = os.fdopen(from_server_w, "wb", buffering=0)
        self.heard = os.fdopen(to_server_r, "rb")
        self.client_out = os.fdopen(to_server_w, "wb", buffering=0)
        self.client_in = os.fdopen(from_server_r, "rb")
        self.reports: list[str] = []
        self.notes: list[str] = []
        self.handlers = handlers.Handlers(
            caps, say=self.notes.append, debounce=0.05, report=self.reports.append, **kwargs
        )
        self.wire = wire.Wire(
            self.client_out, self.client_in,
            report=self.reports.append, on_request=self.handlers.handle_request,
            on_notification=self.handlers.handle_notification,
        )
        self.handlers.attach(self.wire)
        self.wire.start()

    def say(self, message: dict[str, Any]) -> None:
        self.said.write(json.dumps({"jsonrpc": "2.0", **message}).encode() + b"\n")

    def read(self) -> dict[str, Any]:
        """The next line the client wrote (blocks; the tests that call it expect one)."""
        line = self.heard.readline()
        assert line, "the client wrote nothing"
        message: dict[str, Any] = json.loads(line)
        return message

    def ask(self, request_id: Any, method: str, params: dict[str, Any] | None = None
            ) -> dict[str, Any]:
        request: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            request["params"] = params
        self.say(request)
        return self.read()

    def close(self) -> None:
        self.said.close()
        self.wire.join(2)
        for stream in (self.client_out, self.client_in, self.heard):
            stream.close()


class HandlersTest(unittest.TestCase):
    def rig(self, caps: tuple[str, ...] = ALL, **kwargs: Any) -> Rig:
        rig = Rig(caps, **kwargs)
        self.addCleanup(rig.close)
        return rig

    def test_reply_echoes_id_and_type(self) -> None:
        rig = self.rig()
        for request_id in (0, 7, "s-1", "7"):
            reply = rig.ask(request_id, "roots/list")
            self.assertEqual(reply["id"], request_id)
            self.assertIs(type(reply["id"]), type(request_id))
            self.assertIn("result", reply)
            self.assertNotIn("method", reply)
        # every method with a handler answers under its own id, not just roots
        for method, params in (("ping", None), ("sampling/createMessage", {"messages": []}),
                               ("elicitation/create", {"mode": "url", "message": "m"})):
            reply = rig.ask("x-" + method, method, params)
            self.assertEqual(reply["id"], "x-" + method)
            self.assertIn("result", reply)

    def test_undeclared_capability_is_refused(self) -> None:
        cases = {
            "roots/list": ("sampling", "elicitation", "elicitation-url"),
            "sampling/createMessage": ("roots", "elicitation", "elicitation-url"),
            "elicitation/create": ("roots", "sampling"),
        }
        for method, caps in cases.items():
            rig = self.rig(caps)
            reply = rig.ask(3, method, {"message": "m", "requestedSchema": {"properties": {}}})
            self.assertEqual(reply["id"], 3, method)
            self.assertEqual(reply["error"]["code"], -32601, method)
        # form and url are separate declarations
        form_only = self.rig(("elicitation",))
        self.assertEqual(form_only.ask(
            4, "elicitation/create", {"mode": "url", "message": "m", "url": "https://x.test"}
        )["error"]["code"], -32601)
        url_only = self.rig(("elicitation-url",))
        self.assertEqual(url_only.ask(
            5, "elicitation/create", {"message": "m", "requestedSchema": {"properties": {}}}
        )["error"]["code"], -32601)
        # ping needs no capability
        self.assertEqual(self.rig(()).ask(6, "ping")["result"], {})

    def test_unknown_method_is_refused(self) -> None:
        rig = self.rig()
        reply = rig.ask("u-1", "tasks/get")
        self.assertEqual(reply["id"], "u-1")
        self.assertEqual(reply["error"]["code"], -32601)
        self.assertIn("tasks/get", reply["error"]["message"])

    def test_server_request_does_not_block_reader(self) -> None:
        release = threading.Event()
        started = threading.Event()
        real = handlers.Handlers.answer

        def slow(self: handlers.Handlers, message: dict[str, Any]) -> dict[str, Any]:
            if message["method"] == "sampling/createMessage":
                started.set()
                release.wait(5)
            return real(self, message)

        handlers.Handlers.answer = slow  # type: ignore[method-assign]
        self.addCleanup(setattr, handlers.Handlers, "answer", real)
        rig = self.rig()
        pending = rig.wire.start_request("tools/list")  # id 0
        self.assertEqual(rig.read()["method"], "tools/list")
        rig.say({"id": 0, "method": "sampling/createMessage", "params": {"messages": []}})
        self.assertTrue(started.wait(2), "the handler started")
        # the handler is stuck; the reader must still deliver the reply to our own request
        rig.say({"id": 0, "result": {"tools": []}})
        self.assertEqual(pending.wait(2), {"tools": []})
        release.set()
        reply = rig.read()
        self.assertEqual(reply["id"], 0)
        self.assertIn("result", reply)


class RepliesTest(unittest.TestCase):
    def test_sampling_reply_shape(self) -> None:
        reply = handlers.Handlers(("sampling",)).answer(
            {"id": 1, "method": "sampling/createMessage", "params": {"messages": []}})
        self.assertEqual(reply, {"jsonrpc": "2.0", "id": 1, "result": {
            "role": "assistant",
            "content": {"type": "text", "text": "canned reply from wire-lab-raw"},
            "model": "wire-lab-canned", "stopReason": "endTurn"}})
        typed = handlers.Handlers(("sampling",), sampling_text=lambda: "typed by the owner")
        result = typed.answer({"id": 2, "method": "sampling/createMessage"})["result"]
        self.assertEqual(result["content"]["text"], "typed by the owner")

    def test_elicitation_form_values(self) -> None:
        schema = {"properties": {
            "with_default": {"type": "string", "default": "kept"},
            "zero_default": {"type": "integer", "default": 0},
            "fraction": {"type": "number", "default": 3.14},
            "enum_first": {"type": "string", "enum": ["a", "b"]},
            "titled": {"type": "string", "oneOf": [{"const": "one", "title": "One"}]},
            "multi": {"type": "array", "minItems": 1, "items": {"enum": ["x", "y"]}},
            "multi_titled": {"type": "array", "items": {"anyOf": [{"const": "p"}]}},
            "text": {"type": "string"}, "float": {"type": "number"},
            "int": {"type": "integer"}, "flag": {"type": "boolean"},
        }}
        reply = handlers.Handlers(("elicitation",)).answer({
            "id": "e", "method": "elicitation/create",
            "params": {"message": "m", "requestedSchema": schema}})
        self.assertEqual(reply["result"], {"action": "accept", "content": {
            "with_default": "kept", "zero_default": 0, "fraction": 3, "enum_first": "a",
            "titled": "one",
            "multi": ["x"], "multi_titled": ["p"], "text": "wire-lab", "float": 1, "int": 1,
            "flag": True}})
        self.assertIs(reply["result"]["content"]["flag"], True)

    def test_elicitation_url_declines(self) -> None:
        reply = handlers.Handlers(("elicitation-url",)).answer({
            "id": 9, "method": "elicitation/create",
            "params": {"mode": "url", "message": "m", "url": "https://x.test",
                       "elicitationId": "i"}})
        self.assertEqual(reply["result"], {"action": "decline"})

    def test_roots_reply(self) -> None:
        reply = handlers.Handlers(("roots",)).answer({"id": 4, "method": "roots/list"})
        self.assertEqual(reply["result"], {"roots": [{"uri": URI, "name": "wire-lab"}]})
        custom = [{"uri": "file:///wire-lab/other", "name": "other"}]
        reply = handlers.Handlers(("roots",), roots=custom).answer(
            {"id": 5, "method": "roots/list"})
        self.assertEqual(reply["result"], {"roots": custom})

    def test_capability_object(self) -> None:
        self.assertEqual(handlers.capability_object(()), {})
        self.assertEqual(handlers.capability_object(ALL), {
            "roots": {"listChanged": True}, "sampling": {},
            "elicitation": {"form": {}, "url": {}}})
        self.assertEqual(handlers.capability_object(("elicitation-url",)),
                         {"elicitation": {"url": {}}})
        with self.assertRaises(ValueError):
            handlers.capability_object(("telepathy",))


class NotificationsTest(unittest.TestCase):
    def rig(self) -> Rig:
        rig = Rig()
        self.addCleanup(rig.close)
        return rig

    def requests(self, rig: Rig, count: int) -> list[dict[str, Any]]:
        """Read `count` client requests, answering each with an empty list result."""
        seen = []
        for _ in range(count):
            request = rig.read()
            seen.append(request)
            kind = request["method"].split("/")[0]
            rig.say({"id": request["id"], "result": {kind: []}})
        return seen

    def test_list_changed_burst_coalesces(self) -> None:
        rig = self.rig()
        for _ in range(4):  # the server's burst after `initialized`: one note per registration
            rig.say({"method": "notifications/tools/list_changed"})
        rig.say({"method": "notifications/prompts/list_changed"})
        sent = self.requests(rig, 2)
        self.assertTrue(rig.handlers.wait_idle(2))
        self.assertEqual(sorted(m["method"] for m in sent), ["prompts/list", "tools/list"])
        # a later change is a new burst and one more re-list
        rig.say({"method": "notifications/tools/list_changed"})
        self.assertEqual([m["method"] for m in self.requests(rig, 1)], ["tools/list"])
        self.assertTrue(rig.handlers.wait_idle(2))
        self.assertEqual(sorted(rig.handlers.relists), ["prompts", "tools", "tools"])
        self.assertEqual(rig.handlers.counts["notifications/tools/list_changed"], 5)

    def test_resource_updated_rereads(self) -> None:
        rig = self.rig()
        uri = "demo://resource/static/document/architecture.md"
        rig.say({"method": "notifications/resources/updated", "params": {"uri": uri}})
        request = rig.read()
        self.assertEqual((request["method"], request["params"]), ("resources/read", {"uri": uri}))
        rig.say({"id": request["id"], "result": {"contents": []}})
        self.assertTrue(rig.handlers.wait_idle(2))
        self.assertEqual(rig.handlers.rereads, [uri])

    def test_progress_matched_by_token(self) -> None:
        rig = self.rig()
        mine = rig.handlers.watch_progress("tok-a")
        for token, step in (("tok-a", 1), ("tok-b", 1), ("tok-a", 2)):
            rig.say({"method": "notifications/progress",
                     "params": {"progressToken": token, "progress": step}})
        deadline = time.monotonic() + 2
        while len(mine) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual([p["progress"] for p in mine], [1, 2])
        self.assertEqual([p["progressToken"] for p in rig.handlers.unmatched_progress],
                         ["tok-b"])

    def test_every_notification_is_printed(self) -> None:
        rig = self.rig()
        rig.say({"method": "notifications/message",
                 "params": {"level": "warning", "logger": "everything", "data": "careful"}})
        rig.say({"method": "notifications/prompts/list_changed"})
        self.requests(rig, 1)
        self.assertTrue(rig.handlers.wait_idle(2))
        deadline = time.monotonic() + 2
        while len(rig.notes) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(any("level=warning" in n and "logger=everything" in n and "careful" in n
                            for n in rig.notes), rig.notes)
        self.assertTrue(any("notifications/prompts/list_changed" in n for n in rig.notes))

    def test_roots_change_notifies(self) -> None:
        rig = self.rig()
        new = [{"uri": "file:///wire-lab/two", "name": "two"}]
        rig.handlers.set_roots(new)
        self.assertEqual(rig.read(), {"jsonrpc": "2.0",
                                      "method": "notifications/roots/list_changed"})
        reply = rig.ask(0, "roots/list")
        self.assertEqual(reply["result"], {"roots": new})


class CliTest(unittest.TestCase):
    def test_caps_option(self) -> None:
        from client import __main__ as cli

        self.assertEqual(cli.parse_caps("roots,sampling"), ("roots", "sampling"))
        self.assertEqual(cli.parse_caps("none"), ())
        with self.assertRaises(ValueError):
            cli.parse_caps("roots,mind-reading")
        self.assertEqual(cli.main(["tour", "--caps", "bogus", "--", "true"]), 2)
        self.assertEqual(cli.main(["matrix", "--caps", "roots", "--", "true"]), 2)
        self.assertEqual(cli.main(["server-tour"]), 2)


if __name__ == "__main__":
    unittest.main()
