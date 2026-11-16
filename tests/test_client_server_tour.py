"""C201 (phase 8, P8-FL-1): the server tour's steps wait for the notification they depend on.

Over Streamable HTTP the everything server sends a list change or a resource update on the
standalone GET stream, and the tool's result on the POST's own stream. The two are separate
connections, so the result can reach the client first; a step that checked for the
notification as soon as the result came failed in about one run in eight under load.
"""

from __future__ import annotations

import io
import threading
import unittest
from typing import Any

from client.handlers import CAPABILITIES, Handlers
from client.server_tour import STATIC_DOC, ServerTour

LATE = 0.3  # seconds between the tool's result and its notification


class LateNotes:
    """Stands in for the session and the wire: each trigger tool answers at once, and the
    notification it causes arrives `LATE` seconds after the result, as from another stream."""

    def __init__(self, handlers: Handlers) -> None:
        self.handlers = handlers
        self.timers: list[threading.Timer] = []

    def cancel(self) -> None:
        for timer in self.timers:
            timer.cancel()

    def later(self, message: dict[str, Any]) -> None:
        timer = threading.Timer(LATE, self.handlers.handle_notification, args=(message,))
        self.timers.append(timer)
        timer.start()

    def request(self, method: str, params: dict[str, Any] | None = None,
                timeout: float | None = None) -> dict[str, Any]:
        params = params or {}
        if method == "tools/call":
            arguments = params["arguments"]
            if params["name"] == "trigger-list-changed":
                self.later({"method": f"notifications/{arguments['list']}/list_changed"})
            elif params["name"] == "trigger-resource-update":
                self.later({"method": "notifications/resources/updated",
                            "params": {"uri": arguments["uri"]}})
            return {"content": [{"type": "text", "text": "sent"}]}
        if method.endswith("/list"):
            kind = method.split("/")[0]
            return {kind: []}
        return {}


class LateNotificationTest(unittest.TestCase):
    def tour(self) -> ServerTour:
        handlers = Handlers(CAPABILITIES, report=lambda _: None)
        stand_in = LateNotes(handlers)
        handlers.attach(stand_in)  # type: ignore[arg-type]
        self.addCleanup(stand_in.cancel)
        return ServerTour(stand_in, handlers, io.StringIO())  # type: ignore[arg-type]

    def test_list_change_seen_after_the_tool_result(self) -> None:
        tour = self.tour()
        tour.list_changes()
        self.assertEqual(tour.handlers.relists, ["tools", "prompts", "resources"])

    def test_resource_update_seen_after_the_tool_result(self) -> None:
        tour = self.tour()
        tour.resource_update()
        self.assertEqual(tour.handlers.rereads, [STATIC_DOC])


if __name__ == "__main__":
    unittest.main()
