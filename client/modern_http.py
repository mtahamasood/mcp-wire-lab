"""The 2026-07-28 era over Streamable HTTP (phase 7 D11): phase 6's session on phase 7's wire.

`ModernSession` (client/modern.py) already does the era's lifecycle (`server/discover`, the
envelope in every request, `subscriptions/listen`); `HttpSession` (client/http_wire.py) already
posts. This class is both, plus the one rule the transport adds: cancelling a request closes the
connection carrying its stream and sends no `notifications/cancelled`. The wire (built with
`era`) sends no session id; the session opens no GET stream and sends no DELETE, since it never
has a session id.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from client.http_wire import MODERN_ERA, HttpSession, HttpWire
from client.modern import ModernSession, Registry
from client.wire import DEFAULT_TIMEOUT, Message, Pending, stderr_report


class ModernHttpSession(ModernSession, HttpSession):
    """The 2026-07-28 session over HTTP: discover first, request headers on every POST."""

    @classmethod
    def open_http(
        cls, url: str, *, capabilities: Message | None = None,
        report: Callable[[str], None] = stderr_report,
        observer: Callable[[str, Any], None] | None = None,
        on_notification: Callable[[Message], None] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> ModernHttpSession:
        """Connect to `url`; notifications with a subscription id are filed (phase 6 D5)."""
        registry = Registry(on_notification)
        wire = HttpWire(url, report=report, observer=observer, on_notification=registry.feed,
                        era=MODERN_ERA)
        session = cls(wire, timeout=timeout)
        session.registry = registry
        session.capabilities = {} if capabilities is None else capabilities
        return session

    def cancel(self, pending: Pending, reason: str | None = None) -> bool:
        """Stop waiting and close the request's stream; no `notifications/cancelled` (D11).

        `spec:docs/specification/2026-07-28/basic/transports/streamable-http.mdx:235`
        "Closing the SSE response stream **MUST** be treated by the server as"
        """
        return self.wire.abandon(pending)
