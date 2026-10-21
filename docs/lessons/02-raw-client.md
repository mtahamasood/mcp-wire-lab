# Lesson 02: a client with no library

## Goal

Speak MCP yourself. The raw client in `client/` frames JSON-RPC over a child process's stdin and
stdout, matches replies to requests by id, runs the 2025-era opening exchange, and then uses every
request a server offers to a client that has nothing to offer back: tools, resources, prompts,
completion, logging, progress and cancellation. You will run it against the pinned server, check
its recording against the specification's own JSON Schema, read the frames, and then type
messages by hand, mistakes included, to see what the server does with them.

Setup, once: `scripts/bootstrap.sh` (see the README). Everything below runs from the repo root.
Lesson 01 comes first: this one assumes you know what `initialize` is.

## Predict

Before you run anything, write down:

1. The tour sends 17 requests. Which of them will the server answer, and which one will never get
   an answer? Why?
2. Which messages will the server send that the client did not ask for?
3. The client numbers its requests from 0. The server can also send requests, and numbers its
   own from 0. If both are in flight at once, how can the client tell a reply from a request?
4. After the client closes the server's stdin, what does it do if the server does not exit?

## Run

The tour is a script: `python3 -m client tour -- <server command>`. `scripts/record.sh --client tour`
runs it with the tap between the client and the pinned server, so the whole conversation lands in
your own `runs/` folder (git-ignored).

<!-- run -->
```console
$ scripts/record.sh --client tour lesson02
```

<!-- expect -->
```text
recorded: runs/
```

The tour itself prints one line per step as it goes. To see that output, run it against the server
directly, without the tap:

```console
python3 -m client tour -- node vendor/servers/src/everything/dist/index.js stdio
```

It exits 0 only if every step got the reply it expected.

## Read the trace

First, ask the schema whether every frame the client and the server exchanged is valid. `tap.check`
checks each frame against `schema.json` of the 2025-11-25 revision in the pinned specification:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson02 | head -1)
$ python3 -m tap.check "$run/trace.jsonl" --revision 2025-11-25
```

<!-- expect -->
```text
check: ok (41 frames)
```

Now the requests the client sent, in order, with their ids:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson02 | head -1)
$ python3 -m tap.show "$run/trace.jsonl" | grep -o 'request [A-Za-z/]* id=[0-9]*'
```

<!-- expect -->
```text
request initialize id=0
request ping id=1
request tools/list id=2
request tools/call id=3
request tools/call id=4
request resources/list id=5
request resources/templates/list id=6
request resources/read id=7
request resources/subscribe id=8
request resources/unsubscribe id=9
request prompts/list id=10
request prompts/get id=11
request prompts/get id=12
request completion/complete id=13
request logging/setLevel id=14
request tools/call id=15
request tools/call id=16
```

Count the replies. There is one fewer than there are requests; find which id has none:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson02 | head -1)
$ python3 -m tap.show "$run/trace.jsonl" | grep -c '<-  response'
```

<!-- expect -->
```text
16
```

Now read the whole run with explanations: a note after every frame, from
[the walkthrough](../walkthrough/02-raw-client-tour.md). `--explain` exits non-zero if a frame has
no note:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson02 | head -1)
$ python3 -m tap.show "$run/trace.jsonl" --explain docs/walkthrough/02-raw-client-tour.md > /dev/null && echo "every frame has a note"
```

<!-- expect -->
```text
every frame has a note
```

Run the same command without the redirect and read every note against your prediction.

## Read the source

The client is three small files and a tour. Read them in this order:

- `client/wire.py`, the function `classify`: a line is a response, a request or a notification by
  its shape, never by its id alone. That is the answer to Predict 3. Then `Wire._complete`: a
  response completes only the pending request with the same id *and the same type*, so `1` is not
  `"1"` and not `true`. Each function says in its docstring which rule of the spec it implements,
  in the citation form you know from lesson 01, for example
  `spec:docs/specification/2025-11-25/basic/index.mdx:69` "MUST** include the same ID".
- `client/session.py`: `Session.initialize` (the version check and the `initialized` notification),
  `Session._require_ready` (no request before `initialized`), `Session.cancel` and
  `Session.close` (stdin first, then `SIGTERM`, then `SIGKILL`).
- On the server side, follow one request, the tour's `tools/call echo`, from the pipe to the
  handler and back: the source tour at the top of
  [the walkthrough](../walkthrough/02-raw-client-tour.md).

## Experiments

Manual mode is the client without the script: it initializes, then sends exactly the lines you type.
A line that starts with `{` is sent as it is, with nothing added or fixed; `:req <method> [<params>]`
builds a request with the next id; `:note <method> [<params>]` builds a notification. The
outcomes below were **measured against the pinned server** when this lesson was written; they are
what the server did, not what the spec promises, and the commands here fail if a future pin changes them.

**1. Leave out `"jsonrpc": "2.0"`.** Send a ping by hand without the version field, then an
ordinary one. Which gets an answer?

<!-- run -->
```console
$ printf '%s\n' '{"id":50,"method":"ping"}' ':req ping' | scripts/record.sh --client manual lesson02-nojsonrpc > /dev/null 2>&1
$ run=$(ls -dt runs/*-lesson02-nojsonrpc | head -1)
$ python3 -m tap.show "$run/trace.jsonl" | grep -o 'response id=[0-9]*'
```

<!-- expect -->
```text
response id=0
response id=1
```

Measured: the server never answers id 50. It does not reject the line with an error either: the
message fails the server's own validation, which it reports on its stderr (look in the run's
`stderr.txt`), and it carries on with the next line. The spec's rule is that a request is a
JSON-RPC 2.0 object (`spec:docs/specification/2025-11-25/basic/index.mdx:37` "jsonrpc: \"2.0\""),
and the client that sends the broken one is left waiting; that is why a client needs timeouts (`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:248` "SHOULD** establish timeouts").

**2. Ask for a method the server does not have.**

<!-- run -->
```console
$ printf '%s\n' ':req nonsense/method' | scripts/record.sh --client manual lesson02-nomethod > /dev/null 2>&1
$ run=$(ls -dt runs/*-lesson02-nomethod | head -1)
$ python3 -m tap.show "$run/trace.jsonl" | grep -o 'error id=[0-9]* code=-*[0-9]*'
```

<!-- expect -->
```text
error id=1 code=-32601
```

Measured: this time the server answers, with an error response under the request's id, code
`-32601`, method not found. The raw client does the same thing when the *server* sends it a
request it does not handle: `Wire._refuse` answers with `-32601` under the server's own id.

**3. Change the client, predict the trace.** In `client/tour.py`, change the `message` the tour
sends to `echo`, and the text the tour expects back. Before you run `scripts/record.sh --client tour`
again, predict which frames of the trace change and which do not. Then check with `tap.show --full`.

## Check yourself

Answer from your own trace, then open the answers.

1. Which request got no reply, and why does the client stop waiting for it?
2. After that cancel, the server still sends one more progress notification. What does that tell
   you about what a cancellation can promise?
3. Why does the client give `initialize` id 0 and the `ping` id 1 and not the other way round?
4. What does `tap.check` do with a frame whose `method` the schema does not know?
5. In experiment 1, who was at fault, and who paid for it?

<details>
<summary>Answers</summary>

1. Id 16, the second long-running call. The client sent `notifications/cancelled` for it after the
   first progress notification and stopped waiting; the server sent no reply for it.
2. Nothing beyond "ask politely": the spec says receivers SHOULD stop, and this server's tool never
   checks, so it finishes its work. The client must not rely on the work stopping, only on its
   own decision to stop waiting.
3. Ids are allocated from 0 in send order, and `initialize` is the first message of the lifecycle,
   so it is the first request.
4. It reports the frame as `unknown method`, never as valid: a check that passes what it does not
   understand proves nothing.
5. The client: it left out a required field, the server correctly refused to treat the line as a
   request, and the client was left waiting for an answer that was never coming.

</details>
