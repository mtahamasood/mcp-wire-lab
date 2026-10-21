"""What the raw client does when the server speaks first (phase 3 D1, D2).

A server may send the client requests (`roots/list`, `sampling/createMessage`,
`elicitation/create`, `ping`) and unsolicited notifications (list changes, resource updates,
progress, log messages). `Handlers` is the table that answers the first and reacts to the second.
It plugs into a `Wire` as its `on_request` and `on_notification` callbacks.

- A request is answered on a worker thread, under its own `id` (type included), so a client
  request can still complete while a server request is pending. A method with no handler, or a
  method whose capability the client did not declare, gets -32601; an elicitation mode it did
  not declare gets -32602 (invalid params).
- A notification is recorded and printed on the reader's thread (cheap, never blocking); the
  re-requests it calls for (the changed list, the updated resource) are sent by a second worker,
  the reactor, which waits `debounce` seconds first so a burst becomes one re-list.
"""

from __future__ import annotations

import json
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from client.wire import JSON_RPC, METHOD_NOT_FOUND, Message, Wire, stderr_report

CAPABILITIES = ("roots", "sampling", "elicitation", "elicitation-url")
DEFAULT_ROOTS: list[Message] = [{"uri": "file:///wire-lab/project", "name": "wire-lab"}]
CANNED_TEXT = "canned reply from wire-lab-raw"
CANNED_MODEL = "wire-lab-canned"
FIXED_VALUES: dict[str, Any] = {"string": "wire-lab", "number": 1, "integer": 1, "boolean": True}
LIST_METHODS = {
    "notifications/tools/list_changed": "tools",
    "notifications/prompts/list_changed": "prompts",
    "notifications/resources/list_changed": "resources",
}
DEBOUNCE_SECONDS = 0.05
INVALID_PARAMS = -32602


def capability_object(caps: Iterable[str]) -> Message:
    """The `capabilities` object for `initialize` that declares exactly `caps` (D3).

    `spec:docs/specification/2025-11-25/client/roots.mdx:34`
    "listChanged": true
    """
    chosen = list(dict.fromkeys(caps))
    unknown = [c for c in chosen if c not in CAPABILITIES]
    if unknown:
        raise ValueError(f"unknown capability {unknown[0]!r}; use {', '.join(CAPABILITIES)}")
    out: Message = {}
    if "roots" in chosen:
        out["roots"] = {"listChanged": True}
    if "sampling" in chosen:
        out["sampling"] = {}
    if "elicitation" in chosen or "elicitation-url" in chosen:
        out["elicitation"] = {}
        if "elicitation" in chosen:
            out["elicitation"]["form"] = {}
        if "elicitation-url" in chosen:
            out["elicitation"]["url"] = {}
    return out


def _first_option(schema: Message) -> Any:
    """The first value a single-select property allows, or None if it lists none."""
    if schema.get("enum"):
        return schema["enum"][0]
    for key in ("oneOf", "anyOf"):
        if schema.get(key):
            return schema[key][0].get("const")
    return None


def form_value(schema: Message) -> Any:
    """One property of an elicitation form: its default, else its first option, else a fixed value.

    `spec:docs/specification/2025-11-25/client/elicitation.mdx:269`
    "action": "accept",
    """
    if "default" in schema:
        default = schema["default"]
        # ElicitResult.content allows strings, integers, booleans and string lists, no fraction
        # (the schema's own rule), so the server's default of 3.14 goes back as 3.
        return int(default) if isinstance(default, float) else default
    first = _first_option(schema)
    if first is not None:
        return first
    if schema.get("type") == "array":
        option = _first_option(schema.get("items", {}))
        return [] if option is None else [option]
    return FIXED_VALUES.get(schema.get("type", "string"), FIXED_VALUES["string"])


class Handlers:
    """Answers the server's requests and reacts to its notifications."""

    def __init__(
        self,
        caps: Iterable[str] = (),
        roots: Sequence[Message] | None = None,
        *,
        sampling_text: Callable[[], str] | None = None,
        say: Callable[[str], None] | None = None,
        report: Callable[[str], None] = stderr_report,
        debounce: float = DEBOUNCE_SECONDS,
    ) -> None:
        self.caps = tuple(dict.fromkeys(caps))
        capability_object(self.caps)  # rejects an unknown name early
        self.roots: list[Message] = [dict(r) for r in (DEFAULT_ROOTS if roots is None else roots)]
        self.sampling_text = sampling_text
        self._say = say
        self._report = report
        self._debounce = debounce
        self.wire: Wire | None = None
        self._cond = threading.Condition()
        self._busy = 0  # requests being answered plus re-requests being made
        self._dirty: dict[str, None] = {}  # ordered set of "tools", "prompts", ... and URIs
        self._reactor: threading.Thread | None = None
        self._progress: dict[Any, list[Message]] = {}
        self.unmatched_progress: list[Message] = []
        self.counts: Counter[str] = Counter()  # server-initiated methods seen, by method
        self.relists: list[str] = []  # lists re-requested, in order ("tools", ...)
        self.rereads: list[str] = []  # URIs re-read, in order
        self.lists: dict[str, list[str]] = {}  # last re-listed names or URIs, by list

    @property
    def capabilities(self) -> Message:
        return capability_object(self.caps)

    def attach(self, wire: Wire) -> None:
        self.wire = wire

    # -- server requests (D1) ------------------------------------------------------------

    def handle_request(self, message: Message) -> None:
        """Answer a server request on a worker thread, so the reader goes on reading.

        `spec:docs/specification/2025-11-25/basic/index.mdx:69`
        "MUST** include the same ID"
        """
        with self._cond:
            self.counts[message["method"]] += 1
            self._busy += 1
        threading.Thread(target=self._respond, args=(message,), daemon=True).start()

    def _respond(self, message: Message) -> None:
        try:
            reply = self.answer(message)
            assert self.wire is not None, "Handlers.attach(wire) was not called"
            self.wire.send_message(reply)
        except OSError as exc:  # the server is gone; nobody is left to answer
            self._report(f"could not answer the server's {message['method']} request: {exc}")
        finally:
            self._finish()

    def answer(self, message: Message) -> Message:
        """The reply to one server request: the result for its method, or an error.

        The error is -32601 (method not found), except -32602 (invalid params) for an
        `elicitation/create` in a mode the client did not declare. Every reply carries the
        request's `id` exactly as it came, so `1` and `"1"` stay different.

        `spec:docs/specification/2025-11-25/basic/index.mdx:69`
        "MUST** include the same ID"
        `spec:docs/specification/2025-11-25/client/roots.mdx:144`
        "Method not found"
        `spec:docs/specification/2025-11-25/client/elicitation.mdx:700`
        "-32602"
        """
        method = message["method"]
        params = message.get("params") or {}
        mode = params.get("mode", "form")
        if method == "elicitation/create" and not self._declares_mode(mode):
            return {
                "jsonrpc": JSON_RPC, "id": message["id"],
                "error": {"code": INVALID_PARAMS,
                          "message": f"Elicitation mode not declared: {mode}"},
            }
        result = self._result(method, params)
        if result is None:
            return {
                "jsonrpc": JSON_RPC, "id": message["id"],
                "error": {"code": METHOD_NOT_FOUND, "message": f"Method not found: {method}"},
            }
        return {"jsonrpc": JSON_RPC, "id": message["id"], "result": result}

    def _declares_mode(self, mode: Any) -> bool:
        """Whether the client declared the elicitation mode (`form` or `url`) a request asks for."""
        return (mode == "form" and "elicitation" in self.caps) or (
            mode == "url" and "elicitation-url" in self.caps)

    def _result(self, method: str, params: Message) -> Message | None:
        """The result for a method the client handles and declared, else None (refuse)."""
        if method == "ping":
            return {}
        if method == "roots/list" and "roots" in self.caps:
            return {"roots": [dict(r) for r in self.roots]}
        if method == "sampling/createMessage" and "sampling" in self.caps:
            text = CANNED_TEXT if self.sampling_text is None else self.sampling_text()
            return {"role": "assistant", "content": {"type": "text", "text": text},
                    "model": CANNED_MODEL, "stopReason": "endTurn"}
        if method == "elicitation/create":
            if params.get("mode", "form") == "url":
                return {"action": "decline"}
            properties = params.get("requestedSchema", {}).get("properties", {})
            return {"action": "accept",
                    "content": {name: form_value(spec) for name, spec in properties.items()}}
        return None

    def set_roots(self, roots: Sequence[Message]) -> None:
        """Change the roots and tell the server.

        `spec:docs/specification/2025-11-25/client/roots.mdx:78`
        "MUST** send a notification"
        """
        self.roots = [dict(r) for r in roots]
        assert self.wire is not None, "Handlers.attach(wire) was not called"
        self.wire.notify("notifications/roots/list_changed")

    # -- server notifications (D2) -------------------------------------------------------

    def handle_notification(self, message: Message) -> None:
        """Print and record a notification; queue the re-request it calls for.

        `spec:docs/specification/2025-11-25/server/tools.mdx:158`
        "method": "notifications/tools/list_changed"
        `spec:docs/specification/2025-11-25/server/resources.mdx:244`
        "method": "notifications/resources/updated",
        """
        method = message["method"]
        params: Message = message.get("params") or {}
        with self._cond:
            self.counts[method] += 1
            self._cond.notify_all()
        self._print(method, params)
        if method in LIST_METHODS:
            self._mark(LIST_METHODS[method])
        elif method == "notifications/resources/updated" and isinstance(params.get("uri"), str):
            self._mark(params["uri"])
        elif method == "notifications/progress":
            self._match_progress(params)

    def _print(self, method: str, params: Message) -> None:
        """One line per notification; a log message shows its level and logger.

        `spec:docs/specification/2025-11-25/server/utilities/logging.mdx:71`
        "method": "notifications/message",
        """
        if self._say is None:
            return
        if method == "notifications/message":
            logger = params.get("logger") or "-"
            self._say(f"<- {method} level={params.get('level')} logger={logger} "
                      f"{params.get('data')}")
        else:
            self._say(f"<- {method} {_compact(params)}")

    def watch_progress(self, token: Any) -> list[Message]:
        """Start collecting the progress notifications that carry `token`; the list fills.

        `spec:docs/specification/2025-11-25/basic/utilities/progress.mdx:45`
        "progressToken": "abc123",
        """
        with self._cond:
            return self._progress.setdefault(token, [])

    def _match_progress(self, params: Message) -> None:
        with self._cond:
            mine = self._progress.get(params.get("progressToken"))
            (self.unmatched_progress if mine is None else mine).append(params)
            self._cond.notify_all()

    def _mark(self, what: str) -> None:
        """Queue a re-request; asking again before it is sent changes nothing (coalescing)."""
        with self._cond:
            self._dirty[what] = None
            if self._reactor is None or not self._reactor.is_alive():
                self._reactor = threading.Thread(target=self._react, daemon=True)
                self._reactor.start()
            self._cond.notify_all()

    def _react(self) -> None:
        """The reactor: after a quiet `debounce`, re-request everything queued; stop when empty."""
        while True:
            time.sleep(self._debounce)
            with self._cond:
                batch = list(self._dirty)
                self._dirty.clear()
                self._busy += 1
            try:
                for what in batch:
                    self._refresh(what)
            finally:
                self._finish()
            with self._cond:
                if not self._dirty:
                    self._reactor = None
                    self._cond.notify_all()
                    return

    def _refresh(self, what: str) -> None:
        """Re-request one list (`tools/list`, ...) or re-read one resource URI."""
        assert self.wire is not None, "Handlers.attach(wire) was not called"
        try:
            if what in ("tools", "prompts", "resources"):
                reply = self.wire.request(f"{what}/list")
                key = {"tools": "name", "prompts": "name", "resources": "uri"}[what]
                with self._cond:
                    self.relists.append(what)
                    self.lists[what] = [str(item.get(key)) for item in reply.get(what, [])]
            else:
                self.wire.request("resources/read", {"uri": what})
                with self._cond:
                    self.rereads.append(what)
        except Exception as exc:  # a failed re-request is reported, never fatal to the reader
            self._report(f"could not re-request {what}: {exc}")

    # -- waiting -------------------------------------------------------------------------

    def _finish(self) -> None:
        with self._cond:
            self._busy -= 1
            self._cond.notify_all()

    def wait_idle(self, timeout: float) -> bool:
        """True once no answer or re-request is queued or in flight."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._busy or self._dirty or self._reactor is not None:
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self._cond.wait(left)
            return True

    def wait_count(self, method: str, at_least: int, timeout: float) -> bool:
        """True once `at_least` server messages of `method` have been seen in all."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while self.counts[method] < at_least:
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self._cond.wait(left)
            return True


def _compact(params: Message) -> str:
    return json.dumps(params, separators=(",", ":"))[:90]
