# Phase 7 — Streamable HTTP: requirements

**Status: specified in full, awaiting owner approval** (lean profile LP1–LP6 in `mission.md`;
register row 2026-10-22, which un-stubs phases 5, 6 and 7 and has them approved as one
batch before any test or code). Phase 1's decisions D1–D16 and phases 2–3's stand unless a
record below names one it amends. Facts about the pinned server, SDK and spec were measured
on 2026-10-22 (table M below); the walkthrough and code cite them with G8 citations, this
spec cites them by plain `file:line`.

## Learning objective

See what the HTTP transport adds on top of the same messages, by recording it on the wire:
one POST per client message; a reply as one JSON body or as an SSE stream, and why; the
`Mcp-Session-Id` that turns separate POSTs into one 2025-era session; the GET stream that
carries what the server says unprompted; the status codes and headers that carry protocol
rules (202, 404, 406, `MCP-Protocol-Version`); and how 2026-07-28 drops sessions and the GET
stream and adds request headers. The owner can explain, change and debug every HTTP request
the raw client sends and every record the tap writes.

## Scope

In: the tap's HTTP mode (D1–D6), recording over HTTP (D7), the raw client's HTTP transport
and an HTTP tour (D8, D9), the earlier tours over HTTP (D10), the 2026-07-28 era over HTTP
(D11, droppable), the SDK client over HTTP (D12, droppable), walkthrough and lesson 07 (D13).

Out (D14): the deprecated HTTP+SSE transport and OAuth (mission non-goals); resumability
(`Last-Event-ID`, replay, `retry`; roadmap backlog); everything else listed in D14.

## M. Measured at the pins (2026-10-22)

How: the built server started as `env -i PATH=… HOME=… LANG=C.UTF-8 PORT=<high port> node
vendor/servers/src/everything/dist/index.js streamableHttp` (M1–M15) and with `PORT` set to a
Unix-socket path (M16), driven by `curl` and by a stdlib-only Python script (`http.client`),
outputs kept outside the repository (A5). Paths:
`servers:` is `vendor/servers`, `sdk-server` is
`vendor/servers/node_modules/@modelcontextprotocol/server/dist`, `sdk-client` the same for
`client`, `spec` is `vendor/spec/docs/specification`.

| Id | Fact | Where |
| --- | --- | --- |
| M1 | Started by `node dist/index.js streamableHttp`; `PORT` (default 3001) is passed unchanged to Express's `app.listen` with no host and is the only listening setting; one endpoint `/mcp` for POST, GET and DELETE. Given a port number it binds **every interface** (`ss -ltn` shows `*:<port>`), against the spec's SHOULD bind to localhost; given a path it listens on that Unix socket instead (M16). With a port it accepted TCP connections about 1 s after spawn. Logs go to stdout (one `Received MCP POST request` per POST, `Session initialized with ID: …`) and the listening line to stderr | `servers:src/everything/index.ts:35`; `servers:src/everything/transports/streamableHttp.ts:383`, `:187`, `:275`, `:307`; `servers:src/everything/transports/listen.ts:24`; `spec:2025-11-25/basic/transports.mdx:81` |
| M2 | Era routing: a POST with `Mcp-Session-Id`, every GET and every DELETE are 2025 era; a session-less POST is 2026-07-28 when its body carries the `_meta` envelope claim, else 2025 | `streamableHttp.ts:18-21`, `:203-209` |
| M3 | 2025 era: a POST carrying a request is always answered `200` `text/event-stream` (JSON mode is off); the stream opens with a priming event (`id: <uuid>`, empty `data:`; only when the negotiated version is 2025-11-25 or later, absent at 2025-06-18), then one `event: message` / `id: <uuid>` / `data: <one JSON-RPC message>` per message, and ends after the response | `sdk-server/index.mjs:391`, `:520-527`, `:669-673`, `:794-850`, `:994-995` |
| M4 | A POST carrying a notification or a response is answered `202`, empty body | `sdk-server/index.mjs:771-776`; `spec:2025-11-25/basic/transports.mdx:96` |
| M5 | The `initialize` reply carries `mcp-session-id: <uuid>`; a later POST without it gets `400` "Server not initialized" (a session-less POST starts a fresh transport); an unknown or ended session gets `404`, code `-32001`, with the request's id | `sdk-server/index.mjs:752`, `:875-889`; `streamableHttp.ts:77-83`, `:216-252` |
| M6 | POST needs `Accept` listing both `application/json` and `text/event-stream` (else `406`) and `Content-Type: application/json` (else `415`); `MCP-Protocol-Version` may be absent, and if present must be one of 2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05, 2024-10-07 (else `400`) | `sdk-server/index.mjs:707-713`, `:904-910`; `spec:2025-11-25/basic/transports.mdx:265` |
| M7 | GET with the session id: `200` `text/event-stream`, no priming event; a second GET in the same session gets `409`. Every open stream gets a `: keepalive` comment every 15 s (measured 15.0 s) | `sdk-server/index.mjs:531-579`, `:544-546`; `sdk-server/mcp-DIH4cS6P.mjs:62` |
| M8 | Server messages related to a request (progress, log messages, the `sampling/createMessage` of `trigger-sampling-request`) arrive on that request's POST stream. Unrelated ones arrive on the GET stream: with `roots`, `sampling` and `elicitation` declared, four `notifications/tools/list_changed` right after `initialized`, the `roots/list` sync about 350 ms later, and a log message. With no GET stream open they are dropped: with `roots` declared and no GET, the `roots/list` sync never arrived and a `get-roots-list` call got no reply within 15 s. With no capabilities declared the GET stream stayed silent | `sdk-server/index.mjs:939-950` |
| M9 | A server request on a POST stream is answered by a new POST (`202`) while that stream stays open; the tool's result then arrives on the original stream | measured |
| M10 | 2025 cancellation: `notifications/cancelled` is answered `202`; the cancelled request's stream carries the remaining progress events, then only keepalives: no response, and the stream never ends until the client closes it (watched for 30 s) | measured; `spec:2025-11-25/basic/transports.mdx:128` |
| M11 | DELETE with the session id: `200`, empty body; the GET stream ends before the DELETE reply is read; later requests get `404` | `sdk-server/index.mjs:859-869` |
| M12 | SIGINT runs the server's shutdown (closes every session and stream) and exits 0; there is no SIGTERM handler | `streamableHttp.ts:349-369`, `:391` |
| M13 | 2026-07-28 over HTTP: no session id; `server/discover` and `tools/call echo` answered `200` `application/json`; a call that sends progress first is upgraded to `text/event-stream` (events with no `id`, no priming event); `MCP-Protocol-Version` and `Mcp-Method` (and `Mcp-Name` for `tools/call`) are required, else `400` code `-32020`; a GET is answered `400` "No valid session ID provided" by the 2025 route, not the spec's `405` | `sdk-server/index.mjs:101-137`; `sdk-server/src-Cqbh3MYc.mjs:5123-5142`; `streamableHttp.ts:278-287`; `spec:2026-07-28/basic/transports/streamable-http.mdx:244-291`, `:683` |
| M14 | Python's `http.client` reads a chunked SSE response one line at a time (`readline`) while it streams, so the tap and the raw client need no library (P4) | measured |
| M15 | The SDK client 2.3.1 opens its GET stream only after the `initialized` POST is answered `202`, and sends DELETE only from `terminateSession()` | `sdk-client/index.mjs:5797`, `:5836` |
| M16 | With `PORT` set to a Unix-socket path the server listens on that socket only: its process has no TCP listener (`ss -ltnp`) and the socket is listed by `ss -lxp`. It accepted a connection about 0.35 s after spawn. A 2025-era `initialize` POST over the socket, sent with `Host: localhost` by `curl --unix-socket` and by an `http.client.HTTPConnection` subclass whose `connect` opens a `socket.AF_UNIX` socket, got `200` `text/event-stream` with `mcp-session-id`. The listening line on stderr names the path. The path must be short (the Unix limit is about 108 bytes; curl refused a 120-byte path): a `tempfile.mkdtemp()` directory under the system temp directory (mode 0700; under the D14 allowlist `TMPDIR` is unset, so `/tmp`) plus `server.sock` is under 40 bytes. SIGINT exits 0 without removing the socket file. A `python3` started under `env -i` with the D14 allowlist gives its child exactly that allowlist plus `PORT` (read from the server's `/proc/<pid>/environ`) | `servers:src/everything/transports/listen.ts:24`; `servers:src/everything/transports/streamableHttp.ts:383-387`, `:349-369`; measured |

## Parts, in order of value

| Part | What | Depends on | Droppable |
| --- | --- | --- | --- |
| A | Tap HTTP mode (D1–D6) and `record.sh --http` (D7) | nothing new; buildable beside phase 6 | no |
| B1 | Raw client HTTP transport and HTTP tour (D8, D9) | part A for its e2e | no |
| E | Walkthrough and lesson 07 (D13) | A, B1 | no |
| B2 | Earlier raw-client modes over HTTP (D10) | phase 6 merged (it edits the same `client/` files) | yes, with a register row |
| D | 2026-07-28 era over HTTP (D11) | phase 6 | yes, no effect on A, B, E |
| C | SDK client over HTTP (D12) | phases 5 and 6 | yes, no effect on A, B, E |

Files part A touches, exactly: `tap/http.py` (new), `tap/__main__.py` (the `--http` option,
its usage text and the dispatch to `tap.http`; the stdio path is not changed),
`tests/test_tap_http.py` (new), `tests/fake_servers/http_upstream.py` (new); then
`tap/show.py` (`describe` only) and `tests/test_show_http.py` (new) for D6; then
`scripts/record.sh` (one `--http` block), `tests/test_e2e_http.py` (new) and the G5 line of
`scripts/gate.sh` (adds `tests.test_e2e_http`) for D7. None of these is a file phase 6 is
expected to change except `scripts/record.sh` (see *What this phase needs from phases 5
and 6*).

### D1 — One trace format for both transports (amends phase 1 D3)

HTTP mode writes the phase 1 trace format: the same fields, one timeline, strict JSON Lines,
`spawn` first and `exit` last, mode 0600. What HTTP adds goes into `tap` records and into an
`http` object on a frame; JSON-RPC traffic stays in `c2s` and `s2c` frames. Per HTTP
exchange (one request and its response; numbered `exchange` 0, 1, … in the order the request
heads reach the tap):

- `tap` record `http-request`: `http` = `{exchange, method, path, headers, body_bytes}`.
- a request with a non-empty body: then one `c2s` frame whose `bytes`, `raw` (or `raw_b64`),
  `json` and `parse_error` describe the body as phase 1 D3 describes a stdio frame (`raw` is
  the body, no newline added), plus `http` = `{exchange}`;
- `tap` record `http-response` when the response head arrives: `http` =
  `{exchange, status, headers}`;
- a non-empty body that is not an event stream: one `s2c` frame, `http` = `{exchange}`;
- an event stream: one `s2c` frame per event with non-empty data (D4), `http` =
  `{exchange, sse: {id, event}}` (each key only when the event had that field); one `tap`
  record `sse-event` per event with empty data (the priming event, M3), `http` =
  `{exchange, id, retry}`; and when the stream ends, one `tap` record `http-end`, `http` =
  `{exchange, by, comments}` where `by` is `server`, `client` or `tap` and `comments` counts
  the comment lines forwarded but not recorded;
- once, when the server is reachable, a `tap` record `listen` with `listen`
  (`127.0.0.1:<port>`) and `upstream` (`unix:<socket path>`, D2); the path is new on every
  run, so committed docs write it only as `unix:<temp dir>/server.sock`, never a measured
  value (P9);
- the server's stdout and stderr are both `stderr` frames (in HTTP mode stdout carries logs,
  not protocol, M1); those from stdout carry `"stream": "stdout"`.

A request's records are written before it is sent upstream, and an event's record before the
bytes that complete it are forwarded, so a cause is on the timeline before its effect (as
phase 1 D2 orders stdio frames). Consequence: `tap.show`, `tap.check` and `tap.diff` (phase 5)
load HTTP traces with no change to how they read records; `tap.check` sees only bodies; the
`--explain` anchors are phase 1 D11's (`tap.http-request.0`, `c2s.initialize.0`, …).

*Rationale:* one format is the stub's promise and what makes stdio and HTTP traces comparable;
keeping heads, priming events and stream ends out of `c2s`/`s2c` keeps every frame a body, so
`tap.check` passes a clean HTTP session unchanged.
*Rejected:* a new `dir` value such as `http` (the viewer and the checker refuse unknown `dir`
values, phase 1 D5); one record per exchange holding all its messages (loses the order of
events inside a stream, which is the point of M8–M10); splitting SSE bytes on `\n` into frames
(an SSE event is not a line; its data can span lines).
*Cost accepted:* a frame's `raw` is the body or event data, not the bytes on the socket: chunk
framing and the `data: ` prefixes are not recorded, and headers outside D5 are not recorded.
*Source:* stub D1 and register row 2026-10-20 (transports); roadmap.md phase 7 row; stakeholder
ask A2, 2026-10-20; register row 2026-10-22.

### D2 — The HTTP mode starts the server and stands in front of it (amends phase 1 D1, D4)

`python3 -m tap --trace <file> --http <listen-port> -- <server command…>`. `--http` with
`--delay` or `--drop`, or a value that is not a port 1–65535, is a usage error (phase 1 D1: one
`tap:` line or the usage, exit 2, no child started). The tap makes a private directory with
`tempfile.mkdtemp()` under the system temp directory (mode 0700); if that fails, or
`<directory>/server.sock` is longer than 100 bytes, it prints one `tap:` line and exits 1,
starting nothing. It then records `spawn` and starts the command as a child in its own process
group with stdin `/dev/null` and the tap's own environment plus `PORT=<directory>/server.sock`,
so the pinned server listens on that Unix socket and on no network interface (M1, M16). It
relays the child's stdout and stderr to its own stderr (recording both, D1), then tries to
connect to the socket (`socket.AF_UNIX`) every 50 ms for up to 15 s (M16: about 0.35 s). When
one succeeds it binds `127.0.0.1:<listen-port>` (loopback only), records `listen`, prints
`tap: listening on http://127.0.0.1:<listen-port>` on stderr, and proxies (D3) to the socket
until the child exits, with the standard library only (P4): an `http.client.HTTPConnection`
subclass whose `connect` opens an `AF_UNIX` socket to that path. If the child exits first, or
the wait or the bind fails, the tap prints one `tap:` line, sends SIGINT to a child still
running, records `exit` and exits with the child's code (1 if that is 0). Signals are
forwarded as phase 1 D4 says; SIGINT is how a recording ends (M12). When the child exits the
tap stops accepting, gives open exchanges up to 2 s to end (they end when the server's sockets
close), writes `exit` last and exits with the child's code. On every exit after the directory
is made, the tap removes it and the socket in it (the server leaves the socket file behind,
M16). The tap's own stdin and stdout are not used in HTTP mode.

*Rationale:* one process owns the server's life and environment, so the recording allowlist
(D7) still decides what the server sees and the trace still runs from `spawn` to `exit`; the
client is given only the tap's port. The owner decided that the server's listening address
comes from configuration (register row 2026-10-22): `PORT` set to a socket path in a directory
only the tap's user can enter means no recording exposes the server on any network interface,
and no upstream port has to be picked.
*Rejected:* proxying to a server started separately (no `spawn`/`exit`, two processes for
`record.sh` to manage); a forward proxy (each client would need proxy support; a reverse proxy
needs only a URL); a loopback TCP port for the server (the pinned server takes no host, M1, so
it would bind every interface); patching the server (the pin is read-only); a firewall rule
(needs root and differs per platform).
*Cost accepted:* readiness is a socket connection, not an HTTP request; a server under the tap
must take its listening address from `PORT` as a socket path; the socket path is new on every
run and appears in the server's listening line and the `listen` record (D1).
*Source:* stakeholder ask A2, 2026-10-20; register row 2026-10-20 (transports); register row
2026-10-22 (the owner's decision that the server's binding comes from configuration).

### D3 — What the tap forwards unchanged, and what is its own (amends phase 1 D2)

Forwarded unchanged: the request method, path and query, and body bytes; the response status
and body bytes; every header except the hop-by-hop ones (`Connection`, `Keep-Alive`,
`Proxy-*`, `TE`, `Trailer`, `Transfer-Encoding`, `Upgrade`) and `Host`. The tap's own: `Host:
localhost` upstream, always (the received `Host` names the tap's port, which differs per run;
the socket has no host name; the server accepted `localhost`, M16); one upstream connection to
the socket per request (no reuse); the request body read whole and sent with a
`Content-Length`; a response body sent to the client with the upstream's `Content-Length`, or
chunked when it had none, **each piece forwarded and flushed as soon as it is read** (a server
request on a stream must reach the client before the stream's final response, M9). When the
client disconnects mid-stream the tap closes the upstream connection, so the server sees the
disconnect as it would without the tap (`http-end` by `client`); when the server ends a stream
the tap ends the client's response (`http-end` by `server`). If the upstream cannot be reached
or fails before a response head, the tap answers `502` with an empty body and records
`http-response` with `status: 502` and `"by": "tap"`. Recording fails open as phase 1 D2 says:
a trace write failure stops recording, proxying goes on, the exit code is unchanged.

*Rationale:* between an HTTP client and server the contract is method, path, headers, status
and body bytes; chunk boundaries and connection reuse are hop-by-hop, which any HTTP
intermediary may change. Streaming is a correctness requirement here, not a speed-up.
*Rejected:* buffering whole responses (deadlocks the M9 round trip and holds a GET stream
forever); re-serializing bodies (hides the bytes A2 asks to see).
*Cost accepted:* the trace says nothing about TCP connections or chunk boundaries.
*Source:* stakeholder ask A2, 2026-10-20; register row 2026-10-22.

### D4 — An SSE event becomes one frame

The tap reads a `text/event-stream` body as the SSE standard's event-stream interpretation
says: a line ends with CRLF, LF or CR; a line starting with `:` is a comment (forwarded,
counted, not recorded); `field: value` with one leading space after the colon removed, a line
without a colon a field with an empty value; `data` values joined with `\n`; `id`, `event` and
`retry` kept, other fields ignored; a blank line dispatches the event. An event with non-empty
data is an `s2c` frame (D1) whose `raw` is the data and whose `json` is its parse; data that is
not valid UTF-8 is `raw_b64` as phase 1 D3 says. An event with empty data is a `sse-event`
record. An event cut off by the end of the stream (no blank line) is not dispatched by a
client, so it is recorded as a frame with `partial: true` if it has data, and not otherwise.

*Rationale:* a learner reads one message per line in `tap.show`, as on stdio, while the event's
own `id` and `event` stay on the record.
*Rejected:* recording the event-stream text as one blob per response (a stream can last the
whole session).
*Cost accepted:* SSE fields other than `id`, `event`, `retry` and `data` are dropped from the
trace (none is used by the pinned server).
*Source:* register row 2026-10-22; roadmap.md phase 7 row.

### D5 — The headers that matter

`http.headers` holds, with names lowercased, values as received and a repeated header joined
with `, `: `accept`, `content-type`, `last-event-id`, and every header whose name starts with
`mcp-` (`mcp-session-id`, `mcp-protocol-version`, and 2026-07-28's `mcp-method`, `mcp-name`
and `mcp-param-*`). Every other header is forwarded and not recorded.

*Rationale:* these are the headers the two Streamable HTTP specs give rules for (M5, M6, M13);
`Date`, `ETag`, `Host` (holds the tap's port; upstream it is always `localhost`, D3),
`X-Powered-By` and the CORS headers change from run
to run or say nothing about MCP.
*Rejected:* recording every header (traces that differ on every run for no protocol reason).
*Cost accepted:* a header outside the rule is invisible in the trace.
*Source:* stakeholder ask A2, 2026-10-20; register row 2026-10-22.

### D6 — `tap.show` shows the HTTP layer (amends phase 1 D5)

In the default view a `tap` record with an `http` object adds a summary after its event name:
`#<exchange> <METHOD> <path>` for `http-request`, `#<exchange> <status>` for `http-response`
(plus `by tap` for a tap answer), `#<exchange> id=<id>` for `sse-event`, `#<exchange> by <who>
comments=<n>` for `http-end`, each followed by the recorded headers as `name=value`. A frame
with an `http` object gets ` #<exchange>` after its description. Values are escaped as phase
1 D5 escapes server text. Anchors, pairing, `--full`, `--mermaid` and `--explain` are
unchanged.

*Rationale:* the transport is the subject of this lesson, and a learner reads traces with
`tap.show`.
*Rejected:* new viewer options (the default view must already show what HTTP adds).
*Cost accepted:* long lines when a request carries many headers.
*Source:* stakeholder ask A2, 2026-10-20; register row 2026-10-22.

### D7 — Recording over HTTP (amends phase 1 D14 and phase 2 D5)

`scripts/record.sh --http --client <mode> [name]` (modes: `http-tour`; after part B2 also
`tour`, `server-tour` and `manual`; after parts C and D their modes). It makes the run folder
as phase 1 D14 says, picks a free loopback port for the tap (bind port 0, read it, release),
and starts the tap in HTTP mode in the background under the D14 allowlist: `env -i <D14
allowlist> python3 -m tap --trace … --http <listen> -- node <server> streamableHttp`, with
`python3` reached through a link in the run folder's `bin/` as `node` is. The tap gives the
server its own environment plus `PORT` (D2), so the server's environment is exactly the
allowlist plus `PORT` (M16): the allowlist gains `PORT`, the one variable the server reads to
bind (M1), now carrying the socket path; for HTTP runs only. The `spawn` record's argv is
`node <server> streamableHttp`; the allowlist is the tap's environment, not part of argv. It
waits up to 20 s for the tap's port to accept a
connection (else `record: server did not start`, exit 1), runs the client with `--url
http://127.0.0.1:<listen>/mcp`, then sends SIGINT to the tap, waits for it, and prints the same
`recorded:` and `read it:` lines, exiting with the client's status (phase 2 D5). The tap's
stderr, which carries the server's logs, goes to `stderr.txt`. `--http` with a fixture is a
usage error: fixtures stay stdio (D14). `--help` describes `--http`.

*Rationale:* one script still records everything (L16), with the same folder, allowlist and
output lines, so lessons and tests read HTTP runs as they read stdio runs.
*Rejected:* a second recording script (two copies of the allowlist logic); `PORT` in the
server command's `env -i` list (the tap makes the socket's directory, so the path is not known
when the command is written).
*Cost accepted:* the port picked then released can be taken by another process before the tap
binds it; the run then fails and says so.
*Source:* A5, 2026-10-20; owner decision, 2026-10-20 — registered in mission.md (A4,
delegated; roadmap L16); register row 2026-10-22 (the server's binding comes from
configuration).

### D8 — The raw client's HTTP transport

`client/http_wire.py` holds `HttpWire`, a subclass of phase 2's `Wire` whose lines travel by
HTTP, and `HttpSession`, a subclass of `Session`. Classification, id correlation, the pending
table, cancellation bookkeeping, the handlers and the notification queue are phases 2 and 3's
code, reused unchanged: `client/wire.py` and `client/session.py` are not edited.

- **Sending.** Every message the wire writes is one POST to the URL with `Content-Type:
  application/json` and `Accept: application/json, text/event-stream`, and, once `initialize`
  has its result, `Mcp-Session-Id` (when the server gave one) and `MCP-Protocol-Version: <the
  negotiated version>` (not on `initialize` itself). POSTs are sent in the order messages are
  written; each response is read on its own thread, so a long response never blocks the next
  send (M9).
- **Receiving.** `202`: nothing to read. `200` `application/json`: the body is one incoming
  line, given to the phase 2 line handler. `200` `text/event-stream`: each event's data is one
  incoming line, in order, until the stream ends; empty-data events and comments are skipped.
  Any other status: a JSON-RPC body with a non-null `id` is an incoming line (so the request
  fails with its error object); otherwise the request that POST carried fails at once with
  `HttpStatusError` naming the status, and for a POST that carried no request the status is
  reported on stderr.
- **Session.** The session id comes from the `initialize` response's `Mcp-Session-Id`. A `404`
  to a POST that carried it ends the session: pending and later requests fail with
  `SessionEnded` (the spec's re-initialize is not done; D14).
- **The GET stream.** `open_stream()` sends a GET with `Accept: text/event-stream` and the
  session headers and reads it on its own thread; its events go to the same line handler. A
  mode that declares any capability calls it after `initialize` returns and **before**
  `notifications/initialized` (M8: otherwise the server's `roots/list` sync and list-change
  notifications are lost). A `405` or other refusal is reported and the session goes on
  without it.
- **Cancellation.** Abandoning a pending request (phase 2 D2) also closes the connection
  carrying its response stream (M10: otherwise that stream never ends); in the 2025 era
  `Session.cancel` still sends `notifications/cancelled`.
- **Close.** `HttpSession.close()` sends DELETE with the session headers (when there is a
  session), closes the GET stream and every open response, fails what is pending as phase 2 D2
  says after close, and returns the DELETE status (`None` with no session). There is no process
  to wait for.
- No reconnection, no `Last-Event-ID`, no retry (D14). Stream sockets have no read timeout
  (keepalives come every 15 s, M7); a request's wait is bounded by phase 2 D2's timeout.
- Each function that builds, sends or reads an HTTP message carries a verified spec citation
  in its docstring (L2, G8).

*Rationale:* the transport is the only thing that differs; reusing the wire and session shows
that the JSON-RPC layer is untouched by HTTP, which is the lesson's main claim.
*Rejected:* a second raw client (duplicates the claim code of phases 2–3); `urllib.request`
(hides the connection and header steps that `http.client` exposes); a pool of keep-alive
connections (an optimisation the lesson does not need).
*Cost accepted:* one TCP connection and one thread per message.
*Source:* stakeholder asks A2 and A3, 2026-10-20; register row 2026-10-20 (transports);
register row 2026-10-22.

### D9 — The HTTP tour

`python3 -m client.http_tour --url <url>` (`-h`/`--help` prints its usage and exits 0, phase 1
D1). The slice (LP3): `initialize` with no capabilities, `notifications/initialized`,
`tools/call` `echo`, close (DELETE). The widened tour: declares `roots` and `sampling` (answered
by phase 3's handlers); opens the GET stream before `initialized`; waits for the server's
`roots/list` on the GET stream and for the list-change burst to settle (as phase 3's server
tour does); `tools/call` `echo`; `tools/call` `trigger-sampling-request` (the
`sampling/createMessage` arrives on that call's stream and is answered by its own POST); a
`tools/call` of `trigger-long-running-operation` with a `progressToken`, cancelled after its
first progress; close (DELETE, after which the GET stream ends). `--no-stream` skips the GET
stream (an experiment, D13; the tour then expects no `roots/list`). It prints one line per step
with the HTTP status and content type it saw, and exits 0 only if each step saw the message,
status and content type M3–M11 predict (`200` `text/event-stream` for a request, `202` for a
notification or a reply, `200` for DELETE).

*Rationale:* each step shows one thing HTTP adds (session id, 202, the priming event, the GET
stream, a server request on a POST stream, cancellation by closing, DELETE), in a trace short
enough to explain frame by frame.
*Rejected:* explaining the phase 2 tour over HTTP note by note (about 150 records, most of them
repeating phase 2's notes).
*Cost accepted:* a third scripted tour to keep in step with the server.
*Source:* stakeholder ask A2, 2026-10-20; roadmap.md phase 7 row; register row 2026-10-22.

### D10 — The earlier modes over HTTP (part B2, after phase 6 merges)

`python3 -m client <tour|server-tour|manual> --url <url> [--caps …]`, instead of `--
<server command…>` (exactly one of the two), runs that mode over an `HttpSession`: `tour` as
phase 2 D3 (cancellation closes the stream, D8); `server-tour` as phase 3 D4 with the GET
stream opened before `initialized`; `manual` posts each typed line exactly as typed, so a junk
line shows the server's `400` body (`HttpStatusError` printed). `matrix` stays stdio. The fresh
traces of `tour` and `server-tour` over HTTP hold every method phase 2 D3 and phase 3 D4 list
and pass `tap.check --revision 2025-11-25`.

*Source:* roadmap.md phase 7 row (both clients run over HTTP); register row 2026-10-22.

### D11 — The 2026-07-28 era over HTTP (part D; needs phase 6; droppable)

With phase 6's era option and `--url`, the wire speaks 2026-07-28 over HTTP: no `initialize`,
no session id, no GET stream, no DELETE; every POST carries `MCP-Protocol-Version: 2026-07-28`,
`Mcp-Method: <method>`, and for `tools/call`, `resources/read` and `prompts/get` `Mcp-Name:
<params.name or params.uri>` (a value that is not plain ASCII is refused by the client with a
clear error; the Base64 form is D14); a response may be JSON or SSE (M13); cancelling a request
closes its stream and sends no `notifications/cancelled` (the 2026-07-28 rule on Streamable
HTTP); a long-lived stream such as `subscriptions/listen` is closed by the client at shutdown.
Phase 6's 2026 tour runs over HTTP and its fresh trace passes `tap.check --revision
2026-07-28`. Dropping this record changes nothing in D1–D10.

*Source:* register row 2026-10-20 (both eras); roadmap.md phase 7 row; register row 2026-10-22.

### D12 — The SDK client over HTTP (part C; needs phases 5 and 6; droppable)

The SDK client gains `--url <url>`: it uses `StreamableHTTPClientTransport` from the pinned
`@modelcontextprotocol/client` 2.3.1 instead of stdio, runs its 2025-era tour (and its
2026-07-28 tour when phase 6 gave it one), and calls `terminateSession()` before closing (M15:
the SDK sends DELETE only then). `record.sh --http --client <its mode>` records it, and its
fresh trace passes `tap.check`. The walkthrough lists, measured on a fresh pair, where its HTTP
traffic differs from the raw client's (for example the GET stream opened after the
`initialized` `202`, M15). Dropping this record changes nothing in D1–D11.

*Source:* stakeholder ask A3, 2026-10-20; roadmap.md phase 7 row; register row 2026-10-22.

### D13 — Walkthrough and lesson 07

`docs/walkthrough/07-streamable-http.md` has a note for every record of the HTTP tour's fresh
trace, checked by `tap.show --explain` in `tests/test_e2e_http.py` (phase 1 D11 anchors; range
notes for the server's log lines and for HTTP heads whose order varies). A note on a message
or HTTP event cites the 2025-11-25 transport section that governs it and the server or SDK
source that produced it (G8, `servers:` citations, which include the SDK under
`vendor/servers/node_modules`); a prose section explains M2 and M13 (the 2026-07-28 shape),
and the server's deviations from the spec (given a port it binds every interface, M1, which
is why recordings give it a Unix socket, D2 and M16; GET answered `400`
instead of `405` on the modern path, M13). `docs/lessons/07-streamable-http.md` has the L1
sections: *Run* records `scripts/record.sh --http --client http-tour` in a runnable block (G9);
*Read the trace* uses `tap.show`, `--explain` and `tap.check`; *Read the source* follows one
POST through `streamableHttp.ts` into the SDK's `handlePostRequest` (cited); *Experiments* (at
least three, outcomes measured at the pins): the HTTP tour without the GET stream
(`--no-stream`: `roots/list` never arrives, M8); two recordings of the HTTP tour compared (the
session id and SSE event ids are new on every run, the messages are not); phase 1's handshake
fixture over stdio beside the HTTP tour's first exchanges (the same `initialize` body, other
framing); and after part B2, the phase 2 tour over stdio and over HTTP compared (`tap.diff` if
phase 5 built it, else side by side) and a junk line in manual mode over HTTP (`400`);
*Check yourself* with answers in a collapsed block. `README.md` lists lesson 07. Lesson 07 declares no `exercises`
line (D14), and the final atlas coverage is measured at close (L8).

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap L1,
L3, L4, L5, L8); per-phase walkthrough P3; register row 2026-10-22.

### D14 — Nothing else is added

Declined for this phase: the HTTP+SSE transport (`sse`) and OAuth (mission non-goals);
resumability — `Last-Event-ID`, replay, honouring `retry` (roadmap backlog); re-initialising
after a `404`; TLS; the tap listening anywhere but `127.0.0.1`; an upstream on TCP; the fault mode (`--delay`,
`--drop`) over HTTP; fixture recordings over HTTP (they need an HTTP driver, which would be a
client, against phase 1 D9); `matrix` over HTTP; HTTP keep-alive reuse in the raw client;
batch POSTs; the Base64 sentinel for `Mcp-Name`; Origin and DNS-rebinding experiments (the
pinned server does not validate `Origin`); an `exercises` line in lesson 07 (HTTP adds no
method, and the atlas measures methods, not transports); any change to `client/wire.py`,
`client/session.py` or the tap's stdio path.

*Source:* mission.md non-goals; roadmap.md backlog; register row 2026-10-22.

## Amendments to earlier phases

Approving this spec amends, for HTTP mode only: phase 1 D1 (the `--http` option, D2), D2
(forwarding, D3), D3 (record fields, D1), D4 (lifecycle, D2), D5 (viewer summary, D6), D14
(recording: the tap runs under the allowlist and the server gets the allowlist plus `PORT`, a
socket path, D7); and phase 2 D5 (client recordings over HTTP,
D7). The stdio behaviour of each is unchanged. The approval's register row names these.

## What this phase needs from phases 5 and 6

Parts A, B1 and E need nothing from either phase. The rest assumes, of specs being written in
parallel:

- **From phase 5.** (P5-a) An SDK client under `clients/sdk/` on `@modelcontextprotocol/client`
  2.3.1, recorded by `scripts/record.sh --client <sdk mode>`, that builds its transport in one
  place so `--url` can swap in `StreamableHTTPClientTransport` (part C). (P5-b) `tap.diff a b`
  that loads any phase 1 trace; whether it compares or ignores `tap` records, HTTP traces load
  (D1). It is used only by a lesson experiment and part C; without it the lesson compares with
  `tap.show` side by side. (P5-c) Phase 5 may extend `scripts/record.sh`; phase 7's change is
  one `--http` block, merged after phase 5.
- **From phase 6.** (P6-a) A raw-client era option (assumed `--era 2026-07-28`) whose
  2026-07-28 session builds the `_meta` envelope; part D needs only the era and the outgoing
  JSON (it reads `method` and `params.name`/`params.uri` from the message it posts). (P6-b)
  `Wire`'s `_write`, `start`, `join`, `abandon`, `close_input` and `handle_line` keep their
  phase 2 meaning; if phase 6 changes them, D8 is amended by a register row before part B is
  built on them. (P6-c) `tap.check --revision 2026-07-28` (part D's check). (P6-d) Phase 6 edits
  `client/__main__.py`, `client/tour.py` and `client/session.py`, so part B2 waits for its
  merge; part A touches none of them. (P6-e) Phase 6 does not edit `tap/__main__.py`; if it
  does, part A rebases on it.
- If either phase ends this run unbuilt, parts C and D are dropped by a register row and listed
  in *Accepted limits*; nothing in A, B or E changes.

## Build order (LP3: vertical slice first)

1. **Part A core.** `tap/http.py` and the `--http` option with unit tests against
   `tests/fake_servers/http_upstream.py` (a stdlib HTTP server the tap starts as its child,
   listening on the Unix socket that `PORT` names, scripted per path: JSON, SSE with and without priming, `202`, a slow stream, a stream that
   waits for a second POST, a stream held open until DELETE, non-UTF-8 data). Test first.
2. **Slice.** `client/http_wire.py` and `client/http_tour.py` with the four slice steps, unit
   tests against an in-process fake; `record.sh --http --client http-tour`; G5 gains
   `tests.test_e2e_http`, whose first test records the slice against the real server and checks
   the trace (exit 0, the slice's records, `tap.check` passes). A learner can now record and
   read one HTTP session.
3. **D6.** The viewer summary, with its tests.
4. **Widen D9** to the full HTTP tour; the e2e checks M3–M11 on a fresh trace.
5. **Part E.** Walkthrough, lesson 07, README; the `--explain` check in the e2e.
6. **Part B2** after phase 6 merges: `--url` for `tour`, `server-tour`, `manual`, with e2e.
7. **Parts D, then C**, each only if its phases are built; otherwise dropped (register row).
8. **Close.** Final atlas coverage measured (`tools/atlas.py`, counts in the Result);
   `scripts/gate.sh` lists phase 07 in G12; Result, CHANGELOG, tag `lesson-07`. No review round
   (LP4): phase 2 claim code is reused, not changed.

Builder: Sonnet, medium. Estimate: steps 1–2 about two hours, 3–5 about two hours, 6 half an
hour, 7 about an hour per part.

## Stop condition

Every C row of parts A, B1 and E passes, with the gate green locally and in CI; the HTTP tour's
fresh trace passes `tap.check --revision 2025-11-25` and `--explain`. Rows of parts B2, C and
D pass, or the part is dropped by a register row and listed in *Accepted limits*; until C and D
pass, the roadmap's "both clients run both eras over HTTP" is reported as not met.

## Scope cuts

- Fixtures over HTTP: a driver that POSTs would be a client (phase 1 D9); learners record
  clients instead.
- The walkthrough explains the HTTP tour only, not the phase 2 and 3 tours over HTTP: their
  messages are those tours' walkthroughs' subject; D10's check is method coverage and
  `tap.check`.
- Resumability, re-initialisation after `404`, keep-alive reuse, the `Mcp-Name` Base64 form,
  Origin experiments: each is a rule the owner can study later without changing D1–D9.
- `matrix` over HTTP: the capability lesson is transport-independent.
- No `exercises` line for lesson 07, so no change to the atlas claims test.
