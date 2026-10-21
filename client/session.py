"""The raw client's session (D2): the 2025 lifecycle on top of a `Wire`.

initialize (with a protocol version check), then `notifications/initialized`, and only then
other requests; cancellation; and the stdio shutdown. The child's stderr is not touched: it is
inherited, so whatever the server logs goes straight to the client's own stderr.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable, Sequence
from typing import Any

from client.wire import DEFAULT_TIMEOUT, Message, Pending, Wire, stderr_report

PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
CLIENT_INFO = {"name": "wire-lab-raw", "version": "0.2.0"}
GRACE_SECONDS = 2.0


class NotInitialized(RuntimeError):
    """A request was attempted before the lifecycle reached `notifications/initialized`."""


class UnsupportedVersion(RuntimeError):
    """The server answered `initialize` with a protocol version this client does not speak."""


class Session:
    """One connection to one server process, from launch to exit status."""

    def __init__(
        self, wire: Wire, process: subprocess.Popen[bytes] | None = None,
        *, grace: float = GRACE_SECONDS, timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.wire = wire
        self.process = process
        self.grace = grace
        self.timeout = timeout
        self.ready = False  # True once `notifications/initialized` has been sent
        self._status: int | None = None
        self._close_lock = threading.Lock()

    @classmethod
    def open(
        cls, command: Sequence[str], *, report: Callable[[str], None] = stderr_report,
        observer: Callable[[str, Any], None] | None = None,
        grace: float = GRACE_SECONDS, timeout: float = DEFAULT_TIMEOUT,
    ) -> Session:
        """Launch the server command as a child process and start reading its stdout.

        `spec:docs/specification/2025-11-25/basic/transports.mdx:24`
        "launches the MCP server as a subprocess"
        """
        process = subprocess.Popen(  # stderr is inherited: passed through, never parsed (D1)
            list(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0
        )
        assert process.stdin is not None and process.stdout is not None
        wire = Wire(process.stdin, process.stdout, report=report, observer=observer)
        wire.start()
        return cls(wire, process, grace=grace, timeout=timeout)

    def initialize(self, capabilities: Message | None = None) -> Message:
        """Run the opening exchange: `initialize`, the version check, `notifications/initialized`.

        Offers the newest version this client speaks. A reply naming a version outside
        SUPPORTED_VERSIONS raises UnsupportedVersion and sends nothing more.

        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:47`
        "MUST** initiate this phase"
        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:174`
        "does not support the version"
        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:147`
        "MUST** send an `initialized` notification"
        """
        params: Message = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {} if capabilities is None else capabilities,
            "clientInfo": dict(CLIENT_INFO),
        }
        result: Message = self.wire.request("initialize", params, self.timeout)
        version = result.get("protocolVersion")
        if version not in SUPPORTED_VERSIONS:
            raise UnsupportedVersion(
                f"the server chose protocol version {version!r}; this client speaks "
                f"{', '.join(SUPPORTED_VERSIONS)}"
            )
        self.wire.notify("notifications/initialized")
        self.ready = True
        return result

    def _require_ready(self) -> None:
        """Only `initialize` (sent by `initialize`) may go before the lifecycle is complete.

        This is stricter than the spec, which only tells the client not to send anything but
        pings before the `initialize` reply.

        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:157`
        "SHOULD NOT** send requests other than"
        """
        if not self.ready:
            raise NotInitialized("no requests before notifications/initialized has been sent")

    def start_request(self, method: str, params: Message | None = None) -> Pending:
        """Send a request after the lifecycle is complete; returns it unawaited."""
        self._require_ready()
        return self.wire.start_request(method, params)

    def request(
        self, method: str, params: Message | None = None, timeout: float | None = None
    ) -> Any:
        """Send a request and wait for its result; raises RpcError on an error reply."""
        pending = self.start_request(method, params)
        return pending.wait(self.timeout if timeout is None else timeout)

    def notify(self, method: str, params: Message | None = None) -> None:
        self.wire.notify(method, params)

    def cancel(self, pending: Pending, reason: str | None = None) -> bool:
        """Cancel an in-flight request: tell the server, and stop waiting for the reply.

        Returns False, sending nothing, if the request already has its reply. A reply that
        arrives after the cancellation is dropped and reported by the wire. `initialize` is
        never cancelled.

        `spec:docs/specification/2025-11-25/basic/utilities/cancellation.mdx:13`
        "sends a `notifications/cancelled`"
        `spec:docs/specification/2025-11-25/basic/utilities/cancellation.mdx:35`
        "MUST NOT** be cancelled by clients"
        """
        if pending.method == "initialize":
            raise ValueError("the initialize request must not be cancelled")
        if pending.done:
            return False
        self.wire.abandon(pending)
        params: Message = {"requestId": pending.id}
        if reason is not None:
            params["reason"] = reason
        self.wire.notify("notifications/cancelled", params)
        return True

    def close(self) -> int | None:
        """Shut the server down as the stdio lifecycle says; returns its exit status.

        Close the child's stdin and wait `grace` seconds, then SIGTERM and wait `grace` more,
        then SIGKILL. A negative status is the signal that ended it. Safe to call twice.

        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:233`
        "closing the input stream to the child process"
        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:234`
        "sending `SIGTERM` if the server does not exit"
        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:236`
        "Sending `SIGKILL` if the server does not exit"
        """
        with self._close_lock:
            if self._status is not None or self.process is None:
                return self._status
            self.wire.close_input()
            try:
                self._status = self.process.wait(self.grace)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self._status = self.process.wait(self.grace)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self._status = self.process.wait()
            self.wire.join(self.grace)
            if self.process.stdout is not None:
                self.process.stdout.close()
            return self._status
