"""Manual mode (D4): the learner types; the client sends exactly that and prints what comes back.

After the 2025 opening exchange, each line read is one of:

  {...}                    a JSON object line: sent as is. Nothing is added or fixed: no
                           "jsonrpc", no "id", and a line that starts with `{` but is not valid
                           JSON is still sent, so mistakes reach the server and you see its answer
  :req <method> [<json>]   a request with the next id (the wire allocates it)
  :note <method> [<json>]  a notification
  :sample <text>           the text the next sampling request (--caps sampling) is answered with
  :quit                    shut down (end of input does the same)

Every message sent is printed as `-> <json>` and every message received as `<- <json>`.
Replies to lines the learner typed with their own `id` match no pending request, so the wire also
reports them on stderr as unknown-id replies; the `<-` line is the one to read.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any, TextIO

from client.handlers import CANNED_TEXT, Handlers
from client.session import Session
from client.wire import Key, Message, classify, key_of, stderr_report

SETTLE_SECONDS = 5.0  # how long to wait, at the end, for replies to requests still unanswered


class Manual:
    def __init__(self, session: Session, out: TextIO, settle: float = SETTLE_SECONDS,
                 capabilities: Message | None = None) -> None:
        self.session = session
        self.capabilities = capabilities
        self.sample_text: str | None = None  # set by `:sample`, read by the sampling handler
        self.out = out
        self.settle = settle
        self._lock = threading.Lock()
        self._awaiting: set[Key] = set()

    def observe(self, arrow: str, message: Any) -> None:
        """Print every message in or out; remember which requests still wait for a reply.

        `spec:docs/specification/2025-11-25/basic/index.mdx:69`
        "MUST** include the same ID"
        """
        text = message if isinstance(message, str) else json.dumps(message, separators=(",", ":"))
        with self._lock:
            print(f"{arrow} {text}", file=self.out, flush=True)
            if isinstance(message, str):
                try:
                    message = json.loads(message)
                except ValueError:
                    return
            kind = classify(message)
            if arrow == "->" and kind == "request":
                self._awaiting.add(key_of(message["id"]))
            elif arrow == "<-" and kind == "response":
                self._awaiting.discard(key_of(message["id"]))

    def _params(self, text: str) -> Message | None:
        return json.loads(text) if text.strip() else None

    def handle(self, line: str) -> bool:
        """Act on one typed line; False means stop (`:quit`).

        spec: `spec:docs/specification/2025-11-25/basic/transports.mdx:34`
        "MUST NOT** write anything to the server's"
        """
        line = line.strip()
        if not line:
            return True
        if line.startswith("{"):
            self.session.wire.send_line(line)
        elif line == ":quit":
            return False
        elif line.startswith(":sample "):
            self.sample_text = line[len(":sample "):]
        elif line.startswith((":req ", ":note ")):
            command, _, rest = line.partition(" ")
            method, _, text = rest.strip().partition(" ")
            try:
                params = self._params(text)
            except ValueError as exc:
                print(f"manual: the params are not valid JSON ({exc})", file=self.out, flush=True)
                return True
            if command == ":req":
                self.session.start_request(method, params)
            else:
                self.session.notify(method, params)
        else:
            print(f"manual: not a command: {line}", file=self.out, flush=True)
        return True

    def run(self, lines: Iterable[str]) -> int:
        self.session.initialize(self.capabilities)
        for line in lines:
            if not self.handle(line):
                break
        deadline = time.monotonic() + self.settle
        while self._awaiting and time.monotonic() < deadline:
            time.sleep(0.02)
        self.session.close()
        return 0


def run_manual(command: list[str], lines: Iterable[str], out: TextIO,
               settle: float = SETTLE_SECONDS,
               report: Callable[[str], None] = stderr_report,
               caps: Sequence[str] = ()) -> int:
    holder: list[Manual] = []

    def observe(arrow: str, message: Any) -> None:
        if holder:
            holder[0].observe(arrow, message)

    def sampling_text() -> str:
        text = holder[0].sample_text if holder else None
        return CANNED_TEXT if text is None else text

    handlers = Handlers(caps, sampling_text=sampling_text, report=report) if caps else None
    callbacks: dict[str, Any] = {}
    if handlers is not None:
        callbacks = {"on_request": handlers.handle_request,
                     "on_notification": handlers.handle_notification}
    session = Session.open(command, observer=observe, report=report, **callbacks)
    if handlers is not None:
        handlers.attach(session.wire)
    manual = Manual(session, out, settle, None if handlers is None else handlers.capabilities)
    holder.append(manual)
    try:
        return manual.run(lines)
    finally:
        session.close()
