# Lesson 07: the same messages over HTTP

## Goal

See what the HTTP transport adds on top of the messages you already know, by recording it on the
wire: one POST per client message; a reply that is one JSON body or an event stream, and why; the
session id that turns separate POSTs into one 2025-era session; the GET stream that carries what the
server says unprompted; and the status codes and headers that carry protocol rules (`202`, `404`,
`406`, `MCP-Protocol-Version`). You run the raw client's HTTP tour through the tap's HTTP mode and
read the trace with `tap.show`; the 2026-07-28 revision, which drops sessions and the GET stream,
is explained in the walkthrough.

Setup, once: `scripts/bootstrap.sh` (see the README). Everything below runs from the repo root.
Lessons 02 and 03 come first: this one assumes you know requests, replies, server requests and
how the raw client matches replies to requests by id. Nothing here is new at the JSON-RPC level,
and that is the point.

One safety fact, because it shapes the setup: the pinned server, given a port, listens on **every**
network interface. So a recording never gives it one. The tap starts the server on a Unix socket in
a private directory and listens on `127.0.0.1` only; the client talks to the tap.

## Predict

Before you run anything, write down:

1. In lesson 01 the server's reply to `initialize` was one line on a pipe. Over HTTP the client
   POSTs the same request. What are the two shapes the server may answer a request with, and what
   would you expect to see in the trace if it chooses the longer one?
2. The client sends `notifications/initialized` and, later, its answers to the server's requests.
   Neither has a reply. What does the server send back to a POST like that?
3. After the handshake the server wants to ask the client for its roots, and nobody has asked the
   server anything. Which HTTP exchange can carry that request, and who has to open it?
4. The client gives up on a long call. What must it do on the HTTP connection, besides sending
   `notifications/cancelled`?

## Run

The HTTP tour declares `roots` and `sampling`, opens the GET stream before `initialized`, calls
`echo`, calls the sampling tool (whose server request arrives on the call's own stream), starts a
long-running call and cancels it after its first progress, and closes with a DELETE.
`scripts/record.sh --http --client http-tour` runs it with the tap in HTTP mode between the client
and the pinned server, into your own `runs/` folder (git-ignored):

<!-- run -->
```console
$ scripts/record.sh --http --client http-tour lesson07
```

<!-- expect -->
```text
recorded: runs/
```

The run exits 0 only if every step saw what the transport predicts: `200` `text/event-stream` for a
request, `202` for a notification or a reply, `200` for the DELETE.

## Read the trace

First, ask the schema whether every JSON-RPC message of the session is valid. HTTP adds no frames of
its own: heads, priming events and stream ends are `tap` records, so the checker reads only the
bodies:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson07 | head -1)
$ python3 -m tap.check "$run/trace.jsonl" --revision 2025-11-25
```

<!-- expect -->
```text
check: ok (19 frames)
```

Now the exchanges. `tap.show` prints a summary after each HTTP record and `#<n>` after each frame,
where `n` numbers the HTTP exchange (one request and its response). Eleven exchanges carried
nineteen messages. Count the statuses; the `202`s are the messages that needed no answer:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson07 | head -1)
$ python3 -m tap.show "$run/trace.jsonl" | grep -o 'tap http-response #[0-9]* [0-9]*' | awk '{print $4}' | sort | uniq -c | awk '{print $2 " x" $1}'
```

<!-- expect -->
```text
200 x7
202 x4
```

Seven `200`s: the five POST requests, the GET stream and the DELETE. Four `202`s: `initialized`, the
client's answer to `roots/list`, its answer to `sampling/createMessage`, and `notifications/cancelled`.
Now who ended each event stream. Five streams ended `by server`; one ended `by client`, which is
the cancelled call:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson07 | head -1)
$ python3 -m tap.show "$run/trace.jsonl" | grep -o 'tap http-end #[0-9]* by [a-z]*' | awk '{print $5}' | sort | uniq -c | awk '{print $2 " x" $1}'
```

<!-- expect -->
```text
client x1
server x5
```

Look for the one thing no pipe has: the **session id**. It appears once, in the `initialize`
response, and after that in every request header:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson07 | head -1)
$ python3 -m tap.show "$run/trace.jsonl" | grep -o 'tap http-response #0 .*'
```

<!-- expect -->
```text
tap http-response #0 200 content-type=text/event-stream mcp-session-id=
```

Now read the whole run with explanations: a note after every record, from
[the walkthrough](../walkthrough/07-streamable-http.md). The walkthrough also follows one POST
through the server's source and explains the 2026-07-28 shape. `--explain` exits non-zero if a
record has no note:

<!-- run -->
```console
$ run=$(ls -dt runs/*-lesson07 | head -1)
$ python3 -m tap.show "$run/trace.jsonl" --explain docs/walkthrough/07-streamable-http.md > /dev/null && echo "every record has a note"
```

<!-- expect -->
```text
every record has a note
```

Run the same command without the redirect and read every note against your predictions.

## Read the source

- `client/http_wire.py`, `HttpWire._write`: a message the wire writes is one POST; the response is
  read on a new thread, so a long stream never blocks the next send. That is the whole difference
  from lesson 02's `Wire`: classification, ids and the pending table are `client/wire.py`, untouched.
- `HttpWire._receive` and `_refused`: `202` has nothing to read; `200` is a JSON body or a stream
  whose events each go to the same line handler as a pipe's lines; any other status fails the
  request at once (or, if the body is a JSON-RPC error with an id, is that request's error).
- `HttpSession.initialize`: the GET stream opens between the `initialize` result and
  `notifications/initialized`. Move it and the server's `roots/list` is lost (experiment 1).
- `HttpWire.abandon`: cancelling closes the connection carrying the request's stream.
- `tap/http.py`, `SseParser` and `ProxyHandler.pump_stream`: how an event stream becomes one frame per
  event, and why the tap forwards each piece as soon as it is read.
- On the server side, `servers:src/everything/transports/streamableHttp.ts:195` "app.post(\"/mcp\", async (req: Request, res: Response) => {"
  is the one endpoint, and `servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:704` "async handlePostRequest(req, options)"
  is where a POST becomes a `202`, an event stream or an error; the walkthrough's source tour follows one
  POST through both.

## Experiments

The outcomes below were **measured against the pinned server** when this lesson was written; they
are what the server did, and the commands here fail if a future pin changes them.

**1. Leave the GET stream out.** `--no-stream` skips it. The server's `roots/list` request, which
only that stream can carry, never arrives, and the tour says so. The block starts the tap and the
server by hand (as `scripts/record.sh` does), runs the tour, and stops them; its trace goes to a
temporary folder:

<!-- run -->
```console
$ dir=$(mktemp -d)
$ port=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
$ python3 -m tap --trace "$dir/trace.jsonl" --http "$port" -- node vendor/servers/src/everything/dist/index.js streamableHttp 2> "$dir/stderr.txt" &
$ tap_pid=$!
$ for _ in $(seq 1 200); do grep -q 'tap: listening' "$dir/stderr.txt" && break; sleep 0.1; done
$ python3 -m client.http_tour --url "http://127.0.0.1:$port/mcp" --no-stream | grep 'roots/list'
$ kill -INT "$tap_pid"
$ wait "$tap_pid"
$ rm -r "$dir"
```

<!-- expect -->
```text
roots/list (server asked)                  never arrived: no GET stream was open
```

Measured: with no stream open the server drops what it sends unprompted
(`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:947` "if (standaloneSse === void 0) return;"), so the roots sync and the list-change
notifications are lost, and the rest of the tour still passes. Now move the stream by hand: in
`client/http_wire.py` make `HttpSession.initialize` open it after `notifications/initialized`
instead of before. Predict what changes in the trace, run the tour, and undo with
`git checkout client/http_wire.py`.

**2. Compare two recordings.** The session id and every SSE event id are new on every run; the
messages are not. Record the tour twice, count the distinct session ids across both runs, and
compare the sorted message lines with the exchange numbers and timings stripped:

<!-- run -->
```console
$ scripts/record.sh --http --client http-tour lesson07a > /dev/null
$ scripts/record.sh --http --client http-tour lesson07b > /dev/null
$ a=$(ls -dt runs/*-lesson07a | head -1)
$ b=$(ls -dt runs/*-lesson07b | head -1)
$ cat "$a/trace.jsonl" "$b/trace.jsonl" | grep -o '"mcp-session-id": *"[0-9a-f-]*"' | sort -u | wc -l
$ msgs() { python3 -m tap.show "$1" | grep -- '->  \|<-  ' | sed -E 's/^ *[0-9]+ +[0-9.]+ ms +//; s/ \(answers[^)]*\)//; s/ #[0-9]+$//' | sort; }
$ diff <(msgs "$a/trace.jsonl") <(msgs "$b/trace.jsonl") && echo "same messages"
```

<!-- expect -->
```text
2
same messages
```

**3. The same `initialize` result, other framing.** Lesson 01's handshake fixture over stdio and the
HTTP tour ask different questions but get the same `initialize` result. Record the fixture, then
compare the decoded result with the HTTP tour's, and the byte counts of the two frames. The stdio
frame is one byte longer: it ends with the newline that frames it on a pipe; the HTTP body has none.

<!-- run -->
```console
$ scripts/record.sh tests/fixtures/handshake-2025.ndjson lesson07h > /dev/null
$ python3 - "$(ls -dt runs/*-lesson07h | head -1)" "$(ls -dt runs/*-lesson07 | head -1)" <<'PY'
import json, sys
def reply(run):
    for line in open(f"{run}/trace.jsonl"):
        rec = json.loads(line)
        if rec["dir"] == "s2c" and isinstance(rec.get("json"), dict) and rec["json"].get("id") == 0:
            return rec
stdio, http = reply(sys.argv[1]), reply(sys.argv[2])
print("same result:", stdio["json"]["result"] == http["json"]["result"])
print("stdio frame is longer by", stdio["bytes"] - http["bytes"], "byte")
PY
```

<!-- expect -->
```text
same result: True
stdio frame is longer by 1 byte
```

## Check yourself

Answer from your own trace, then open the answers.

1. How many `Mcp-Session-Id` headers does the client send before the `initialize` response, and how
   does it learn the id?
2. Which exchange carries the server's `roots/list`, and which carries its `sampling/createMessage`?
   Why are they different?
3. The tap forwards each event as soon as it reads it. What would break in the sampling call if it
   forwarded a response only when it had ended?
4. In the trace of the cancelled call, which HTTP record shows the client closed the connection,
   and is there a response frame for it?
5. After the DELETE, which stream ends, and what would a POST with the old session id get?
6. Why does the recording give the server a Unix socket instead of a port?

<details>
<summary>Answers</summary>

1. None: the `initialize` request carries neither the session id nor the protocol version, because
   the session does not exist yet. The id arrives in the `initialize` response's `mcp-session-id`
   header (`tap http-response #0`), and every later request, the GET and the DELETE carry it.
2. `roots/list` is a frame of the GET exchange: nothing the client sent is waiting for it, so only
   the standalone stream can carry it. `sampling/createMessage` is a frame of the `tools/call`
   exchange that caused it: a request-related server message travels on the request's own stream.
3. A deadlock. The server's sampling request is in the stream's first events and the client
   answers it with a new POST, while the stream stays open waiting for that answer. If the tap held
   the stream until its end, the client would never see the request and never answer it.
4. The `http-end` record of the long call's exchange says `by client`. There is no response frame: the server never answers a cancelled
   request, and without the closed connection its stream would stay open with only keepalives.
5. The GET stream ends `by server`, before the DELETE's own response is read. A POST with the old
   session id would get `404` (`servers:node_modules/@modelcontextprotocol/server/dist/index.mjs:636` "Session not found").
6. Given a port, the pinned server listens on all interfaces. A socket in a directory only the
   tap's user can enter exposes it on no network interface at all.

The *Predict* answers:

1. One JSON object, or an event stream. Over a stream you would see `text/event-stream` in the
   response head, an empty-data priming event first, then the response as one event, and the stream
   ending. This server always chooses the stream.
2. `202 Accepted` with no body: there is nothing to answer.
3. The GET stream, which the client must open itself: a server cannot start an exchange with a
   client, so the client keeps one request open for it.
4. Close the connection that carries the request's stream. Without it the server's stream for the
   call stays open until the session ends.

</details>
