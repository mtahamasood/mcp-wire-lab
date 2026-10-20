# Walkthrough 01: the 2025-era handshake, frame by frame

This explains every record in a trace of `tests/fixtures/handshake-2025.ndjson` recorded
against the pinned everything server. Record your own, then read it with its notes:

```console
scripts/record.sh tests/fixtures/handshake-2025.ndjson
python3 -m tap.show runs/<your-run>/trace.jsonl --explain docs/walkthrough/01-handshake-2025.md
```

Each note is headed by an identity anchor: `<direction>.<method or response>.<id or occurrence>`
(`stderr.<n>` and `tap.<event>.<n>` for the non-protocol records). `--explain` exits non-zero if a
frame has no note here, or a note here names a frame the run never produced (G5 checks this on
every gate run).

Citations point into the two pinned submodules: `spec` is the 2025-11-25 revision of the
specification, `servers` is the everything reference server. The server's protocol plumbing
(request routing, the `initialize` reply itself, `ping`) lives in the TypeScript SDK, which this
repository does not pin, so those notes cite the spec for the rule and the server for what it
configures, and say so.

The examples below are hand-written and trimmed; your trace has the full bytes.

#### `tap.spawn.0`

The tap starts the server as a child process. Over stdio the client launches the server
(`spec:docs/specification/2025-11-25/basic/transports.mdx:24` "The client launches the MCP server as a subprocess"),
so someone has to be the client and the tap sits between. The server's own entry point is
`servers:src/everything/transports/stdio.ts:49` "serveStdio(", which attaches the protocol to
`servers:src/everything/transports/stdio.ts:60` "new StdioServerTransport(stdin, stdout)".
The `spawn` record lists the command and the minimal environment `scripts/record.sh` gives the
server, so none of your own environment reaches the trace.

#### `c2s.initialize.0`

The first thing any client says. The spec requires the client to open the connection with an
`initialize` request (`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:47` "MUST** initiate this phase") carrying the protocol
version it speaks, its capabilities and who it is
(`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:57` "\"method\": \"initialize\"").
The fixture offers `2025-11-25` and no capabilities. `id` is `0`: requests carry an `id` so the
reply can be matched when several are in flight; notifications carry none.

```json
{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"wire-lab-fixture","version":"0"}}}
```

Without it nothing else works: the server has not agreed on a version or exchanged capabilities.

#### `stderr.0`

Not protocol at all. The server prints a boot line on stderr, which the spec allows for logging
(`spec:docs/specification/2025-11-25/basic/transports.mdx:29` "standard error") and tells clients not to read as an error
(`spec:docs/specification/2025-11-25/basic/transports.mdx:32` "SHOULD NOT"). Its source is
`servers:src/everything/transports/stdio.ts:92` "Starting default (STDIO) server...". The tap records
stderr as its own stream, interleaved by time, so you can see it arrive before the reply.

#### `s2c.response.0`

The answer to `initialize`, matched by `id`. The spec requires the server to answer with its
capabilities and information (`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:98` "MUST** respond with its own capabilities").
Version negotiation: if the server supports the requested version it echoes it back, otherwise it
names one it does support (`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:170` "MUST** respond with the same").
In the trace the server echoes `2025-11-25`. The reply is the largest frame of the handshake
because it also carries the server's `instructions` text, read at
`servers:src/everything/server/index.ts:120` "readInstructions()".

What the server declares is configured in the everything server: its identity at
`servers:src/everything/server/index.ts:128` "name: \"mcp-servers/everything\"" and its capabilities from
`servers:src/everything/server/index.ts:133` "capabilities: {" (for example resources with
subscribe and listChanged at `servers:src/everything/server/index.ts:141` "resources: {", and logging at
`servers:src/everything/server/index.ts:148` "logging: {}"). The `tools` capability is added by the first tool
registration, which is why it is not in that block. The reply itself is assembled by the SDK, which is
not pinned here.

This is the slowest frame of the run, the server's start-up showing as latency: `tap.show` prints
the time between request and reply.

#### `c2s.notifications/initialized.0`

The client's second handshake message, and a notification, so it has no `id` and gets no reply.
The spec says the client must send it once initialization succeeded
(`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:147` "MUST** send an `initialized` notification"). It means
"I have your answer and I am ready". On the server it fires the hook at
`servers:src/everything/server/index.ts:194` "server.server.oninitialized", where it registers tools that need
to know what the client can do.

```json
{"jsonrpc":"2.0","method":"notifications/initialized"}
```

Until it arrives the server should only send pings and log messages
(`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:160` "The server **SHOULD NOT** send requests other than").

#### `c2s.tools/list.1`

The first ordinary request after the handshake: ask the server what tools it has. The spec's form
is `spec:docs/specification/2025-11-25/server/tools.mdx:57` "To discover available tools, clients send a `tools/list` request".
The everything server registers its tools in one place, starting at
`servers:src/everything/tools/index.ts:47` "registerEchoTool(server)", and the SDK turns those
registrations into the reply. `id` is `1`; ids only need to be unique per sender.

#### `s2c.response.1`

The tool list, matched to `tools/list` by `id` 1: each tool's name, description and JSON Schema for
its arguments. This is what a model is shown so it can decide what to call. Its size is why the
viewer truncates it by default and `--full` prints it whole.

#### `c2s.ping.2`

A liveness check. The spec defines `ping` as a request with no parameters
(`spec:docs/specification/2025-11-25/basic/utilities/ping.mdx:23` "\"method\": \"ping\"") that either side may send.
It is the one request the spec exempts from the handshake order: the client should not send requests
other than pings before the server has answered `initialize`
(`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:157` "The client **SHOULD NOT** send requests other than"
continues on `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:158` "[pings](").
The fixture sends it last so you can compare its latency with `initialize`'s.

#### `s2c.response.2`

The receiver must answer promptly with an empty result
(`spec:docs/specification/2025-11-25/basic/utilities/ping.mdx:29` "empty response"). The trace shows `"result":{}`
and a reply in about a millisecond or two, against hundreds for `initialize`: the start-up cost was
paid once, before the first reply, not on every request.

```json
{"jsonrpc":"2.0","id":2,"result":{}}
```

#### `tap.exit.0`

The fixture driver has sent its last line and closed the server's stdin; the server shuts down and
the tap records the child's exit code. Closing stdin is how a stdio client ends a session
(`spec:docs/specification/2025-11-25/basic/transports.mdx:48` "Close stdin, terminate subprocess"), and the exit
code `0` says the server left cleanly. The wire itself carries no "goodbye" message.
