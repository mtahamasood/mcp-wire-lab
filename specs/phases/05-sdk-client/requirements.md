# Phase 5 — SDK client, 2025 era (TypeScript, stdio): requirements

**Status: specified in full, awaiting owner approval** (register row 2026-10-22, which un-stubs
phases 5–7; lean profile LP1–LP6 in `mission.md`). No test or code is written before the owner
approves this spec in the batch with phases 6 and 7. Phase 1's decisions D1–D16 and phases 2–3's
decisions stand unless amended here. Facts about the SDK below were read on 2026-10-22 from
`@modelcontextprotocol/client` 2.3.1 as installed in the pinned server's `node_modules` (the same
tarball the SDK client will install: one version, one integrity hash in the lockfile) and measured
against the pinned, built server; the *Measured at the pins* section lists them. The walkthrough
cites the SDK with G8 citations (D6, D7); this spec does not.

## Learning objective

See what an SDK hides. Run the raw client's two tours (phases 2 and 3) through
`@modelcontextprotocol/client` 2.3.1, diff the two clients' fresh traces message by message, and
explain every difference; then follow one `client.callTool` from the API call down to the bytes
written to the server's stdin and back. A reader who finishes can say which bytes the SDK chose
for them, and where in its source it chose them.

## Scope

In: the SDK client in `clients/sdk/` (D1), its `tour` and `server-tour` modes mirroring phases 2
and 3 (D2), recording it through the tap (D3), the trace diff `tap.diff` (D4, L12), the
TypeScript gates (D5), the `sdk` citation root (D6), the walkthrough, the SDK source tour and
lesson 05 (D7, L1, L13). Out: the 2026-07-28 era (phase 6; see *What phase 6 needs*); Streamable
HTTP (phase 7); a real LLM (non-goal).

**Scope cuts** (from the stub and the roadmap row; each is reversible by a later register row):

- No SDK `manual` mode (L9). Typing JSON by hand defeats an SDK; L9 stays a raw-client feature.
- No SDK capability matrix (L10). What a capability buys is a property of the server, measured
  once by the raw client in phase 3; the SDK declares the same capability objects (measured).
- `tap.diff` compares messages, not their order (D4). Order is read with `tap.show`; in both
  measured tour pairs the order was the same.
- No TypeScript linter. G3's `tsc --strict` is the TypeScript gate; a linter would add
  dependencies for little learning value.

### D1 — Where the SDK client lives and how it runs

`clients/sdk/` holds `package.json` (`"private": true`, `"type": "module"`), a committed
`package-lock.json`, `tsconfig.json`, `src/*.ts` and `test/*.test.ts`. Dependencies are exact
versions: `@modelcontextprotocol/client` `2.3.1` (P1; tech-stack row *SDK client*), and as dev
dependencies `typescript` `5.9.3` and `@types/node` `24.19.2`, the versions the pinned server's
own lockfile already holds, so the phase adds no version the project has not pinned. The client
is run as TypeScript source with Node 24's built-in type stripping, with no build step and no
emitted JavaScript: `node clients/sdk/src/main.ts <mode> [options] -- <server command…>`.
`tsconfig.json` sets `strict`, `noEmit`, `erasableSyntaxOnly` (only syntax Node can strip),
`verbatimModuleSyntax`, `allowImportingTsExtensions` (relative imports name `.ts` files),
`module`/`moduleResolution` `nodenext`, `types: ["node"]` and `skipLibCheck: true`.
`scripts/bootstrap.sh` installs it after building the server: `npm ci --ignore-scripts` in
`clients/sdk/` (the narrowest install, as for the server), then fails unless the installed
`@modelcontextprotocol/client` and `@modelcontextprotocol/core` report version `2.3.1`.
`clients/sdk/node_modules/` is ignored by the existing `node_modules/` rule.

The client's code talks to the server only through the SDK: it constructs `Client` and
`StdioClientTransport`, calls `Client` methods, and registers handlers. It never builds a
JSON-RPC object (its source has no `jsonrpc` literal), never calls a `send` method, and never
touches the child's streams; that is what makes the diff (D4) a measurement of the SDK and not
of this code. It imports nothing but the SDK and `node:` built-ins.

*Source:* stakeholder ask A3, 2026-10-20 (a client built on the official SDK); register row
2026-10-20 (client language: the SDK client in TypeScript); P1 and P2, ratified by register row
2026-10-20; tech-stack.md rows *SDK client* and *Node*.

### D2 — Two modes that mirror the raw client's tours

`main.ts` takes a mode, `tour` or `server-tour`, an optional `--caps <list>` (the raw client's
names: `roots`, `sampling`, `elicitation`, `elicitation-url`, declared as the same capability
objects the raw client sends, e.g. all four as `{"roots":{"listChanged":true},"sampling":{},
"elicitation":{"form":{},"url":{}}}`; default as phase 3 D3: none for `tour`, all four for
`server-tour`), and the server command after `--`. `-h`/`--help` prints the
usage on stdout and exits 0 (as phase 1 D1, register row 2026-10-21, self-explanatory help); a
usage error exits 2. Each mode prints one line per step in the raw client's format
(`NN  <label>  <summary>`), prints every notification it receives, exits 0 only if every step got
what it expects, prints `FAILED` and the reason otherwise, and always closes the client.
`client.onerror` prints each SDK-reported error on stderr as one `sdk: <message>` line.

- **`tour`** runs phase 2 D3's steps in the same order with the same arguments and the same
  expectations: `connect` (initialize, initialized), `ping`, `listTools`, `callTool` `echo` and
  `get-sum`, `listResources`, `listResourceTemplates`, `readResource`, `subscribeResource`,
  `unsubscribeResource`, `listPrompts`, `getPrompt` (`simple-prompt`, then `args-prompt` with
  `city` `Oslo`), `complete` (`department` = `E` of `completable-prompt`), `setLoggingLevel`
  `debug`, `callTool` `trigger-long-running-operation` (`duration` 1, `steps` 2) to completion,
  the same call cancelled after its first progress notification, and `close`.
- **`server-tour`** runs phase 3 D4's steps in the same order, answering the server with
  handlers registered by `setRequestHandler` that return phase 3 D1's values (canned sampling text
  `canned reply from wire-lab-sdk`, model `wire-lab-canned`, stop reason `endTurn`; form
  elicitation from `default`, first `enum` value, else the fixed value per type, a non-integer
  number sent as its integer part; URL elicitation declined; the root `file:///wire-lab/project`
  named `wire-lab`, then a second root `file:///wire-lab/other` named `other` announced with
  `sendRootsListChanged`). It waits at the raw server tour's settle points by counting the
  server traffic it has seen, never by a fixed sleep alone.

Where the SDK has its own way to do something, the client uses it, because that way is what the
lesson studies: `clientInfo` is `{"name":"wire-lab-sdk","version":"0.5.0"}`; progress is asked
for with the `onprogress` option (the SDK then chooses the `progressToken`); cancellation is an
`AbortSignal` aborted with the raw tour's reason text; list changes are followed with the
`listChanged` client option (its default 300 ms debounce); a resource update is followed by a
`setNotificationHandler` that calls `readResource`. Everything else, every input a step sends,
equals the raw client's, so the two clients' traces differ only where the clients do (stub D1).

*Source:* stakeholder asks A2 and A3, 2026-10-20; roadmap.md phase 5 row ("runs the tour of
phases 2–3"); register row 2026-10-22 (phases 5–7 un-stubbed).

### D3 — Recording the SDK client

`scripts/record.sh --client <sdk-tour|sdk-server-tour> [name]` records the SDK client through
the tap exactly as phase 2 D5 records the raw client: same allowlisted server environment, same
`recorded:` and `read it:` lines, the client's exit status passed on (phase 1 D14 as amended by
register row 2026-10-21, phase 2 build amendments). The client runs as
`node clients/sdk/src/main.ts <tour|server-tour> -- <the tap and server command>`. The default
names are `client-sdk-tour` and `client-sdk-server-tour`. When `clients/sdk/node_modules` is
missing the script exits 1 with `record: clients/sdk/node_modules missing (run
scripts/bootstrap.sh)` before creating a run folder. The `StdioClientTransport` passes the SDK's
default inherited variables to the process it starts; that process is the tap, which starts the
server with `env -i` and the allowlist, so the server's environment is unchanged.

*Source:* A5, 2026-10-20; register row 2026-10-20 (run output is never committed); roadmap.md
L16.

### D4 — The trace diff: `tap.diff` (L12)

`python3 -m tap.diff <a> <b> [--explain <walkthrough.md>[#section]]` (stdlib only, P4; it reuses
`tap.show`'s loading, classification, response pairing and note parsing) compares the JSON-RPC
messages of two traces:

- **Message identity, ids normalised.** Each frame in `c2s` or `s2c` gets a key. A request or
  notification: `<dir>.<method>#<n>`, `n` counting that method in that direction from 0. A
  response (result or error): `<dir>.response:<method>#<n>`, the key of the request it answers,
  paired by direction and id with the id's JSON type kept (as `tap.show` pairs them). Anything
  else (not JSON, not one object, a batch array, a partial frame, a response that answers no
  request): `<dir>.non-message#<n>`. Frames with the same key in `a` and `b` form a pair; a key in
  one trace only is `only in a` or `only in b`. So two traces whose ids are numbered differently,
  but whose messages are otherwise equal, show no difference.
- **What is compared.** In each pair, the two messages with every `id` member replaced by its
  request's key, and `params.requestId` of `notifications/cancelled` replaced the same way when it
  names a request of that trace. Equal means the same JSON value: member order ignored, array order
  kept, and types kept (`1`, `1.0` and `true` differ, as `tap.show` keeps them). `progressToken`
  is not normalised: the SDK choosing it is one of the differences this phase explains. Timings,
  `seq`, byte counts, `stderr` and `tap` records are not compared. Non-message frames are compared
  by their text.
- **Output.** One line per differing pair, `~ <key>  (a seq <i>, b seq <j>)`, then one indented
  line per differing JSON path (`params.clientInfo.name: "wire-lab-raw" | "wire-lab-sdk"`;
  `(absent)` for a missing member; values compact, escaped as `tap.show` escapes them, cut at 60
  characters); `- <key>  only in a (seq <i>)` and `+ <key>  only in b (seq <j>)`, in order of `a`,
  then of `b`; a last line `summary: <p> pairs, <e> equal, <y> equal as JSON but not as bytes,
  <d> differ; <x> only in a, <z> only in b`. Pairs equal as JSON but not as bytes (member order,
  spacing, escapes) are counted, not listed. Exit 0 when nothing differs and nothing is in one
  trace only, 1 otherwise, 2 on a usage error or an unreadable trace (one `diff:` line on stderr);
  `-h`/`--help` prints the usage and exits 0.
- **`--explain`.** Each reported entry is followed by the walkthrough note whose anchor heading
  (`` #### `<key>` ``, phase 1 D11 form) is its key; `#section` reads only that `##` section plus
  `## shared`, as `tap.show` does (register row 2026-10-21, phase 4 build amendments). An anchor
  `<prefix>#<a>-<b>` is one note for keys `<prefix>#a` to `<prefix>#b`. The run fails (exit 1) on
  an entry with no note (`(no note)  [<key>]`) and on a note with no entry (`(no difference)
  [<key>]`); otherwise it exits 0, whatever the differences.

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap.md L12);
P4, ratified by register row 2026-10-20.

### D5 — TypeScript in the gates

`scripts/gate.sh` gains, inside the existing gates: G3, `node
clients/sdk/node_modules/typescript/bin/tsc -p clients/sdk` (strict, no emit; tech-stack G3 "tsc
--strict from phase 5"); G4, `node --test "clients/sdk/test/*.test.ts"`. The SDK client's own
unit checks use Node's built-in test runner, `node:test` with `node:assert/strict`: no test
dependency (the test tool tech-stack's *SDK client* row leaves to this spec). They cover the
pure parts: argument parsing and the handler values of D2. Everything that needs a server is
checked from Python, in `tests/test_e2e.py`, by recording through `scripts/record.sh` (D3), as
for the raw client. G12 checks a TypeScript test by its file only (it resolves Python tests to
the method); this is an accepted limit. `05` is added to G12's `--phases` list when the phase's
named tests exist (phase 2 D7 as amended by register row 2026-10-21, phase 2 build amendments).

*Source:* tech-stack.md rows *SDK client* and G3; register row 2026-10-21, lean profile (LP2).

### D6 — Citing the SDK's source: the `sdk` citation root

The SDK's source is not in either submodule; the pinned server's copy lives in its untracked
`node_modules`, which no git pin covers. G8 gains a third root, `sdk`, which resolves to
`clients/sdk/node_modules/@modelcontextprotocol/` (so `client/…` and `core/…` are both
citable): `` `sdk:client/dist/index.mjs:<line>` "<fragment>" ``. Its pin is the lockfile:
`npm ci` installs exactly the tarball whose `sha512` integrity `clients/sdk/package-lock.json`
records, and bootstrap checks the version (D1). G8 applies its rules unchanged (the path stays
inside the root; a fragment of at least 6 characters on that line) and, when the root is missing,
fails with one line naming `scripts/bootstrap.sh`. Citations point into the package's `dist/`
ES module files, the code Node runs (unminified, comments kept); the original TypeScript exists
only inside the `.map` files and is not cited. G8 also scans `clients/sdk/src/` and
`clients/sdk/test/` (never `node_modules/`). The tech-stack rows G8 and *Citation form* are
amended by a register row before this lands (see the report that accompanies this spec).

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap.md L3,
L13); tech-stack.md G8 (amended by register row 2026-10-21, step (b) review).

### D7 — Walkthrough, SDK source tour, lesson 05

`docs/walkthrough/05-sdk-client.md` has three parts.

1. **What is the same.** The raw client's walkthroughs explain every frame of the SDK client's
   fresh traces: `tap.show --explain docs/walkthrough/02-raw-client-tour.md` on an `sdk-tour`
   trace and `--explain docs/walkthrough/03-server-initiated.md` on an `sdk-server-tour` trace pass
   with no missing and no extra note (measured; checked in `tests/test_e2e.py`). The walkthrough
   says why: same message sequence, same ids, same server replies.
2. **What differs, difference by difference.** Sections `## tour` and `## server-tour` hold one
   note per `tap.diff` entry between a fresh raw trace and a fresh SDK trace of that tour, keyed
   by D4's keys and checked by `tap.diff --explain` in `tests/test_e2e.py`. Each note says what
   differs, why, and where (an `sdk:` or `servers:` citation), and says when a difference is noise
   that a raw-vs-raw diff shows too (the server's random URL-elicitation id). Prose outside the
   note sections explains the bytes-only differences (the SDK writes `method` and `params` first,
   then `jsonrpc` and `id`; the server's frames have the SDK's order too, because it is built on
   the same SDK generation) and what the SDK does that never reaches the wire, each with a
   citation: result validation, the response cache, page aggregation in `list*`, the progress
   handler table that drops a late progress with an `onerror`, its 60 s default request timeout
   (the raw client's is 30 s).
3. **Source tour (L13, one request):** the tour's `callTool` `echo`, from `Client.callTool`
   through `Protocol.request` (id allocation, the message object, the response handler keyed by
   id, the timeout, the `progressToken` when `onprogress` is given) to
   `StdioClientTransport.send`, `serializeMessage` and the write to the child's stdin; and back:
   the stdout `data` handler, `ReadBuffer`, `onmessage`, `_onresponse`, the handler looked up by
   id, result decoding and validation, and `callTool`'s output-schema check. Every hop is a
   verified `sdk:` citation (D6).

`docs/lessons/05-sdk-client.md` has the L1 sections in order, an `<!-- exercises: … -->` line
for the methods its two recordings show (mapped in `tests/test_e2e.py`'s `AtlasClaimsTest`;
`docs/atlas.md` regenerated, G10), and runnable blocks (G9) that record both clients' tours,
run `tap.diff … --explain docs/walkthrough/05-sdk-client.md#tour` and check the SDK trace with
`tap.check --revision 2025-11-25`. `README.md` lists lesson 05.

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap.md L1,
L3, L4, L12, L13); per-phase walkthrough P3, ratified by register row 2026-10-20; roadmap.md
phase 5 row.

## Measured at the pins

Measured 2026-10-22 on this machine (Node 24.22.0), with a throwaway script calling the SDK as
D2 describes, recorded through the tap against the pinned, built server, outside the repository.
Values only; no run output is kept (A5).

- **Era.** With no `versionNegotiation` option the 2.3.1 client connects in `legacy` mode: a
  plain `initialize` offering `2025-11-25`, then `notifications/initialized`, no
  `server/discover`.
- **Tour.** 44 trace records for each client; the same request ids, 0 to 16, and the same message
  sequence. `tap.check --revision 2025-11-25` passes on the SDK trace (41 frames). A prototype of
  D4 found 41 message pairs: 20 equal, 14 equal as JSON but not as bytes (member order), 7
  differ, none in one trace only. The 7: `initialize` (`clientInfo`), the two long-running
  `tools/call` requests (`_meta.progressToken` is the request id, 15 and 16, instead of
  `"tour-done"` and `"tour-cancel"`) and their four progress notifications. The
  `notifications/cancelled` frames are equal. The same 7 on a second SDK run.
- **Server tour.** 77 records for each client; 74 frames pass `tap.check`; 45 equal, 24 equal
  as JSON only, 5 differ, none in one trace only: `initialize`, the reply to
  `sampling/createMessage` and the `tools/call` result that quotes it (the canned text names the
  client), the URL `elicitation/create` and the `tools/call` result that quotes it (the
  server's random `elicitationId`, different on every run).
- **Raw walkthroughs.** `tap.show --explain` with walkthrough 02 on the SDK tour trace, and with
  walkthrough 03 on the SDK server-tour trace, both exit 0 (no missing, no extra note).
- **Slice.** `connect`, one `callTool` `echo` with no `listTools` before it, `close`: initialize,
  initialized, one `tools/call`, the reply; no hidden `tools/list`.
- **Late progress.** After the abort, the server's second progress notification is dropped by
  the SDK and reported through `onerror` ("Received a progress notification for an unknown
  token").
- **Shutdown.** `client.close()` took 45–52 ms; the tap recorded the server's exit 0. Tour wall
  time 3.3 s (SDK) and 2.8 s (raw).
- **TypeScript.** Node 24.22.0 runs a `.ts` file importing a `.ts` module with no flag and no
  warning; `node --test "test/*.test.ts"` runs a `.ts` test. `tsc` 5.9.3 with D1's options
  type-checks a client importing `@modelcontextprotocol/client` and `…/client/stdio` with exit
  0: 1.3 s and about 330 MB with `skipLibCheck`, 8.4 s and about 750 MB without (it also passes).
- **Package.** `@modelcontextprotocol/client` 2.3.1 is Apache-2.0, ships bundled ES modules
  (`dist/index.mjs` 5887 lines, `dist/stdio.mjs` 217, the protocol layer in a chunk
  `dist/src-<hash>.mjs` 7225) with `.map` files, and depends on `@modelcontextprotocol/core`
  2.3.1 (zod schemas), `zod`, `cross-spawn`, `jose`, `eventsource`, `eventsource-parser` and
  `pkce-challenge`. Hops of the source tour as of that tarball: `callTool` at `index.mjs` line
  4224, its `this.request` at 4254; `request` at `src-<hash>.mjs` 6068, the id at 6170, the
  progress token at 6183, the response handler at 6208, `_transport.send` at 6245,
  `serializeMessage` at 6775; `StdioClientTransport.send` at `stdio.mjs` 206, the stdin write at
  210, the stdout `data` handler at 102. The builder re-reads them; G8 checks the walkthrough's.

## What phase 6 needs from this client (forward reference only)

Phase 6 is specified separately. From the 2.3.1 source (read, not measured): the era is a
`Client` constructor option, `versionNegotiation: { mode: { pin: "2026-07-28" } }` or
`{ mode: "auto" }`; with either, on the SDK's stdio transport, the client probes
`server/discover` on a **second, disposable process started with the same command**
(`negotiateStdioViaSibling` in `index.mjs`), so under `record.sh` a second tap would start with
the same `--trace` path, which the tap replaces. On a 2026-07-28 connection the SDK drops
server-to-client JSON-RPC requests and serves `input_required` results through the handlers D2
registers. This phase leaves `main.ts`'s option parsing open to a later `--era` option and
`tap.diff`'s keys era-blind (an `initialize` against a `server/discover` shows as one key in
each trace only).

## Build order (LP3: vertical slice first)

1. **Slice.** `clients/sdk/` (package files, lockfile, tsconfig), bootstrap's install and
   version check, G3's `tsc` line; `main.ts tour` doing only connect, one `callTool` `echo`,
   close; `record.sh --client sdk-tour`; an e2e test that its fresh trace holds initialize,
   initialized and one `tools/call`, and passes `tap.check`.
2. **`tap.diff`**, tests first (`tests/test_diff.py`), on traces built in the tests.
3. **Widen `tour`** to D2's full list; e2e: the SDK trace passes `tap.check`, walkthrough 02
   explains it, and the raw-vs-SDK diff is explained by `05-sdk-client.md#tour` (notes written
   from the diff of fresh traces).
4. **`server-tour`**, handler unit tests first (`node --test`), then the mode; e2e as step 3
   with walkthrough 03 and `#server-tour`.
5. **Docs and gates.** G8's `sdk` root and scanned paths; the walkthrough's prose and source
   tour; lesson 05, its atlas line and `AtlasClaimsTest` entry, `docs/atlas.md`, README; `05` in
   G12's `--phases`. Close: Result, CHANGELOG, tag `lesson-05`.

Builder: Sonnet, medium. No review round (LP4): the phase adds new code beside phases 1–3's and
changes their claim code only if `tap/show.py`'s helpers must be refactored for reuse, which
their existing tests must then still pass unchanged; if they do not, a review round runs.

## Stop condition

Every C row in `validation.md` passes; the gate (G1–G5, G7–G12, with D5's additions and `05` in
G12's list) is green locally and in CI; the fresh SDK traces of both tours pass
`tap.check --revision 2025-11-25` and the raw walkthroughs' `--explain`, and `tap.diff --explain`
passes for `#tour` and `#server-tour` on fresh traces.
