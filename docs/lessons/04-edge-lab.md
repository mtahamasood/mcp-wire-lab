# Lesson 04: the edge lab

<!-- exercises: initialize, notifications/initialized, ping, tools/list -->

## Goal

Learn the protocol's contract from its error paths. For a malformed or out-of-order message you
predict the server's reply from the spec, record it, and then work out where the server follows the
spec, where it is stricter or looser, and where the spec says nothing. Then break the wire itself:
make the tap lose or delay a message and watch what a client without a timeout does.

Setup, once: `scripts/bootstrap.sh` (see the README). Lesson 01 comes first: you need to be
able to read a trace. Everything below runs from the repo root.

## Predict

Write down answers before you run anything:

1. A request for a method that does not exist. Does the server answer with a result, an error,
   or nothing? If an error, which code?
2. A JSON array of two requests on one line (a JSON-RPC batch). Two replies, one error, or
   silence? And does the connection survive?
3. A message with no `"jsonrpc"` member. Same three choices.
4. You drop a request at the tap so the server never sees it. What does the client see, and
   how long does it wait?

## Run

Two edge fixtures, recorded with the same script as lesson 01. Each one does the normal handshake
and then breaks exactly one rule. The first sends the unknown method `does/not/exist`:

<!-- run -->
```console
$ run=$(scripts/record.sh tests/fixtures/edge-unknown-method.ndjson lesson04-unknown | sed -n 's|^recorded: \(.*\)/trace.jsonl$|\1|p')
$ python3 -m tap.show "$run/trace.jsonl" | grep -o 'error id=1 code=-32601'
```

<!-- expect -->
```text
error id=1 code=-32601
```

The second sends the batch array of two requests, then a plain `ping`. Some messages get no
reply by design, so the fixture marks them for the driver (`"_drive"`, see the walkthrough) and the
driver waits a fixed time instead of waiting for an id. Which replies did you get?

<!-- run -->
```console
$ run=$(scripts/record.sh tests/fixtures/edge-batch-array.ndjson lesson04-batch | sed -n 's|^recorded: \(.*\)/trace.jsonl$|\1|p')
$ python3 -m tap.show "$run/trace.jsonl" | grep -o 'response id=[0-9]'
```

<!-- expect -->
```text
response id=0
response id=3
```

Only the handshake and the lone `ping` (id 3) were answered. The two requests inside the array, ids
1 and 2, got no reply at all. `scripts/record.sh` will also print, on stderr (so the `sed` above does
not see it), that the run ended with exit code 1: that is the server reporting a transport error,
and it is the last record in your trace.

## Read the trace

Read each recording with its notes. The walkthrough has one section per experiment, so name it
after a `#`:

```console
python3 -m tap.show runs/<your-unknown-method-run>/trace.jsonl --explain docs/walkthrough/04-edge-lab.md#unknown-method
python3 -m tap.show runs/<your-batch-run>/trace.jsonl --explain docs/walkthrough/04-edge-lab.md#batch-array
```

Every note ends with a verdict: *follows the spec*, *stricter*, *looser* or *spec silent*. Compare
the verdicts with your predictions. The batch run also has a long stderr stream: that is the
server explaining on its own log channel what it refused, and it is the only place the client could
have learned it.

## Read the source

Where a verdict says *follows the spec*, find the rule. The error code the server used is defined in
the schema: `spec:schema/2025-11-25/schema.ts:175` "METHOD_NOT_FOUND = -32601". The reason the batch
got no reply is that the server's message parser rejected the array before any handler saw it, and
the server's hook prints the failure and records it in the exit status:
`servers:src/everything/transports/stdio.ts:66` "process.exitCode = 1;". The parser itself
is in the SDK, which the lockfile fixes at 2.3.1 but which is not a submodule here, so its lines are
not cited. Open both files at those lines.

## Experiments

The other five experiments are fixtures in `tests/fixtures/`. Each has a fixture to record and a
section name to read it with (the name after the `#` in `--explain`; they are not the same word):

| Fixture to record | Section for `--explain ...04-edge-lab.md#` |
| --- | --- |
| `edge-missing-jsonrpc` | `missing-jsonrpc` |
| `exp-list-first` (the before-`initialize` experiment) | `before-initialize` |
| `edge-duplicate-id` | `duplicate-id` |
| `edge-string-id` | `string-id` |
| `edge-notification-with-id` | `notification-with-id` |

Pick one, predict, record, then read it against its section in
[the walkthrough](../walkthrough/04-edge-lab.md). (The walkthrough also has notes for an
oversized frame, a 1 MiB `tools/call`; `tests/test_e2e.py` generates that one, so it is not an
experiment you can pick.) A wrong section name prints the names the file does have.

**The fault run: lose a message.** The tap can misbehave on request. `--drop c2s:tools/list`
stops the first `tools/list` request at the tap: it is recorded as a frame, so you can see it
arrived, but it is never forwarded to the server. The driver is a client with no way to give up
on a request except its timeout, which this run sets to three seconds:

<!-- run -->
```console
$ mkdir -p runs
$ python3 tests/drive.py tests/fixtures/handshake-2025.ndjson --timeout 3 -- python3 -m tap --trace runs/lesson04-fault.jsonl --drop c2s:tools/list -- node vendor/servers/src/everything/dist/index.js stdio 2>&1 >/dev/null | grep 'no response' || true
```

<!-- expect -->
```text
drive: no response with id 1 within 3.0s
```

(The driver exits 1 when a reply never comes; the `|| true` only keeps the lesson check going.)
The reply never comes because the server never saw the request; nothing in the protocol tells the
client that. What the trace says is that the tap dropped it:

<!-- run -->
```console
$ grep -o '"event": "fault", "kind": "drop"' runs/lesson04-fault.jsonl
```

<!-- expect -->
```text
"event": "fault", "kind": "drop"
```

The fault record names the dropped frame by `seq` and says it was not forwarded; the
frame itself is recorded just before it. The spec expects a client to bound its waiting:
`spec:docs/specification/2025-11-25/basic/lifecycle.mdx:248` "SHOULD** establish timeouts for all sent requests" (the fixture driver's
`--timeout` is exactly that), and after a timeout to tell the server to stop with
`notifications/cancelled`; a server may ignore a cancellation for a request it never saw
(`spec:docs/specification/2025-11-25/basic/utilities/cancellation.mdx:42` "The referenced request is unknown").

Try the other fault yourself: `--delay s2c:2000` holds every server frame for two seconds
after recording it, so the printed reply latencies stay small. Look instead at the time column:
the next client frame arrives about two seconds after the reply, and a "tap fault" row follows
each reply. Which part of a delayed run is the tap and which is the server? With `--timeout 1` the same fixture fails: a slow server and a
lost message look the same to a client.

## Check yourself

1. Why does `edge-unknown-method` get an error reply while `edge-batch-array` gets none for the
   array, although both are things the spec does not allow a server to do anything useful with?
2. In the `edge-duplicate-id` run, what does a client that tracks requests by id alone do wrong?
3. In the fault run, which record proves the request reached the tap, and which proves it did not
   reach the server?
4. A request is silently lost. Name two things a client should have set up before it happens.

<details>
<summary>Answers</summary>

1. A well-formed request for an unknown method is a request: the server can attach an error to its
   `id`. An array is not a valid message at all, so the parser throws before any id is read and
   there is nothing to reply to; the failure goes to stderr and the exit status instead.
2. It cannot tell the two replies with `id` 1 apart; only content and order do. The server answered
   both rather than refusing the reused id, so the client must not reuse ids.
3. The `c2s` frame record for `tools/list` proves it arrived at the tap; the `fault` record with
   its `frame_seq` and `"forwarded": false` proves it went no further.
4. A timeout on every request, and the means to send `notifications/cancelled` (and to ignore a
   late reply) when the timeout fires.

</details>
