# Lesson 05: what an SDK hides

<!-- exercises: initialize, notifications/initialized, ping, tools/list, tools/call, resources/list, resources/templates/list, resources/read, resources/subscribe, resources/unsubscribe, prompts/list, prompts/get, completion/complete, logging/setLevel, notifications/cancelled, notifications/message, notifications/progress -->

## Goal

Run the raw client's tour through the official TypeScript SDK, `@modelcontextprotocol/client`
2.3.1, and find out which bytes the SDK chose for you. The SDK client in `clients/sdk/` makes the
same calls as the raw client of lesson 02, through the SDK's methods, and never writes a
message itself. You will record both clients, diff the two traces message by message with
`tap.diff`, explain every difference, and then follow one `client.callTool` from the API call to
the bytes on the server's stdin and back, in the SDK's own source.

Setup, once: `scripts/bootstrap.sh` (it also installs the SDK client's packages). Everything
below runs from the repo root. Lessons 02 and 03 come first: this one assumes you have read the
raw client's traces.

## Predict

Before you run anything, write down:

1. The SDK client runs the same 17 steps. Will its trace have the same request ids as the raw
   client's? The same messages in the same order?
2. Which fields of the traces will differ? Think about what the client chooses (its name, the
   token it asks progress with) and what the SDK chooses for it.
3. The raw client chose the progress tokens `"tour-done"` and `"tour-cancel"`. The SDK client
   asks for progress with an `onprogress` callback and does not name a token. What will the
   token be?
4. The raw client cancelled a call by sending `notifications/cancelled`. The SDK client aborts an
   `AbortSignal`. Will the two `notifications/cancelled` frames be equal?

(Answers to 1 to 4: the *Predict answers* at the end.)

## Run

The SDK client is TypeScript run as source by Node 24, with no build step:
`node clients/sdk/src/main.ts tour -- <server command>`. `scripts/record.sh --client sdk-tour`
runs it with the tap between the client and the pinned server. Record the raw tour and the SDK
tour:

<!-- run -->
```console
$ scripts/record.sh --client tour lesson05-raw
```

<!-- expect -->
```text
recorded: runs/
```

<!-- run -->
```console
$ scripts/record.sh --client sdk-tour lesson05-sdk
```

<!-- expect -->
```text
recorded: runs/
```

Each run prints one line per step. To see it, run the SDK client against the server directly:

```console
node clients/sdk/src/main.ts tour -- node vendor/servers/src/everything/dist/index.js stdio
```

It exits 0 only if every step got what it expects. Near the end it prints a line on stderr
starting with `sdk:`; the *Read the trace* section explains it.

## Read the trace

First, ask the schema whether every frame of the SDK client's trace is valid:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson05-sdk | head -1)
$ python3 -m tap.check "$run/trace.jsonl" --revision 2025-11-25
```

<!-- expect -->
```text
check: ok (41 frames)
```

The raw client's own walkthrough explains every frame of the SDK client's trace too, which is
the first half of the lesson's claim: same messages, same ids.

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson05-sdk | head -1)
$ python3 -m tap.show "$run/trace.jsonl" --explain docs/walkthrough/02-raw-client-tour.md > /dev/null && echo "the raw walkthrough explains it"
```

<!-- expect -->
```text
the raw walkthrough explains it
```

Now the second half: what differs. `tap.diff` names each message by direction, method and
occurrence, so ids do not matter, and compares the two as JSON:

```console
python3 -m tap.diff runs/<your-raw-run>/trace.jsonl runs/<your-sdk-run>/trace.jsonl
```

Run it on your two recordings and read it before the next command. Then ask for the notes in
[the walkthrough](../walkthrough/05-sdk-client.md); `--explain` exits non-zero if a difference
has no note, or a note names a difference that is not there:

<!-- run -->
```console
$ raw=$(ls -dt runs/*-lesson05-raw | head -1)
$ sdk=$(ls -dt runs/*-lesson05-sdk | head -1)
$ python3 -m tap.diff "$raw/trace.jsonl" "$sdk/trace.jsonl" --explain docs/walkthrough/05-sdk-client.md#tour > /dev/null && echo "every difference has a note"
```

<!-- expect -->
```text
every difference has a note
```

The tour's stderr is in the run folder: `cat runs/*-lesson05-sdk/stderr.txt`. The line
starting `sdk:` is the SDK telling you, through `client.onerror`, that the server's second progress
notification of the cancelled call arrived after the call was abandoned.

## Read the source

- `clients/sdk/src/tour.ts`: the tour. Notice what is not in it: no message object, no id, no
  `send`. Every step is a `Client` method (`listTools`, `callTool`, `readResource`, ...).
  `clients/sdk/src/client.ts` builds the client: the capabilities, the handlers for what the
  server asks, the `listChanged` option that re-lists for you.
- The SDK itself, following one request: the source tour in
  [the walkthrough](../walkthrough/05-sdk-client.md) goes from `Client.callTool` through
  `Protocol.request` (the id, the message, the response handler, the timeout) to
  `StdioClientTransport.send` and the write to stdin, and back through `ReadBuffer` and
  `_onresponse`. Every hop is a citation you can open, in the form you know from lesson 01, for
  example `sdk:client/dist/src-WCy6ifGf.mjs:6170` "const messageId = this._requestMessageId++;".

## Experiments

**1. Ask for progress the raw client's way.** In `clients/sdk/src/tour.ts`, in `longRunning`,
change the `callTool` params to include `_meta: { progressToken: "tour-done" }` and drop the
`onprogress` option (the tour then fails its progress check; that is part of the answer). Before
you run `scripts/record.sh --client sdk-tour` again, predict the new diff against the raw
trace, and what the SDK does with the two progress notifications (hint: `client.onerror`). Then
undo the edit with `git checkout clients/sdk/src/tour.ts`, so the gate still sees the original.

**2. Read the order.** Run `python3 -m tap.show` on both traces and compare the order of the
frames. `tap.diff` compares messages, not their order; what does the order tell you that the
diff does not?

## Check yourself

Answer from your own traces, then open the answers.

1. How many message pairs did the tour diff compare, how many differ, and which are they?
2. Why are the SDK's progress tokens 15 and 16?
3. Why are the `notifications/cancelled` frames equal although the progress tokens are not?
4. What does the SDK do that your traces cannot show?

<details>
<summary>Answers</summary>

1. 41 pairs; 7 differ: `initialize` (the client's name and version), the two long-running
   `tools/call` requests (the progress token) and their four progress notifications. 14 more are
   equal as JSON and differ only in the order of their members, which the diff counts and does
   not list.
2. When you pass `onprogress`, the SDK puts the request's own id in `_meta.progressToken`
   (`Protocol.request`); the two calls were requests 15 and 16.
3. A cancellation names the request by its id, not by its progress token, and both clients gave
   the call the same id, 16.
4. It validates every result against its schema, caches the tool list for `callTool`'s output
   check, follows `nextCursor` through every page, drops a progress notification whose handler
   is gone and reports it through `onerror`, and times every request out after 60 s.

The *Predict* answers:

1. Yes to both: the same ids, 0 to 16, and the same messages in the same order; the diff keys
   messages by direction, method and occurrence and finds none in one trace only.
2. The client's name and version in `initialize`; the progress token of each long-running call
   and of the progress notifications that carry it. Everything else is equal as JSON, and 14
   pairs differ only in member order.
3. The request's id: 15 for the first long-running call and 16 for the second.
4. Yes: the frame names the request by id (16), and both clients used the same id and the
   same reason text.

</details>
