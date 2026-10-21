"""The scripted tour (D3): every client-initiated request the everything server offers, in order.

Each step sends one message, checks the reply is the kind it expects, and prints one line. Every
notification the server sends is printed as it arrives, indented, above the line of the step it
came during. The tour avoids the server's timer tools (`toggle-*`), so its message sequence is
the same on every run; only content (timestamps, text) can differ. It exits 0 only if every step
got the reply it expects.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, TextIO

from client.handlers import Handlers
from client.session import Session
from client.wire import Cancelled, Message, classify, stderr_report

STATIC_DOC = "demo://resource/static/document/architecture.md"
COMPLETABLE_PROMPT = "completable-prompt"
NOTE_WAIT = 5.0  # seconds to wait for a notification the tour needs to see


class TourFailure(Exception):
    """A step got a reply other than the one it expects."""


class Tour:
    def __init__(self, session: Session, out: TextIO, capabilities: Message | None = None) -> None:
        self.session = session
        self.capabilities = capabilities
        self.out = out
        self.step_no = 0
        self._print_lock = threading.Lock()

    # -- output ------------------------------------------------------------------------

    def say(self, text: str) -> None:
        with self._print_lock:
            print(text, file=self.out, flush=True)

    def observe(self, arrow: str, message: Any) -> None:
        """Print each notification the server sends, as it arrives.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:27`
        "individual JSON-RPC requests, notifications, or responses"
        """
        if arrow == "<-" and classify(message) == "notification":
            params = json.dumps(message.get("params", {}), separators=(",", ":"))
            self.say(f"      <- {message['method']} {params[:90]}")

    def step(self, label: str, summary: str) -> None:
        self.say(f"{self.step_no:>2}  {label:<42} {summary}")
        self.step_no += 1

    def expect(self, condition: bool, what: str) -> None:
        if not condition:
            raise TourFailure(what)

    def call(self, method: str, params: Message | None = None) -> Any:
        """One request, awaited; the step methods below build the params.

        `spec:docs/specification/2025-11-25/basic/index.mdx:46`
        "include a string or integer ID"
        """
        return self.session.request(method, params)

    def drain(self) -> None:
        while not self.session.wire.notifications.empty():
            self.session.wire.notifications.get_nowait()

    def wait_for_progress(self, token: str, want: int | None = None) -> Message:
        """Read notifications until progress for `token` arrives (the `want`th, if given).

        `spec:docs/specification/2025-11-25/basic/utilities/progress.mdx:43`
        "method": "notifications/progress"
        """
        notes = self.session.wire.notifications
        deadline = time.monotonic() + NOTE_WAIT
        while True:
            try:
                note = notes.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                raise TourFailure(f"no progress for {token} within {NOTE_WAIT} s") from None
            params: Message = note.get("params", {})
            if note.get("method") == "notifications/progress" and (
                params.get("progressToken") == token
            ):
                if want is None or params.get("progress") == want:
                    return params

    # -- steps -------------------------------------------------------------------------

    def run(self) -> None:
        self.lifecycle()
        self.tools()
        self.resources()
        self.prompts()
        self.utilities()
        self.long_running()
        self.cancelled()

    def lifecycle(self) -> None:
        """`initialize`, `notifications/initialized` (sent by the session) and `ping`.

        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:57`
        "method": "initialize"
        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:153`
        "method": "notifications/initialized"
        `spec:docs/specification/2025-11-25/basic/utilities/ping.mdx:23`
        "method": "ping"
        """
        result = self.session.initialize(self.capabilities)
        info = result.get("serverInfo", {})
        self.step("initialize", f"version {result['protocolVersion']}, server {info.get('name')}")
        self.step("notifications/initialized", "sent")
        self.expect(self.call("ping") == {}, "ping must be answered with {}")
        self.step("ping", "{}")

    def tools(self) -> None:
        """`tools/list`, then `tools/call` of `echo` and `get-sum`.

        `spec:docs/specification/2025-11-25/server/tools.mdx:66`
        "method": "tools/list"
        `spec:docs/specification/2025-11-25/server/tools.mdx:122`
        "method": "tools/call"
        """
        tools = self.call("tools/list")["tools"]
        names = {t["name"] for t in tools}
        needed = {"echo", "get-sum", "trigger-long-running-operation"}
        self.expect(needed <= names, f"tools/list lacks {sorted(needed - names)}")
        self.step("tools/list", f"{len(tools)} tools")
        echo = self.call("tools/call", {"name": "echo", "arguments": {"message": "hello"}})
        text = echo["content"][0]["text"]
        self.expect(text == "Echo: hello", "echo must say Echo: hello")
        self.step("tools/call echo", text)
        total = self.call("tools/call", {"name": "get-sum", "arguments": {"a": 2, "b": 3}})
        text = total["content"][0]["text"]
        self.expect("5" in text, "get-sum of 2 and 3 must say 5")
        self.step("tools/call get-sum", text)

    def resources(self) -> None:
        """The resource requests: list, templates, read, subscribe, unsubscribe.

        `spec:docs/specification/2025-11-25/server/resources.mdx:96`
        "method": "resources/list"
        `spec:docs/specification/2025-11-25/server/resources.mdx:178`
        "method": "resources/templates/list"
        `spec:docs/specification/2025-11-25/server/resources.mdx:141`
        "method": "resources/read"
        `spec:docs/specification/2025-11-25/server/resources.mdx:232`
        "method": "resources/subscribe"
        `spec:schema/2025-11-25/schema.ts:769`
        method: "resources/unsubscribe"
        """
        resources = self.call("resources/list")["resources"]
        self.expect(any(r["uri"] == STATIC_DOC for r in resources), f"no resource {STATIC_DOC}")
        self.step("resources/list", f"{len(resources)} resources")
        templates = self.call("resources/templates/list")["resourceTemplates"]
        self.expect(len(templates) > 0, "no resource templates")
        self.step("resources/templates/list", f"{len(templates)} templates")
        contents = self.call("resources/read", {"uri": STATIC_DOC})["contents"]
        self.expect(contents[0]["uri"] == STATIC_DOC and bool(contents[0].get("text")),
                    "resources/read must return the document's text")
        self.step("resources/read", f"{len(contents[0]['text'])} characters of text")
        self.expect(self.call("resources/subscribe", {"uri": STATIC_DOC}) == {}, "subscribe -> {}")
        self.step("resources/subscribe", "{}")
        self.expect(self.call("resources/unsubscribe", {"uri": STATIC_DOC}) == {},
                    "unsubscribe -> {}")
        self.step("resources/unsubscribe", "{}")

    def prompts(self) -> None:
        """`prompts/list`, then `prompts/get` of `simple-prompt` and `args-prompt`.

        `spec:docs/specification/2025-11-25/server/prompts.mdx:59`
        "method": "prompts/list"
        `spec:docs/specification/2025-11-25/server/prompts.mdx:110`
        "method": "prompts/get"
        """
        prompts = self.call("prompts/list")["prompts"]
        needed = {"simple-prompt", "args-prompt", COMPLETABLE_PROMPT}
        missing = needed - {p["name"] for p in prompts}
        self.expect(not missing, f"prompts/list lacks {sorted(missing)}")
        self.step("prompts/list", f"{len(prompts)} prompts")
        simple = self.call("prompts/get", {"name": "simple-prompt"})["messages"]
        self.expect(len(simple) > 0, "simple-prompt returned no messages")
        self.step("prompts/get simple-prompt", f"{len(simple)} message")
        city = {"name": "args-prompt", "arguments": {"city": "Oslo"}}
        text = self.call("prompts/get", city)["messages"][0]["content"]["text"]
        self.expect("Oslo" in text, "args-prompt must use the city")
        self.step("prompts/get args-prompt", text)

    def utilities(self) -> None:
        """`completion/complete` and `logging/setLevel`.

        `spec:docs/specification/2025-11-25/server/utilities/completion.mdx:49`
        "method": "completion/complete"
        `spec:docs/specification/2025-11-25/server/utilities/logging.mdx:57`
        "method": "logging/setLevel"
        """
        ask = {
            "ref": {"type": "ref/prompt", "name": COMPLETABLE_PROMPT},
            "argument": {"name": "department", "value": "E"},
        }
        values = self.call("completion/complete", ask)["completion"]["values"]
        self.expect("Engineering" in values, "department E must complete Engineering")
        self.step("completion/complete department=E", ", ".join(values))
        self.expect(self.call("logging/setLevel", {"level": "debug"}) == {}, "setLevel -> {}")
        self.step("logging/setLevel debug", "{}")

    def long_running(self) -> None:
        """A `tools/call` with a `progressToken`, which the server answers with progress.

        `spec:docs/specification/2025-11-25/basic/utilities/progress.mdx:27`
        "progressToken": "abc123"
        """
        self.drain()
        done = self.call("tools/call", {
            "name": "trigger-long-running-operation",
            "arguments": {"duration": 1, "steps": 2},
            "_meta": {"progressToken": "tour-done"},
        })
        self.expect("completed" in done["content"][0]["text"], "the operation must complete")
        tokens = []
        while not self.session.wire.notifications.empty():
            note = self.session.wire.notifications.get_nowait()
            tokens.append(note.get("params", {}).get("progressToken"))
        self.expect(tokens.count("tour-done") == 2, "expected two progress notifications")
        self.step("tools/call long-running (done)", "completed, 2 progress notifications")

    def cancelled(self) -> None:
        """The same call, cancelled after its first progress notification.

        `spec:docs/specification/2025-11-25/basic/utilities/cancellation.mdx:22`
        "method": "notifications/cancelled"
        """
        self.drain()
        pending = self.session.start_request("tools/call", {
            "name": "trigger-long-running-operation",
            "arguments": {"duration": 1, "steps": 2},
            "_meta": {"progressToken": "tour-cancel"},
        })
        self.wait_for_progress("tour-cancel", 1)
        sent = self.session.cancel(pending, "the tour cancels after the first progress")
        self.expect(sent, "the request had already finished before it could be cancelled")
        try:
            pending.wait(0)
        except Cancelled:
            pass
        else:
            raise TourFailure("a cancelled request must stop waiting")
        # The server's tool ignores the cancellation and finishes its second step (measured).
        self.wait_for_progress("tour-cancel", 2)
        time.sleep(0.3)  # room for a late reply, which the wire drops and reports
        self.step("tools/call long-running (cancelled)", "cancelled after progress 1")


def run_tour(
    command: Sequence[str], out: TextIO, report: Callable[[str], None] | None = None,
    caps: Sequence[str] = (),
) -> int:
    """Run the tour against the server command; 0 if every step got its expected reply.

    With `caps` the client declares them and answers what the server then asks (phase 3), so the
    server's re-lists and requests interleave with the tour's and its ids no longer run 0 to 16.
    """
    holder: list[Tour] = []

    def observe(arrow: str, message: Any) -> None:
        if holder:
            holder[0].observe(arrow, message)

    kwargs: dict[str, Any] = {"observer": observe}
    if report is not None:
        kwargs["report"] = report
    handlers = Handlers(caps, report=report or stderr_report) if caps else None
    if handlers is not None:
        kwargs.update(on_request=handlers.handle_request,
                      on_notification=handlers.handle_notification)
    session = Session.open(command, **kwargs)
    if handlers is not None:
        handlers.attach(session.wire)
    tour = Tour(session, out, None if handlers is None else handlers.capabilities)
    holder.append(tour)
    status = 0
    try:
        tour.run()
    except Exception as exc:  # any failed step: say which, then still shut down
        failure = f"{tour.step_no:>2}  FAILED  {type(exc).__name__}: {exc}"
        tour.say(failure)
        (report or stderr_report)(f"tour failed at step {failure.strip()}")
        status = 1
    code = session.close()
    tour.say(f"    shutdown: server exited with status {code}")
    return status
