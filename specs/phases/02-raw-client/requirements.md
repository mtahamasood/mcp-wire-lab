# Phase 2 — Raw client, 2025 era, client-initiated: requirements

Lean profile (LP1–LP6 in `mission.md`; register row 2026-10-21, lean profile). Phase 1's
decisions D1–D16 stand unless amended here. Facts about the pinned server below were read
from the pinned source on 2026-10-21; the walkthrough cites them with G8 citations, this
spec does not.

## Learning objective

Speak MCP with no library: frame JSON-RPC over stdio, correlate replies by id, run the
2025 lifecycle, and use every client-initiated request the server offers, so that the
owner can explain, change and debug every byte the client sends.

## Scope

In: the raw client package `client/` (D1–D4), scripted and manual modes (D3, D4),
recording it through the tap (D5), the schema check `tap.check` (D6), gate G12 (D7),
walkthrough, one source tour and lesson 02 (D8). Out: answering server-initiated requests
beyond a refusal (phase 3); the 2026-07-28 era (phase 6); HTTP (phase 7); the atlas (L8,
G10; deferred by the lean profile).

### D1 — Framing and correlation

`client/wire.py` runs the server command as a child process and speaks newline-delimited
JSON-RPC 2.0 over its stdin and stdout, one compact UTF-8 JSON object per line, no
embedded newline (spec, stdio transport). The child's stderr is passed through to the
client's stderr, never parsed. One reader thread classifies each incoming line:

- a **response** (has `id`, has `result` or `error`, has no `method`) completes the
  pending request with that exact `id` (same JSON type and value; `1` and `"1"` differ);
- a **server request** (has `method` and `id`) goes to the request handler; in phase 2
  the only handler replies with error `-32601` (method not found) and the same `id`;
- a **notification** (has `method`, no `id`) goes to a notification queue the caller can
  read and print;
- anything else (not JSON, not an object, a response with an unknown `id`) is reported
  on the client's stderr and otherwise ignored.

Request ids are integers allocated from 0, in send order. A request waits for its
response up to a per-call timeout (default 30 s) and raises an error carrying the
JSON-RPC error object when the reply is an error. Writes are serialised by one lock.
The server's own request ids start at 0 too, so the classification above, not the id
alone, decides what a line is; this is the phase's central correctness claim.

*Source:* stakeholder asks A2 and A3, 2026-10-20 (raw client, no SDK); register row
2026-10-20 (client language: Python).

### D2 — The 2025 lifecycle

`client/session.py` performs `initialize` with `protocolVersion` `2025-11-25`, the
client's capabilities (default `{}`) and `clientInfo` `{"name":"wire-lab-raw","version":"0.2.0"}`;
checks that the reply's `protocolVersion` is one the client speaks (`2025-11-25`,
`2025-06-18`, `2025-03-26`) and stops with a clear error otherwise; then sends
`notifications/initialized`; and only then lets other requests through (a request
before that raises without sending). Shutdown follows the stdio lifecycle: close the
child's stdin, wait up to 2 s, then SIGTERM, wait up to 2 s, then SIGKILL; the child's
exit status is returned. Cancellation sends `notifications/cancelled` with the pending
request's `requestId` and an optional `reason`, and stops waiting for that request; a
late reply to it is dropped and reported on stderr. A request that times out is cancelled the same way (reason `timeout`) and forgotten. After end of input from the server, or after the client closes the wire, every pending and every new request fails at once with `OSError` (amended by register row 2026-10-21, phase 2 review).

*Source:* stakeholder asks A2 and A3, 2026-10-20; roadmap.md phase 2 row; amended by register row 2026-10-21, phase 2 review.

### D3 — The scripted tour

`python3 -m client tour -- <server command…>` runs, in order and printing one line per
step: `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`
(`echo`, then `get-sum`), `resources/list`, `resources/templates/list`, `resources/read`
(one static document), `resources/subscribe` and `resources/unsubscribe` of that
document, `prompts/list`, `prompts/get` (`simple-prompt`, then `args-prompt` with a
city), `completion/complete` (the `department` argument of `completable-prompt`),
`logging/setLevel` (`debug`), a `tools/call` of `trigger-long-running-operation` with a
`progressToken` and a short duration that completes, the same call again cancelled after
its first progress notification, and shutdown. Every notification received is printed as
it arrives. The tour avoids the server's timer tools (`toggle-*`) so its trace's message
sequence is the same on every run; content that changes (timestamps, random values) does
not change the sequence. The tour exits 0 only if every step got the reply it expects.

*Source:* stakeholder ask A2, 2026-10-20; roadmap.md phase 2 row (L2).

### D4 — Manual mode

`python3 -m client manual -- <server command…>` initializes as D2, then reads lines from
its stdin: a line that is a JSON object is sent as is, except that a missing `"jsonrpc"`
is not added and a missing `id` is not added (the learner sends exactly what they type,
mistakes included); `:req <method> [<json params>]` builds and sends a request with the
next id; `:note <method> [<json params>]` sends a notification; `:quit` shuts down. Each
reply and notification is printed as one JSON line prefixed `<-`, each sent line as `->`.
End of input shuts down as `:quit` does.

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap
L9).

### D5 — Recording a client run

`scripts/record.sh --client <tour|manual> [name]` records the raw client through the tap
into a new run folder with the same allowlisted server environment as a fixture
recording (phase 1 D14): the client runs `python3 -m tap --trace … -- env -i … node
<server> stdio` as its server command. In `manual` mode the script's stdin goes to the
client. The fixture form `scripts/record.sh <fixture> [name]` is unchanged. Output lines
are the same `recorded:` and `read it:` lines.

*Source:* A5, 2026-10-20; owner decision, 2026-10-20 — registered in mission.md (A4,
delegated; roadmap L16).

### D6 — The schema check

`python3 -m tap.check <trace> --revision 2025-11-25` validates every frame of a trace
against `vendor/spec/schema/<revision>/schema.json` with a stdlib validator that
implements exactly the keywords P8 lists and fails loudly (exit 2, naming the keyword) on
any other keyword it meets. Each frame is checked against the definition that names it:
a request or notification by its `method` (the definition whose `method` is that
`const`), a response by the method of the request it answers (paired by direction and
`id`, as `tap.show` pairs them) to that method's result definition, and an error
response to `JSONRPCErrorResponse`. A frame with no matching definition is reported as
`unknown method`, not as valid. Output: one line per failing frame with its `seq`, the
JSON path that failed and the definition; exit 0 when no frame fails, 1 otherwise. The
tour's fresh trace must pass; tap events, stderr records and `partial` frames are
skipped.

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap
L7; P8).

### D7 — Gate G12

`tools/check_claims.py`, run by `scripts/gate.sh` as G12 after G11: for each phase
directory numbered 02 or later that has a `validation.md`, each row of its section C
table must name at least one check in the form LP2 fixes, and each named item must exist:
a `tests/<file>.py::<Class>::<method>` as that method defined in that class of that file
(found by parsing the file with `ast`), any other named path as a file or directory.
Failures print `claims: <phase> <row>: <reason>`. Phase 1 is not checked. G12's row in
`tech-stack.md` becomes implemented.

*Source:* register row 2026-10-21, review profile (RP5, G12); register row 2026-10-21,
lean profile (LP2).

### D8 — Walkthrough, source tour, lesson 02

`docs/walkthrough/02-raw-client-tour.md` has one note per frame of the tour's fresh trace
(phase 1 D11 anchors; checked by `tap.show --explain` in `tests/test_e2e.py`), each
citing the spec section that governs the message (G8). It contains one source tour
(L13, cut to one request by the lean profile): the tour's `tools/call echo` traced
through the pinned server from the stdio transport to the echo handler and back, every
hop a verified citation. Each function in `client/` that builds, sends or classifies a
message carries a verified spec citation in its docstring (L2); G8 scans `client/`.
`docs/lessons/02-raw-client.md` has the L1 sections, records the tour with
`scripts/record.sh --client tour` and validates it with `tap.check` in runnable blocks
(G9), and `README.md` lists it.

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap
L1, L2, L3, L13); per-phase walkthrough P3.

## Build order (LP3: vertical slice first)

1. G12 (`tools/check_claims.py`) with its tests, wired into `gate.sh`.
2. Slice: `client/wire.py` + `client/session.py` with unit tests against fake servers in
   `tests/fake_servers/`; a tour of initialize, initialized, one `tools/call echo`,
   shutdown, recorded by `record.sh --client tour` against the real server.
3. Widen the tour to D3's full list; cancellation; manual mode.
4. `tap.check` with unit tests and the tour trace passing it.
5. Walkthrough, source tour, lesson 02, README; `pyproject.toml` mypy `files` and G8's
   scanned paths gain `client`.
6. Review round (LP4): an Opus reviewer on the phase diff, reproduced blockers and majors
   fixed, the rest to *Accepted limits*. Close: Result, CHANGELOG, tag `lesson-02`.

Builder: Sonnet, medium. Reviewer: Opus, high. Review budget: one round, at most about a
third of the phase's commits (RP6).

## Stop condition

Every C row in `validation.md` passes, the gate (G1–G5, G7–G9, G11, G12) is green locally
and in CI, and the tour's fresh trace passes `tap.check` and `--explain`.
