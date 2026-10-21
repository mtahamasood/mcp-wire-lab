# Lesson 03: when the server speaks first

<!-- exercises: initialize, notifications/initialized, tools/list, tools/call, logging/setLevel, resources/list, prompts/list, resources/subscribe, resources/read, roots/list, sampling/createMessage, elicitation/create, notifications/tools/list_changed, notifications/prompts/list_changed, notifications/resources/list_changed, notifications/resources/updated, notifications/message, notifications/roots/list_changed -->

## Goal

See the protocol run backwards. So far the client asked and the server answered. Here the server
sends the client *requests* (list your roots, ask your model, ask your user) and *notifications*
nobody asked for (the list of tools changed, a resource was updated, a log line). What the client
declares in `initialize` decides which of these the server may use at all. You will run the raw
client's server tour, read the capability matrix, check the recording against the specification's
schema, and then answer a sampling request by hand.

Setup, once: `scripts/bootstrap.sh` (see the README). Everything below runs from the repo root.
Lesson 02 comes first: this one assumes you know the raw client and how requests and replies are
matched by id.

## Predict

Before you run anything, write down:

1. The client declares `roots`, `sampling` and `elicitation` in `initialize`. What changes in the
   server's list of tools compared with lesson 02, where the client declared nothing?
2. The server numbers its own requests from 0, like the client. Both are in flight at the same
   time. How many messages in the trace will have `"id": 0`, and how can you tell them apart?
3. The server sends a request while the client's own `tools/call` is still unanswered. What would
   happen if the client handled the server's request on the same thread that reads the pipe?
4. A client that declared nothing is sent `sampling/createMessage` anyway. What should it answer?

## Run

The server tour declares every capability and then calls the tools that make the server speak:
roots, sampling, elicitation (form, two rounds, URL), log messages, list changes, and a resource
update. `scripts/record.sh --client server-tour` runs it with the tap between the client and the
pinned server, into your own `runs/` folder (git-ignored). It avoids the server's timer tools
(`toggle-*`), so its messages are the same on every run, except for one random `elicitationId`
(a UUID) in the URL-elicitation request and in that tool's result.

<!-- run -->
```console
$ scripts/record.sh --client server-tour lesson03
```

<!-- expect -->
```text
recorded: runs/
```

To see the tour's own output, with every notification printed as it arrives, run it against the
server directly:

```console
python3 -m client server-tour -- node vendor/servers/src/everything/dist/index.js stdio
```

It exits 0 only if every step saw the server traffic it expects. Next, what each capability adds.
`matrix` runs one short session per capability set and prints a table (it is never committed). The
columns are the capabilities the client declared, the tools the server listed for that set, and the
server-initiated methods seen. Compare the `none` row (no extra tools, which is lesson 02's
situation) with `all` (five extra tools, and the server also asks `roots/list` and sends log
messages):

<!-- run -->
```console
$ python3 -m client matrix -- node vendor/servers/src/everything/dist/index.js stdio 2>/dev/null
```

<!-- expect -->
```text
sampling | trigger-sampling-request | notifications/tools/list_changed
```

## Read the trace

First, ask the schema whether every frame is valid. The client's replies to the server's requests
are checked too:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson03 | head -1)
$ python3 -m tap.check "$run/trace.jsonl" --revision 2025-11-25
```

<!-- expect -->
```text
check: ok (74 frames)
```

Now the requests the *server* sent, in order, with their ids. Compare with the ids of the client's
own requests:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson03 | head -1)
$ python3 -m tap.show "$run/trace.jsonl" | grep -o '<-  request [A-Za-z/]* id=[0-9]*'
```

<!-- expect -->
```text
<-  request roots/list id=0
<-  request roots/list id=1
<-  request sampling/createMessage id=2
<-  request elicitation/create id=3
<-  request elicitation/create id=4
<-  request elicitation/create id=5
<-  request elicitation/create id=6
<-  request roots/list id=7
```

The first is the roots sync: 350 ms after `initialized`, the server asks for the client's roots. The
rest each happen *inside* a `tools/call` of the client: the tool asks, the client answers, the tool
finishes. Find the client's replies, which carry the server's ids:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson03 | head -1)
$ python3 -m tap.show "$run/trace.jsonl" | grep -c -- '->  response'
```

<!-- expect -->
```text
8
```

Now read the whole run with explanations: a note after every frame, from
[the walkthrough](../walkthrough/03-server-initiated.md). The walkthrough also has the source tour
of one server request and the capability matrix explained. `--explain` exits non-zero if a frame
has no note:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson03 | head -1)
$ python3 -m tap.show "$run/trace.jsonl" --explain docs/walkthrough/03-server-initiated.md > /dev/null && echo "every frame has a note"
```

<!-- expect -->
```text
every frame has a note
```

Run the same command without the redirect and read every note against your predictions.

## Read the source

- `client/handlers.py`, `Handlers.answer`: one table, keyed by method. The reply carries the
  request's `id` untouched, so `1` and `"1"` stay different. A method the client has no handler
  for, or whose capability it did not declare, gets `-32601`, method not found; an
  `elicitation/create` in a mode it did not declare gets `-32602`, invalid params.
- `Handlers.handle_request`: the reply is built and sent on a worker thread, so the reader can go
  on reading. That is the answer to Predict 3: on one thread the client would wait for its own
  reader to deliver the reply to a request that the reader is itself busy answering.
- `Handlers.handle_notification` and `Handlers._react`: a list-changed notification marks the list,
  and a second thread waits 50 ms before it re-requests, so the five `tools/list_changed` the server
  sends right after `initialized` cost one `tools/list`.
- `client/server_tour.py`, `settle_after_initialized`: why the tour waits before it sends
  anything numbered, and what that does to the ids in the trace.
- On the server side, `servers:src/everything/tools/index.ts:96` "if (capabilities.roots !== undefined) registerGetRootsListTool(server)"
  decides which tools a client gets, and
  `servers:src/everything/tools/get-roots-list.ts:54` "inputRequests: { roots: inputRequired.listRoots() }"
  is where a tool asks the client a question: the walkthrough's source tour follows it.

## Experiments

The outcomes below were **measured against the pinned server** when this lesson was written; they
are what the server did, and the commands here fail if a future pin changes them.

**1. Answer a sampling request yourself.** Manual mode with `--caps sampling` answers the server's
request, with canned text unless you type `:sample <text>` first. The tool returns whatever the
client answered:

<!-- run -->
```console
$ printf '%s\n' ':sample typed by me' ':req tools/call {"name":"trigger-sampling-request","arguments":{"prompt":"hi"}}' | python3 -m client manual --caps sampling -- node vendor/servers/src/everything/dist/index.js stdio 2>/dev/null | grep -c 'typed by me'
```

<!-- expect -->
```text
2
```

The count is two lines: the client's answer to the server (`->`), and the tool's result (`<-`),
which repeats it inside its JSON text. Look at the ids in the output: the server's
request has id 0, the client's `tools/call` has id 1.

**2. Ask for a tool the client's capabilities did not unlock.** Declare nothing, and call
`get-roots-list`:

<!-- run -->
```console
$ printf '%s\n' ':req tools/call {"name":"get-roots-list","arguments":{}}' | python3 -m client manual -- node vendor/servers/src/everything/dist/index.js stdio 2>/dev/null | grep -o '"code":-32602,"message":"Tool get-roots-list not found"'
```

<!-- expect -->
```text
"code":-32602,"message":"Tool get-roots-list not found"
```

Measured: the tool does not exist for this client, so the server answers an error under the
request's id. Declaring `roots` is what makes it appear.

**3. Change the roots.** In `client/server_tour.py`, change the `uri` and `name` in `OTHER_ROOT`
(for example to `file:///wire-lab/mine` and `mine`). Predict which frames of the trace change and which do not (hint: only the client's answer to the
last `roots/list` carries the roots themselves; the server's log line about them reports a count).
Record again and compare with the recipe in the README (*Record and read a trace*). Then undo the edit with `git checkout client/server_tour.py`, so the gate still
sees the original.

## Check yourself

Answer from your own trace, then open the answers.

1. Why does the client's id sequence in the trace run 0 to 17 even though the server also sends
   requests and notifications?
2. How many `tools/list` requests did the client send after `initialized`, and how many
   `notifications/tools/list_changed` did the server send?
3. Which capability makes the server ask a question without being asked, and after how long?
4. The client answers `-32601` to a method whose capability it did not declare. What does the
   spec say a client without `roots` answers to `roots/list`?
5. For an `elicitation/create` in a mode the client did not declare, what does the client answer?
6. Why does the tour not call the server's `toggle-simulated-logging`?

<details>
<summary>Answers</summary>

1. The client's ids are the client's own counter. The server's requests carry the server's ids and
   are answered under them; the two counters only look alike. The tour also waits for the server's
   traffic to settle before each numbered request, so the order of the server's messages cannot
   shift the client's ids.
2. Six `list_changed` notifications for tools in the whole run (five right after `initialized`,
   one from `trigger-list-changed`), and two `tools/list` requests: one for the burst, one for the
   triggered change.
3. `roots`: the server asks `roots/list` 350 ms after `initialized`. The other capabilities only
   unlock tools.
4. `-32601`, method not found (`spec:docs/specification/2025-11-25/client/roots.mdx:144` "Client does not support roots: `-32601`"),
   and this client sends exactly that for every method whose capability it did not declare.
5. `-32602`, invalid params (`spec:docs/specification/2025-11-25/client/elicitation.mdx:700` "-32602"),
   and this client sends exactly that.
6. It sends a log message every five seconds at a random level, so two runs would never match
   frame for frame.

The *Predict* answers:

1. The server lists more tools: `get-roots-list` once `roots` is declared, the sampling and
   elicitation tools for those capabilities (the `matrix` table shows which). With nothing
   declared the list is lesson 02's.
2. Four: the client's `initialize`, the server's reply to it, the server's first `roots/list`,
   and the client's answer to that. A request is told from a response by shape, and the two ids
   0 belong to two different counters.
3. A deadlock: the reader would wait for the handler to finish, and the handler's own reply
   path needs that reader to go on delivering the answer to the client's unanswered `tools/call`.
4. An error response under the server's own id: `-32601` for an undeclared capability (see 4 above).

</details>
