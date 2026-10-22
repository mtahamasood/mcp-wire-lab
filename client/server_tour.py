"""The server tour (phase 3 D4): the everything server's requests and notifications to the client.

Declares every capability, answers what the server asks, and calls the tools that make the server
speak first: roots, sampling, elicitation (form, multi-step and URL), log messages, list changes
and a resource update. It avoids the server's timer tools (`toggle-*`), and it waits for each
step's server traffic to settle before the next, so the same requests carry the same ids on every
run (the order of the frames in between can differ). It exits 0 only if every step saw the
server traffic it expects.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from typing import Any, TextIO

from client.handlers import CAPABILITIES, Handlers
from client.http_wire import HttpSession
from client.session import Session
from client.wire import Message, stderr_report

STATIC_DOC = "demo://resource/static/document/architecture.md"
SETTLE = 5.0  # seconds to wait for server traffic a step needs to see
OTHER_ROOT: Message = {"uri": "file:///wire-lab/other", "name": "other"}
GATED_TOOLS = (
    "get-roots-list", "trigger-sampling-request", "trigger-elicitation-request",
    "trigger-multi-step-elicitation", "trigger-url-elicitation",
)
NOTE = "notifications/message"
ELICIT = "elicitation/create"


class TourFailure(Exception):
    """A step did not see the server traffic it expects."""


def settle_after_initialized(handlers: Handlers, caps: Sequence[str]) -> None:
    """Wait for what the server sends right after `initialized`, then for the re-lists.

    The server registers the tools the declared capabilities allow (one `tools/list_changed`
    each, no debounce) and, if the client declared roots, asks `roots/list` 350 ms later and
    logs it. A raw client that sent requests before this settles would see its ids interleave
    with the re-lists, so the tours wait.
    """
    gating = [c for c in caps if c in CAPABILITIES]
    if gating:
        handlers.wait_count("notifications/tools/list_changed", 1, SETTLE)
    if "roots" in caps:
        handlers.wait_count("roots/list", 1, SETTLE)
        handlers.wait_count(NOTE, 1, SETTLE)
    handlers.wait_idle(SETTLE)


class ServerTour:
    def __init__(self, session: Session, handlers: Handlers, out: TextIO) -> None:
        self.session = session
        self.handlers = handlers
        self.out = out
        self.step_no = 0
        self._print_lock = threading.Lock()

    def say(self, text: str) -> None:
        with self._print_lock:
            print(text, file=self.out, flush=True)

    def step(self, label: str, summary: str) -> None:
        self.say(f"{self.step_no:>2}  {label:<42} {summary}")
        self.step_no += 1

    def expect(self, condition: bool, what: str) -> None:
        if not condition:
            raise TourFailure(what)

    def seen(self, method: str) -> int:
        return self.handlers.counts[method]

    def tool(self, name: str, arguments: Message | None = None) -> str:
        """Call a tool and return the first text of its result; an error result is a failure."""
        result = self.session.request(
            "tools/call", {"name": name, "arguments": arguments or {}})
        self.expect(not result.get("isError"), f"{name} returned an error: {result}")
        text: str = result["content"][0]["text"]
        return text

    def settle(self, what: str) -> None:
        self.expect(self.handlers.wait_idle(SETTLE), f"{what}: the client did not go idle")

    def run(self) -> None:
        self.opening()
        self.roots()
        self.sampling()
        self.elicitation()
        self.logging()
        self.list_changes()
        self.resource_update()
        self.roots_change()

    def opening(self) -> None:
        """`initialize` with every capability, then the server's roots sync and tool burst.

        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:57`
        "method": "initialize"
        """
        result = self.session.initialize(self.handlers.capabilities)
        info = result.get("serverInfo", {})
        self.step("initialize (all capabilities)", f"version {result['protocolVersion']}, "
                  f"server {info.get('name')}")
        self.step("notifications/initialized", "sent")
        settle_after_initialized(self.handlers, self.handlers.caps)
        self.expect(self.seen("roots/list") == 1, "the server did not ask roots/list after init")
        self.expect(self.seen(NOTE) == 1, "no log message after the roots sync")
        self.step("roots/list (server asked)", "answered, 1 root")
        listed = self.handlers.lists.get("tools", [])
        missing = [t for t in GATED_TOOLS if t not in listed]
        self.expect(not missing, f"tools/list after the burst lacks {missing}")
        self.expect(self.handlers.relists.count("tools") >= 1, "no re-list after list_changed")
        self.step("tools/list_changed burst", f"re-listed, {len(listed)} tools")

    def roots(self) -> None:
        """`get-roots-list` makes the server ask `roots/list` again.

        `spec:docs/specification/2025-11-25/client/roots.mdx:55`
        "method": "roots/list"
        """
        before = self.seen("roots/list")
        text = self.tool("get-roots-list")
        self.expect(self.seen("roots/list") == before + 1, "get-roots-list asked no roots/list")
        self.expect("wire-lab" in text, f"the roots were not reported back: {text!r}")
        self.step("tools/call get-roots-list", text.splitlines()[0])

    def sampling(self) -> None:
        """`trigger-sampling-request` makes the server ask `sampling/createMessage`.

        `spec:docs/specification/2025-11-25/client/sampling.mdx:101`
        "method": "sampling/createMessage",
        """
        before = self.seen("sampling/createMessage")
        text = self.tool("trigger-sampling-request", {"prompt": "hello from the wire lab"})
        self.expect(self.seen("sampling/createMessage") == before + 1, "no sampling request")
        self.expect("canned reply from wire-lab-raw" in text, f"canned reply missing: {text!r}")
        self.step("tools/call trigger-sampling-request", "sampling answered with canned text")

    def elicitation(self) -> None:
        """Form, two-round form and URL elicitation: `elicitation/create` in both modes.

        `spec:docs/specification/2025-11-25/client/elicitation.mdx:245`
        "method": "elicitation/create",
        """
        before = self.seen(ELICIT)
        text = self.tool("trigger-elicitation-request")
        self.expect(self.seen(ELICIT) == before + 1, "no form elicitation request")
        self.expect("provided the requested information" in text, f"form not accepted: {text!r}")
        self.step("tools/call trigger-elicitation-request", "form accepted from defaults")
        text = self.tool("trigger-multi-step-elicitation")
        self.expect(self.seen(ELICIT) == before + 3, "multi-step asked other than two rounds")
        self.step("tools/call trigger-multi-step-elicitation", "two rounds answered")
        text = self.tool("trigger-url-elicitation", {"url": "https://example.com/wire-lab"})
        self.expect(self.seen(ELICIT) == before + 4, "no URL elicitation request")
        self.expect("declined" in text, f"the URL elicitation was not declined: {text!r}")
        self.step("tools/call trigger-url-elicitation", "URL mode declined")

    def logging(self) -> None:
        """`logging/setLevel`, then one `notifications/message` at each of eight levels.

        `spec:docs/specification/2025-11-25/server/utilities/logging.mdx:57`
        "method": "logging/setLevel"
        """
        self.expect(self.session.request("logging/setLevel", {"level": "debug"}) == {},
                    "setLevel -> {}")
        self.step("logging/setLevel debug", "{}")
        before = self.seen(NOTE)
        self.tool("trigger-log-messages")
        self.expect(self.seen(NOTE) == before + 8, "expected a message at each of 8 levels")
        self.step("tools/call trigger-log-messages", "8 notifications/message")

    def list_changes(self) -> None:
        """`trigger-list-changed` for each list; the client re-requests the one that changed."""
        for kind in ("tools", "prompts", "resources"):
            note = f"notifications/{kind}/list_changed"
            before, relisted = self.seen(note), self.handlers.relists.count(kind)
            self.tool("trigger-list-changed", {"list": kind})
            self.settle(f"{kind} list_changed")
            self.expect(self.seen(note) == before + 1, f"no {note}")
            self.expect(self.handlers.relists.count(kind) == relisted + 1, f"{kind} not re-listed")
            self.step(f"tools/call trigger-list-changed {kind}", f"{kind}/list re-requested")

    def resource_update(self) -> None:
        """Subscribe, then `trigger-resource-update`: the client re-reads the resource.

        `spec:docs/specification/2025-11-25/server/resources.mdx:232`
        "method": "resources/subscribe"
        """
        self.expect(self.session.request("resources/subscribe", {"uri": STATIC_DOC}) == {},
                    "subscribe -> {}")
        self.step("resources/subscribe", "{}")
        before = self.seen("notifications/resources/updated")
        self.tool("trigger-resource-update", {"uri": STATIC_DOC})
        self.settle("resources/updated")
        self.expect(self.seen("notifications/resources/updated") == before + 1, "no update")
        self.expect(self.handlers.rereads == [STATIC_DOC], "the resource was not re-read")
        self.step("tools/call trigger-resource-update", "resources/updated, re-read")

    def roots_change(self) -> None:
        """Change the roots: `notifications/roots/list_changed`, and the server asks again."""
        asked, logged = self.seen("roots/list"), self.seen(NOTE)
        self.handlers.set_roots([*self.handlers.roots, OTHER_ROOT])
        self.step("notifications/roots/list_changed", "sent, 2 roots now")
        self.expect(self.handlers.wait_count("roots/list", asked + 1, SETTLE),
                    "the server did not ask roots/list after the change")
        self.expect(self.handlers.wait_count(NOTE, logged + 1, SETTLE), "no log after the change")
        self.settle("roots change")
        self.step("roots/list (server asked)", "answered, 2 roots")


def run_server_tour(
    command: Sequence[str], out: TextIO, caps: Sequence[str] = CAPABILITIES,
    report: Callable[[str], None] | None = None, url: str | None = None,
) -> int:
    """Run the server tour against the server command (or, with `url`, over Streamable HTTP,
    phase 7 D10); 0 if every step saw its traffic."""
    say_lock = threading.Lock()

    def say(text: str) -> None:
        with say_lock:
            print(f"      {text}", file=out, flush=True)

    handlers = Handlers(caps, say=say, report=report or stderr_report)
    callbacks: dict[str, Any] = {
        "report": report or stderr_report, "on_request": handlers.handle_request,
        "on_notification": handlers.handle_notification}
    session = Session.open(command, **callbacks) if url is None else HttpSession.connect(
        url, **callbacks)
    handlers.attach(session.wire)
    tour = ServerTour(session, handlers, out)
    status = 0
    try:
        tour.run()
    except Exception as exc:  # any failed step: say which, then still shut down
        failure = f"{tour.step_no:>2}  FAILED  {type(exc).__name__}: {exc}"
        tour.say(failure)
        (report or stderr_report)(f"server tour failed at step {failure.strip()}")
        status = 1
    code = session.close()
    tour.say(f"    shutdown: server exited with status {code}")
    return status

