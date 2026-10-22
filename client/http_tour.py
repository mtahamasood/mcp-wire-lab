"""The HTTP tour (phase 7 D9): what Streamable HTTP adds, one step at a time.

Usage:
  python3 -m client.http_tour --url <url> [--no-stream] [--slice]

The slice (`--slice`): `initialize` with no capabilities, `notifications/initialized`,
`tools/call echo`, close (DELETE). The tour: the client declares `roots` and `sampling`, opens
the GET stream before `notifications/initialized`, answers the server's `roots/list` on it, calls
`echo`, calls `trigger-sampling-request` (whose `sampling/createMessage` arrives on that call's
own stream and is answered by its own POST), starts `trigger-long-running-operation` with a
`progressToken` and cancels it after its first progress, and closes with a DELETE, after which
the GET stream ends. `--no-stream` leaves the GET stream out (the server's `roots/list` then never
arrives). Each step prints the HTTP status and content type it saw, and the tour exits 0 only if
every step saw what the 2025-11-25 transport predicts: `200` `text/event-stream` for a request,
`202` for a notification or a reply, `200` for DELETE.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable, Sequence
from typing import TextIO

from client.handlers import Handlers
from client.http_wire import EVENT_STREAM, HttpSession
from client.server_tour import settle_after_initialized
from client.wire import Cancelled, Message, stderr_report

USAGE = (
    "usage: python3 -m client.http_tour --url <url> [--no-stream] [--slice]\n"
    "  Runs the HTTP tour against a Streamable HTTP server (for example the everything server\n"
    "  started with `streamableHttp`), printing the HTTP status and content type of each step.\n"
    "  --no-stream  do not open the GET stream (the server's roots/list never arrives)\n"
    "  --slice      only initialize, initialized, one tools/call and the DELETE\n"
    "  To record a run with the tap in between, use scripts/record.sh --http --client http-tour."
)
CAPS = ("roots", "sampling")
CANCEL_PROGRESS = "http-tour-cancel"
PROGRESS_WAIT = 10.0


class TourFailure(Exception):
    """A step did not see the message, status or content type the transport predicts."""


class HttpTour:
    def __init__(
        self, session: HttpSession, handlers: Handlers, out: TextIO, *,
        stream: bool = True, slice_only: bool = False,
    ) -> None:
        self.session = session
        self.handlers = handlers
        self.out = out
        self.stream = stream
        self.slice_only = slice_only
        self.step_no = 0
        self._print_lock = threading.Lock()

    # -- output and checks -------------------------------------------------------------

    def say(self, text: str) -> None:
        with self._print_lock:
            print(text, file=self.out, flush=True)

    def step(self, label: str, summary: str) -> None:
        self.say(f"{self.step_no:>2}  {label:<42} {summary}")
        self.step_no += 1

    def expect(self, condition: bool, what: str) -> None:
        if not condition:
            raise TourFailure(what)

    def saw(self, kind: str, ident: object, status: int, content_type: str = "") -> str:
        """Wait for the HTTP response to one of our requests; check it; describe it."""
        head = self.session.http.wait_head(kind, ident)
        self.expect(head is not None, f"no HTTP response seen for {kind} {ident!r}")
        assert head is not None
        # A 202 has no body to describe; the server labels it text/plain, which proves nothing.
        self.expect(head.status == status
                    and (not content_type or head.content_type == content_type),
                    f"{kind} {ident!r}: expected HTTP {status} {content_type}, "
                    f"saw {head.status} {head.content_type}")
        return f"HTTP {head.status}" + (f" {head.content_type}" if content_type else "")

    def tool(self, name: str, arguments: Message) -> tuple[int, str]:
        """Call a tool; the request id and the first text of its result."""
        pending = self.session.start_request("tools/call", {"name": name, "arguments": arguments})
        result = pending.wait(self.session.timeout)
        self.expect(not result.get("isError"), f"{name} returned an error: {result}")
        text: str = result["content"][0]["text"]
        return pending.id, text

    # -- the steps ---------------------------------------------------------------------

    def run(self) -> None:
        self.opening()
        if not self.slice_only:
            self.server_traffic()
        self.echo()
        if not self.slice_only:
            self.sampling()
            self.cancelled()
        self.closing()

    def opening(self) -> None:
        """`initialize`, the GET stream (if any), `notifications/initialized`.

        `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:57`
        "method": "initialize"
        """
        caps = None if self.slice_only else self.handlers.capabilities
        result = self.session.initialize(caps, stream=self.stream)
        http = self.session.http
        self.expect(http.session_id is not None, "the server gave no Mcp-Session-Id")
        info = result.get("serverInfo", {})
        self.step("initialize", f"{self.saw('request', 0, 200, EVENT_STREAM)}, version "
                  f"{result['protocolVersion']}, server {info.get('name')}, session id received")
        if caps and self.stream:
            self.step("GET (stream, before initialized)", self.saw("stream", "", 200, EVENT_STREAM))
        self.step("notifications/initialized", self.saw(
            "notification", "notifications/initialized", 202))

    def server_traffic(self) -> None:
        """What the server says unprompted, which only the GET stream carries (M8)."""
        if not self.stream:
            time.sleep(1.0)  # past the server's 350 ms roots sync, so its absence is a fact
            self.expect(self.handlers.counts["roots/list"] == 0,
                        "roots/list arrived with no GET stream open")
            self.step("roots/list (server asked)", "never arrived: no GET stream was open")
            return
        settle_after_initialized(self.handlers, self.handlers.caps)
        self.expect(self.handlers.counts["roots/list"] == 1, "the server did not ask roots/list")
        asked = self.session.http.server_request_ids("roots/list")[0]
        self.step("roots/list (server asked, on the GET stream)",
                  f"answered by POST: {self.saw('response', asked, 202)}")

    def echo(self) -> None:
        """`tools/call` `echo`: a request is answered on its own event stream."""
        request_id, text = self.tool("echo", {"message": "hello over http"})
        self.expect("hello over http" in text, f"echo did not repeat the message: {text!r}")
        self.step("tools/call echo", self.saw("request", request_id, 200, EVENT_STREAM))

    def sampling(self) -> None:
        """`trigger-sampling-request`: the server's request arrives on this call's stream."""
        request_id, text = self.tool("trigger-sampling-request", {"prompt": "hello over http"})
        self.expect(self.handlers.counts["sampling/createMessage"] == 1, "no sampling request")
        self.expect("canned reply from wire-lab-raw" in text, f"canned reply missing: {text!r}")
        reply = self.saw("response", self.sampling_id(), 202)
        self.step("tools/call trigger-sampling-request",
                  f"{self.saw('request', request_id, 200, EVENT_STREAM)}; reply by POST: {reply}")

    def sampling_id(self) -> int:
        """The id the server gave its `sampling/createMessage` request."""
        ids = self.session.http.server_request_ids("sampling/createMessage")
        self.expect(len(ids) == 1, "expected one sampling/createMessage request")
        return int(ids[0])

    def cancelled(self) -> None:
        """A long-running call cancelled after its first progress: the connection is closed.

        `spec:docs/specification/2025-11-25/basic/utilities/cancellation.mdx:22`
        "method": "notifications/cancelled"
        """
        progress = self.handlers.watch_progress(CANCEL_PROGRESS)
        pending = self.session.start_request("tools/call", {
            "name": "trigger-long-running-operation",
            "arguments": {"duration": 2, "steps": 4},
            "_meta": {"progressToken": CANCEL_PROGRESS},
        })
        deadline = time.monotonic() + PROGRESS_WAIT
        while not progress and time.monotonic() < deadline:
            time.sleep(0.05)
        self.expect(bool(progress), f"no progress within {PROGRESS_WAIT:g} s")
        self.expect(self.session.cancel(pending, "the tour cancels after the first progress"),
                    "the request had already finished before it could be cancelled")
        try:
            pending.wait(0)
        except Cancelled:
            pass
        else:
            raise TourFailure("a cancelled request must stop waiting")
        self.step("tools/call long-running (cancelled)",
                  f"{self.saw('request', pending.id, 200, EVENT_STREAM)}; stream closed by the "
                  f"client; notifications/cancelled: "
                  f"{self.saw('notification', 'notifications/cancelled', 202)}")

    def closing(self) -> None:
        """DELETE with the session id; the server then ends the GET stream (M11)."""
        status = self.session.close()
        self.expect(status == 200, f"DELETE answered {status}, expected 200")
        http = self.session.http
        if not self.slice_only and self.stream:
            self.expect(http.stream_end == "server", "the GET stream did not end after DELETE")
            self.step("DELETE (close)", "HTTP 200; the GET stream ended, closed by the server")
        else:
            self.step("DELETE (close)", "HTTP 200")


def run_http_tour(
    url: str, out: TextIO, *, stream: bool = True, slice_only: bool = False,
    report: Callable[[str], None] | None = None,
) -> int:
    """Run the tour against `url`; 0 if every step saw what the transport predicts."""
    say_lock = threading.Lock()

    def say(text: str) -> None:
        with say_lock:
            print(f"      {text}", file=out, flush=True)

    handlers = Handlers(() if slice_only else CAPS, say=say, report=report or stderr_report)
    session = HttpSession.connect(
        url, report=report or stderr_report,
        on_request=handlers.handle_request, on_notification=handlers.handle_notification,
    )
    handlers.attach(session.wire)
    tour = HttpTour(session, handlers, out, stream=stream, slice_only=slice_only)
    status = 0
    try:
        tour.run()
    except Exception as exc:  # any failed step: say which, then still shut down
        failure = f"{tour.step_no:>2}  FAILED  {type(exc).__name__}: {exc}"
        tour.say(failure)
        (report or stderr_report)(f"http tour failed at step {failure.strip()}")
        status = 1
        session.close()
    return status


def main(argv: Sequence[str]) -> int:
    if list(argv[:1]) in (["-h"], ["--help"]):
        print(USAGE)
        return 0
    args = list(argv)
    stream, slice_only = True, False
    for flag in ("--no-stream", "--slice"):
        if flag in args:
            args.remove(flag)
            stream, slice_only = (False, slice_only) if flag == "--no-stream" else (stream, True)
    if len(args) != 2 or args[0] != "--url":
        print(USAGE, file=sys.stderr)
        return 2
    return run_http_tour(args[1], sys.stdout, stream=stream, slice_only=slice_only)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
