# Lesson 05: what an SDK hides

<!-- exercises: initialize, notifications/initialized, ping, tools/list, tools/call, resources/list, resources/templates/list, resources/read, resources/subscribe, resources/unsubscribe, prompts/list, prompts/get, completion/complete, logging/setLevel, notifications/cancelled, notifications/message, notifications/progress -->

## Goal

Run the raw client's tour through the official TypeScript SDK, `@modelcontextprotocol/client`
2.3.1, and find out which bytes the SDK chose for you. The SDK client in `clients/sdk/` makes the
same calls as the raw client of lesson 02, through the SDK's methods, and never writes a
message itself. (An *SDK*, software development kit, is the library that does the protocol's
bookkeeping for you: ids, framing, validation, timeouts. The *tap* is the lab's recorder between
client and server; a *trace* is what it wrote.) You will record both clients, diff the two traces message by message with
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
3. A *progress token* is a value the client puts in a request's `_meta` member (the spec's slot
   for side information about a request) to ask the server for `notifications/progress` about
   it; the server echoes it in each notification. The raw client chose the progress tokens `"tour-done"` and `"tour-cancel"`. The SDK client
   asks for progress with an `onprogress` callback and does not name a token. What will the
   token be?
4. The raw client cancelled a call by sending `notifications/cancelled`. The SDK client aborts an
   `AbortSignal` (JavaScript's standard handle for cancelling an operation in progress). Will the two `notifications/cancelled` frames be equal?

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

### The server tour: when the server asks the client

The first tour has the client ask and the server answer. The *server tour* (lesson 03) also has the
server ask the client: it sends `roots/list`, `sampling/createMessage` (a request for the client
to produce a model reply) and `elicitation/create` (a request for the client to ask its user for
input). A client that sits on an SDK does not write those answers itself; it registers handlers
and the SDK sends the replies. Record both clients' server tours, then check the SDK trace and
diff the two:

<!-- run -->
```console
$ scripts/record.sh --client server-tour lesson05-raw-server
```

<!-- expect -->
```text
recorded: runs/
```

<!-- run -->
```console
$ scripts/record.sh --client sdk-server-tour lesson05-sdk-server
```

<!-- expect -->
```text
recorded: runs/
```

<!-- run -->
```console
$ raw=$(ls -dt runs/*-lesson05-raw-server | head -1)
$ sdk=$(ls -dt runs/*-lesson05-sdk-server | head -1)
$ python3 -m tap.check "$sdk/trace.jsonl" --revision 2025-11-25
$ python3 -m tap.diff "$raw/trace.jsonl" "$sdk/trace.jsonl" > "$sdk/diff.txt" || true
$ grep '^summary' "$sdk/diff.txt"
```

<!-- expect -->
```text
check: ok (74 frames)
summary: 74 pairs, 45 equal, 24 equal as JSON but not as bytes, 5 differ; 0 only in a, 0 only in b
```

Five differ (`tap.diff` exits 1 when anything differs, which is why the command above ends
the diff with `|| true`), and none is in one trace only. As with the first tour, read the diff, guess the five,
then ask for the notes in the walkthrough's `#server-tour` section (the same exit rule applies):

<!-- run -->
```console
$ raw=$(ls -dt runs/*-lesson05-raw-server | head -1)
$ sdk=$(ls -dt runs/*-lesson05-sdk-server | head -1)
$ python3 -m tap.diff "$raw/trace.jsonl" "$sdk/trace.jsonl" --explain docs/walkthrough/05-sdk-client.md#server-tour > /dev/null && echo "every difference has a note"
```

<!-- expect -->
```text
every difference has a note
```

Two of the five are not about the SDK at all: each run's elicitation id is a fresh random value,
so a diff of two raw runs shows it too.

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

**1. See the member order.** The 14 pairs that differ only in member order are bytes, not
meaning. Print the first request of each tour trace, cut to 60 characters (the raw client first,
then the SDK client):

<!-- run -->
```console
$ for who in raw sdk; do run=$(ls -dt runs/*-lesson05-$who | head -1); python3 -c 'import json,sys; print(json.loads(open(sys.argv[1]).readlines()[1])["raw"][:60].rstrip())' "$run/trace.jsonl"; done
```

<!-- expect -->
```text
{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"pro
{"method":"initialize","params":{"protocolVersion":"2025-11-
```

Same message, two byte orders. A receiver that parses JSON cannot tell them apart.

**2. Read the progress tokens.** List the distinct `progressToken` values on the wire in each tour
trace:

<!-- run -->
```console
$ for who in raw sdk; do run=$(ls -dt runs/*-lesson05-$who | head -1); echo "$who: $(grep -o '"progressToken": [^,}]*' "$run/trace.jsonl" | sort -u | tr '\n' ' ')"; done
```

<!-- expect -->
```text
raw: "progressToken": "tour-cancel" "progressToken": "tour-done" 
sdk: "progressToken": 15 "progressToken": 16 
```

The SDK's tokens are request ids. Compare them with your answer to Predict 3.

**3. See what the SDK answers for you.** In the SDK server tour the server sent requests to the
client. List them (the lines starting `<-` that are requests):

<!-- run -->
```console
$ sdk=$(ls -dt runs/*-lesson05-sdk-server | head -1)
$ python3 -m tap.show "$sdk/trace.jsonl" | grep '<-  request' | sed 's/^ *[0-9]* *[0-9.]* ms *<-  //'
```

<!-- expect -->
```text
request roots/list id=0
request roots/list id=1
request sampling/createMessage id=2
request elicitation/create id=3
request elicitation/create id=4
request elicitation/create id=5
request elicitation/create id=6
request roots/list id=7
```

These ids belong to the server, not to the client: the server numbers its own requests from 0,
so id 2 here is a different message from the client's request 2. Find each one's reply in
`tap.show` (the `->  response id=N (answers seq M)` lines) and open `clients/sdk/src/handlers.ts`
to see the few lines of code that produced them.

**4. Ask for progress the raw client's way.** In `clients/sdk/src/tour.ts`, in `longRunning`,
change the `callTool` params to include `_meta: { progressToken: "tour-done" }` and drop the
`onprogress` option (the tour then fails its progress check; that is part of the answer). Before
you run `scripts/record.sh --client sdk-tour` again, predict the new diff against the raw
trace, and what the SDK does with the two progress notifications (hint: `client.onerror`). Then
undo the edit with `git checkout clients/sdk/src/tour.ts`, so the gate still sees the original.
The measured outcome is under *Check yourself*, after the answers.

**5. Read the order.** Run `python3 -m tap.show` on both traces and compare the order of the
frames. `tap.diff` compares messages, not their order; what does the order tell you that the
diff does not? (Answer after the answers below.)

## Check yourself

Answer from your own traces, then open the answers.

1. How many message pairs did the tour diff compare, how many differ, and which are they?
2. Why are the SDK's progress tokens 15 and 16?
3. Why are the `notifications/cancelled` frames equal although the progress tokens are not?
4. What does the SDK do that your traces cannot show?
5. In the server tour, which of the five differences come from the SDK client, and which would
   appear between any two runs?

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
5. The client's name and version (`initialize`), and the canned sampling text that names the
   client, with the tool result that quotes it, differ because of the client. The two
   elicitation differences (the random id in the server's request, and the result that quotes
   it) appear between any two runs.

The *Predict* answers:

1. Yes to both: the same ids, 0 to 16, and the same messages in the same order; the diff keys
   messages by direction, method and occurrence and finds none in one trace only.
2. The client's name and version in `initialize`; the progress token of each long-running call
   and of the progress notifications that carry it. Everything else is equal as JSON, and 14
   pairs differ only in member order.
3. The request's id: 15 for the first long-running call and 16 for the second.
4. Yes: the frame names the request by id (16), and both clients used the same id and the
   same reason text.

Experiment answers:

4. The first call's frame now equals the raw client's, token `"tour-done"` included, and its two
   progress notifications arrive. But the SDK stored no handler under that token, so it drops
   both and reports them on stderr (`sdk: Received a progress notification for an unknown
   token`), the tour fails its check at step 16 and the client exits 1, so the cancelled call is
   never made. Measured against the raw tour: 37 pairs compared, 1 differs (`initialize`), 4 only
   in the raw trace (the second `tools/call`, its two notifications and the `notifications/cancelled`).
5. The order shows what the diff hides: when a message lands relative to the others. In the SDK
   server tour the client sends `tools/call` id 2, the server asks `roots/list` while that call is
   still open, the client answers, and only then does the reply to id 2 arrive. A reply can come
   after a request the server made to you, so a client must keep reading while it waits.

</details>
