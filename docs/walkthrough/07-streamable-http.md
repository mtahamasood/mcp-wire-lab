# Walkthrough 07: Streamable HTTP, record by record

This explains every record in a trace of the raw client's HTTP tour (`python3 -m client.http_tour`)
recorded through the tap's HTTP mode against the pinned everything server started with
`streamableHttp`. The messages are the ones you know from lessons 01 to 03; what is new is
everything around them: one POST per message, an answer that is a JSON body or an event stream,
a session id, a second stream for what the server says unprompted, and status codes and headers
that carry protocol rules. Record your own, check it against the schema, then read it with its
notes:

```console
scripts/record.sh --http --client http-tour
python3 -m tap.check runs/<your-run>/trace.jsonl --revision 2025-11-25
python3 -m tap.show runs/<your-run>/trace.jsonl --explain docs/walkthrough/07-streamable-http.md
```

The note format and the anchors are those of [walkthrough 02](02-raw-client-tour.md): a JSON-RPC
message is `<direction>.<method or response>.<id or occurrence>`, a tap record is
`tap.<event>.<occurrence>`, a server log line is `stderr.<occurrence>`. What HTTP adds goes in
`tap` records and in an `http` object on a frame (`tap.show` prints the exchange number as
`#<n>` after a frame, and the headers that matter after a `tap` record):

- `http-request` and `http-response`: the head of one HTTP exchange (exchanges are numbered from 0
  in the order the request heads reach the tap), with the headers that carry MCP rules
  (`accept`, `content-type`, `last-event-id` and every `mcp-*`).
- `sse-event`: an event-stream event with **no data**, which is how the server primes a stream.
  An event *with* data is not a `tap` record: it is an ordinary `s2c` frame, one message per event.
- `http-end`: the end of an event stream, and who ended it (`server`, `client`).

A frame's `raw` is the body or the event's data, not the socket's bytes: chunk framing and the
`data: ` prefixes are not recorded (the tap's spec lists what it leaves out).

Three things to know before reading the notes.

- **The server is behind a Unix socket.** Given a port number, this server binds every network
  interface (`servers:src/everything/transports/streamableHttp.ts:383` "const PORT = process.env.PORT || 3001;"
  goes unchanged to `servers:src/everything/transports/listen.ts:24` "app.listen(port,"), against the
  spec's advice to bind localhost
  (`spec:docs/specification/2025-11-25/basic/transports.mdx:81` "bind only to localhost"). Recordings
  therefore give it a path instead: `PORT` is a socket in a private directory the tap makes, so no
  recording exposes the server on any network interface, and the client talks only to the tap on
  `127.0.0.1`. The socket's directory is new on every run, so the server's own log line
  (`stderr.1`) names a different path each time.
- **The order of some records can differ between runs.** The server's log lines and the
  re-list of `tools/list` race with other traffic, so the notes for those use ranges, and notes for
  an exchange say what the exchange *is*, not just its number: where a note and your trace
  disagree, trust the trace.
- **Citations into the SDK are checked.** The server's HTTP plumbing is in the TypeScript SDK
  (the `server` package under `vendor/servers/node_modules`); the notes cite its lines as
  `servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:<line>`.

## Source tour: one POST, from the wire through the server to the SDK and back

The tour's `tools/call echo` is the POST in exchange 5. Follow it one hop at a time.

1. **The launcher binds the socket.** `streamableHttp` selects the HTTP transport; the server reads
   `PORT` and listens (`servers:src/everything/transports/streamableHttp.ts:383` "const PORT = process.env.PORT || 3001;"),
   then prints its listening line to stderr
   (`servers:src/everything/transports/listen.ts:27` "console.error(listeningMessage);").
2. **Express routes the POST.** One endpoint, `/mcp`, handles POST, GET and DELETE. The POST handler
   logs the line you see as a `stderr` record
   (`servers:src/everything/transports/streamableHttp.ts:196` "Received MCP POST request").
3. **Which era?** A POST with a session id is a 2025-era session's, and so is every GET and DELETE
   (`servers:src/everything/transports/streamableHttp.ts:18` "A request with an `Mcp-Session-Id`, a GET and a DELETE are 2025-era by"). A POST
   *without* one is classified from its body by the SDK
   (`servers:src/everything/transports/streamableHttp.ts:205` "isLegacyRequest(await toWebRequest(req, req.body))"): a body
   carrying the 2026-07-28 `_meta` envelope goes to the modern handler, anything else, including
   `initialize`, to the 2025 path.
4. **The transport owns the session.** A POST with a known session id is handed to that session's
   transport, which the `initialize` POST created
   (`servers:src/everything/transports/streamableHttp.ts:222` "sessionIdGenerator: () => randomUUID(),").
5. **The SDK validates, then answers.** Inside the transport's `handlePostRequest`
   (`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:704` "async handlePostRequest(req, options)")
   the `Accept` header must list both content types, else `406`
   (`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:707` "acceptHeader?.includes(\"application/json\")"); a body with no request in it
   (a notification, or the client's reply to a server request) is answered `202` with no body
   (`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:776` "status: 202");
   a body with a request opens an event stream
   (`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:807` "text/event-stream") and writes the priming event first
   (`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:523` "storeEvent(streamId, {})").
6. **The reply travels back on the same stream.** The response to `tools/call` is written as one event
   on the stream the request opened, and the stream ends; the tap records it as the `s2c` frame
   of exchange 5.

## The 2026-07-28 shape, and where this server departs from the spec

Everything above is the 2025 shape. The 2026-07-28 revision drops sessions and the GET stream and
adds request headers: every POST names the protocol version and mirrors the method (and, for a
tool call, the tool name) into headers so intermediaries need not parse the body
(`spec:docs/specification/2026-07-28/basic/transports/streamable-http.mdx:246` "mirrors selected JSON-RPC body fields"). The pinned server serves both from one
endpoint: a POST with a session id, every GET and every DELETE are the 2025 era, and a session-less
POST with the 2026 envelope is the modern one
(`servers:src/everything/transports/streamableHttp.ts:18` "A request with an `Mcp-Session-Id`, a GET and a DELETE are 2025-era by"). A modern reply is
plain `application/json`, or an event stream when the call sends progress first, and its events
carry no ids and no priming event. Where the server departs from the spec (measured, and recorded
as measured): given a port it binds every interface (above); and a GET on the modern path is
answered `400` by the 2025 route, where the 2026 spec asks for `405` on GET and DELETE
(`spec:docs/specification/2026-07-28/basic/transports/streamable-http.mdx:683` "HTTP GET or DELETE to the MCP endpoint"). This tour speaks only the 2025 shape.

## The SDK client over HTTP: where its traffic differs from the raw client's

`scripts/record.sh --http --client sdk-tour` records the phase 5 SDK client's tour (the raw
client's phase 2 tour, so a different message list from the HTTP tour above) with
`StreamableHTTPClientTransport` in place of stdio; `node clients/sdk/src/main.ts tour --url <url>`
runs it against any Streamable HTTP server. Measured on a fresh pair, one recording of each
(the SDK's trace passes `tap.check --revision 2025-11-25`), the HTTP layer differs in these ways.
The messages themselves are the SDK's, as in [walkthrough 05](05-sdk-client.md).

- **The GET stream opens after `initialized`, not before.** The raw tour declares `roots` and
  `sampling` and opens its GET stream between the `initialize` result and `notifications/initialized`
  (exchange 1). The SDK sends `initialized` (a `202`, exchange 1) and the transport then opens the
  GET (exchange 2) on seeing that notification
  (`sdk:client/dist/index.mjs:5797` "if (isInitializedNotification(message)) this._startOrAuthSse({ resumptionToken: void 0 })"). It does so even
  when the tour declares no capabilities, which the raw client never does.
- **Cancelling leaves the stream open.** The raw client closes the connection of the cancelled call
  (`http-end` `by client`) and also posts `notifications/cancelled`. The SDK posts
  `notifications/cancelled` (`202`) and keeps reading the call's stream: it has no `http-end` until
  the session is deleted, then ends `by server`, together with the GET stream, just before the
  DELETE's `200`. The late `notifications/progress` is read and dropped by the SDK.
- **DELETE only on `terminateSession()`.** Closing the SDK client sends nothing; the tour calls
  `terminateSession()` first
  (`sdk:client/dist/index.mjs:5836` "async terminateSession() {"), so the trace ends with the DELETE, as the raw tour's does.
  The DELETE carries `accept: */*` (the fetch default), where the raw client's carries no `accept`.
- **No reply POSTs.** The tour declares no capabilities, so the server asks nothing and the trace
  has no client reply (no `c2s` response with its own `202`), where the raw tour has two.

## The earlier tours and the 2026-07-28 era over HTTP

`python3 -m client <tour|server-tour|manual> --url <url>` (and `tour`/`manual` with `--era
2026-07-28`) run phase 2, 3 and 6 modes over the same `HttpWire`; `scripts/record.sh --http --client
<mode>` records them. Measured on fresh recordings:

- **The 2025 tours.** `tour` sends the same 19 messages as over stdio and ends with the DELETE.
  One step differs: after the cancelled call the stdio tour waits for the server's second progress
  notification, which the server still sends; over HTTP cancelling closes the connection that
  carried the stream, so that progress can never arrive and the tour does not wait for it.
  `server-tour` declares every capability, so it opens the GET stream before `initialized` and
  hears the server's list-change burst and `roots/list` there.
- **The 2026-07-28 tour.** 30 POSTs and nothing else: no `initialize`, no session id, no GET, no
  DELETE. Every POST carries `MCP-Protocol-Version: 2026-07-28` and `Mcp-Method`, and `Mcp-Name`
  for `tools/call`, `resources/read` and `prompts/get`
  (`spec:docs/specification/2026-07-28/basic/transports/streamable-http.mdx:252` "Every POST request to the MCP endpoint **MUST** include an"). 25 answers are `application/json`; 4 are
  event streams (the calls that send progress or logs first, and `subscriptions/listen`); one is a
  `400` whose body is the JSON-RPC error `-32021` for the call that declared no capability. Two
  streams end `by client`: the cancelled call and the subscription closed at the end. Neither is
  followed by a `notifications/cancelled`, because on Streamable HTTP the closed stream is the
  cancellation
  (`spec:docs/specification/2026-07-28/basic/transports/streamable-http.mdx:235` "Closing the SSE response stream **MUST** be treated by the server as").
- **The SDK client's 2026 tour over HTTP** (`record.sh --http --client sdk-tour-2026`) makes 31
  POSTs, the raw client's 30 with the same headers plus one, which is a departure from the spec: when it closes its
  subscription it also POSTs `notifications/cancelled` (a `202`, and the only POST with no
  `Mcp-Method`), although the 2026 transport sends no notifications
  (`sdk:client/dist/index.mjs:4023` `method: "notifications/cancelled",`).
  Its probe is the first POST: `server/discover` with the id `server-discover-probe-1`.

### Why the SDK's server tour is not recorded over HTTP

`node clients/sdk/src/main.ts server-tour --url <url>` exits 1: step 3 reports that `tools/list`
"lacks" `get-roots-list` and four other gated tools. Measured through the tap: the SDK client sends
`notifications/initialized` and opens its GET only after that POST is answered `202`
(`sdk:client/dist/index.mjs:5797` "if (isInitializedNotification(message)) this._startOrAuthSse({ resumptionToken: void 0 })"). The server sends its five `tools/list_changed` notifications as it
handles `initialized`, before any GET exists; with no standalone stream it returns without writing
(`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:947` "if (standaloneSse === void 0) return;"). The trace has no `list_changed` frame at all; the roots sync, which the server
delays by 350 ms, arrives after the GET and is answered. The raw client opens the GET before
`initialized` and its trace shows the five notifications right after the `202`. The cause is the
SDK transport's order and the server's drop rule, not the tap or the raw client.

## Notes

#### `tap.spawn.0`

The tap's first record: it starts the server command as a child. Its `argv` is
`node <server> streamableHttp`; the server's environment is the recording allowlist plus `PORT`,
which the tap points at a private socket (see the top of this page). The server's stdin is
`/dev/null`: in HTTP mode stdio carries logs, not protocol.

#### `stderr.0-1`

The server's two start-up lines: "Starting Streamable HTTP server..."
(`servers:src/everything/transports/streamableHttp.ts:379` "Starting Streamable HTTP server...") goes to *stdout*, and the listening line, which names the socket path
(`servers:src/everything/transports/listen.ts:27` "console.error(listeningMessage);"), goes to *stderr*. The tap records both as `stderr` frames; the one from stdout
carries `"stream": "stdout"` in the trace. They are two pipes, so their order can differ.

#### `tap.listen.0`

The tap saw the socket accept a connection, bound `127.0.0.1:<port>` and wrote this record. From here on every HTTP exchange
goes through the tap. Its `upstream` is `unix:<temp dir>/server.sock`: a path that is new on every run.

#### `tap.http-request.0`

Exchange 0: the client's first POST. The recorded headers are the two that every MCP POST needs.
`content-type: application/json`, and an `accept` that lists *both* `application/json` and
`text/event-stream`; with either missing the server answers `406`
(`spec:docs/specification/2025-11-25/basic/transports.mdx:91` "MUST** use HTTP POST", `spec:docs/specification/2025-11-25/basic/transports.mdx:93` "as supported content types"). There is
no `mcp-session-id` and no `mcp-protocol-version`: the session does not exist yet.

#### `c2s.initialize.0`

The same `initialize` as lesson 01, now the body of a POST: the frame's `raw` is the body byte for byte, with no newline
added (`spec:docs/specification/2025-11-25/basic/transports.mdx:94` "body of the POST request **MUST** be"). The tap wrote this frame *before* sending the request upstream.

```json
{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{"roots":{"listChanged":true},"sampling":{}},"clientInfo":{"name":"wire-lab-raw","version":"0.2.0"}}}
```

#### `stderr.2-17`

The server's request log, one line per event, between the protocol records: "Received MCP POST request"
for each POST (`servers:src/everything/transports/streamableHttp.ts:196` "Received MCP POST request"), "Session initialized with ID: ..."
when the session is made (`servers:src/everything/transports/streamableHttp.ts:227` "Session initialized with ID"), "Received MCP GET request" and "Establishing new SSE stream for
session ..." for the GET stream (`servers:src/everything/transports/streamableHttp.ts:299` "Establishing new SSE stream"), "Received session termination request" for the
DELETE (`servers:src/everything/transports/streamableHttp.ts:326` "Received session termination request"), "Transport closed for session ..." when the
session is dropped (`servers:src/everything/transports/streamableHttp.ts:237` "Transport closed for session"), and "Shutting down server..." /
"Server shutdown complete" when the tap's SIGINT reaches it (`servers:src/everything/transports/streamableHttp.ts:350` "Shutting down server..."). They
are stdout lines, written by a different process on a different pipe, so where each lands among the other records can
differ from run to run; this note covers them all.

#### `tap.http-response.0`

The response head to exchange 0: `200`, `content-type: text/event-stream`, and **`mcp-session-id`**.
The session id is how separate POSTs become one session: the server makes it when it handles `initialize`
(`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:752` "this.sessionIdGenerator?.()"), and the spec lets it assign one in this very response
(`spec:docs/specification/2025-11-25/basic/transports.mdx:199` "MCP-Session-Id"). The server could have answered with one JSON object instead: the spec allows
either for a request and requires clients to handle both
(`spec:docs/specification/2025-11-25/basic/transports.mdx:101` "MUST** either"). This server always opens a stream
(`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:807` "text/event-stream").

#### `tap.sse-event.0`

The **priming event**: an event with an id and an empty `data` field, sent first so a client that loses the
connection has an id to resume from (`spec:docs/specification/2025-11-25/basic/transports.mdx:106` "SHOULD** immediately send an SSE event"). It carries no
message, so it is a `tap` record, not a frame. The server writes it only when the negotiated version is 2025-11-25 or later
(`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:523` "storeEvent(streamId, {})"). The id changes on every run.

#### `s2c.response.0`

The reply to `initialize`: one event's data, one frame (`#0` after it in `tap.show`). The result names the version the server
chose and its capabilities, as in lesson 01. This is the frame the raw client waits for before it sends anything else.

#### `tap.http-end.0`

The event stream ended, `by server`: after the response the server ends the stream
(`spec:docs/specification/2025-11-25/basic/transports.mdx:124` "SHOULD** terminate the"). `comments=0`: no keepalive line was forwarded in this short stream.

#### `tap.http-request.1`

Exchange 1: a **GET**, with `accept: text/event-stream` and, from now on, the session headers
`mcp-session-id` and `mcp-protocol-version: 2025-11-25`
(`spec:docs/specification/2025-11-25/basic/transports.mdx:265` "MCP-Protocol-Version:"). A client that wants to hear what the server says unprompted
must open this stream itself (`spec:docs/specification/2025-11-25/basic/transports.mdx:138` "MUST** include an `Accept` header"). The raw client opens it **before**
`notifications/initialized`: the server sends its `roots/list` sync and list-change notifications right after `initialized`, and with
no stream open it drops them
(`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:947` "if (standaloneSse === void 0) return;").

#### `tap.http-response.1`

`200 text/event-stream` for the GET: the server offers the stream
(`spec:docs/specification/2025-11-25/basic/transports.mdx:140` "either return `Content-Type: text/event-stream`"). The head arrives and then nothing: this exchange stays open until the session ends.
A second GET in the same session would be answered `409`
(`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:546` "Only one SSE stream is allowed per session"). There is no priming event on this stream.

#### `tap.http-request.2`

Exchange 2: the POST that carries `notifications/initialized`, with the session headers.

#### `c2s.notifications/initialized.0`

The last message of the opening exchange (`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:147` "MUST** send an `initialized` notification"). A notification has no id, so
there will be no response.

#### `tap.http-response.2`

**`202`**, no body, no stream: the server accepted a message that needs no answer
(`spec:docs/specification/2025-11-25/basic/transports.mdx:96` "return HTTP status code 202"; `servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:776` "status: 202"). The same happens for every notification and every
client reply to a server request. (The content type this server puts on an empty `202` proves nothing.)

#### `s2c.notifications/tools/list_changed.0-1`

The server registers the tools the client's capabilities allow once it is initialized, and announces each change. These arrive on the
**GET stream** (exchange 1), not on the POST that caused them: nothing asked for them, so no POST stream is theirs
(`spec:docs/specification/2025-11-25/basic/transports.mdx:145` "SHOULD** be unrelated to any concurrently-running JSON-RPC"). How many arrive can differ (the lesson's check asks you to count).

#### `tap.http-request.3-4`

Two POSTs whose order depends on timing: the client's re-list of `tools/list` after the list-change notifications (about 50 ms after
the first), and the client's reply to the server's `roots/list` (the server asks about 350 ms after `initialized`). They are different exchanges
with different answers; read the frames next to them to tell which is which.

#### `c2s.tools/list.1`

The re-list: the raw client reacts to a list-change notification by asking for the list again (phase 3's handlers). Its id is
`1`, the client's second request. It is an ordinary POST, answered on its own event stream.

#### `tap.http-response.3-4`

The two heads for the two POSTs above: `200 text/event-stream` for the re-list, `202` for the roots reply.

#### `tap.sse-event.1`

The priming event of the `tools/list` stream: every response stream starts with one.

#### `s2c.response.1`

The server's list of tools for this client: longer than lesson 02's, because the client declared `roots` and `sampling`.

#### `tap.http-end.1`

The `tools/list` stream ended, `by server`, right after its response.

#### `s2c.roots/list.0`

A **server request** (id `0`, the server's own counter), and it is a frame of the *GET* exchange: the server asks the client for its
roots about 350 ms after `initialized`, and nothing the client sent is waiting for it, so it uses the standalone stream
(`spec:docs/specification/2025-11-25/client/roots.mdx:55` "method": "roots/list"). The client cannot answer on this stream: a client message always goes by POST.

#### `c2s.response.0`

The client's answer to the server's `roots/list`, under the server's id `0`: a POST like any other message
(`spec:docs/specification/2025-11-25/basic/transports.mdx:94` "body of the POST request **MUST** be"), answered `202`.

#### `s2c.notifications/message.0`

A log line the server sends after it received the roots ("Roots updated: 1 root(s) received from client"), also on the GET stream.

#### `tap.http-request.5`

Exchange 5: the POST of `tools/call echo`, the source tour's subject.

#### `c2s.tools/call.2`

The call, id `2`: `{"name":"echo","arguments":{"message":"hello over http"}}`.

#### `tap.http-response.5`

`200 text/event-stream`: a request is answered on a stream of its own, the one this POST opened.

#### `tap.sse-event.2`

Priming event of the echo stream.

#### `s2c.response.2`

`"Echo: hello over http"`, the tool's result, as the data of one event on the stream the POST opened. The `#5` after it ties it to its request.

#### `tap.http-end.2`

The stream ended by the server after its response.

#### `tap.http-request.6`

Exchange 6: the POST of `tools/call trigger-sampling-request`.

#### `c2s.tools/call.3`

The call, id `3`. The tool does not answer at once: it asks the client's model a question first.

#### `tap.http-response.6`

`200 text/event-stream`, and this stream will carry more than one message.

#### `tap.sse-event.3`

Priming event of the sampling call's stream.

#### `s2c.sampling/createMessage.1`

The server's request (id `1`) is a frame of **this call's own stream**, not of the GET stream: it belongs to the request that caused it, so it travels on that
request's stream (`spec:docs/specification/2025-11-25/basic/transports.mdx:119` "MAY** send JSON-RPC _requests_ and _notifications_ before sending the"). The stream stays open: the call's response comes later, on the same stream.

#### `tap.http-request.7`

Exchange 7: the client's answer to the sampling request, a **new POST**, sent while the first POST's stream is still open. This is why the tap forwards every piece as soon as it arrives:
if it held the stream until its end, the answer could never be sent and the call would never finish.

#### `c2s.response.1`

The client's answer to the server's request `1`: a canned model reply. A reply is a POST.

#### `tap.http-response.7`

`202`, no stream: the server accepted the reply, and the result of the call arrives on the original stream.

#### `s2c.response.3`

The result of `tools/call` id `3`, now that the sampling answer is in: the last event of the call's stream. It carries the client's canned text.

#### `tap.http-end.3`

The call's stream ended, `by server`.

#### `tap.http-request.8`

Exchange 8: the POST of the long-running tool, with a `progressToken` in `params._meta`.

#### `c2s.tools/call.4`

`trigger-long-running-operation`, id `4`, with `_meta.progressToken`. The tour cancels it after the first progress notification.

#### `tap.http-response.8`

`200 text/event-stream`.

#### `tap.sse-event.4`

Priming event of the long call's stream.

#### `s2c.notifications/progress.0`

The first progress notification (`"progress":1,"total":4`), related to the request, so on its stream
(`spec:docs/specification/2025-11-25/basic/utilities/progress.mdx:43` "method": "notifications/progress"). It is the last frame of this exchange: the response never comes.

#### `tap.http-end.4`

This stream ended `by client`: to cancel a request over HTTP the client also **closes the connection** that carries its stream (the spec lets
it: `spec:docs/specification/2025-11-25/basic/transports.mdx:154` "client **MAY** close the SSE stream"). Closing is not cancelling by itself
(`spec:docs/specification/2025-11-25/basic/transports.mdx:128` "Disconnection **SHOULD NOT** be interpreted"), which is why the next POST exists; but without it the server's stream for the
call would never end, because the server sends only keepalives
(`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:407` "keepalive") and never a response to a cancelled request. No response frame follows in this trace.

#### `tap.http-request.9`

Exchange 9: the POST that carries `notifications/cancelled`.

#### `c2s.notifications/cancelled.0`

`{"requestId":4,"reason":"..."}`: the 2025 way to cancel is this notification
(`spec:docs/specification/2025-11-25/basic/utilities/cancellation.mdx:22` "method": "notifications/cancelled"), sent after the stream was closed.

#### `tap.http-response.9`

`202`, as for every notification.

#### `tap.http-request.10`

Exchange 10: **DELETE** with the session headers: the client ends the session
(`spec:docs/specification/2025-11-25/basic/transports.mdx:217` "send an HTTP DELETE to the MCP endpoint"). It has no body, so it adds no JSON-RPC frame.

#### `tap.http-end.5`

The **GET stream** (exchange 1) ends, `by server`: the server closes the session, which closes every stream of it, and this happens before the DELETE's own response
is read (`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:859` "async handleDeleteRequest(req)"). A later request with this session id would get `404`.

#### `tap.http-response.10`

`200`, empty: the session is gone.

#### `tap.exit.0`

The last record: the tap sent SIGINT to the server, which shut down and exited `0`
(`servers:src/everything/transports/streamableHttp.ts:391` "process.on(\"SIGINT\", shutdown);"). The tap removed the socket's private directory before it exited.
