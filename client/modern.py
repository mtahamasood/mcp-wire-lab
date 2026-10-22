"""The raw client in the 2026-07-28 era (phase 6 part A, D2 to D7): one module, so the era diff
isolates what the protocol changed. `client/wire.py` is reused unchanged.

What replaced what, from the client's side:

- `initialize` and `notifications/initialized` -> `server/discover` (`ModernSession.discover`);
- the session -> an envelope in `params._meta` of every request (`envelope`);
- server-to-client requests -> `input_required` results and a retry (`request_with_input`);
- `resources/subscribe` and unsolicited list changes -> `subscriptions/listen` (`Subscription`);
- tasks -> the `io.modelcontextprotocol/tasks` extension (`TASKS_EXTENSION`).
"""

from __future__ import annotations

import copy
import json
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, TextIO

from client.handlers import Handlers
from client.session import CLIENT_INFO, GRACE_SECONDS, NotInitialized, Session, UnsupportedVersion
from client.tour import NOTE_WAIT, STATIC_DOC, Tour, TourFailure
from client.wire import DEFAULT_TIMEOUT, Message, Pending, RpcError, key_of, stderr_report

ERA = "2026-07-28"
META = "io.modelcontextprotocol/"
TASKS_EXTENSION = "io.modelcontextprotocol/tasks"
SUBSCRIPTION_ID = META + "subscriptionId"
LISTEN_WAIT = 5.0  # seconds to wait for the acknowledgment of a subscriptions/listen
UNSUPPORTED_VERSION = -32022
MISSING_CAPABILITY = -32021


class NotDiscovered(NotInitialized):
    """A request was attempted before the reply to `server/discover` had arrived."""


class InvalidResult(RuntimeError):
    """A result whose `resultType` the client cannot accept for that request."""


class TooManyRounds(RuntimeError):
    """A multi-round request was still `input_required` after `max_rounds` requests."""


class CannotAnswer(RuntimeError):
    """An input request the client has no answer for."""


class InputRequired:
    """A result of type `input_required`: what the server asks, and its opaque `requestState`."""

    def __init__(self, result: Message) -> None:
        self.result = result
        self.input_requests: Message = result.get("inputRequests") or {}
        self.request_state: Any = result.get("requestState")


def envelope(
    params: Message | None, capabilities: Message, *, log_level: str | None = None
) -> Message:
    """A copy of `params` whose `_meta` carries the per-request envelope (D2).

    The reserved keys are always the client's; any other key the caller put in `_meta` (a
    `progressToken`) is kept.

    `spec:docs/specification/2026-07-28/basic/index.mdx:368` "fields marked as required"
    """
    out: Message = copy.deepcopy(params) if params else {}
    meta: Message = dict(out.get("_meta") or {})
    meta[META + "protocolVersion"] = ERA
    meta[META + "clientInfo"] = dict(CLIENT_INFO)
    meta[META + "clientCapabilities"] = copy.deepcopy(capabilities)
    if log_level is not None:
        meta[META + "logLevel"] = log_level
    out["_meta"] = meta
    return out


def with_tasks(capabilities: Message) -> Message:
    """`capabilities` plus the tasks extension (D2, D7)."""
    out = copy.deepcopy(capabilities)
    out["extensions"] = {**out.get("extensions", {}), TASKS_EXTENSION: {}}
    return out


def declares_tasks(capabilities: Message) -> bool:
    return TASKS_EXTENSION in (capabilities.get("extensions") or {})


def classify_result(result: Any, tasks_declared: bool) -> InputRequired | Message:
    """Decide the outcome by `resultType` (D3).

    `complete` or absent -> the result; `input_required` -> an InputRequired; `task` only when the
    request declared the tasks extension; anything else -> InvalidResult.

    `spec:schema/2026-07-28/schema.ts:232` "the client MUST treat the absent field"
    """
    if not isinstance(result, dict):
        raise InvalidResult(f"the result is not an object: {json.dumps(result)[:80]}")
    kind = result.get("resultType", "complete")
    if kind == "complete":
        return result
    if kind == "input_required":
        return InputRequired(result)
    if kind == "task" and tasks_declared:
        return result
    if kind == "task":
        raise InvalidResult("resultType 'task' for a request that did not declare the tasks "
                            "extension")
    raise InvalidResult(f"unrecognized resultType {kind!r}")


class Subscription:
    """One `subscriptions/listen` stream (D5): its id, the acknowledged filter, its messages."""

    def __init__(self, session: ModernSession, pending: Pending, acknowledged: Message) -> None:
        self.session = session
        self.pending = pending
        self.id = pending.id
        self.filter = acknowledged
        self.closed = False

    def wait_for(self, method: str, timeout: float = NOTE_WAIT,
                 match: Callable[[Message], bool] | None = None) -> Message:
        """The next notification of `method` on this stream (its params); TimeoutError if none."""
        return self.session.registry.wait(self.id, method, timeout, match)

    def seen(self) -> list[Message]:
        return self.session.registry.messages(self.id)

    def close(self) -> bool:
        """Cancel the listen request: `notifications/cancelled` with its id; stop waiting.

        `spec:docs/specification/2026-07-28/basic/transports/stdio.mdx:82`
        "MUST NOT"
        """
        if self.closed:
            return False
        self.closed = True
        return self.session.cancel(self.pending, "the client closes the subscription")


class Registry:
    """Notifications that carry a subscription id, by that id alone (D5).

    Fed from the wire's reader thread. A message is filed under `key_of(id)`, so `3` and `"3"`
    are different streams, whether or not anyone is listening yet.
    """

    def __init__(self, downstream: Callable[[Message], None] | None = None) -> None:
        self._cond = threading.Condition()
        self._by_id: dict[Any, list[Message]] = {}
        self._downstream = downstream

    def feed(self, message: Message) -> None:
        params = message.get("params")
        meta = params.get("_meta") if isinstance(params, dict) else None
        if isinstance(meta, dict) and SUBSCRIPTION_ID in meta:
            with self._cond:
                self._by_id.setdefault(key_of(meta[SUBSCRIPTION_ID]), []).append(message)
                self._cond.notify_all()
        if self._downstream is not None:
            self._downstream(message)

    def messages(self, stream_id: Any) -> list[Message]:
        with self._cond:
            return list(self._by_id.get(key_of(stream_id), []))

    def wait(self, stream_id: Any, method: str, timeout: float,
             match: Callable[[Message], bool] | None = None) -> Message:
        """Take the first unread message of `method` for the stream; TimeoutError if none."""
        deadline = time.monotonic() + timeout
        key = key_of(stream_id)
        with self._cond:
            while True:
                for i, message in enumerate(self._by_id.get(key, [])):
                    params: Message = message.get("params") or {}
                    if message.get("method") == method and (match is None or match(params)):
                        del self._by_id[key][i]
                        return params
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(f"no {method} on subscription {stream_id!r} within "
                                       f"{timeout} s")
                self._cond.wait(left)


class ModernSession(Session):
    """The 2026-07-28 session: discover first, then requests that each carry the envelope."""

    registry: Registry
    capabilities: Message

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.capabilities = {}
        self.registry = Registry()
        self.discovered: Message | None = None

    @classmethod
    def open_modern(
        cls, command: Sequence[str], *, capabilities: Message | None = None,
        report: Callable[[str], None] = stderr_report,
        observer: Callable[[str, Any], None] | None = None,
        on_notification: Callable[[Message], None] | None = None,
        grace: float = GRACE_SECONDS, timeout: float = DEFAULT_TIMEOUT,
    ) -> ModernSession:
        """Launch the server command; notifications with a subscription id are filed (D5)."""
        registry = Registry(on_notification)
        session = cls.open(command, report=report, observer=observer,
                           on_notification=registry.feed, grace=grace, timeout=timeout)
        assert isinstance(session, ModernSession)
        session.registry = registry
        session.capabilities = {} if capabilities is None else capabilities
        return session

    # -- the opening exchange (D3) ----------------------------------------------------------

    def discover(self) -> Message:
        """`server/discover`, the version check; no other request goes before its reply.

        A `DiscoverResult` whose `supportedVersions` holds 2026-07-28 makes the session ready;
        any other list, or a -32022 error, raises UnsupportedVersion naming what the server
        offered; any other error raises with a hint to try `--era 2025-11-25`. There is no
        fallback.

        `spec:docs/specification/2026-07-28/basic/versioning.mdx:167`
        "SHOULD** send `server/discover` first"
        """
        params = envelope({}, self.capabilities)
        try:
            raw = self.wire.request("server/discover", params, self.timeout)
        except RpcError as exc:
            error = exc.error if isinstance(exc.error, dict) else {}
            if error.get("code") == UNSUPPORTED_VERSION:
                offered = (error.get("data") or {}).get("supported")
                raise UnsupportedVersion(
                    f"the server does not speak {ERA}; it offered {json.dumps(offered)}") from exc
            raise RuntimeError(
                f"server/discover failed ({error.get('message', exc)}); this server may speak "
                "only the 2025 era: try --era 2025-11-25") from exc
        result = classify_result(raw, False)
        if isinstance(result, InputRequired):
            raise InvalidResult("server/discover answered input_required")
        offered = result.get("supportedVersions")
        if not isinstance(offered, list) or ERA not in offered:
            raise UnsupportedVersion(
                f"the server does not speak {ERA}; it offered {json.dumps(offered)}")
        self.discovered = result
        self.ready = True
        return result

    def _require_ready(self) -> None:
        if not self.ready:
            raise NotDiscovered("no requests before the reply to server/discover has arrived")

    # -- requests (D2, D3) -------------------------------------------------------------------

    def start_request(
        self, method: str, params: Message | None = None, *,
        capabilities: Message | None = None, log_level: str | None = None,
    ) -> Pending:
        """Send a request after discovery, its params wrapped in the envelope (D2)."""
        self._require_ready()
        caps = self.capabilities if capabilities is None else capabilities
        return self.wire.start_request(method, envelope(params, caps, log_level=log_level))

    def request(
        self, method: str, params: Message | None = None, timeout: float | None = None,
        *, capabilities: Message | None = None, log_level: str | None = None,
    ) -> Any:
        """Send a request, wait, and classify the result (D3): a result dict or an InputRequired.

        A JSON-RPC error raises RpcError.
        """
        caps = self.capabilities if capabilities is None else capabilities
        pending = self.start_request(method, params, capabilities=caps, log_level=log_level)
        try:
            raw = pending.wait(self.timeout if timeout is None else timeout)
        except TimeoutError:
            try:
                self.cancel(pending, "timeout")
            except OSError:
                pass
            raise
        return classify_result(raw, declares_tasks(caps))

    def call(self, method: str, params: Message | None = None, **options: Any) -> Message:
        """`request` for a method that must answer `complete`; an input_required is an error."""
        result = self.request(method, params, **options)
        if isinstance(result, InputRequired):
            raise InvalidResult(f"{method} answered input_required where a result was expected")
        assert isinstance(result, dict)
        return result

    # -- multi-round requests (D4) -----------------------------------------------------------

    def request_with_input(
        self, method: str, params: Message | None, answer: Callable[[Message], Message] | None,
        max_rounds: int = 5, *, capabilities: Message | None = None,
        say: Callable[[str], None] | None = None, **options: Any,
    ) -> Message:
        """Send a request; while it is `input_required`, answer and retry (D4).

        The retry is the same method and params plus the top-level `inputResponses` (one entry per
        `inputRequests` key, the value being `answer(input_request)`) and `requestState` copied
        byte for byte when present (opaque: never parsed). Each retry is a fresh id with the full
        envelope. At most `max_rounds` requests are sent.

        `spec:docs/specification/2026-07-28/server/tools.mdx:178`
        "clients include `inputResponses` and"
        """
        base = copy.deepcopy(params) if params else {}
        current = dict(base)
        for number in range(1, max_rounds + 1):
            result = self.request(method, current, capabilities=capabilities, **options)
            if not isinstance(result, InputRequired):
                done: Message = result
                return done
            if say is not None:
                say(f"round {number}: {', '.join(result.input_requests) or '(state only)'}")
            if number == max_rounds:
                break
            responses: Message = {}
            for key, input_request in result.input_requests.items():
                if answer is None:
                    raise CannotAnswer(f"no answer function for input request {key!r}")
                responses[key] = answer(input_request)
            current = dict(base)
            current["inputResponses"] = responses
            if result.request_state is not None:
                current["requestState"] = result.request_state
        raise TooManyRounds(f"{method} was still input_required after {max_rounds} requests")

    # -- subscriptions (D5) ------------------------------------------------------------------

    def listen(self, notifications: Message, timeout: float = LISTEN_WAIT) -> Subscription:
        """Open a `subscriptions/listen` stream and wait for its acknowledgment (D5).

        Does not wait for the response (it only marks a graceful end). The acknowledgment is the
        `notifications/subscriptions/acknowledged` whose subscription id equals the listen
        request's id, type included.

        `spec:docs/specification/2026-07-28/basic/transports/stdio.mdx:51`
        "io.modelcontextprotocol/subscriptionId"
        """
        pending = self.start_request("subscriptions/listen", {"notifications": notifications})
        try:
            ack = self.registry.wait(pending.id, "notifications/subscriptions/acknowledged",
                                     timeout)
        except TimeoutError:
            self.cancel(pending, "no acknowledgment")
            raise
        return Subscription(self, pending, ack.get("notifications", ack))


# -- answering input requests (D4) ---------------------------------------------------------


def default_answer(handlers: Handlers) -> Callable[[Message], Message]:
    """Phase 3's handlers, unchanged, applied to one input request (D4)."""

    def answer(input_request: Message) -> Message:
        synthetic = {"jsonrpc": "2.0", "id": 0, "method": input_request.get("method"),
                     "params": input_request.get("params") or {}}
        reply = handlers.answer(synthetic)
        if "error" in reply:
            raise CannotAnswer(f"cannot answer {input_request.get('method')}: "
                               f"{reply['error'].get('message')}")
        result: Message = reply["result"]
        return result

    return answer


# -- the tour (D6) -------------------------------------------------------------------------


class ModernTour(Tour):
    """The 2026 tour: the 2025 tour's steps with the new era's messages."""

    session: ModernSession

    def __init__(self, session: ModernSession, out: TextIO, handlers: Handlers) -> None:
        super().__init__(session, out, session.capabilities)
        self.handlers = handlers
        self.subscription: Subscription | None = None

    def call(self, method: str, params: Message | None = None, **options: Any) -> Any:
        return self.session.call(method, params, **options)

    def tool(self, name: str, arguments: Message | None = None, **options: Any) -> Message:
        return self.session.call(
            "tools/call", {"name": name, "arguments": arguments or {}}, **options)

    def count_messages(self) -> int:
        count = 0
        while not self.session.wire.notifications.empty():
            note = self.session.wire.notifications.get_nowait()
            count += note.get("method") == "notifications/message"
        return count

    def run(self) -> None:
        self.discovery()
        self.tools()
        self.resources()
        self.prompts()
        self.utilities()
        self.log_levels()
        self.long_running()
        self.cancelled()
        self.subscriptions()
        self.input_required()
        self.close_subscription()

    def discovery(self) -> None:
        """`server/discover`: the first message; replaces `initialize`.

        `spec:docs/specification/2026-07-28/basic/versioning.mdx:167`
        "SHOULD** send `server/discover` first"
        """
        result = self.session.discover()
        info = (result.get("_meta") or {}).get(META + "serverInfo", {})
        self.step("server/discover", f"versions {result['supportedVersions']}, "
                  f"server {info.get('name')}, ttlMs {result.get('ttlMs')}")

    def tools(self) -> None:
        tools = self.call("tools/list")["tools"]
        names = {t["name"] for t in tools}
        needed = {"echo", "get-sum", "trigger-long-running-operation", "trigger-log-messages",
                  "trigger-list-changed", "trigger-resource-update", "get-roots-list",
                  "trigger-sampling-request", "trigger-elicitation-request",
                  "trigger-multi-step-elicitation"}
        self.expect(needed <= names, f"tools/list lacks {sorted(needed - names)}")
        self.step("tools/list", f"{len(tools)} tools")
        text = self.tool("echo", {"message": "hello"})["content"][0]["text"]
        self.expect(text == "Echo: hello", "echo must say Echo: hello")
        self.step("tools/call echo", text)
        text = self.tool("get-sum", {"a": 2, "b": 3})["content"][0]["text"]
        self.expect("5" in text, "get-sum of 2 and 3 must say 5")
        self.step("tools/call get-sum", text)

    def resources(self) -> None:
        resources = self.call("resources/list")["resources"]
        self.expect(any(r["uri"] == STATIC_DOC for r in resources), f"no resource {STATIC_DOC}")
        self.step("resources/list", f"{len(resources)} resources")
        templates = self.call("resources/templates/list")["resourceTemplates"]
        self.expect(len(templates) > 0, "no resource templates")
        self.step("resources/templates/list", f"{len(templates)} templates")
        result = self.call("resources/read", {"uri": STATIC_DOC})
        contents = result["contents"]
        self.expect(contents[0]["uri"] == STATIC_DOC and bool(contents[0].get("text")),
                    "resources/read must return the document's text")
        self.step("resources/read", f"{len(contents[0]['text'])} characters of text, "
                  f"ttlMs {result.get('ttlMs')}, cacheScope {result.get('cacheScope')}")

    def prompts(self) -> None:
        prompts = self.call("prompts/list")["prompts"]
        needed = {"simple-prompt", "args-prompt"}
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
        ask = {
            "ref": {"type": "ref/prompt", "name": "completable-prompt"},
            "argument": {"name": "department", "value": "E"},
        }
        values = self.call("completion/complete", ask)["completion"]["values"]
        self.expect("Engineering" in values, "department E must complete Engineering")
        self.step("completion/complete department=E", ", ".join(values))

    def log_levels(self) -> None:
        """The log level is per request: absent means no `notifications/message` (replaces
        `logging/setLevel`).

        `spec:docs/specification/2026-07-28/server/utilities/logging.mdx:63`
        "io.modelcontextprotocol/logLevel"
        """
        self.drain()
        self.tool("trigger-log-messages")
        got = self.count_messages()
        self.expect(got == 0, f"no log level was sent, yet {got} notifications/message arrived")
        self.step("tools/call trigger-log-messages", "no logLevel: 0 notifications/message")
        self.tool("trigger-log-messages", log_level="warning")
        got = self.count_messages()
        self.expect(got == 5, f"logLevel warning must give 5 notifications/message, got {got}")
        self.step("tools/call trigger-log-messages", "logLevel warning: 5 notifications/message")

    def subscriptions(self) -> None:
        """`subscriptions/listen`, then each change the server announces on that stream."""
        sub = self.session.listen({
            "toolsListChanged": True, "promptsListChanged": True,
            "resourcesListChanged": True, "resourceSubscriptions": [STATIC_DOC]})
        self.subscription = sub
        self.step("subscriptions/listen", f"acknowledged, subscriptionId {sub.id}")
        for kind in ("tools", "prompts", "resources"):
            self.tool("trigger-list-changed", {"list": kind})
            sub.wait_for(f"notifications/{kind}/list_changed")
            self.step(f"tools/call trigger-list-changed {kind}",
                      f"notifications/{kind}/list_changed on subscription {sub.id}")
        self.tool("trigger-resource-update", {"uri": STATIC_DOC})
        params = sub.wait_for("notifications/resources/updated")
        self.expect(params.get("uri") == STATIC_DOC, "the update must name the document")
        self.step("tools/call trigger-resource-update",
                  f"notifications/resources/updated on subscription {sub.id}")

    def input_required(self) -> None:
        """No server-to-client requests: the server answers `input_required`; the client retries.

        `spec:docs/specification/2026-07-28/basic/transports/stdio.mdx:55`
        "MUST NOT** write JSON-RPC _requests_"
        """
        bare = {"name": "get-roots-list", "arguments": {}}
        try:
            self.session.call("tools/call", bare, capabilities={})
        except RpcError as exc:
            code = exc.error.get("code") if isinstance(exc.error, dict) else None
            self.expect(code == MISSING_CAPABILITY, f"expected -32021, got {exc.error}")
            self.step("tools/call get-roots-list (no caps)", f"error {code}")
        else:
            raise TourFailure("get-roots-list without the roots capability must fail")
        answer = default_answer(self.handlers)
        say = lambda text: self.say(f"      {text}")  # noqa: E731
        calls: list[tuple[str, Message, str, int]] = [
            ("get-roots-list", {}, "roots listed", 1),
            ("trigger-sampling-request", {"prompt": "Say hello"}, "sampling answered", 1),
            ("trigger-elicitation-request", {}, "form accepted from defaults", 1),
            ("trigger-multi-step-elicitation", {}, "three rounds answered", 3),
        ]
        for name, arguments, summary, _rounds in calls:
            result = self.session.request_with_input(
                "tools/call", {"name": name, "arguments": arguments}, answer, say=say)
            self.expect(bool(result.get("content")), f"{name} returned no content")
            self.step(f"tools/call {name}", summary)

    def close_subscription(self) -> None:
        assert self.subscription is not None
        self.expect(self.subscription.close(), "the listen request was already finished")
        self.step("notifications/cancelled", f"closed subscription {self.subscription.id}")


def run_modern_tour(
    command: Sequence[str], out: TextIO, report: Callable[[str], None] | None = None,
    caps: Sequence[str] = ("roots", "sampling", "elicitation"),
) -> int:
    """Run the 2026 tour; 0 only if every step got the reply it expects (D6)."""
    handlers = Handlers(caps, report=report or stderr_report)
    holder: list[ModernTour] = []

    def observe(arrow: str, message: Any) -> None:
        if holder:
            holder[0].observe(arrow, message)

    session = ModernSession.open_modern(
        command, capabilities=handlers.capabilities, observer=observe,
        report=report or stderr_report)
    tour = ModernTour(session, out, handlers)
    holder.append(tour)
    return _finish(tour, session, report)


# -- the tasks run (D7) ---------------------------------------------------------------------


class TasksRun(ModernTour):
    """A reduced tasks run: one task completed by `tasks/update`, one cancelled; no polling loop."""

    def run(self) -> None:
        self.discovery()
        self.without_the_extension()
        self.input_required_task()
        self.cancelled_task()

    def without_the_extension(self) -> None:
        """A task-augmented call from a client that did not declare the extension fails.

        `spec:seps/2663-tasks-extension.md:87`
        "invalid response"
        """
        try:
            self.session.call("tools/call", {"name": "simulate-research-query",
                                             "arguments": {"topic": "wire"}},
                              capabilities=self.handlers.capabilities)
        except RpcError as exc:
            code = exc.error.get("code") if isinstance(exc.error, dict) else None
            self.expect(code == MISSING_CAPABILITY, f"expected -32021, got {exc.error}")
            self.step("tools/call simulate-research-query (no ext)", f"error {code}")
        else:
            raise TourFailure("a task without the extension declared must fail")

    def input_required_task(self) -> None:
        handle = self.tool("trigger-sampling-request-async", {"prompt": "Say hello"})
        self.expect(handle.get("resultType") == "task", "expected a task handle")
        self.expect(handle.get("status") == "input_required", "the task must wait for input")
        task_id = handle["taskId"]
        self.step("tools/call trigger-sampling-request-async",
                  f"task {task_id} {handle['status']}")
        answer = default_answer(self.handlers)
        responses = {key: answer(req) for key, req in handle["inputRequests"].items()}
        self.call("tasks/update", {"taskId": task_id, "inputResponses": responses})
        self.step("tasks/update", f"answered {', '.join(responses)}")
        done = self.call("tasks/get", {"taskId": task_id})
        self.expect(done.get("status") == "completed" and "result" in done,
                    f"expected a completed task with a result, got {done.get('status')}")
        self.step("tasks/get", "completed, with a result")

    def cancelled_task(self) -> None:
        handle = self.tool("simulate-research-query", {"topic": "wire"})
        self.expect(handle.get("resultType") == "task" and handle.get("status") == "working",
                    "expected a working task handle")
        task_id = handle["taskId"]
        self.step("tools/call simulate-research-query", f"task {task_id} working")
        got = self.call("tasks/get", {"taskId": task_id})
        self.expect(got.get("status") == "working", f"expected working, got {got.get('status')}")
        self.step("tasks/get", "working")
        self.call("tasks/cancel", {"taskId": task_id})
        self.step("tasks/cancel", "acknowledged")
        got = self.call("tasks/get", {"taskId": task_id})
        self.expect(got.get("status") == "cancelled", f"not cancelled: {got.get('status')}")
        self.step("tasks/get", "cancelled")


def run_tasks(
    command: Sequence[str], out: TextIO, report: Callable[[str], None] | None = None,
) -> int:
    """Run the tasks run (D7): sampling, form elicitation and the tasks extension declared."""
    handlers = Handlers(("sampling", "elicitation"), report=report or stderr_report)
    holder: list[ModernTour] = []

    def observe(arrow: str, message: Any) -> None:
        if holder:
            holder[0].observe(arrow, message)

    session = ModernSession.open_modern(
        command, capabilities=with_tasks(handlers.capabilities), observer=observe,
        report=report or stderr_report)
    # without the extension for that one request: the handlers' own capability object
    run = TasksRun(session, out, handlers)
    holder.append(run)
    return _finish(run, session, report)


def _finish(tour: ModernTour, session: ModernSession,
            report: Callable[[str], None] | None) -> int:
    status = 0
    try:
        tour.run()
    except Exception as exc:
        failure = f"{tour.step_no:>2}  FAILED  {type(exc).__name__}: {exc}"
        tour.say(failure)
        (report or stderr_report)(f"tour failed at step {failure.strip()}")
        status = 1
    code = session.close()
    tour.say(f"    shutdown: server exited with status {code}")
    return status


__all__ = [
    "ERA", "ModernSession", "ModernTour", "envelope", "run_modern_tour",
    "run_tasks",
]
