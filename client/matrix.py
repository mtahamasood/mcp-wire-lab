"""The capability matrix (phase 3 D3): what each client capability lets the server do.

One short session per capability set: none, each one alone, all of them. Each declares exactly
that set in `initialize`, waits for the server's burst after `initialized` to settle, asks
`tools/list` once more, and records which tools the server offers that only a capability
unlocks and which server-initiated methods it saw. The table is printed, never committed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TextIO

from client.handlers import CAPABILITIES, Handlers
from client.server_tour import GATED_TOOLS, settle_after_initialized
from client.session import Session
from client.wire import stderr_report

CAPABILITY_SETS: list[tuple[str, ...]] = [
    (), *[(c,) for c in CAPABILITIES], CAPABILITIES,
]
Row = tuple[str, list[str], list[str]]


def label(caps: Sequence[str]) -> str:
    if not caps:
        return "none"
    return "all" if tuple(caps) == CAPABILITIES else "+".join(caps)


def measure(
    command: Sequence[str], caps: Sequence[str], report: Callable[[str], None]
) -> Row:
    """One session: (capability set, gated tools listed, server-initiated methods seen)."""
    handlers = Handlers(caps, report=report)
    session = Session.open(
        command, report=report,
        on_request=handlers.handle_request, on_notification=handlers.handle_notification,
    )
    handlers.attach(session.wire)
    try:
        session.initialize(handlers.capabilities)
        settle_after_initialized(handlers, caps)
        tools = {t["name"] for t in session.request("tools/list")["tools"]}
        gated = [t for t in GATED_TOOLS if t in tools]
        seen = sorted(m for m in handlers.counts if m != "ping")
    finally:
        session.close()
    return label(caps), gated, seen


def run_matrix(
    command: Sequence[str], out: TextIO, report: Callable[[str], None] = stderr_report
) -> int:
    """Print the table; 0 once every session ran."""
    print("capabilities | gated tools listed | server-initiated methods seen", file=out)
    print("--- | --- | ---", file=out)
    for caps in CAPABILITY_SETS:
        name, tools, seen = measure(command, caps, report)
        print(f"{name} | {', '.join(tools) or '-'} | {', '.join(seen) or '-'}", file=out,
              flush=True)
    return 0
