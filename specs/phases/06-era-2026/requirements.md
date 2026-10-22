# Phase 6 — 2026-07-28 era, both clients (stdio): requirements

**Status: specified in full, awaiting owner approval** (lean profile, LP1–LP6 in `mission.md`;
register row 2026-10-22, phases 5–7 un-stubbed; approved as one batch with phases 5 and 7
before any test or code). Phases 1–4 decisions stand unless amended here. Phase 5's SDK client
is assumed as listed in *What this phase needs from phase 5*. The spec is in two parts: **Part
A, the raw client** (D1–D10), and **Part B, the SDK client** (D11–D13). Part B can be dropped
(a register row and one *Accepted limits* line) without changing anything in Part A.

## Learning objective

Understand what changed between the 2025 era and 2026-07-28 by speaking both from one client:
discovery instead of a handshake, a `_meta` envelope on every request instead of a session,
input requests carried in results instead of server-to-client requests, a subscription stream
instead of `resources/subscribe`, and tasks as an extension, so that the owner can explain,
change and debug every byte the client sends in the new era and say what each 2025 message
became.

## Recon (measured 2026-10-22, pinned server and SDK, stdio)

Measured by driving the built pinned server with a throwaway stdlib script and with
`@modelcontextprotocol/client` 2.3.1 from the server's own `node_modules`, through the tap,
traces kept under the session's temporary directory (never in the repository). The stub was
written without this recon; where it disagrees, this section wins.

- **Era choice.** The server's stdio entry hands its factory to the SDK's `serveStdio`
  (`vendor/servers/src/everything/transports/stdio.ts:49`); the client's *first message* pins
  the connection's era (SDK `classifyOpeningMessage`, `@modelcontextprotocol/server`
  `dist/stdio.mjs:235`): `initialize` without an envelope → 2025 era; any request whose
  `params._meta` carries `io.modelcontextprotocol/protocolVersion` → 2026-07-28. There is no
  `initialize` and no `notifications/initialized`. Opening with `tools/call` plus an envelope
  (no `server/discover`) also works.
- **`server/discover`** returns `resultType: "complete"`, `supportedVersions: ["2026-07-28"]`,
  `capabilities` (tools, prompts, resources with `subscribe` and `listChanged`, `logging`,
  `completions`, `extensions: {"io.modelcontextprotocol/tasks": {}}`), `instructions`,
  `ttlMs` 300000, `cacheScope` `public`, and `_meta["io.modelcontextprotocol/serverInfo"]`.
  A discover claiming version `2099-01-01` gets `-32022` with `data.supported`.
- **Envelope.** A request without `_meta` gets `-32602`; without `clientCapabilities`,
  `-32602`. Every result carries `resultType`; the list results and `resources/read` add
  `ttlMs`/`cacheScope`. The tool list is the same 22 tools whatever the declared
  capabilities (the capability-gated and task tools are listed up front; the `toggle-*` tools
  are absent). Looser than the spec: once the era is pinned, a later request claiming
  `2025-11-25` in its envelope is served.
- **Removed methods.** `ping`, `logging/setLevel`, `resources/subscribe` → `-32601`.
  `initialize` on a 2026-pinned connection → `-32022`, and the server process later exits 1.
- **Logging and progress.** `trigger-log-messages` sends no `notifications/message` without
  `io.modelcontextprotocol/logLevel`; with `warning` it sends 5 (warning..emergency), with
  `debug` 8. `progressToken` in `_meta` yields `notifications/progress` as in 2025. After
  `notifications/cancelled` the server still sends the remaining progress notifications and no
  response (the 2026 stdio binding says it MUST NOT send further messages for a cancelled
  request, `vendor/spec/docs/specification/2026-07-28/basic/transports/stdio.mdx:82`).
- **`subscriptions/listen`** with all four filter fields → `notifications/subscriptions/acknowledged`
  echoing the filter, `_meta["io.modelcontextprotocol/subscriptionId"]` = the listen request's
  id; `trigger-list-changed` (`list`: tools, prompts, resources) and `trigger-resource-update`
  deliver their notifications tagged with that id. `notifications/cancelled` for the listen id
  stops delivery; no listen response is sent then, nor when stdin closes.
- **Multi-round requests (MRTR).** `get-roots-list`, `trigger-sampling-request`,
  `trigger-elicitation-request` answer `resultType: "input_required"` with `inputRequests`
  (keys `roots`, `sampling`, `form`); a retry on a fresh id with top-level `inputResponses`
  completes. `trigger-multi-step-elicitation` takes three rounds and carries an opaque
  `requestState` (it embeds an expiry, so its bytes differ per run). Without the needed
  capability in that request's envelope: `-32021` with `data.requiredCapabilities`.
  `trigger-url-elicitation` needs a `url` argument.
- **Tasks (extension `io.modelcontextprotocol/tasks`).** Without the extension declared:
  `-32021`. `simulate-research-query` returns a task handle (`resultType: "task"`, `taskId`,
  `status: "working"`, `pollIntervalMs` 1000) and completes after 4 × 1000 ms by the clock;
  `tasks/get` reports status, `tasks/cancel` → `cancelled`. `trigger-sampling-request-async`
  returns a handle in `input_required` with `inputRequests`; `tasks/update` with
  `inputResponses`, then `tasks/get` → `completed` with the result. `tasks/list` → `-32601`.
  The pinned spec has **no schema** for the extension (only `docs/extensions/tasks/overview.mdx`).
- **Schema check.** `tap.check --revision 2026-07-28` loads the 2026 schema with no
  unimplemented keyword and all three envelope definitions. On a trace of all of the above,
  it fails 13 of 60 frames: the 3 `input_required` results (checked against `CallToolResult`,
  which requires `content`) and the 10 `tasks/*` frames (`unknown method`). The `-32021`
  error, the task handle (it carries `content: []`), the listen traffic and the envelope pass.
  The 2025-11-25 schema has no `InputRequiredResult`.
- **SDK client 2.3.1.** `versionNegotiation` defaults to `'legacy'`; `{ mode: { pin:
  "2026-07-28" } }` probes with `server/discover` (string id `server-discover-probe-1`) and then
  attaches the envelope to every request **and notification**. With the base
  `StdioClientTransport` the probe runs on a **second, short-lived process** spawned from the
  same command (`@modelcontextprotocol/client` `dist/index.mjs:2880`, `readStdioServerParams`);
  under `scripts/record.sh` both spawns write the same trace path and the tap truncates on
  open (`tap/__main__.py:136`), so the recorded trace would lack the discover. A trivial
  subclass of the transport probes in place: one process, discover on the trace (measured
  both). `listen()` uses string ids `listen:<n>`; MRTR is fulfilled automatically through the
  registered `setRequestHandler` handlers; a per-call `_meta` overrides the reserved keys
  (an empty `clientCapabilities` reproduces `-32021`); `onprogress` and `AbortSignal` give
  progress and cancellation. A `resultType: "task"` result is rejected with
  `UNSUPPORTED_RESULT_TYPE` (`dist/src-WCy6ifGf.mjs:3991`): the SDK client cannot use the
  tasks extension. Its 2026 trace passes `tap.check` except for its 2 `input_required` results.

## Scope

In, Part A (raw client): the era option and the 2026 session (D1–D4), subscriptions (D5), the
2026 tour (D6), a reduced tasks run (D7), manual mode in the new era (D8), recording (D9), the
schema check for the new era (D10's first half), walkthrough 06 with the era diff, lesson 06
and the atlas declaration (D10). In, Part B (SDK client): the SDK client's 2026 mode (D11), its
recording (D12), the raw-vs-SDK diff of the 2026 tour (D13).

Out, each with its reason:

- **Automatic fallback** (`discover` → `initialize` on a legacy server, stdio.mdx backward
  compatibility): the pinned server always answers `server/discover`, so the fallback branch
  could never appear in a recorded trace; the era is chosen by `--era`. Cut.
- **Task polling to completion**: `simulate-research-query` completes by the clock, so the
  number of `tasks/get` frames would vary per run and the walkthrough's notes could not cover
  every trace. The tasks run (D7) completes one task by `tasks/update` and cancels the other.
  Reduced.
- **Tasks in the SDK client**: SDK 2.3.1 rejects task results (recon). Cut, measured.
- **A schema for the tasks extension**: none is pinned; `tap.check` keeps reporting its frames
  as `unknown method` (D7, D10). Hand-writing one would present unpinned text as normative.
- **URL elicitation over MRTR, `ping`, `logging/setLevel`, `resources/subscribe` in a
  recorded tour**: the removed methods have no 2026 schema definition, so a tour sending them
  could not pass `tap.check`; they are shown in lesson 06's experiments through manual mode,
  and URL mode only in the era diff (it is phase 3's `decline` path, unchanged).
- **`server-tour` and `matrix` in the new era**: there are no server-to-client requests in
  2026-07-28 (stdio.mdx:55); their content moves into the tour's MRTR steps. `--era
  2026-07-28` with those modes is a usage error.
- HTTP (phase 7). A real LLM (non-goal in `mission.md`).

## Part A — the raw client

### D1 — One client, two eras

The era is a client option, not a second client: `python3 -m client <mode> [--caps <list>]
[--era 2025-11-25|2026-07-28] -- <server command…>`, the options in any order, default
`2025-11-25`, so every earlier command, test and lesson is unchanged. Modes in the new era:
`tour`, `tasks` (D7, 2026 only) and `manual`; `server-tour` and `matrix` with `--era
2026-07-28`, `tasks` without it, and any other era value print the usage on stderr and exit 2.
The wire (`client/wire.py`: framing, classification, id correlation, the write lock) and the
shutdown of `client/session.py` are reused unchanged; the new-era code is one new module,
`client/modern.py`, so the era diff isolates what the protocol changed.

*Source:* register row 2026-10-20 (both eras, the 2025 era first); roadmap.md phase 6 row;
register row 2026-10-22 (phases 5–7 un-stubbed).

### D2 — The per-request envelope

`client/modern.py` builds every request's params with one function, `envelope(params,
capabilities, *, log_level=None)`: a copy of `params` whose `_meta` holds
`io.modelcontextprotocol/protocolVersion` `"2026-07-28"`, `io.modelcontextprotocol/clientInfo`
(phase 2 D2's `CLIENT_INFO`, unchanged), `io.modelcontextprotocol/clientCapabilities` (the
capability object for the declared `--caps`, phase 3 D3's names; `{}` for none), and
`io.modelcontextprotocol/logLevel` only when given. Keys the caller put in `_meta` (for example
`progressToken`) are kept; the reserved keys are always the client's. Every request a
`ModernSession` sends goes through it, including retries (D4) and `subscriptions/listen` (D5),
because the server may not infer capabilities from earlier requests. Notifications
(`notifications/cancelled`) carry no envelope (`RequestMetaObject` is a request field). Phase
3's `capability_object` is reused unchanged; the tasks mode (D7) adds
`extensions: {"io.modelcontextprotocol/tasks": {}}` to it.

*Source:* stakeholder asks A2 and A3, 2026-10-20 (every byte on the wire, no SDK);
roadmap.md phase 6 row (`_meta` envelope).

### D3 — Discovery, the version check and result types

`ModernSession` (in `client/modern.py`, built on phase 2's `Session` and `Wire`) replaces the
handshake with `discover()`: it sends `server/discover` as its first request and lets no other
request through until the reply has arrived (a request before that raises without sending,
as phase 2 D2's "no request before initialized" does; stricter than the spec, which makes the
probe a SHOULD for a client that speaks both eras). A `DiscoverResult` whose
`supportedVersions` holds `2026-07-28` makes the session ready; any other version list, or a
`-32022` error, stops it with `UnsupportedVersion` naming the versions the server offered; any
other error stops it with a message that suggests `--era 2025-11-25`. No fallback is attempted
(scope).

Every result is classified by its `resultType`: `complete` (or absent, which the spec says to
treat as complete) → the result; `input_required` → handed to the caller as an input-required
outcome (D4); `task` → accepted only when that request declared the tasks extension (D7);
anything else → an `InvalidResult` error, since the spec makes an unrecognized `resultType`
invalid. A JSON-RPC error still raises phase 2's `RpcError`.

*Source:* stakeholder ask A2, 2026-10-20; roadmap.md phase 6 row (`server/discover`);
register row 2026-10-20 (both eras).

### D4 — Multi-round requests

`ModernSession.request_with_input(method, params, answer, max_rounds=5)` sends the request;
while the result is `input_required` it builds `inputResponses` with one entry per key of
`inputRequests` (the value is `answer(input_request)`), copies `requestState` byte for byte
when present (never parsed: the spec calls it opaque), and sends the same method and params
again with those two top-level fields, on a fresh id and with the full envelope. It returns the
`complete` result, raises after `max_rounds` rounds, and raises if `answer` cannot answer a key.
The default `answer` reuses phase 3's handlers unchanged: `Handlers.answer` on a synthetic
request built from the input request's `method` and `params` (canned sampling reply, form
elicitation from defaults, the configured roots, URL elicitation `decline`); an `error` reply
there means the client cannot answer. Each round is printed (`round <n>: <keys>`), so the
learner sees the loop phase 3's server requests became.

*Source:* stakeholder ask A2, 2026-10-20; roadmap.md phase 6 row (multi-round); mission.md
non-goal (no real LLM: canned replies).

### D5 — Subscriptions

`ModernSession.listen(filter)` sends `subscriptions/listen` with the `notifications` filter and
does not wait for its response (the response, if any, only marks a graceful end). It waits up
to 5 s for `notifications/subscriptions/acknowledged` whose
`_meta["io.modelcontextprotocol/subscriptionId"]` equals the listen request's id, type
included (phase 2 D1's id rule), and returns a `Subscription` holding that id and the
acknowledged filter. Notifications are routed to a subscription only by that `_meta` field,
never by arrival order or method, as the stdio binding requires; request-scoped notifications
(`notifications/progress`, `notifications/message`) carry no such field and stay on the
wire's queue as before. `Subscription.close()` cancels the listen request with phase 2's
`Session.cancel` (it sends `notifications/cancelled` with `requestId` = the listen id and stops
waiting), so a late listen response is dropped and reported.

*Source:* stakeholder ask A2, 2026-10-20; roadmap.md phase 6 row (`subscriptions/listen`).

### D6 — The 2026 tour

`python3 -m client tour --era 2026-07-28 -- <server command…>` declares `roots`, `sampling`
and `elicitation` (form) unless `--caps` says otherwise, prints one line per step as the
phase 2 tour does, and runs in order: `server/discover`; `tools/list`; `tools/call` `echo`, then
`get-sum`; `resources/list`; `resources/templates/list`; `resources/read` (the static document
of phase 2 D3, printing `ttlMs` and `cacheScope`); `prompts/list`; `prompts/get`
`simple-prompt`, then `args-prompt` with a city; `completion/complete` (`department`, `E`);
`tools/call` `trigger-log-messages` without a log level (expects no `notifications/message`),
then with `logLevel` `warning` (expects exactly five); `tools/call`
`trigger-long-running-operation` (`duration` 1, `steps` 2) with a `progressToken` that
completes, then the same call cancelled after its first progress notification (phase 2 D3's
pattern); `subscriptions/listen` with `toolsListChanged`, `promptsListChanged`,
`resourcesListChanged` and `resourceSubscriptions` = [the static document]; `trigger-list-changed`
for `tools`, `prompts`, `resources` and `trigger-resource-update` on the document, each
expecting its notification tagged with the listen id; `get-roots-list` with an empty
`clientCapabilities` (expects `-32021`), then MRTR (D4) for `get-roots-list`,
`trigger-sampling-request`, `trigger-elicitation-request` and
`trigger-multi-step-elicitation` (three rounds); closing the subscription; shutdown (phase 2's
stdio shutdown, unchanged). It exits 0 only if every step got the reply it expects. Its
messages are exactly the 21 methods of the 2026-07-28 schema (the three `InputRequest` methods
inside results), and nothing the 2026 schema does not define, so its trace can pass
`tap.check`. The sequence is the same on every run; content (texts, `requestState`) varies.

*Source:* stakeholder ask A2, 2026-10-20; roadmap.md phase 6 row; roadmap.md L8 (atlas
coverage).

### D7 — The tasks run (reduced)

`python3 -m client tasks --era 2026-07-28 -- <server command…>` declares `sampling`,
`elicitation` (form) and the tasks extension, and runs: `server/discover`; `tools/call`
`simulate-research-query` with the extension left out of that one request's capabilities
(expects `-32021`); `tools/call` `trigger-sampling-request-async` (expects a task handle in
`input_required`), `tasks/update` with the canned sampling answer for its `inputRequests`, and
`tasks/get` (expects `completed` with a result); `tools/call` `simulate-research-query`
(expects `working`), `tasks/get` (expects `working`), `tasks/cancel`, `tasks/get` (expects
`cancelled`); shutdown. It never polls in a loop (scope). Its trace does not pass `tap.check`:
the extension's methods have no schema in the pinned spec, and the check says so as `unknown
method`; the walkthrough explains this, and the e2e check accepts exactly those failures.

*Source:* roadmap.md phase 6 row (tasks); register row 2026-10-22 (phases 5–7 un-stubbed);
the reduction is this spec's scope cut, approved with the batch.

### D8 — Manual mode in the new era

`python3 -m client manual --era 2026-07-28 -- <server command…>` runs `discover()` (D3), then
reads lines as phase 2 D4 does: a JSON object line is sent exactly as typed (no envelope
added, mistakes included); `:req <method> [<json params>]` sends a request whose params go
through `envelope` (D2) with the declared `--caps` (default none); `:note` sends a
notification as typed; `:quit` and end of input shut down. Its use in lesson 06: send `ping`
and `logging/setLevel` and read their `-32601`.

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap L9).

### D9 — Recording

`scripts/record.sh --client <mode> [name]` gains the modes `tour-2026`, `tasks-2026` and
`manual-2026`, which run `python3 -m client <tour|tasks|manual> --era 2026-07-28 -- <the
tap-wrapped server command>` exactly as phase 2 D5 runs the 2025 modes (same allowlisted
environment, same output lines, the client's exit status passed on, phase 2's register row of
2026-10-21). Default run names `client-tour-2026`, `client-tasks-2026`,
`client-manual-2026`. The usage and `--help` text list them (phase 1 D1 as amended by the
help rows).

*Source:* A5, 2026-10-20; owner decision, 2026-10-20 — registered in mission.md (A4,
delegated; roadmap L16).

### D10 — Schema check, walkthrough, era diff, lesson 06, atlas

**Schema check (L7).** `tap.check --revision 2026-07-28` works on the new traffic with one
added rule in the definition choice (phase 2 D6): when the revision's schema defines
`InputRequiredResult`, a response whose `result.resultType` is `"input_required"` is checked
against `InputRequiredResult` instead of the method's result definition (measured: without it,
every MRTR interim result fails `CallToolResult`). The 2025-11-25 schema has no such
definition, so 2025 checks are unchanged. Nothing else changes: an extension method stays
`unknown method`. The tour's fresh trace (D6) must pass with no failure.

**Walkthrough.** `docs/walkthrough/06-era-2026.md` has the section `## tour` (one note per
frame of a fresh `tour-2026` trace), `## tasks` (one per frame of a fresh `tasks-2026` trace)
and `## shared`, read with `tap.show --explain <file>#<section>` (phase 1 D11 as amended by
the phase 4 row of 2026-10-21). Each note cites the 2026-07-28 spec section that governs the
message (G8). It contains:

- the **era diff**, section `## era-diff`: one note per entry `tap.diff` (phase 5 D4) reports
  between a fresh 2025 `tour` trace and a fresh `tour-2026` trace, keyed by phase 5's keys
  (`<dir>.<method>#<n>`, ranges allowed) and checked by `tap.diff --explain
  docs/walkthrough/06-era-2026.md#era-diff`, so the 2025 era is diffed message by message: the
  keys only in the 2025 trace (`initialize`, `notifications/initialized`, `ping`,
  `logging/setLevel`, `resources/subscribe`, …), the keys only in the 2026 trace
  (`server/discover`, `subscriptions/listen`, the MRTR retries, …) and every pair that differs
  (the envelope, `resultType`, the cache fields). Both tours are deterministic in sequence, so
  the set of entries is the same on every run (to be confirmed by two fresh pairs in the
  build). A prose table beside it maps phase 3's server-to-client requests (`server-tour`) to
  their MRTR form, and prose names the five shifts the learning objective lists;
- the server's measured departures from the spec (progress after cancellation; a later
  request claiming another version on a pinned connection; no listen response on stdin
  close), each labelled with its spec line;
- a short **source tour** (L13): the opening message through `serveStdio`'s era choice to the
  factory that registers the modern tool set (`servers:src/everything/transports/stdio.ts`,
  `servers:src/everything/server/index.ts`), every hop a G8 citation; the SDK server's
  `serveStdio` is named in prose (phase 5's `sdk` root covers the client packages only).

**Lesson.** `docs/lessons/06-era-2026.md` has the L1 sections (G9), records `tour` and
`tour-2026` and `tasks-2026`, checks the 2026 tour with `tap.check --revision 2026-07-28` and
runs `tap.diff … --explain docs/walkthrough/06-era-2026.md#era-diff` in runnable blocks, and
declares `<!-- exercises: … -->` the 21 methods of the 2026-07-28 schema. `README.md` lists it.
Its experiments include manual mode (D8) with a removed method and `--caps none` on the tour.

**Atlas (L8, already built: phase 3 D6, G10).** Phase 6 changes no generator code; the
regenerated `docs/atlas.md` gains lesson 06 in its rows. Phase 3 D6's check that a lesson's
declared methods appear in its fresh trace is amended: a declared method also counts as
present when it is the `method` of an entry in a response's `result.inputRequests` (2026-07-28
carries `roots/list`, `sampling/createMessage` and `elicitation/create` only there), and lesson
06 maps to the `tour-2026` recording. Lesson 06 does not declare `tasks/*`: the atlas's
`tasks/*` rows are the 2025-11-25 core methods, a different contract from the extension's
methods of the same names. Coverage is measured at close and recorded in the Result: methods of
2026-07-28 declared by lesson 06, and the atlas's unexercised count per revision.

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap L1,
L3, L5, L7, L8, L12, L13); per-phase walkthrough P3; roadmap.md phase 6 row (era diff, atlas
coverage). The amendment of phase 3 D6's trace check is to be named in the register row
that approves this batch (proposed alongside register row 2026-10-22).

## Part B — the SDK client

### D11 — The SDK client's 2026 mode

The SDK client (`clients/sdk/`, phase 5 D1) gains the option `--era 2025-11-25|2026-07-28`
(default 2025-11-25, so phase 5's modes are unchanged); `node clients/sdk/src/main.ts tour
--era 2026-07-28 -- <server command…>` mirrors D6 step for step with the same inputs.
`server-tour` with `--era 2026-07-28` is a usage error (exit 2), as for the raw client. The 2026
tour constructs `new Client(…, { capabilities: <the D6 capability objects>,
versionNegotiation: { mode: { pin: "2026-07-28" } } })`, with phase 5's `clientInfo`; registers
phase 5 D2's handlers for `roots/list`, `sampling/createMessage` and `elicitation/create`
(through which the SDK fulfils MRTR); sets **no** `listChanged` option (phase 5's tours use it,
but on a 2026 connection it makes the SDK open its own subscription and re-list; this tour
opens one with `listen()`); sends the log level and the empty-capabilities step through a
per-call `_meta`; gets progress with `onprogress` and cancels with an `AbortSignal` after the
first progress (phase 5 D2's ways); and closes the subscription with its `close()`.

**The transport is a member-less subclass of `StdioClientTransport`** in this mode only. With
the base class the SDK runs the `server/discover` probe on a second process started from the
same command (`sdk:client/dist/index.mjs:2880`, `readStdioServerParams`, which only the base
class satisfies); under `scripts/record.sh` that process is a second tap writing the same trace
path, truncated on open, so the trace loses the discover. Measured 2026-10-22: the base class
started two processes (the first trace held only `server/discover` and its result, the second
the rest of the session with no discover); the subclass started one, whose trace opened with
`server/discover`. Phase 5's 2025 modes are untouched (they never probe). Tasks are not in this
mode (the SDK rejects task results; scope).

*Source:* stakeholder ask A3, 2026-10-20 (both clients); register row 2026-10-20 (SDK client
in TypeScript on the pinned SDK, P1); roadmap.md phase 6 row (both clients).

### D12 — Recording the SDK client

`scripts/record.sh --client sdk-tour-2026 [name]` (default name `client-sdk-tour-2026`) runs
`node clients/sdk/src/main.ts tour --era 2026-07-28 -- <the tap and server command>` exactly as
phase 5 D3 runs `sdk-tour`. The fresh trace must hold one tap `spawn`, start with
`server/discover`, and pass `tap.check --revision 2026-07-28`.

*Source:* A5, 2026-10-20; owner decision, 2026-10-20 — registered in mission.md (A4,
delegated; roadmap L16).

### D13 — Raw vs SDK in the new era

`docs/walkthrough/06-sdk-2026.md` holds one note per entry `tap.diff` reports between fresh
`tour-2026` and `sdk-tour-2026` traces, checked by `tap.diff --explain
docs/walkthrough/06-sdk-2026.md` in `tests/test_e2e.py` (phase 5 D4, D7). Expected from the
recon: every request pair differs in its envelope's `clientInfo`; the SDK puts the envelope on
`notifications/cancelled` too; it chooses its own `progressToken`s; its canned sampling text
names it. Prose outside the notes covers what `tap.diff` normalises away and `tap.show` shows:
the SDK's string ids `server-discover-probe-1` and `listen:0`, and the sibling-process probe
D11 avoids, with `sdk:` citations. Lesson 06 points to it in one subsection of *Read the
trace*, dropped with Part B.

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap L12);
roadmap.md phase 5 row (diff explained and checked by CI).

## What this phase needs from phase 5

Checked against the phase 5 spec as written (`specs/phases/05-sdk-client/requirements.md`,
commit `b96af16`, awaiting the same batch approval). If phase 5 changes any of these, the
named part of this spec changes with it. Part A needs only items 6 and 7.

1. **Location and run (phase 5 D1).** `clients/sdk/`, TypeScript run as source by Node 24
   with no build step: `node clients/sdk/src/main.ts <tour|server-tour> [--caps <list>] --
   <server command…>`; `scripts/bootstrap.sh` installs it with `npm ci`. Phase 6 adds the
   `--era` option to `main.ts` (phase 5 leaves room for it) and adds no build step.
2. **Transport and era (phase 5 D1, D2).** The client constructs `Client` and
   `StdioClientTransport` and sets no `versionNegotiation` (measured by phase 5: its 2025
   modes connect in `legacy` mode, no probe). Part B constructs a member-less subclass of the
   transport in its 2026 mode only (D11), which still "talks to the server only through the
   SDK" as phase 5 D1 requires.
3. **Handlers and options (phase 5 D2).** Handlers registered with `setRequestHandler` return
   phase 3 D1's values (canned text `canned reply from wire-lab-sdk`); `clientInfo`
   `wire-lab-sdk`; progress with `onprogress`, cancellation with an `AbortSignal`; list
   changes with the `listChanged` option, which Part B must not set in its 2026 mode.
4. **Recording (phase 5 D3).** `scripts/record.sh --client <sdk-tour|sdk-server-tour>` runs
   `node clients/sdk/src/main.ts <mode> -- <tap and server command>`; Part B adds
   `sdk-tour-2026` beside them.
5. **SDK unit tests (phase 5 D5).** `node --test "clients/sdk/test/*.test.ts"` under G4, a
   TypeScript test named by its file in a C row (G12 checks the file only).
6. **`tap.diff` (phase 5 D4).** `python3 -m tap.diff <a> <b> --explain <file>[#section]`,
   keys `<dir>.<method>#<n>` and `<dir>.response:<method>#<n>` (era-independent), exit 0 under
   `--explain` when every entry has a note and every note an entry. Part A's era diff (D10) and
   Part B's diff (D13) are checked with it.
7. **Unchanged behaviour.** Phase 5 does not change `client/`, `tap/check.py`, the existing
   `record.sh` modes or the `tap.show` note format; it may refactor `tap/show.py` helpers under
   their existing tests.
8. **`sdk` citation root (phase 5 D6).** `` `sdk:client/dist/index.mjs:<line>` "<fragment>" ``
   resolves into `clients/sdk/node_modules/@modelcontextprotocol/`; D11 and D13 cite with it.
   The pinned server's SDK server package (`serveStdio`) is not under that root; it is named
   in prose.

## Build order (LP3: vertical slice first)

Part A first; each step test-first (LP2).

1. **Slice.** `client/modern.py` with `envelope`, `discover()` and result-type handling, unit
   tests against a new fake 2026 server in `tests/fake_servers/`; `--era` parsing in
   `client/__main__.py`; a tour of `server/discover`, one `tools/call` `echo`, shutdown;
   `record.sh --client tour-2026`; its trace passes `tap.check --revision 2026-07-28` (no new
   rule is needed for this slice).
2. `tap.check`'s `input_required` rule with its tests.
3. Widen the tour: lists, read, prompts, completion, log levels, progress, cancellation.
4. `listen()` and the subscription steps.
5. `request_with_input` and the MRTR steps.
6. Manual mode in the new era.
7. Walkthrough `#tour`, era diff, source tour, lesson 06 with its `exercises` line, README, the
   atlas-check amendment and regenerated atlas; `scripts/gate.sh` adds `06` to G12's
   `--phases` once the rows' tests exist (phase 2 D7).
8. The tasks run, `record.sh --client tasks-2026`, walkthrough `#tasks`. Droppable last: if
   cut, a register row and one *Accepted limits* line.
9. Part B (after phase 5 is merged, register row 2026-10-22): `--era` parsing with a
   `node:test` test, the transport subclass and the 2026 tour (D11), `record.sh --client
   sdk-tour-2026` (D12), the diff notes (D13).
10. Close: Result (coverage values, mutation run), CHANGELOG, tag `lesson-06`. No review round
    (LP4): the only change to earlier claim code is D10's rule in `tap/check.py`, inert for
    2025-11-25 and covered by its own tests and the unchanged phase 2 tests.

Builder: Sonnet, medium. Part A steps 1–7 are about half a session; steps 8 and 9 a quarter
each.

## Stop condition

Every C row of `validation.md` passes for the parts built; the gate (G1–G5, G7–G12, G12 with
phase 06) is green locally and in CI; the fresh `tour-2026` trace passes `tap.check
--revision 2026-07-28` and `--explain #tour`; G10 is green with lesson 06 declared. If Part B
or the tasks run is not built, its rows are removed by a register row and listed in
*Accepted limits*, and the phase still closes.
