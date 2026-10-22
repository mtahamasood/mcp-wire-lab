# Walkthrough 05: the SDK client, and what it hides

The SDK client (`clients/sdk/`) runs the raw client's two tours through
`@modelcontextprotocol/client` 2.3.1. This walkthrough has three parts: what is the same in the two
clients' traces, what differs (difference by difference), and one `client.callTool` followed from
the API call down to the bytes written to the server's stdin and back. Record your own traces,
diff them, and read the diff with its notes:

```console
scripts/record.sh --client tour mine-raw
scripts/record.sh --client sdk-tour mine-sdk
python3 -m tap.diff runs/<your-raw-run>/trace.jsonl runs/<your-sdk-run>/trace.jsonl --explain docs/walkthrough/05-sdk-client.md#tour
```

`tap.diff` names each message by direction, method and occurrence, never by id, so the two
clients' numbering does not matter. For the server tour use `server-tour` and `sdk-server-tour`
and `#server-tour`. Citations: `sdk:` points into the installed SDK package
(`clients/sdk/node_modules/@modelcontextprotocol/`, the `dist/` files Node runs, pinned by the
lockfile and checked by `scripts/bootstrap.sh`); `servers:` is the pinned everything server.

## What is the same

`python3 -m tap.show <sdk trace> --explain docs/walkthrough/02-raw-client-tour.md` passes on a
fresh `sdk-tour` trace, and the same with `03-server-initiated.md` on an `sdk-server-tour` trace:
no frame without a note and no note without a frame (`tests/test_e2e.py` checks both on every
gate run). That is a strong statement: the notes of walkthroughs 02 and 03 are keyed by request
id, so the SDK sends the same requests, in the same order, with the same ids (0 to 16 for the
tour), and the server's replies are the same frames. Of the 41 message pairs of the tour, 20 are
equal bytes for bytes, 14 are equal as JSON and differ only in the order of their members, and 7
differ. Of the 74 pairs of the server tour, 45 are equal, 24 differ only in member order, and 5
differ. Nothing is in one trace only. The notes below explain the rest.

## Bytes only: member order

The 14 and 24 pairs that are equal as JSON but not as bytes differ in the order of their
members. The SDK builds each outgoing request as the request object first and then the version
and id: `method` and `params`, then `jsonrpc`, then `id`
(`sdk:client/dist/src-WCy6ifGf.mjs:6173` "...request,"
`sdk:client/dist/src-WCy6ifGf.mjs:6174` "jsonrpc: \"2.0\","
`sdk:client/dist/src-WCy6ifGf.mjs:6175` "id: messageId"). The raw client writes `jsonrpc` and `id`
first. JSON objects are unordered, so the receiver cannot tell the difference
(`spec:docs/specification/2025-11-25/basic/index.mdx:37` "jsonrpc: \"2.0\""). The server's frames
come back in the SDK's order for every client, because the server is built on the same SDK
generation (`servers:src/everything/package.json:41` "@modelcontextprotocol/server"); that is why
even a response the SDK client did not change shows as bytes-only against the raw client's trace.
`tap.diff` counts these pairs and does not list them.

## What the SDK does that never reaches the wire

These things happen between your call and the bytes; the traces cannot show them.

- **Result validation.** Every result is decoded and checked against the SDK's schema for the
  method before your `await` returns
  (`sdk:client/dist/src-WCy6ifGf.mjs:6214` "decoded = codec.decodeResult(request.method, response.result);"
  and `sdk:client/dist/src-WCy6ifGf.mjs:6235` "validateStandardSchema(resultSchema, result)"). A
  reply the schema rejects becomes a rejected promise; the raw client hands back whatever
  arrived.
- **The response cache.** `listTools` stores its list in a cache, and `callTool` reads the
  tool's output schema from it (`sdk:client/dist/src-WCy6ifGf.mjs:6048` "const handler = this._responseHandlers.get(messageId);"
  is the pending-request table; the cache is `sdk:client/dist/index.mjs:4244` "this._cache.outputValidator(params.name"). With no
  `listTools` before it, `callTool` sends no hidden `tools/list`, and the tour's `echo` call
  produces exactly one request.
- **Page aggregation.** `listTools`, `listPrompts`, `listResources` and
  `listResourceTemplates` follow `nextCursor` until the end and return one list
  (`sdk:client/dist/index.mjs:3778` "async _listAllPages(method"). The server's lists fit one page, so
  the trace shows one request each.
- **The progress handler table.** `onprogress` is stored under the request id; a progress
  notification whose token has no handler is dropped and reported through `onerror`
  (`sdk:client/dist/src-WCy6ifGf.mjs:6024` "Received a progress notification for an unknown token"). The
  tour's cancelled call shows it: after the abort the server's second progress notification
  arrives, finds no handler, and the client prints `sdk: Received a progress notification for an unknown token`
  on stderr (the raw client's wire drops and reports a late reply the same way).
- **The timeout.** Every request has a 60 s default timeout
  (`sdk:client/dist/src-WCy6ifGf.mjs:5536` "DEFAULT_REQUEST_TIMEOUT_MSEC = 6e4"), applied here
  (`sdk:client/dist/src-WCy6ifGf.mjs:6242` "const timeout = options?.timeout ?? DEFAULT_REQUEST_TIMEOUT_MSEC;"). The raw client's is
  30 s (`client/wire.py`, `DEFAULT_TIMEOUT`).
- **List-change debounce.** The `listChanged` option re-lists after a 300 ms quiet window; the
  raw client waits 50 ms. Both coalesce a burst into one re-list in the measured traces.

## Source tour: one `callTool` echo, from the API call to the pipe and back

The tour's `callTool` of `echo` is request id 3 in the tour. Follow it through the SDK.

**Out.**

1. **The API call.** `client.callTool({ name: "echo", arguments: { message: "hello" } })` is
   `Client.callTool` (`sdk:client/dist/index.mjs:4224` "async callTool(params, options) {"). It looks up the tool's
   output validator in the cache (`sdk:client/dist/index.mjs:4244` "let compiled = options?.toolDefinition === void 0") and then calls
   `this.request` with the method `tools/call` and your params
   (`sdk:client/dist/index.mjs:4254` "result = await this.request({").
2. **`Protocol.request`.** `request` picks the result schema for the method and hands over to the
   request funnel (`sdk:client/dist/src-WCy6ifGf.mjs:6068` "request(request, schemaOrOptions, maybeOptions) {"
   then `sdk:client/dist/src-WCy6ifGf.mjs:6136` "_requestWithSchema(request, resultSchema, options) {").
3. **The id.** The next number from a counter that starts at 0:
   `sdk:client/dist/src-WCy6ifGf.mjs:6170` "const messageId = this._requestMessageId++;". `initialize` took 0, `ping` 1, and so on.
4. **The message object.** The request you gave, then the version and the id
   (`sdk:client/dist/src-WCy6ifGf.mjs:6172` "const jsonrpcRequest = {"). If you passed `onprogress`, the handler is stored under the id
   (`sdk:client/dist/src-WCy6ifGf.mjs:6178` "this._progressHandlers.set(messageId, options.onprogress);") and the
   `progressToken` in `_meta` is the id (`sdk:client/dist/src-WCy6ifGf.mjs:6183` "progressToken: messageId"); the
   echo call passes none, so its frame has no `_meta`.
5. **The response handler.** A function keyed by the id, which will decode and validate the result
   and settle the promise (`sdk:client/dist/src-WCy6ifGf.mjs:6208` "this._responseHandlers.set(messageId, (response) => {").
6. **The timeout.** Started before the send (`sdk:client/dist/src-WCy6ifGf.mjs:6244` "this._setupTimeout(messageId, timeout").
7. **The send.** `this._transport.send(outbound, ...)`
   (`sdk:client/dist/src-WCy6ifGf.mjs:6245` "this._transport.send(outbound, {"). The transport is a
   `StdioClientTransport`, whose `send` serializes the message
   (`sdk:client/dist/stdio.mjs:206` "send(message) {", `sdk:client/dist/stdio.mjs:209` "const json = serializeMessage(message);")
   as one line of JSON and a newline (`sdk:client/dist/src-WCy6ifGf.mjs:6776` "return JSON.stringify(message)")
   and writes it to the child's stdin (`sdk:client/dist/stdio.mjs:210` "this._process.stdin.write(json)"). The child
   is the tap, which copies the line to the server and records it. The transport's
   framing is the newline rule of
   `spec:docs/specification/2025-11-25/basic/transports.mdx:28` "contain embedded newlines".

**Back.**

8. **The stdout handler.** The child's stdout delivers chunks
   (`sdk:client/dist/stdio.mjs:102` "this._process.stdout?.on(\"data\", (chunk) => {"); each is appended to the read buffer
   (`sdk:client/dist/stdio.mjs:104` "this._readBuffer.append(chunk);").
9. **`ReadBuffer`.** It cuts the buffer at each newline and parses the line
   (`sdk:client/dist/src-WCy6ifGf.mjs:6753` "readMessage() {", `sdk:client/dist/src-WCy6ifGf.mjs:6760` "return deserializeMessage(line);"), checking
   it against the SDK's message schema (`sdk:client/dist/src-WCy6ifGf.mjs:6773` "JSONRPCMessageSchema.parse(JSON.parse(line))").
10. **`onmessage`.** The transport hands each message to its `onmessage`
    (`sdk:client/dist/stdio.mjs:140` "this.onmessage?.(message);"); `Protocol.connect` installed the function that
    sends a response to `_onresponse`
    (`sdk:client/dist/src-WCy6ifGf.mjs:5848` "this._onresponse(message)").
11. **`_onresponse`, the handler by id.** `Client` first checks for a subscription id
    (`sdk:client/dist/index.mjs:4147` "_onresponse(response) {") and passes on to the protocol layer, which looks the handler up by
    the response's id and calls it (`sdk:client/dist/src-WCy6ifGf.mjs:6046` "_onresponse(response) {",
    `sdk:client/dist/src-WCy6ifGf.mjs:6048` "const handler = this._responseHandlers.get(messageId);",
    `sdk:client/dist/src-WCy6ifGf.mjs:6056` "if (isJSONRPCResultResponse(response)) handler(response);").
12. **Decoding and validation.** The handler decodes the result and checks it against the schema
    (`sdk:client/dist/src-WCy6ifGf.mjs:6214` "decoded = codec.decodeResult(request.method, response.result);",
    `sdk:client/dist/src-WCy6ifGf.mjs:6235` "validateStandardSchema(resultSchema, result)") and resolves the promise.
13. **`callTool`'s output-schema check.** Back in `callTool`, if the tool declared an output
    schema the structured content is checked against it
    (`sdk:client/dist/index.mjs:4276` "if (validator) {", `sdk:client/dist/index.mjs:4280` "Structured content does not match"); `echo` declares none, so the
    result is returned as it is, and the tour reads `content[0].text`.

## tour

The seven differences between a raw and an SDK trace of the tour.

#### `c2s.initialize#0`
The client's own name and version: `clientInfo` is `wire-lab-raw` 0.2.0 in the raw client and
`wire-lab-sdk` 0.5.0 in the SDK client, because each client says who it is
(`clients/sdk/src/client.ts`, `CLIENT_INFO`). Everything else in the request is equal: the SDK
offers `2025-11-25` and, with no `versionNegotiation` option, sends no `server/discover`. This
difference would show in a raw-vs-raw diff too if the two raw clients had different names.

#### `c2s.tools/call#2`
The first long-running call. The raw client chose the token `"tour-done"` itself and put it in
`_meta`. The SDK client asked for progress with `onprogress`, and the SDK chose the token: the
request's own id, 15 (`sdk:client/dist/src-WCy6ifGf.mjs:6183` "progressToken: messageId"). Nothing else in the call differs.

#### `s2c.notifications/progress#0-1`
The server's two progress notifications for that call. They carry the token the client
sent, so they differ for the same reason as the request: `"tour-done"` against 15. The server
sends whatever token it was given: the tool reads it from the request's `_meta`
(`servers:src/everything/tools/trigger-long-running-operation.ts:49` "ctx.mcpReq._meta?.progressToken") and puts it in each notification.

#### `c2s.tools/call#3`
The cancelled call. The same difference as `c2s.tools/call#2`: the token is `"tour-cancel"` in the raw
trace and 16, the request's id, in the SDK trace. The `notifications/cancelled` frame that
follows is equal in both traces: it names the request by id, not by token, and both clients gave
the call id 16 (`sdk:client/dist/src-WCy6ifGf.mjs:6170` "const messageId = this._requestMessageId++;"). The reason text is the same, because the SDK
sends the abort's reason as given.

#### `s2c.notifications/progress#2-3`
The two progress notifications of the cancelled call, `"tour-cancel"` against 16. In the SDK
client the second one finds no handler, because the abort removed it, and the SDK drops it and
reports it on stderr (`sdk:client/dist/src-WCy6ifGf.mjs:6024` "Received a progress notification for an unknown token"). The frame is on the wire all the same.

## server-tour

The five differences between a raw and an SDK trace of the server tour.

#### `c2s.initialize#0`
The client's name and version, as in the tour. The capabilities object is equal: the SDK client
declares the same objects the raw client sends, `roots` with `listChanged`, `sampling`, and
`elicitation` with `form` and `url`.

#### `c2s.response:sampling/createMessage#0`
The client's answer to the server's sampling request. The values are phase 3 D1's, with one
difference: the canned text names the client, `canned reply from wire-lab-raw` against
`canned reply from wire-lab-sdk` (`clients/sdk/src/handlers.ts`, `CANNED_TEXT`).

#### `s2c.response:tools/call#1`
The server's result of the `trigger-sampling-request` call. It quotes the client's canned text
(`servers:src/everything/tools/trigger-sampling-request.ts:94` "LLM sampling result"), so it differs wherever the text does. It is the same
difference as the previous note, one hop later.

#### `s2c.elicitation/create#3`
The server's URL-mode elicitation request. Its `elicitationId` is a fresh random UUID on every
run (`servers:src/everything/tools/trigger-url-elicitation.ts:165` "requestedElicitationId ?? randomUUID()"). This is noise, not a difference between the clients: a
raw-vs-raw diff of two fresh traces shows it too.

#### `s2c.response:tools/call#4`
The result of the `trigger-url-elicitation` call. It quotes the elicitation id
(`servers:src/everything/tools/trigger-url-elicitation.ts:241` "User declined to open the URL (Elicitation ID:"), so it carries the same noise as the previous note and
a raw-vs-raw diff shows it too.
