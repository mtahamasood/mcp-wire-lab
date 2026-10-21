# Walkthrough 02: the raw client's tour, frame by frame

This explains every record in a trace of the raw client's scripted tour (`python3 -m client tour`)
recorded against the pinned everything server. Record your own, check it against the schema, then
read it with its notes:

```console
scripts/record.sh --client tour
python3 -m tap.check runs/<your-run>/trace.jsonl --revision 2025-11-25
python3 -m tap.show runs/<your-run>/trace.jsonl --explain docs/walkthrough/02-raw-client-tour.md
```

Each note is headed by an identity anchor, as in walkthrough 01:
`<direction>.<method or response>.<id or occurrence>`. Requests and responses are keyed by `id`
(the client allocates ids from 0, in send order, so the tour's requests are ids 0 to 16);
notifications by how many of that method came before in that direction. `--explain` exits non-zero
if a frame has no note here, or a note here names a frame the run never produced (G5 checks this
on every gate run).

Citations point into the two pinned submodules: `spec` is the 2025-11-25 revision of the
specification, `servers` is the everything reference server. The server's protocol plumbing (request
routing, building replies, cancellation) lives in the TypeScript SDK, which the server's lockfile
fixes at 2.3.1 but which is not a submodule, so its lines cannot be cited and checked here. Those
notes cite the spec for the rule and the server for what it configures, and say so.

The notifications the server sends while a request is in flight (`notifications/message` after a
subscribe, `notifications/progress` during a long call) are written to the same stream as the
replies, and their position among the other frames can differ from run to run; their anchors count
occurrences, so they do not depend on it. The examples are hand-written and trimmed, not
machine-checked: where one differs from your trace, trust the trace.

## Source tour: one `tools/call echo`, from the pipe to the handler and back

The tour's request with id 3 asks the server to run its `echo` tool. Follow it through the pinned
server, one hop at a time.

1. **The process starts.** The command the tap runs ends in `node .../dist/index.js stdio`. The
   launcher picks the transport from that argument
   (`servers:src/everything/index.ts:25` "./transports/stdio.js") and starts it. It writes its boot
   line to stderr (`servers:src/everything/transports/stdio.ts:92` "Starting default (STDIO) server...")
   and calls `main` (`servers:src/everything/transports/stdio.ts:93` "await main(stdin, stdout)").
2. **The pipe becomes the protocol.** `main` hands the process's stdin and stdout to the SDK's
   stdio transport (`servers:src/everything/transports/stdio.ts:60` "new StdioServerTransport(stdin, stdout)"),
   served by `serveStdio` (`servers:src/everything/transports/stdio.ts:49` "serveStdio(").
   That transport is what splits stdin into lines and parses each one as JSON-RPC, and what writes
   replies back as lines (the transport rule is `spec:docs/specification/2025-11-25/basic/transports.mdx:28`
   "contain embedded newlines"). Its code is in the SDK, not cited here.
3. **The era is chosen by the first message.** Because the first line is `initialize`, `serveStdio`
   builds the 2025-era server from the factory
   (`servers:src/everything/transports/stdio.ts:51` "createServer({ era })").
4. **The factory registers the tool.** `createServer` makes the `McpServer`
   (`servers:src/everything/server/index.ts:126` "new McpServer("), then registers the tools every
   client gets (`servers:src/everything/server/index.ts:180` "registerTools(server, context)"), which
   includes echo (`servers:src/everything/tools/index.ts:47` "registerEchoTool(server)").
5. **Routing.** When the line `{"method":"tools/call", ...}` arrives, the SDK looks the tool name up
   among the registered tools and calls its handler with the `arguments`. This step is SDK code, not cited.
6. **The handler runs.** The echo handler validates its input and builds the reply
   (`servers:src/everything/tools/echo.ts:33` "server.registerTool(name, config",
   `servers:src/everything/tools/echo.ts:34` "EchoSchema.parse(args)",
   `servers:src/everything/tools/echo.ts:36` "Echo: ${validatedArgs.message}").
7. **The reply goes back.** The SDK wraps the returned object as the `result` of a response with the
   request's own `id` and writes it to stdout as one line. The raw client reads that line in
   `Wire.handle_line` (`client/wire.py`), classifies it by shape as a response, finds the pending
   request with that id and type in `Wire._complete`, and wakes the caller waiting in
   `Pending.wait`: the tour then checks the text is `Echo: hello`.

Where to look next in your trace: the frame pair `c2s.tools/call.3` and `s2c.response.3` below.

## The frames

#### `tap.spawn.0`

The tap starts the server as a child process. Over stdio the client launches the server
(`spec:docs/specification/2025-11-25/basic/transports.mdx:24` "launches the MCP server as a subprocess"),
and here the raw client launches the tap, which launches the server, so the tap can watch both
directions. The `spawn` record lists the command and the minimal environment `scripts/record.sh`
gives the server, so none of your own environment reaches the trace. The launcher script's own
entry point is `servers:src/everything/index.ts:25` "./transports/stdio.js".

#### `c2s.initialize.0`

The first thing any client says. The spec requires the client to open the connection with an
`initialize` request (`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:47` "initiate this phase")
carrying the protocol version it speaks, its capabilities and who it is
(`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:57` "\"method\": \"initialize\""). The raw
client offers `2025-11-25`, empty capabilities, and the name `wire-lab-raw`. Its `id` is `0`: the
first id the client allocates. The line is one compact JSON object with no embedded newline.

```json
{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"wire-lab-raw","version":"0.2.0"}}}
```

#### `stderr.0`

Not protocol at all. The server prints its boot line on stderr (source:
`servers:src/everything/transports/stdio.ts:92` "Starting default (STDIO) server..."), which the
spec allows for logging (`spec:docs/specification/2025-11-25/basic/transports.mdx:29` "standard error")
and tells clients not to read as an error (`spec:docs/specification/2025-11-25/basic/transports.mdx:32`
"SHOULD NOT"). The raw client does not parse it: the child's stderr is inherited, so it goes
straight through the client and the tap to your terminal or `stderr.txt`.

#### `s2c.response.0`

The answer to `initialize`, matched by `id`. The spec requires the server to answer with its
capabilities and information (`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:98` "MUST** respond with its own capabilities")
and, on version negotiation, to echo a version it supports (`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:170`
"MUST** respond with the same"). The client's `Session.initialize` then checks the reply's
`protocolVersion` is one the client speaks, and would stop here with a clear error if not
(`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:174` "does not support the version"). The server
declares its identity at `servers:src/everything/server/index.ts:128` "name: \"mcp-servers/everything\""
and its capabilities from `servers:src/everything/server/index.ts:133` "capabilities: {". The reply
itself is assembled by the SDK.

#### `c2s.notifications/initialized.0`

The client's second duty: after a successful `initialize`, it MUST say it is ready
(`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:147` "MUST** send an `initialized` notification").
A notification has a `method` and no `id`
(`spec:docs/specification/2025-11-25/basic/index.mdx:108` "Notifications **MUST NOT** include an ID"),
so the server sends nothing back. This is also the gate in the client: `Session` sends no other
request until this line has been written, which is stricter than the spec's "SHOULD NOT"
(`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:157` "SHOULD NOT** send requests other than").
The server hooks this notification to register capability-dependent tools
(`servers:src/everything/server/index.ts:194` "server.server.oninitialized"); with empty client
capabilities it registers none, which is why the tour sees no `notifications/tools/list_changed`.

```json
{"jsonrpc":"2.0","method":"notifications/initialized"}
```

#### `c2s.ping.1`

The cheapest request: `ping` has no parameters
(`spec:docs/specification/2025-11-25/basic/utilities/ping.mdx:23` "\"method\": \"ping\""), and the receiver
must answer promptly with an empty result.

#### `s2c.response.1`

The empty result, `{}`, for id 1
(`spec:docs/specification/2025-11-25/basic/utilities/ping.mdx:29` "MUST** respond promptly with an empty response").
Answered by the SDK; the server code has no ping handler to cite.

#### `c2s.tools/list.2`

The client asks what tools exist (`spec:docs/specification/2025-11-25/server/tools.mdx:66` "\"method\": \"tools/list\"").
The server declared the `tools` capability, so the request is allowed.

#### `s2c.response.2`

The tool list: 16 tools in the 2025 era for a client with empty capabilities, each with a name, a
description and a JSON Schema for its input. The tools are registered from
`servers:src/everything/tools/index.ts:46` "export const registerTools". This is the largest frame
of the trace. The raw client only checks that `echo`, `get-sum` and `trigger-long-running-operation`
are in it.

#### `c2s.tools/call.3`

Run a tool (`spec:docs/specification/2025-11-25/server/tools.mdx:122` "\"method\": \"tools/call\""): the
name `echo` and its arguments. This is the request the source tour above follows.

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"echo","arguments":{"message":"hello"}}}
```

#### `s2c.response.3`

The echo tool's result: a `content` list with one text block, `Echo: hello`
(`servers:src/everything/tools/echo.ts:36` "Echo: ${validatedArgs.message}"). Same `id` as the request,
a `result` and no `error` (`spec:docs/specification/2025-11-25/basic/index.mdx:69` "MUST** include the same ID").

#### `c2s.tools/call.4`

The second tool call: `get-sum` with two numbers, `a` and `b`.

#### `s2c.response.4`

`The sum of 2 and 3 is 5.`, built at `servers:src/everything/tools/get-sum.ts:45` "The sum of ${validatedArgs.a}".

#### `c2s.resources/list.5`

The client asks for the resources the server exposes
(`spec:docs/specification/2025-11-25/server/resources.mdx:96` "\"method\": \"resources/list\"").

#### `s2c.response.5`

Seven static documents, each with a `demo://` URI. They are registered one per file in the server's
docs folder (`servers:src/everything/resources/files.ts:47` "demo://resource/static/document/").

#### `c2s.resources/templates/list.6`

Templates are resources described by a URI pattern instead of a fixed URI
(`spec:docs/specification/2025-11-25/server/resources.mdx:178` "\"method\": \"resources/templates/list\"").

#### `s2c.response.6`

Two templates, one for text and one for binary dynamic resources, registered at
`servers:src/everything/resources/templates.ts:169` "registerResourceTemplates". Their URI templates contain
`{resourceId}`.

#### `c2s.resources/read.7`

Read one document by its URI (`spec:docs/specification/2025-11-25/server/resources.mdx:141` "\"method\": \"resources/read\"").
The tour reads the static `architecture.md`.

#### `s2c.response.7`

The document's text, as a `contents` list with the URI, a MIME type and the text. The server reads
the file when asked (`servers:src/everything/resources/files.ts:58` "async (uri) => {").

#### `c2s.resources/subscribe.8`

Ask to be told when that resource changes
(`spec:docs/specification/2025-11-25/server/resources.mdx:232` "\"method\": \"resources/subscribe\"").
The server advertised `subscribe: true` (`servers:src/everything/server/index.ts:142` "subscribe: true").

#### `s2c.notifications/message.0`

Not an answer to anything the client asked: a log notification. The server logs each subscribe
request at info level (`servers:src/everything/resources/subscriptions.ts:30` "server.sendLoggingMessage("),
and a log line is a notification with a `level` and `data`
(`spec:docs/specification/2025-11-25/server/utilities/logging.mdx:71` "\"method\": \"notifications/message\"").
The client queues it and the tour prints it. It never sets a log level before this, and the server
sends it anyway.

#### `s2c.response.8`

The subscription is recorded and acknowledged with an empty result
(`servers:src/everything/resources/subscriptions.ts:37` "subscribed.add(uri)").

#### `c2s.resources/unsubscribe.9`

The matching cancel. The spec's prose has no example for it, so the method is cited from the schema
(`spec:schema/2025-11-25/schema.ts:769` "method: \"resources/unsubscribe\"").

#### `s2c.notifications/message.1`

The server logs the unsubscribe the same way
(`servers:src/everything/resources/subscriptions.ts:43` "server.sendLoggingMessage(").

#### `s2c.response.9`

Empty result: the URI is removed from the server's set
(`servers:src/everything/resources/subscriptions.ts:50` "subscribed.delete(uri)").

#### `c2s.prompts/list.10`

The client asks for prompt templates
(`spec:docs/specification/2025-11-25/server/prompts.mdx:59` "\"method\": \"prompts/list\"").

#### `s2c.response.10`

Four prompts, registered at `servers:src/everything/prompts/index.ts:12` "export const registerPrompts".
`args-prompt` lists its arguments (`city` required, `state` optional), which is what a client would
use to build a form.

#### `c2s.prompts/get.11`

Fetch one prompt by name (`spec:docs/specification/2025-11-25/server/prompts.mdx:110` "\"method\": \"prompts/get\"");
`simple-prompt` takes no arguments.

#### `s2c.response.11`

The fixed message the prompt returns
(`servers:src/everything/prompts/simple.ts:23` "This is a simple prompt without arguments.").

#### `c2s.prompts/get.12`

`args-prompt` with the argument `city` set to `Oslo`.

#### `s2c.response.12`

The server substitutes the argument into the prompt text
(`servers:src/everything/prompts/args.ts:34` "What's weather in ${location}?").

#### `c2s.completion/complete.13`

Ask the server to complete an argument value
(`spec:docs/specification/2025-11-25/server/utilities/completion.mdx:49` "\"method\": \"completion/complete\""),
naming the prompt and the argument typed so far: department `E`.

#### `s2c.response.13`

The candidates that start with `E`: `Engineering`
(`servers:src/everything/prompts/completions.ts:18` "[\"Engineering\", \"Sales\", \"Marketing\", \"Support\"]").
A server that supports completion must declare the `completions` capability
(`spec:docs/specification/2025-11-25/server/utilities/completion.mdx:26` "MUST** declare the `completions` capability"),
and this one's `initialize` reply does (the SDK adds it; that code is not cited).

#### `c2s.logging/setLevel.14`

Ask the server to send log messages at `debug` and above
(`spec:docs/specification/2025-11-25/server/utilities/logging.mdx:57` "\"method\": \"logging/setLevel\"").
The server declared `logging` (`servers:src/everything/server/index.ts:148` "logging: {}").

#### `s2c.response.14`

Empty result: the level is set. The handler is in the SDK.

#### `c2s.tools/call.15`

A tool call that takes about a second and reports progress. The client asks for progress by putting
a `progressToken` in the request's `_meta`
(`spec:docs/specification/2025-11-25/basic/utilities/progress.mdx:27` "\"progressToken\": \"abc123\"").
`trigger-long-running-operation` is told to take 1 second in 2 steps.

```json
{"jsonrpc":"2.0","id":15,"method":"tools/call","params":{"name":"trigger-long-running-operation","arguments":{"duration":1,"steps":2},"_meta":{"progressToken":"tour-done"}}}
```

#### `s2c.notifications/progress.0`

Progress 1 of 2, carrying the token back
(`spec:docs/specification/2025-11-25/basic/utilities/progress.mdx:43` "\"method\": \"notifications/progress\"").
The tool sends one after each step, but only because a token was given
(`servers:src/everything/tools/trigger-long-running-operation.ts:56` "if (progressToken !== undefined)").
It is a notification: no `id`, no reply, and it arrives while request 15 is still unanswered.

#### `s2c.notifications/progress.1`

Progress 2 of 2, half a second after the first
(`servers:src/everything/tools/trigger-long-running-operation.ts:57` "await server.server.notification(").

#### `s2c.response.15`

The call completes: `Long running operation completed. Duration: 1 seconds, Steps: 2.`
(`servers:src/everything/tools/trigger-long-running-operation.ts:75` "Long running operation completed.").
This is the slow frame of the trace: its latency is the tool's own 1 second.

#### `c2s.tools/call.16`

The same call with a different token, `tour-cancel`. The client will not wait for this one.

#### `s2c.notifications/progress.2`

Progress 1 of 2 for the second call. The client sees it and decides to cancel.

#### `c2s.notifications/cancelled.0`

The cancellation: a notification naming the id of the request to cancel and, optionally, a reason
(`spec:docs/specification/2025-11-25/basic/utilities/cancellation.mdx:22` "\"method\": \"notifications/cancelled\"").
Cancellation only refers to a request that is believed to be still in progress
(`spec:docs/specification/2025-11-25/basic/utilities/cancellation.mdx:32` "MUST** only reference requests that"),
and the sender should ignore any response that arrives afterwards
(`spec:docs/specification/2025-11-25/basic/utilities/cancellation.mdx:45` "ignore any response to the").
The client does exactly that: `Session.cancel` stops waiting for id 16 at once, and the wire would drop
and report a late reply. Note there is no `s2c.response.16` in the trace.

```json
{"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":16,"reason":"the tour cancels after the first progress"}}
```

#### `s2c.notifications/progress.3`

The server's tool does not notice. Its loop has no check for cancellation
(`servers:src/everything/tools/trigger-long-running-operation.ts:51` "for (let i = 1; i < steps + 1; i++)"),
so it finishes step 2 and sends the second progress notification after the cancel. Cancellation is
advisory: receivers SHOULD stop, and may not
(`spec:docs/specification/2025-11-25/basic/utilities/cancellation.mdx:37` "Receivers of cancellation notifications **SHOULD**").
The tour waits for this notification so its trace is the same on every run. The SDK then sends no
reply for the cancelled request (measured: the trace has none), so nothing late reaches the wire.

#### `tap.exit.0`

The client ended the session the way the stdio lifecycle says: it closed the server's stdin
(`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:233` "closing the input stream to the child process"),
the server noticed the end of its input and exited, and the tap recorded the child's exit status,
`0`. The client's escalation to `SIGTERM` and `SIGKILL`
(`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:234` "sending `SIGTERM` if the server does not exit")
was not needed.
