"""The raw client's wire (D1): newline-delimited JSON-RPC 2.0 over a child's stdin and stdout.

A `Wire` owns two byte streams (the server's stdin to write, its stdout to read) and nothing
else: no process, no lifecycle (that is `client.session`). One reader thread turns each incoming
line into one of three things by its shape, never by its id alone (the server's own request ids
start at 0 too, so they overlap ours):

- a response (has `id` and `result` or `error`, no `method`) completes the pending request
  with that exact id, type included: `1` and `"1"` differ;
- a server request (has `method` and `id`) goes to the request handler, which in phase 2 only
  refuses it with -32601 under the same id (written by a sender thread, never by the reader);
- a notification (has `method`, no `id`) goes to `notifications`, a queue the caller reads.

Anything else is reported through `report` and otherwise ignored.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
from collections.abc import Callable
from typing import IO, Any

JSON_RPC = "2.0"
METHOD_NOT_FOUND = -32601
DEFAULT_TIMEOUT = 30.0
ID_TYPES = (str, int)

Message = dict[str, Any]
Key = tuple[str, Any]


class RpcError(Exception):
    """The server answered a request with a JSON-RPC error; `error` is its error object."""

    def __init__(self, error: Any) -> None:
        super().__init__(f"server error {error}")
        self.error = error


class Cancelled(Exception):
    """The request was cancelled by the client, so no reply is awaited."""


def stderr_report(text: str) -> None:
    """The default `report`: one line on the client's own stderr."""
    print(f"client: {text}", file=sys.stderr, flush=True)


def key_of(message_id: Any) -> Key:
    """An id as a dict key that keeps `1`, `"1"` and `true` apart (Python's `1 == True`)."""
    return (type(message_id).__name__, message_id)


def valid_id(message_id: Any) -> bool:
    """An id is a string or an integer, never null and never a boolean.

    `spec:docs/specification/2025-11-25/basic/index.mdx:46`
    "include a string or integer ID"
    """
    return isinstance(message_id, ID_TYPES) and not isinstance(message_id, bool)


def classify(message: Any) -> str:
    """response, request, notification or junk, by the shape of a decoded line.

    A request has `method` and `id`; a notification has `method` and no `id`; a response has
    `id` (a string, an integer or null) and `result` or `error` and no `method`. A bad `method`
    or `id` type is junk.

    `spec:docs/specification/2025-11-25/basic/index.mdx:108`
    "Notifications **MUST NOT** include an ID"
    """
    if not isinstance(message, dict):
        return "junk"
    if "method" in message:
        if not isinstance(message["method"], str):
            return "junk"
        if "id" not in message:
            return "notification"
        return "request" if valid_id(message["id"]) else "junk"
    if "id" in message and ("result" in message or "error" in message):
        # null is the id of the error reply to a request the server could not parse
        return "response" if message["id"] is None or valid_id(message["id"]) else "junk"
    return "junk"


class Pending:
    """One request in flight: filled in by the reader thread, awaited by the caller."""

    def __init__(self, request_id: int, method: str) -> None:
        self.id = request_id
        self.method = method
        self._event = threading.Event()
        self._result: Any = None
        self._failure: Exception | None = None

    @property
    def done(self) -> bool:
        return self._event.is_set()

    def complete(self, result: Any = None, failure: Exception | None = None) -> None:
        if not self._event.is_set():
            self._result, self._failure = result, failure
            self._event.set()

    def wait(self, timeout: float | None = DEFAULT_TIMEOUT) -> Any:
        """The reply's `result`; raises RpcError for an error reply, TimeoutError, Cancelled.

        `spec:docs/specification/2025-11-25/basic/index.mdx:90`
        "MUST** include an `error` field"
        """
        if not self._event.wait(timeout):
            raise TimeoutError(f"no reply to {self.method} (id {self.id}) within {timeout} s")
        if self._failure is not None:
            raise self._failure
        return self._result


class Wire:
    """Frames and classifies JSON-RPC messages on a pair of byte streams."""

    def __init__(
        self,
        stdin: IO[bytes],
        stdout: IO[bytes],
        *,
        report: Callable[[str], None] = stderr_report,
        observer: Callable[[str, Any], None] | None = None,
        on_request: Callable[[Message], None] | None = None,
        on_notification: Callable[[Message], None] | None = None,
    ) -> None:
        self._stdin = stdin
        self._stdout = stdout
        self._report = report
        self._observer = observer
        self._on_request = on_request  # phase 3: answers server requests; None means refuse
        self._on_notification = on_notification  # phase 3: also sees each notification
        # Two locks: `_write_lock` is held only around a write (one writer at a time, and ids
        # reach the wire in allocation order); `_table_lock` guards the fields below and is
        # never held across I/O, so the reader thread never waits behind a write that is
        # blocked on a full pipe.
        self._write_lock = threading.Lock()
        self._table_lock = threading.Lock()
        self._next_id = 0
        self._pending: dict[Key, Pending] = {}
        self._abandoned: set[Key] = set()
        self._closed: OSError | None = None  # set once: EOF from the server, or close_input()
        self._outbox: queue.Queue[Message] = queue.Queue()  # refusals, written by the sender
        self._sender: threading.Thread | None = None
        self.notifications: queue.Queue[Message] = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)

    # -- sending -----------------------------------------------------------------------

    def _write(self, text: str) -> None:
        """One line to the server's stdin; the caller holds the write lock.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:25`
        "reads JSON-RPC messages from its standard input"
        """
        try:
            self._stdin.write(text.encode("utf-8") + b"\n")
            self._stdin.flush()
        except ValueError as exc:  # a closed file object says ValueError; callers expect OSError
            raise OSError(f"the server's stdin is closed ({exc})") from exc

    def send_message(self, message: Message) -> None:
        """Send one message as one compact JSON line.

        ASCII-only output (`ensure_ascii`) keeps U+2028, U+0085 and friends, which some line
        readers split on, out of the line; a newline inside a string is always escaped.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:28`
        "contain embedded newlines"
        """
        text = json.dumps(message, separators=(",", ":"), ensure_ascii=True)
        with self._write_lock:
            self._write(text)
        self._observe("->", message)

    def send_line(self, text: str) -> None:
        """Send text exactly as given, plus the newline (manual mode: mistakes included).

        The spec forbids writing anything but valid messages; manual mode lets the learner break
        that rule on purpose, to see what the server does.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:34`
        "MUST NOT** write anything to the server's"
        """
        with self._write_lock:
            self._write(text)
        self._observe("->", text)

    def start_request(self, method: str, params: Message | None = None) -> Pending:
        """Send a request with the next id (from 0, in send order) and return its Pending.

        The id is allocated and the line written under the write lock, so the order ids are
        written in is the order they were allocated in. The request is in the pending table
        before its line is written, so a fast reply finds it; the table lock is only held for
        the table, never during the write. Raises OSError at once once the wire is closed.

        `spec:docs/specification/2025-11-25/basic/index.mdx:48`
        "MUST NOT** have been previously used"
        """
        with self._write_lock:
            with self._table_lock:
                if self._closed is not None:
                    raise self._closed
                request_id = self._next_id
                self._next_id += 1
                pending = Pending(request_id, method)
                self._pending[key_of(request_id)] = pending
            message: Message = {"jsonrpc": JSON_RPC, "id": request_id, "method": method}
            if params is not None:
                message["params"] = params
            try:
                self._write(json.dumps(message, separators=(",", ":"), ensure_ascii=True))
            except OSError:
                with self._table_lock:
                    self._pending.pop(key_of(request_id), None)
                raise
        self._observe("->", message)
        return pending

    def request(
        self, method: str, params: Message | None = None, timeout: float | None = DEFAULT_TIMEOUT
    ) -> Any:
        """Send a request and wait for its result (see Pending.wait for the failures).

        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:248`
        "SHOULD** establish timeouts"
        """
        return self.start_request(method, params).wait(timeout)

    def notify(self, method: str, params: Message | None = None) -> None:
        """Send a notification: a message with a method and no id.

        `spec:docs/specification/2025-11-25/basic/index.mdx:96`
        "MUST NOT** send a response"
        """
        message: Message = {"jsonrpc": JSON_RPC, "method": method}
        if params is not None:
            message["params"] = params
        self.send_message(message)

    def abandon(self, pending: Pending) -> bool:
        """Stop waiting for a request: a reply that arrives later is dropped and reported.

        Returns True if the request was still waiting, False if it already had its reply (or
        was already abandoned or failed); the check and the removal are one step under the table
        lock, so a reply cannot land in between.

        `spec:docs/specification/2025-11-25/basic/utilities/cancellation.mdx:45`
        "ignore any response to the"
        """
        key = key_of(pending.id)
        with self._table_lock:
            if self._pending.pop(key, None) is None:
                return False
            self._abandoned.add(key)
        pending.complete(failure=Cancelled(f"{pending.method} (id {pending.id}) was cancelled"))
        return True

    def close_input(self) -> None:
        """Close the server's stdin: the first step of a stdio shutdown.

        The wire is closed from here on: requests still pending fail at once with OSError, and
        so does every new one.
        """
        self._fail_all(OSError("the wire is closed"))
        try:
            self._stdin.close()
        except OSError:
            pass  # the server is already gone; the pipe had nothing left to flush

    # -- receiving ---------------------------------------------------------------------

    def start(self) -> None:
        self._reader.start()

    def join(self, timeout: float) -> None:
        if self._reader.is_alive():
            self._reader.join(timeout)

    def _read_loop(self) -> None:
        """Read lines until EOF; one bad line never ends the loop, and the end fails every wait."""
        try:
            for raw in self._stdout:
                try:
                    self.handle_line(raw)
                except Exception as exc:  # the reader must outlive any one line
                    self._report(f"error while handling a line ({type(exc).__name__}: {exc}): "
                                 f"{raw[:80]!r}")
        finally:
            self._fail_all(ConnectionError("the server closed its stdout"))

    def _fail_all(self, failure: OSError) -> None:
        """Close the wire (first failure wins) and fail every pending request with `failure`."""
        with self._table_lock:
            if self._closed is None:
                self._closed = failure
            waiting = list(self._pending.values())
            self._pending.clear()
        for pending in waiting:
            pending.complete(failure=failure)

    def handle_line(self, raw: bytes) -> str:
        """Classify one incoming line and act on it; returns the kind it was taken to be.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:33`
        "valid MCP message"
        """
        try:
            message = json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError) as exc:  # a bad line, or one nested too deep
            self._report(f"ignored a line that is not JSON ({exc}): {raw[:80]!r}")
            return "junk"
        self._observe("<-", message)
        kind = classify(message)
        if kind == "response":
            return "response" if self._complete(message) else "junk"
        if kind == "request":
            # The callback must not block the reader (client.handlers answers on a worker, and
            # the default refusal is written by the sender thread).
            (self._on_request or self._refuse)(message)
        elif kind == "notification":
            self.notifications.put(message)
            if self._on_notification is not None:
                self._on_notification(message)
        else:
            self._report(f"ignored a message that is not a request, response or notification: "
                         f"{json.dumps(message)[:80]}")
        return kind

    def _complete(self, message: Message) -> bool:
        """Give a response to the request with the same id; False if there is none.

        `spec:docs/specification/2025-11-25/basic/index.mdx:69`
        "MUST** include the same ID"
        """
        key = key_of(message["id"])
        with self._table_lock:
            pending = self._pending.pop(key, None)
            late = pending is None and key in self._abandoned
            if late:
                self._abandoned.discard(key)
        if pending is None:
            what = "a late reply to a cancelled request" if late else "a reply with an unknown id"
            self._report(f"dropped {what}: id {json.dumps(message['id'])}")
            return late
        if "error" in message:
            pending.complete(failure=RpcError(message["error"]))
        else:
            pending.complete(result=message["result"])
        return True

    def _refuse(self, message: Message) -> None:
        """Answer a server request with -32601 under its own id (phase 2 handles none).

        `spec:docs/specification/2025-11-25/client/roots.mdx:144`
        "Method not found"
        """
        reply: Message = {
            "jsonrpc": JSON_RPC,
            "id": message["id"],
            "error": {
                "code": METHOD_NOT_FOUND,
                "message": f"Method not found: {message['method']}",
            },
        }
        with self._table_lock:  # the sender starts once, on the first refusal
            if self._sender is None:
                self._sender = threading.Thread(target=self._send_refusals, daemon=True)
                self._sender.start()
        self._outbox.put(reply)

    def _send_refusals(self) -> None:
        """Write queued refusals, one at a time, so the reader never waits on the write lock."""
        while True:
            reply = self._outbox.get()
            try:
                self.send_message(reply)
            except OSError as exc:
                self._report(f"could not refuse the server's request {reply['id']!r}: {exc}")

    def _observe(self, arrow: str, message: Any) -> None:
        if self._observer is not None:
            self._observer(arrow, message)
