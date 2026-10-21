# Walkthrough 03: the server speaks first, frame by frame

This explains every record in a trace of the raw client's server tour
(`python3 -m client server-tour`) recorded against the pinned everything server. In phase 2 the
client only asked. Here it declares all four capabilities (`roots`, `sampling`, `elicitation`
with `form` and `url`) and the server uses them: it sends *requests* to the client, and
unsolicited *notifications*. Record your own, check it against the schema, then read it with its
notes:

```console
scripts/record.sh --client server-tour
python3 -m tap.check runs/<your-run>/trace.jsonl --revision 2025-11-25
python3 -m tap.show runs/<your-run>/trace.jsonl --explain docs/walkthrough/03-server-initiated.md
```

The note format, the anchors and the citation rules are those of
[walkthrough 02](02-raw-client-tour.md): `<direction>.<method or response>.<id or occurrence>`.
Three things are new here.

- **Server requests have ids too, and they overlap the client's.** The server numbers its own
  requests from 0, so `s2c.roots/list.0` (the server asks) and `c2s.tools/list.0` would be
  different messages even if both existed, and `c2s.response.0` (the client answers the
  server's id 0) is not `s2c.response.0` (the server answers the client's id 0). The direction
  in the anchor tells them apart; so does the shape of the message, never its id alone
  (`client/wire.py`, `classify`).
- **The order of server-initiated traffic can differ between runs.** The server sends its
  `roots/list` 350 ms after `initialized`, and its `tools/list_changed` notifications in a burst
  right after it. The tour waits for all of that to settle before it sends anything numbered, so
  the client's own request ids are the same on every run (they run 0 to 17); notes are keyed by
  identity, not by position, and `--explain` accepts the frames in any order.
- **Citations into the SDK are absent.** The server's request plumbing (including the "legacy
  shim" below) lives in the TypeScript SDK, which the server's lockfile fixes at 2.3.1 but which
  is not a submodule. Those notes cite the spec for the rule and the server for what it
  configures, and say so. The examples are hand-written and trimmed: where one differs from your
  trace, trust the trace.

## Source tour: one `get-roots-list`, from the tool to the client's answer and back

The tour's request with id 2 calls the server's `get-roots-list` tool. The server answers it by
asking the *client* a question. Follow it one hop at a time.

1. **The tool exists only for a client that declared roots.** After `initialized`, the server's
   hook registers the tools the client's capabilities allow
   (`servers:src/everything/server/index.ts:197` "registerConditionalTools(server, context)"), and
   `get-roots-list` is among them only if `roots` was declared
   (`servers:src/everything/tools/index.ts:96` "if (capabilities.roots !== undefined) registerGetRootsListTool(server)").
2. **The handler asks instead of answering.** Its first round does not return a result: it returns
   an `input_required` result that carries a `roots/list` request
   (`servers:src/everything/tools/get-roots-list.ts:54` "inputRequests: { roots: inputRequired.listRoots() }").
   This code is written once for both protocol eras. A 2026-07-28 client would receive that
   `input_required` result as the tool's reply and retry.
3. **The legacy shim turns it into a real request.** For a 2025-era client such as this one, the
   SDK's *legacy shim* does what the older protocol expects: it sends a real `roots/list`
   request to the client, waits for the client's answer, and re-enters the handler with it
   (the file says so at `servers:src/everything/tools/get-roots-list.ts:7` "SDK's legacy shim sends a real `roots/list` request"). The shim is SDK code, not cited.
   On the wire that is the frame `s2c.roots/list.1`, sent while the tool call (id 2) is still
   unanswered.
4. **The client answers on a worker thread.** The raw client's reader classifies the line as a
   request by its shape (`client/wire.py`, `classify`), hands it to `Handlers.handle_request`
   (`client/handlers.py`), which starts a worker thread and goes back to reading. The worker's
   `Handlers.answer` builds the reply under the request's own `id`
   (`spec:docs/specification/2025-11-25/basic/index.mdx:69` "MUST** include the same ID"), and the
   reader is never blocked: a client request could still complete while this one is pending.
5. **The handler finishes.** With the answer in hand the handler formats the list
   (`servers:src/everything/tools/get-roots-list.ts:91` "Current MCP Roots"), and the SDK sends
   the result of the original `tools/call`, id 2.

Where to look next in your trace: the frame group `c2s.tools/call.2`, `s2c.roots/list.1`,
`c2s.response.1`, `s2c.response.2` below.

## The capability matrix

`python3 -m client matrix -- node vendor/servers/src/everything/dist/index.js stdio` runs one short
session per capability set and prints (never commits) a table. What the pinned server did when
this was written:

| Client declares | Gated tools the server lists | Server-initiated methods seen |
| --- | --- | --- |
| nothing | none | none |
| `roots` | `get-roots-list` | `roots/list`, `notifications/message`, `notifications/tools/list_changed` |
| `sampling` | `trigger-sampling-request` | `notifications/tools/list_changed` |
| `elicitation` (form) | `trigger-elicitation-request`, `trigger-multi-step-elicitation` | `notifications/tools/list_changed` |
| `elicitation` (url) | `trigger-url-elicitation` | `notifications/tools/list_changed` |
| all four | all five | all of the above |

What each capability adds: the capability decides which tools the server registers
(`servers:src/everything/tools/index.ts:98` "registerTriggerElicitationRequestTool(server);",
`servers:src/everything/tools/index.ts:102` "registerTriggerUrlElicitationTool(server, context);",
`servers:src/everything/tools/index.ts:105` "registerTriggerSamplingRequestTool(server);"), and each
registration after `initialized` makes the server send one `notifications/tools/list_changed`
(that is why `none` sees nothing at all and every other row sees the notification). Only `roots`
also makes the server ask a question on its own: its roots sync after 350 ms
(`servers:src/everything/server/index.ts:202` "setTimeout(() => syncRoots(server), 350)"). The
spec's rule behind all of it is that a party only uses capabilities that were negotiated
(`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:220` "Only use capabilities that were successfully negotiated").

One difference to know about. When the *server* sends a request for a capability the client did
not declare, this client answers `-32601`, method not found, as the roots page says to
(`spec:docs/specification/2025-11-25/client/roots.mdx:144` "Method not found"). For an elicitation
mode the client did not declare the spec asks for `-32602` instead
(`spec:docs/specification/2025-11-25/client/elicitation.mdx:700` "-32602"); the lab's client uses
`-32601` for every undeclared capability and says so here (spec D1). The pinned server never sends
a request the client did not declare, so a recorded run never shows either.

## The frames

#### `tap.spawn.0`

The tap starts the server as a child process, exactly as in walkthrough 02.

#### `c2s.initialize.0`

The first thing any client says (`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:57` "\"method\": \"initialize\""),
but with a difference from phase 2: `capabilities` is no longer empty. The client declares
`roots` (with `listChanged`, because it will send that notification), `sampling`, and
`elicitation` with both `form` and `url`
(`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:195` "`elicitation`"). The server decides
from this object which tools to register.

```json
{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{"roots":{"listChanged":true},"sampling":{},"elicitation":{"form":{},"url":{}}},"clientInfo":{"name":"wire-lab-raw","version":"0.2.0"}}}
```

#### `stderr.0`

The server's boot line (`servers:src/everything/transports/stdio.ts:92` "Starting default (STDIO) server..."),
not protocol, as in walkthrough 02.

#### `s2c.response.0`

The server's answer to `initialize`, as in walkthrough 02. Its own capabilities do not depend on
the client's; the tools do, as the next frames show.

#### `c2s.notifications/initialized.0`

The client says it is ready (`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:147` "MUST** send an `initialized` notification").
This is the server's cue: its `oninitialized` hook registers the capability-dependent tools and
schedules the roots sync (`servers:src/everything/server/index.ts:194` "server.server.oninitialized").

#### `s2c.notifications/tools/list_changed.0-4`

Five notifications in a row, one per registration the capabilities allowed (`get-roots-list`, the
two form-elicitation tools, the URL tool, the sampling tool). A server that changes its tool list
sends `notifications/tools/list_changed` and the client is meant to ask again
(`spec:docs/specification/2025-11-25/server/tools.mdx:158` "\"method\": \"notifications/tools/list_changed\""). The
raw client's reaction is the next frame: it does not re-list five times. Its handler marks
the list as changed and waits 50 ms for more, so the burst becomes one `tools/list`
(`client/handlers.py`, `Handlers._react`). The notifications carry no `id` and get no reply.

#### `c2s.tools/list.1`

The one re-list the burst caused. It is a normal request with the next client id, 1: the client
reacted on its own, not because the tour asked.

#### `s2c.response.1`

The tool list, now 21 tools instead of the 16 an empty-capability client sees. The tour checks
that the five gated tools are in it. The registrations behind them are at
`servers:src/everything/tools/index.ts:96` "if (capabilities.roots !== undefined) registerGetRootsListTool(server)".

#### `s2c.roots/list.0`

The first request the server sends. 350 ms after `initialized` it asks the client for its roots
(`spec:docs/specification/2025-11-25/client/roots.mdx:55` "\"method\": \"roots/list\"";
the server side is `servers:src/everything/server/roots.ts:33` "server.server.listRoots()"). Its `id`
is 0, which is also the id of the client's own `initialize`: the two do not collide because one is a
request from the server and the other an answered request from the client. The client's reader
tells them apart by shape and hands this one to its handler table.

```json
{"jsonrpc":"2.0","id":0,"method":"roots/list"}
```

#### `c2s.response.0`

The client's answer, sent on a worker thread under the request's own id: one root,
`file:///wire-lab/project`, named `wire-lab` (a fixed, authored URI, never a path from the machine
that runs the client). A `file://` URI is what the spec asks for
(`spec:docs/specification/2025-11-25/client/roots.mdx:110` "`file://`").

```json
{"jsonrpc":"2.0","id":0,"result":{"roots":[{"uri":"file:///wire-lab/project","name":"wire-lab"}]}}
```

#### `s2c.notifications/message.0`

After the answer the server reports it as a log message: "Roots updated: 1 root(s) received from
client" at level `info` from the logger `everything-server`
(`servers:src/everything/server/roots.ts:38` "Roots updated:"). A log message is a notification
with a `level`, a `logger` and `data`
(`spec:docs/specification/2025-11-25/server/utilities/logging.mdx:71` "\"method\": \"notifications/message\""); the client
prints it with its level and logger and does nothing else.

#### `c2s.tools/call.2`

The first numbered request of the tour proper: the tour waited for everything above before
sending it, so this id is 2 on every run. It calls `get-roots-list`; the source tour above
follows it.

#### `s2c.roots/list.1`

The legacy shim's request (step 3 of the source tour), sent while `tools/call` 2 is unanswered.
The server's second request, so its id is 1 (the client's next request is id 3 and has nothing to do with it),
and the two counters stay independent.

#### `c2s.response.1`

The client's answer, the same single root as before, sent from a worker thread. While it ran, the
reader was free: nothing here waits for it.

#### `s2c.response.2`

The result of `get-roots-list`: "Current MCP Roots (1 total)" and the root's name and URI,
formatted at `servers:src/everything/tools/get-roots-list.ts:91` "Current MCP Roots".

#### `c2s.tools/call.3`

`trigger-sampling-request` with a `prompt`. Sampling is the server asking the *client's model* for
a completion; this client has no model (a non-goal of the lab), so it will answer with canned text.

#### `s2c.sampling/createMessage.2`

The server's request: the prompt as a user message, a system prompt and `maxTokens`
(`spec:docs/specification/2025-11-25/client/sampling.mdx:101` "\"method\": \"sampling/createMessage\"";
the tool builds it at `servers:src/everything/tools/trigger-sampling-request.ts:71` "inputRequired.createMessage("). It is
the shim again: the tool returned `input_required`, the SDK sent this as a real request.

#### `c2s.response.2`

The canned `CreateMessageResult`: role `assistant`, text `canned reply from wire-lab-raw`, model
`wire-lab-canned`, stop reason `endTurn`
(`spec:docs/specification/2025-11-25/client/sampling.mdx:140` "\"stopReason\": \"endTurn\""). The `id` is the server's 2, not
the client's.

#### `s2c.response.3`

The tool's result: the canned result, echoed back as JSON text
(`servers:src/everything/tools/trigger-sampling-request.ts:94` "LLM sampling result"). It answers the
client's request 3.

#### `c2s.tools/call.4`

`trigger-elicitation-request`: the server asks the user to fill in a form.

#### `s2c.elicitation/create.3`

A form-mode elicitation request, with a `requestedSchema` that has one field of each type
(`spec:docs/specification/2025-11-25/client/elicitation.mdx:245` "\"method\": \"elicitation/create\"";
the form is `servers:src/everything/tools/trigger-elicitation-request.ts:176` "form: inputRequired.elicit("). The
client has no user: it fills each property from its `default`, else the first option of an
`enum`, `oneOf` or `anyOf`, else a fixed value of its type.

#### `c2s.response.3`

`action: accept` with a value for every property, for example `firstLine` from its default and
`number` as `3`. The server's default for that field is 3.14, but the schema's `ElicitResult`
allows only strings, integers, booleans and lists of strings as values, so the client sends the
integer part (the check against the schema, `tap.check`, would reject `3.14`). The spec's `accept`
is at `spec:docs/specification/2025-11-25/client/elicitation.mdx:269` "\"action\": \"accept\",".

#### `s2c.response.4`

The tool's result: "User provided the requested information!" and a summary of the values
(`servers:src/everything/tools/trigger-elicitation-request.ts:196` "User provided the requested information").

#### `c2s.tools/call.5`

`trigger-multi-step-elicitation`: two questions, one after the other.

#### `s2c.elicitation/create.4`

Round one, "What is your name?": a form with one string property
(`servers:src/everything/tools/trigger-multi-step-elicitation.ts:64` "name: inputRequired.elicit(").

#### `c2s.response.4`

`accept` with `name` set to the fixed string value `wire-lab`.

#### `s2c.elicitation/create.5`

Round two, addressed to the name the client gave: "Thanks, wire-lab. Which color do you like
best?", with an `enum` of three colors
(`servers:src/everything/tools/trigger-multi-step-elicitation.ts:73` "color: inputRequired.elicit(").
The shim re-entered the handler with the first answer and the handler asked again.

#### `c2s.response.5`

`accept` with `color` set to the first value of the enum, `red`.

#### `s2c.response.5`

The tool's result, `wire-lab's favorite color is red.`
(`servers:src/everything/tools/trigger-multi-step-elicitation.ts:136` "favorite color is"). The
request ids are all different: server request 4 and 5 are answered by `c2s.response.4` and
`c2s.response.5`, and client request 5 by `s2c.response.5`.

#### `c2s.tools/call.6`

`trigger-url-elicitation` with a fixed example URL. URL mode asks the user to open a link, for
interactions a form must not carry (such as secrets).

#### `s2c.elicitation/create.6`

The server's request, `mode: url`, with the URL, a message and an `elicitationId`
(`spec:docs/specification/2025-11-25/client/elicitation.mdx:372` "\"mode\": \"url\"").
On a 2025-era connection this tool sends the request itself rather than through the shim
(`servers:src/everything/tools/trigger-url-elicitation.ts:219` "await ctx.mcpReq.send(").

#### `c2s.response.6`

The client declines: `{"action":"decline"}`. It never opens a browser; the lab's client answers
every URL-mode request this way, which the spec allows
(`spec:docs/specification/2025-11-25/client/elicitation.mdx:555` "**Decline** (`action: \"decline\"`)").

#### `s2c.response.6`

The tool reports "User declined to open the URL"
(`servers:src/everything/tools/trigger-url-elicitation.ts:241` "User declined to open the URL").

#### `c2s.logging/setLevel.7`

The client chooses the log level, `debug`, so the next tool's messages are not filtered
(`spec:docs/specification/2025-11-25/server/utilities/logging.mdx:57` "\"method\": \"logging/setLevel\"").

#### `s2c.response.7`

The empty result.

#### `c2s.tools/call.8`

`trigger-log-messages`: one log message at each level.

#### `s2c.notifications/message.1-8`

Eight notifications, `debug` to `emergency`, logger `everything`
(`servers:src/everything/tools/trigger-log-messages.ts:61` "ctx.mcpReq.log(level"). They arrive
before the tool's result, in order, and the client prints each with its level and logger.

#### `s2c.response.8`

The tool's result, which says one message was sent at each of 8 levels.

#### `c2s.tools/call.9`

`trigger-list-changed` with `list: tools`: the server announces a change of its tool list.

#### `s2c.notifications/tools/list_changed.5`

The sixth `tools/list_changed` of the run: this one comes from the tool
(`servers:src/everything/tools/trigger-list-changed.ts:52` "context.publish.toolsChanged()").

#### `s2c.response.9`

The tool's result: "Sent notifications/tools/list_changed".

#### `c2s.tools/list.10`

The client's reaction: one `tools/list`. Its id, 10, is reserved by the tour waiting for the
re-list before it sends the next request.

#### `s2c.response.10`

The tool list again.

#### `c2s.tools/call.11`

The same tool for `prompts`.

#### `s2c.notifications/prompts/list_changed.0`

`notifications/prompts/list_changed`
(`spec:docs/specification/2025-11-25/server/prompts.mdx:149` "\"method\": \"notifications/prompts/list_changed\"").

#### `s2c.response.11`

The tool's result.

#### `c2s.prompts/list.12`

The client re-requests the prompt list, not the tool list: each notification names its own list.

#### `s2c.response.12`

The prompt list.

#### `c2s.tools/call.13`

The same tool for `resources`.

#### `s2c.notifications/resources/list_changed.0`

`notifications/resources/list_changed`
(`spec:docs/specification/2025-11-25/server/resources.mdx:217` "\"method\": \"notifications/resources/list_changed\"").

#### `s2c.response.13`

The tool's result.

#### `c2s.resources/list.14`

The client re-requests the resource list.

#### `s2c.response.14`

The resource list.

#### `c2s.resources/subscribe.15`

The client subscribes to the static resource `architecture.md`
(`spec:docs/specification/2025-11-25/server/resources.mdx:232` "\"method\": \"resources/subscribe\""), so the
server may tell it when that resource changes.

#### `s2c.notifications/message.9`

The server logs the subscription at info level, as in walkthrough 02
(`servers:src/everything/resources/subscriptions.ts:30` "await server.sendLoggingMessage(").

#### `s2c.response.15`

The subscription is acknowledged with an empty result.

#### `c2s.tools/call.16`

`trigger-resource-update` for that URI.

#### `s2c.notifications/resources/updated.0`

`notifications/resources/updated` with the URI. It is sent only because the client subscribed
(`servers:src/everything/server/context.ts:75` "if (isSubscribed(uri))"); unlike the list
notifications it names exactly which resource changed
(`spec:docs/specification/2025-11-25/server/resources.mdx:244` "\"method\": \"notifications/resources/updated\",").

#### `s2c.response.16`

The tool's result, which says the notification went to each subscriber.

#### `c2s.resources/read.17`

The client's reaction: it re-reads the resource that changed, by the URI in the notification.

#### `s2c.response.17`

The document's text.

#### `c2s.notifications/roots/list_changed.0`

The client changed its roots (the tour adds a second one, `file:///wire-lab/other`) and says so.
A client that declared `listChanged` must send this when its roots change
(`spec:docs/specification/2025-11-25/client/roots.mdx:78` "MUST** send a notification"). It carries no
`id`; the server's answer is a request of its own, not a reply.

```json
{"jsonrpc":"2.0","method":"notifications/roots/list_changed"}
```

#### `s2c.roots/list.7`

The server asks again, as its roots handler does on every such notification
(`servers:src/everything/server/roots.ts:56` "\"notifications/roots/list_changed\","). Its id is 7:
the server's counter has moved on past the earlier requests, including the shim's.

#### `c2s.response.7`

The client answers with both roots now.

#### `s2c.notifications/message.10`

"Roots updated: 2 root(s) received from client", the log line for the new answer.

#### `tap.exit.0`

The tour closes the server's stdin and the server exits with status 0, as in walkthrough 02.
