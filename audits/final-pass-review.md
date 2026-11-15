# Final-pass review (phase 8, D10): the corpus and its dispositions

One adversarial review round over phases 3 to 7 (`specs/phases/08-final-pass/requirements.md`
D10; row C8 of `validation.md`). Findings are numbered `P8-R<phase>-<n>`, as the reviewers wrote
them. Each was reproduced by the reviewer and, where it is fixed here, reproduced again before the
fix: a code defect by a probe or the failing test, a test gap by a surviving mutant that the new
test now kills (`python3 tools/mutate.py` on the survivor, run in a temporary copy).

Sections:

1. Phases 5 and 6 (reviewer: Opus 5.5): disposition table, then the report as written.
2. Phases 3, 4 and 7 (reviewer: Opus 5.5): disposition table, then the report as written, then
   the results of `mutants-07.json`.

## 1. Phases 5 and 6

### Disposition

Branch `phase-08-fix-r56`. The C rows are in `specs/phases/08-final-pass/validation.md`.

| Finding | Severity | Disposition | Commit and test (C row) |
| --- | --- | --- | --- |
| P8-R5-1 | major | fixed in Stage A (`clients/sdk/src/order.ts`, `order.test.ts`) | Stage A; row C3 |
| P8-R5-2 | minor | fixed: test gap closed; the mutant `pending.pop` to `pending.get` was killed, the code was already right | `2fa6a30`; `tests/test_diff.py::KeysTest::test_response_keyed_by_the_request_it_answers` (C22) |
| P8-R6-1 | minor | reproduced, fixed: `ModernSession.listen` waits on the acknowledgment and on the answer to its own request, and raises the server's `RpcError` | `5982316`; `tests/test_client_modern.py::ListenTest::test_listen_error_is_raised_not_timed_out` (C23) |
| P8-R6-2 | minor | reproduced (`AttributeError` on `data: ["2025-11-25"]`), fixed: `data.supported` only when `data` is an object, else `data` as sent | `5982316`; `tests/test_client_modern.py::DiscoverTest::test_unsupported_version_error_with_malformed_data_still_says_what_was_sent` (C24) |
| P8-R6-3a | minor | fixed: test gap closed (mutant `p6-modern-stale-retry` killed); the code was already right | `5982316`; `tests/test_client_modern.py::InputRequiredTest::test_retry_does_not_inherit_a_previous_rounds_state` (C25) |
| P8-R6-3b | minor | fixed: test gap closed (mutant `p6-modern-wait-method` killed); the code was already right | `5982316`; `tests/test_client_modern.py::ListenTest::test_wait_for_takes_only_the_method_asked_for` (C26) |
| P8-R6-4 | minor | reproduced by reading (the old tour passed a `list_changed` tagged with any id or none: the new test's fake server shows it), fixed: the tour reads the id of its `subscriptions/listen` request from the transport (`clients/sdk/src/listen.ts`) and `expect`s each list change and the resource update to carry it | branch `phase-08-fix-sdk`; `clients/sdk/test/listen.test.ts` (C141) |
| P8-R6-5 | minor | reproduced by reading the pinned lines (`stdio.mdx:82`, `subscriptions.mdx:122`), fixed in `docs/walkthrough/06-era-2026.md` | `cb0f335`; `tests/test_walkthrough_06.py::EraDocTest::test_cancelled_listen_is_not_a_departure`, `::test_notification_is_never_given_an_error_code` (C27) |

Note on P8-R6-4: the SDK's `listen()` result holds only `honoredFilter`, `close` and `closed`; the
listen id the SDK sends (a string, `sdk:client/dist/index.mjs:3987`, `listen:<n>`) is not exposed.
The fix reads it from the `subscriptions/listen` request as the transport is handed it (the
transport's own `send` slot is observed, nothing is built or sent by the tour; phase 5's source
test still passes), then fails any list change or resource update that carries another id or none.
No scope change.

The mutants named above are in `mutants-05-06.json` (the review's file); the survivors were re-run
against the new tests and all three are killed.

The other 26 mutants of the review were already killed. The near-equivalent survivor
`p5-diff-cancel-method-gate` is left to D9, which signs or kills it (the review did not count it).

### The report as written

The report follows unchanged except that its headings are three levels lower.

#### Phase 5 and 6 review (LP4, deferred to phase 8's final pass): the SDK client, `tap.diff`, the 2026-07-28 era

Reviewer: an independent agent (Opus 5.5) that did not build this work; the builders were Sonnet.
Date: 2026-11-14. Scope: phase 5 (`git log e776590..d219dc8`, merged at `63f69d3`) and phase 6
(`55afe82`, `3777577`, `702f03a`, merged at `77aa95e`, closed `18a1c49`), restricted to
`tap/diff.py`, `clients/sdk/src/*.ts`, `clients/sdk/test/`, the `sdk` root in
`tools/check_citations.py`, `client/modern.py`, the era parts of `client/__main__.py` and
`client/manual.py`, `tap/check.py`'s `input_required` and SEP-2663 rules,
`tap/schemas/2026-07-28/sep-2663-tasks.json`, `scripts/record.sh`'s sdk and 2026 modes,
`tests/test_diff.py`, `tests/test_client_modern.py`, the phase 6 parts of `tests/test_check.py`,
the SDK and 2026 classes of `tests/test_e2e.py`, `docs/walkthrough/05-*`, `06-*`,
`docs/lessons/05-*`, `06-*`. Contract: `specs/phases/05-sdk-client/` and
`specs/phases/06-era-2026/` (`requirements.md`, `validation.md`). The register rows of
2026-10-22 (phase 5 build, phase 6 build), A44 and A45 are taken as accepted and not
re-litigated. The SDK cancel step's late-progress wait (`clients/sdk/src/tour.ts` ~124-150) is
being fixed by another agent and is not reviewed here, except where P8-R5-1 touches it.

##### What I ran

- Unit tests `tests.test_diff`, `tests.test_client_modern`, `tests.test_check`,
  `tests.test_sdk_client`: 66 tests, OK. `tools/check_claims.py --phases 05,06`: `claims: ok`.
  The full gate and the e2e suite were not run (another agent's stress run and gate share the
  machine; load average 8 during this review).
- Fresh recordings through `scripts/record.sh --client` of `tour-2026`, `tasks-2026`, `tour`,
  `sdk-tour-2026` and `sdk-tour` (run folders deleted afterwards). The raw ones exit 0. On the
  `tour-2026` trace: `tap.check --revision 2026-07-28` ok (74 frames),
  `tap.show --explain …06-era-2026.md#tour` exit 0, `tap.diff <tour> <tour-2026> --explain
  …#era-diff` exit 0 (30 pairs, 4 equal, 26 differ; 11 only in a, 44 only in b). On the
  `tasks-2026` trace: `tap.check` ok with the `12 of 18 frames … SEP-2663` line, and with
  `--no-extensions` exactly the 10 `tasks/*` requests and responses fail as `unknown method`, as
  lesson 06 says; `--explain #tasks` exit 0. Both SDK recordings exited 1 (P8-R5-1).
- The SDK `tour` run directly against the built server six times: 5 of 6 exit 1, all at
  `expected two progress notifications`. A fake server and a 12-line SDK probe that reproduce it
  deterministically (P8-R5-1).
- Probe scripts with fake 2026 servers for `ModernSession.discover` and `listen` (P8-R6-1,
  P8-R6-2).
- 30 single-edit mutants on a temporary copy of `tap/`, `client/`, `tests/` and `tools/` (vendor
  symlinked), each run against the C row's test module: 26 killed, 4 survived (P8-R5-2,
  P8-R6-3; one is near-equivalent, see *Not reported*). The list is in *Mutation candidates* and
  in `mutants-05-06.json`; every `old` was checked to occur exactly once.
- Read against the pinned text: SEP-2663 lines 80-440 against every definition of the
  transcribed schema (each matches its TypeScript declaration; required fields, optional
  `statusMessage`/`pollIntervalMs`, the `resultType` consts at 128, 340, 383, 412, `allOf`
  `RequestParams` on the three requests); the 2026-07-28 `stdio.mdx` (cancellation, era, request
  kinds), `subscriptions.mdx` (cancellation and graceful closure), `versioning.mdx`; the SDK's
  `Protocol` dispatch (`src-WCy6ifGf.mjs` 5840-5905, 6019-6060) and `Client` overrides
  (`index.mjs` 4105-4165).

Counts: 0 blockers, 1 major, 6 minors.

##### Majors

###### P8-R5-1: the SDK tours drop an on-time progress notification, so both SDK tours fail most runs under load

- Severity: major (reproduced: deterministic with a fake server; 5 of 6 real runs at load
  average 8; both SDK recordings of this review failed). Affects phase 5 C5-C8 and C11, phase 6
  C13-C15, lesson 05's and 06's G9 blocks, and is very likely the open A45/A46 flake
  "`SdkClientTest` setup exiting 1".
- File: `clients/sdk/src/tour.ts:112-121` (`longRunning`, the check at 119) and
  `clients/sdk/src/era.ts:197-206` (the same at 204); the cause is in the pinned SDK,
  `sdk:client/dist/src-WCy6ifGf.mjs:5903` (notification handlers, progress included, run in a
  `Promise.resolve().then` microtask) against `src-WCy6ifGf.mjs:6046-6055` (`_onresponse` runs
  synchronously and deletes the request's progress handler).
- Claim: phase 5 D2 and phase 6 D11 make the tour's long-running call (the one that is not
  cancelled) expect two progress notifications through `onprogress`, and walkthrough 05 says a
  progress notification is dropped only when its token has no handler, "after the abort". In the
  SDK, a response is handled synchronously when its line is parsed, while a notification's
  handler is deferred to a microtask. When the server's second progress notification and the
  response arrive in one stdout chunk (the server writes them 0.4 ms apart: trace seq 37 at
  2080.1 ms, seq 38 at 2080.5 ms), `_onresponse` deletes the progress handler before the
  deferred `_onprogress` runs. The SDK then reports `Received a progress notification for an
  unknown token` through `onerror` for a notification that arrived *before* the response, and
  `onprogress` is called once. The tour fails with `expected two progress notifications`.
  Whether the two lines share a chunk depends on scheduling, so it fails more under CPU load.
  The raw client is not affected (one reader thread queues the notification before it completes
  the request).
- Reproduction: a fake server that answers `initialize`, then for `tools/call` writes progress
  1, sleeps 0.2 s, and writes progress 2 and the result in one `write`:

  ```python
  # fake_server.py
  import json, sys, time
  def out(*m): sys.stdout.write("".join(json.dumps(x) + "\n" for x in m)); sys.stdout.flush()
  for line in sys.stdin:
      m = json.loads(line)
      if m.get("method") == "initialize":
          out({"jsonrpc":"2.0","id":m["id"],"result":{"protocolVersion":"2025-11-25",
               "capabilities":{"tools":{}},"serverInfo":{"name":"fake","version":"0"}}})
      elif m.get("method") == "tools/call":
          tok = m["params"]["_meta"]["progressToken"]
          out({"jsonrpc":"2.0","method":"notifications/progress","params":{"progressToken":tok,"progress":1,"total":2}})
          time.sleep(0.2)
          out({"jsonrpc":"2.0","method":"notifications/progress","params":{"progressToken":tok,"progress":2,"total":2}},
              {"jsonrpc":"2.0","id":m["id"],"result":{"content":[{"type":"text","text":"completed"}]}})
  ```

  ```js
  // probe.mjs: imports Client and StdioClientTransport from clients/sdk/node_modules
  const client = new Client({ name: "probe", version: "0" });
  client.onerror = (e) => console.log("onerror:", e.message.slice(0, 90));
  await client.connect(new StdioClientTransport({ command: "python3", args: [process.argv[2]] }));
  const seen = [];
  await client.callTool({ name: "x", arguments: {} }, { onprogress: (p) => seen.push(p.progress) });
  await new Promise((r) => setTimeout(r, 100));
  console.log("onprogress calls:", JSON.stringify(seen));
  ```

  Observed: `onerror: Received a progress notification for an unknown token …`, then
  `onprogress calls: [1]`. Against the real server, `node clients/sdk/src/main.ts tour -- node
  vendor/servers/src/everything/dist/index.js stdio` six times in a row: runs 1-5 exit 1 at
  `16  FAILED  Error: expected two progress notifications` (stderr: the `unknown token` line for
  progress 2 of token 15), run 6 exit 0. `record.sh --client sdk-tour-2026` failed the same way
  at step 13 (token 12).
- Suggested fix: count the call's progress where the SDK cannot lose it: `onprogress` calls plus
  `onerror` "unknown token" reports naming this call's token (the token is the request id, which
  the tour can read from the traffic it already marks), and expect that sum to be 2; or wait for
  two `notifications/progress` frames via the existing `Traffic` counter fed from a transport
  `onmessage` wrapper, which sees every line synchronously. Update the two e2e assertions that
  the SDK stderr holds exactly one `sdk:` line (`tests/test_e2e.py:495-499` and `818-822`),
  which a tolerant tour would still trip, to allow an `unknown token` line for either call.
  Add a sentence with the two citations above to walkthrough 05's *progress handler table*
  bullet: the SDK can drop an on-time progress notification that shares a read with its
  response. Close A45's open flake against this finding if the gate stays green under load
  afterwards.
- Should be caught by: phase 5 C5 (`SdkClientTest`, `setUpClass` asserts exit 0) and phase 6
  C13 (`SdkModernTourTest`); they do catch it, but as an intermittent setup failure that A45
  recorded as "not reproduced alone". A `node --test` unit test with the fake server above
  (one chunk holding the last progress and the response) would pin it.

##### Minors

- **P8-R5-2** (minor, test gap, reproduced by mutant) `tap/diff.py:116`: C1 says a response that
  answers no request is a non-message frame, and the code pops the request from `pending` so a
  second response with the same id gets `<dir>.non-message#n` (checked: `[ping, response,
  response]` keys as `c2s.ping#0`, `s2c.response:ping#0`, `s2c.non-message#0`). But the mutant
  `pending.pop(flight, "")` → `pending.get(flight, "")` survives all of `tests.test_diff`: no
  test has a duplicate response. With the mutant the duplicate takes the same key as the first
  response, and `compare`'s `b_by_key` silently keeps only one of them, so a duplicate reply in
  one trace is neither paired nor reported. Fix: add a duplicate response to
  `KeysTest::test_response_keyed_by_the_request_it_answers` and expect `s2c.non-message#0`. C1.
- **P8-R6-1** (minor, reproduced) `client/modern.py:350-356` (`listen`): a JSON-RPC error answering
  `subscriptions/listen` (for example a capacity or params rejection, which the 2026 SDK client
  itself handles as a pre-ack failure at `sdk:client/dist/index.mjs:4147`) is ignored, and
  `listen` reports `TimeoutError: no notifications/subscriptions/acknowledged … within 5.0 s`
  after 5.1 s instead of the server's error. Reproduced with a fake 2026 server that answers the
  listen with `-32602`. No hang beyond the 5 s and no stray `notifications/cancelled` (the
  request is already complete, so `cancel` sends nothing). Fix: wait on the ack and on
  `pending.done` together, and raise the `RpcError` when the listen request fails before its
  ack. Add a C5 test with a listen error.
- **P8-R6-2** (minor, reproduced) `client/modern.py:239`: `discover` reads `-32022`'s
  `data.supported` with `(error.get("data") or {}).get("supported")`; a `data` that is a list or
  a string raises `AttributeError: 'list' object has no attribute 'get'` instead of
  `UnsupportedVersion`, so the D3 message naming what the server offered is lost for malformed
  input (reproduced with `data: ["2025-11-25"]`). Fix: take `supported` only when `data` is an
  object; otherwise raise `UnsupportedVersion` naming `data` as sent. C2.
- **P8-R6-3** (minor, test gaps, reproduced by mutants) `client/modern.py:332` and `:181`. Two C
  claims have no failing test:
  (a) C4 "`requestState` echoed": the mutant `current = dict(base)` → `current = dict(current)`
  survives, which makes a retry inherit the previous round's `inputResponses`/`requestState`
  when the new `input_required` result omits `requestState`; every C4 test has one round.
  (b) C5 "tagged notifications reach their subscription": the mutant that drops the `method`
  test in `Registry.wait` survives, so `wait_for("notifications/prompts/list_changed")` could
  return any notification on the stream. Fix: a three-round fake `mrtr` whose second round has
  no `requestState` (expect none in the third request), and a C5 test that emits a tools change
  then waits for a prompts change and must time out.
- **P8-R6-4** (minor, weaker check than D11 states; code reading, no wire defect reproduced)
  `clients/sdk/src/era.ts:83-90, 244-255`: D11 says the SDK 2026 tour mirrors D6 step for step,
  and D6 expects each list change and the resource update "tagged with the listen id". The SDK
  tour stores the last notification's `subscriptionId` and prints it, but never compares it with
  the subscription it opened; any untagged or wrongly tagged `list_changed` passes the step. Fix:
  record the listen id from the acknowledged subscription (or the `listen:<n>` id the SDK uses)
  and `expect` equality, as the raw tour does by routing on the id. C13/C14.
- **P8-R6-5** (minor, docs false against the pinned spec) `docs/walkthrough/06-era-2026.md:107-112`
  and `:57`. (a) The departure "No `subscriptions/listen` response at shutdown" includes "(or the
  client cancels the listen request)". For a cancelled request the server is required to send
  nothing (`spec:docs/specification/2026-07-28/basic/transports/stdio.mdx:82` "MUST NOT** send any
  further messages for it"), and `subscriptions.mdx:122` lists client cancellation as its own
  case with no response; the server is right there, not departing. (b) The era table puts
  `notifications/roots/list_changed` under "removed (`-32601`)"; a notification is never
  answered, so it cannot get `-32601`. Fix: drop the parenthetical (keep the stdin-close case,
  which D10 names), and split the table cell: the three requests get `-32601`, the notification
  is simply gone. No test (docs).

##### Mutation candidates

All 30 are in `mutants-05-06.json` next to this report (`links`: `vendor`,
`clients/sdk/node_modules`). Run on a temporary copy on 2026-11-14: 26 killed, 4 survived
(marked *survives* below; the first three are P8-R5-2 and P8-R6-3, the fourth is near-equivalent).

`tap/diff.py`, command `python3 -m unittest tests.test_diff`:

| id | change | result |
| --- | --- | --- |
| p5-diff-pop-to-get | `pending.pop(flight, "")` → `pending.get(…)` | survives (P8-R5-2) |
| p5-diff-response-direction | response flight uses `direction`, not `OTHER[direction]` | killed |
| p5-diff-cancel-direction | `requestId` looked up in `OTHER[direction]` | killed |
| p5-diff-asked-dropped | delete `asked[flight] = key` | killed |
| p5-diff-same-type | delete `same`'s type check | killed |
| p5-diff-order-ignored | bytes-only test drops `fa.ordered == fb.ordered` | killed |
| p5-diff-plain-always | `plain` always `True` | killed |
| p5-diff-id-not-normalised | delete the `norm["id"]` replacement | killed |
| p5-diff-nonmessage-text | non-message frames compared as `""` | killed |
| p5-diff-only-b-dropped | `only_b = []` | killed |
| p5-diff-cancel-method-gate | map `requestId` in any notification | survives (near-equivalent) |
| p5-diff-explain-exit | `--explain` exit also needs `result.clean` | killed |

`client/modern.py`, command `python3 -m unittest tests.test_client_modern`:

| id | change | result |
| --- | --- | --- |
| p6-modern-task-gate | `task` accepted without the extension | killed |
| p6-modern-version-check | `ERA not in offered` dropped | killed |
| p6-modern-32022 | `-32601` also taken as unsupported version | killed |
| p6-modern-gate-off | `if not self.ready` → `if False` | killed |
| p6-modern-ready-early | `self.ready = True` before the version check | killed |
| p6-modern-state-dropped | `requestState` not echoed | killed |
| p6-modern-stale-retry | `current = dict(current)` | survives (P8-R6-3a) |
| p6-modern-rounds | `range(1, max_rounds)` (an upward change is equivalent: the `break` caps it) | killed |
| p6-modern-sub-key-type | subscription id stringified when filed | killed |
| p6-modern-wait-method | `Registry.wait` ignores the method | survives (P8-R6-3b) |
| p6-modern-wait-consume | matched notification not removed | killed |

`tap/check.py`, command `python3 -m unittest tests.test_check`:

| id | change | result |
| --- | --- | --- |
| p6-check-input-required | `input_required` rule never fires | killed |
| p6-check-task-other-method | `task` allowed on any method but `tasks/get` | killed |
| p6-check-name-collision | definition-name guard off | killed |
| p6-check-method-collision | method guard off | killed |
| p6-check-ref-resolve | `$ref` existence check off | killed |
| p6-check-label | `SEP-2663:` label and count off | killed |
| p6-check-by-method | merged `method` index not rebuilt | killed |

The JSON (also in `mutants-05-06.json`, with exact `old`/`new` texts):

```json
{
 "links": [
  "vendor",
  "clients/sdk/node_modules"
 ],
 "mutants": [
  {
   "id": "p5-diff-pop-to-get",
   "file": "tap/diff.py",
   "old": "request_key = pending.pop(flight, \"\")",
   "new": "request_key = pending.get(flight, \"\")",
   "command": "python3 -m unittest tests.test_diff",
   "note": "a second response with the same id pairs again; expected to SURVIVE (no test has a duplicate response)"
  },
  {
   "id": "p5-diff-response-direction",
   "file": "tap/diff.py",
   "old": "flight = (OTHER[direction], type(msg[\"id\"]).__name__, id_text(msg[\"id\"]))",
   "new": "flight = (direction, type(msg[\"id\"]).__name__, id_text(msg[\"id\"]))",
   "command": "python3 -m unittest tests.test_diff",
   "note": "responses pair with requests of their own direction"
  },
  {
   "id": "p5-diff-cancel-direction",
   "file": "tap/diff.py",
   "old": "target = asked.get((direction, type(params[\"requestId\"]).__name__,",
   "new": "target = asked.get((OTHER[direction], type(params[\"requestId\"]).__name__,",
   "command": "python3 -m unittest tests.test_diff",
   "note": "requestId looked up in the other direction"
  },
  {
   "id": "p5-diff-asked-dropped",
   "file": "tap/diff.py",
   "old": "                asked[flight] = key\n",
   "new": "",
   "command": "python3 -m unittest tests.test_diff",
   "note": "requestId never mapped"
  },
  {
   "id": "p5-diff-same-type",
   "file": "tap/diff.py",
   "old": "    if type(a) is not type(b):\n        return False\n",
   "new": "",
   "command": "python3 -m unittest tests.test_diff",
   "note": "1, 1.0 and true compare equal"
  },
  {
   "id": "p5-diff-order-ignored",
   "file": "tap/diff.py",
   "old": "if fa.ordered == fb.ordered and fa.plain == fb.plain:",
   "new": "if fa.plain == fb.plain:",
   "command": "python3 -m unittest tests.test_diff",
   "note": "member order no longer a bytes-only difference"
  },
  {
   "id": "p5-diff-plain-always",
   "file": "tap/diff.py",
   "old": "out.append(Frame(key, seq, norm, dump(norm), raw == dump(msg)))",
   "new": "out.append(Frame(key, seq, norm, dump(norm), True))",
   "command": "python3 -m unittest tests.test_diff",
   "note": "spacing/escapes no longer a bytes-only difference"
  },
  {
   "id": "p5-diff-id-not-normalised",
   "file": "tap/diff.py",
   "old": "        if \"id\" in norm:\n            norm[\"id\"] = request_key\n",
   "new": "",
   "command": "python3 -m unittest tests.test_diff",
   "note": "ids compared as written"
  },
  {
   "id": "p5-diff-nonmessage-text",
   "file": "tap/diff.py",
   "old": "out.append(Frame(key, seq, text, text, True))",
   "new": "out.append(Frame(key, seq, \"\", text, True))",
   "command": "python3 -m unittest tests.test_diff",
   "note": "non-message frames always equal"
  },
  {
   "id": "p5-diff-only-b-dropped",
   "file": "tap/diff.py",
   "old": "only_b = [f for f in b if f.key not in a_keys]",
   "new": "only_b = []",
   "command": "python3 -m unittest tests.test_diff",
   "note": "keys only in b not reported"
  },
  {
   "id": "p5-diff-cancel-method-gate",
   "file": "tap/diff.py",
   "old": "if norm.get(\"method\") == \"notifications/cancelled\" and isinstance(params, dict):",
   "new": "if isinstance(params, dict):",
   "command": "python3 -m unittest tests.test_diff",
   "note": "requestId of any notification mapped; expected to SURVIVE (no other notification with requestId in the tests)"
  },
  {
   "id": "p5-diff-explain-exit",
   "file": "tap/diff.py",
   "old": "        return 0 if ok else 1\n",
   "new": "        return 0 if ok and result.clean else 1\n",
   "command": "python3 -m unittest tests.test_diff",
   "note": "--explain exits 1 when differences exist, even if all are explained"
  },
  {
   "id": "p6-modern-task-gate",
   "file": "client/modern.py",
   "old": "if kind == \"task\" and tasks_declared:",
   "new": "if kind == \"task\":",
   "command": "python3 -m unittest tests.test_client_modern",
   "note": "task accepted without the extension"
  },
  {
   "id": "p6-modern-version-check",
   "file": "client/modern.py",
   "old": "if not isinstance(offered, list) or ERA not in offered:",
   "new": "if not isinstance(offered, list):",
   "command": "python3 -m unittest tests.test_client_modern",
   "note": "any version list accepted"
  },
  {
   "id": "p6-modern-32022",
   "file": "client/modern.py",
   "old": "if error.get(\"code\") == UNSUPPORTED_VERSION:",
   "new": "if error.get(\"code\") in (UNSUPPORTED_VERSION, -32601):",
   "command": "python3 -m unittest tests.test_client_modern",
   "note": "other errors reported as unsupported version"
  },
  {
   "id": "p6-modern-gate-off",
   "file": "client/modern.py",
   "old": "        if not self.ready:\n            raise NotDiscovered",
   "new": "        if False:\n            raise NotDiscovered",
   "command": "python3 -m unittest tests.test_client_modern",
   "note": "requests allowed before discover"
  },
  {
   "id": "p6-modern-ready-early",
   "file": "client/modern.py",
   "old": "        params = envelope({}, self.capabilities)\n",
   "new": "        params = envelope({}, self.capabilities)\n        self.ready = True\n",
   "command": "python3 -m unittest tests.test_client_modern",
   "note": "ready before the version check"
  },
  {
   "id": "p6-modern-state-dropped",
   "file": "client/modern.py",
   "old": "            if result.request_state is not None:\n                current[\"requestState\"] = result.request_state\n",
   "new": "",
   "command": "python3 -m unittest tests.test_client_modern",
   "note": "requestState not echoed"
  },
  {
   "id": "p6-modern-stale-retry",
   "file": "client/modern.py",
   "old": "            current = dict(base)\n            current[\"inputResponses\"]",
   "new": "            current = dict(current)\n            current[\"inputResponses\"]",
   "command": "python3 -m unittest tests.test_client_modern",
   "note": "a retry inherits the previous round's fields (stale requestState); expected to SURVIVE"
  },
  {
   "id": "p6-modern-rounds",
   "file": "client/modern.py",
   "old": "for number in range(1, max_rounds + 1):",
   "new": "for number in range(1, max_rounds):",
   "command": "python3 -m unittest tests.test_client_modern",
   "note": "one request fewer than max_rounds (the break at max_rounds makes an upward mutant equivalent)"
  },
  {
   "id": "p6-modern-sub-key-type",
   "file": "client/modern.py",
   "old": "self._by_id.setdefault(key_of(meta[SUBSCRIPTION_ID]), []).append(message)",
   "new": "self._by_id.setdefault(key_of(str(meta[SUBSCRIPTION_ID])), []).append(message)",
   "command": "python3 -m unittest tests.test_client_modern",
   "note": "subscription id type dropped"
  },
  {
   "id": "p6-modern-wait-method",
   "file": "client/modern.py",
   "old": "if message.get(\"method\") == method and (match is None or match(params)):",
   "new": "if match is None or match(params):",
   "command": "python3 -m unittest tests.test_client_modern",
   "note": "a stream's wait_for takes any method; expected to SURVIVE"
  },
  {
   "id": "p6-modern-wait-consume",
   "file": "client/modern.py",
   "old": "                        del self._by_id[key][i]\n",
   "new": "",
   "command": "python3 -m unittest tests.test_client_modern",
   "note": "a notification is read twice"
  },
  {
   "id": "p6-check-input-required",
   "file": "tap/check.py",
   "old": "if result_type == \"input_required\" and \"InputRequiredResult\" in defs:",
   "new": "if result_type == \"input_required_\" and \"InputRequiredResult\" in defs:",
   "command": "python3 -m unittest tests.test_check",
   "note": "input_required checked against the method's result"
  },
  {
   "id": "p6-check-task-other-method",
   "file": "tap/check.py",
   "old": "if method != \"tools/call\":",
   "new": "if method == \"tasks/get\":",
   "command": "python3 -m unittest tests.test_check",
   "note": "task on another method accepted"
  },
  {
   "id": "p6-check-name-collision",
   "file": "tap/check.py",
   "old": "        if def_name in schema.defs:\n",
   "new": "        if False:\n",
   "command": "python3 -m unittest tests.test_check",
   "note": "extension may shadow a pinned definition"
  },
  {
   "id": "p6-check-method-collision",
   "file": "tap/check.py",
   "old": "        if method in pinned_methods:\n",
   "new": "        if False:\n",
   "command": "python3 -m unittest tests.test_check",
   "note": "extension may shadow a pinned method"
  },
  {
   "id": "p6-check-ref-resolve",
   "file": "tap/check.py",
   "old": "if not ref.startswith(\"#/$defs/\") or ref[len(\"#/$defs/\"):] not in merged:",
   "new": "if not ref.startswith(\"#/$defs/\"):",
   "command": "python3 -m unittest tests.test_check",
   "note": "unresolved extension $ref not caught at load"
  },
  {
   "id": "p6-check-label",
   "file": "tap/check.py",
   "old": "        if definition in schema.extension_defs:\n",
   "new": "        if False:\n",
   "command": "python3 -m unittest tests.test_check",
   "note": "extension frames not labelled"
  },
  {
   "id": "p6-check-by-method",
   "file": "tap/check.py",
   "old": "    schema.by_method = methods_of(merged)\n",
   "new": "",
   "command": "python3 -m unittest tests.test_check",
   "note": "extension methods not indexed"
  }
 ]
}
```

##### Not reported

- `p5-diff-cancel-method-gate` survives, but for real traffic only `notifications/cancelled`
  carries `params.requestId`; I did not count it as a finding. A one-line test with a
  `notifications/progress` holding a `requestId` would kill it if wanted.
- `ModernTour.input_required` ignores its expected round counts (`_rounds`, `client/modern.py:541`)
  and prints "three rounds answered" unchecked, but `ModernTourTest::test_tour_2026_runs_every_step`
  pins the exact method sequence and ids 0-29, which fixes the number of retries. Dropped.
- `Registry.feed` with an unhashable `subscriptionId` (array or object) raises inside the
  reader's callback; the wire's per-line guard (phase 2 P2-R1 fix) reports it and the reader
  survives; the notification is still on the wire's queue. Not a hang. Dropped.
- The departure "a later request claiming another version on a pinned connection is served":
  `versioning.mdx` makes the version per request but only requires `-32022` for a version the
  server does not support, and this server supports `2025-11-25`. Arguable either way; not
  reported.
- Held up: `tap.diff`'s keys and typed equality (all C1/C2 mutants but the one above killed);
  `tap.check`'s two phase 6 rules and the loader guards (all killed); the SEP-2663 transcription
  (every definition matches its cited declaration and MUST line); `classify_result`; the
  discover gate (no request leaves before the reply, reproduced by the unit test and a mutant);
  `envelope` (caller `_meta` kept, reserved keys overwritten, a deep copy); the CLI era rules;
  manual mode's discover-first in 2026; lesson 06's `--no-extensions` count (10) and
  `12 of 18 frames` line against a fresh trace.

##### Not covered (budget)

- The SDK `server-tour` (`clients/sdk/src/server_tour.ts`) and `handlers.ts` beyond reading their
  call sites; `clients/sdk/test/*.test.ts` were not run (`node --test`).
- Walkthrough `06-sdk-2026.md` and walkthrough 05's per-note text, beyond the progress claims;
  lesson 05's and 06's G9 blocks were not run (P8-R5-1 would fail the SDK ones under load).
- `record.sh`'s missing-`node_modules` path and allowlist for the SDK modes (covered by e2e C11,
  not re-run); `tools/check_citations.py`'s `sdk` root tests (read only).
- The SDK cancel step (other agent) and every phase 7 HTTP path.

## 2. Phases 3, 4 and 7

### Disposition

Branch `phase-08-fix-r34` for the phase 3 and 4 findings (the C rows are in
`specs/phases/08-final-pass/validation.md`; the orchestrator renumbers them at merge). The
phase 7 rows are other fixers' or the orchestrator's: their cells say where each stands, and the
orchestrator finalizes the pending ones.

| Finding | Severity | Disposition | Commit and test (C row) |
| --- | --- | --- | --- |
| P8-R3-1 | minor | reproduced (a request with non-object `params` got no reply and the worker raised `AttributeError`; the new test blocked on the missing reply), fixed: `answer` returns `-32602` for non-object `params`, and `_respond` turns a malformed shape into `-32602` under the request's id | `ffeacdd`; `tests/test_client_handlers.py::HandlersTest::test_malformed_params_still_get_a_reply_under_the_id` (C80) |
| P8-R3-2 | minor, false claim | reproduced by the reviewer's inline-handler experiment (the tour passes with the reply on the reader thread), fixed: lesson 03's Predict 3 answer and its source note now say what the worker thread buys (a slow handler does not stall the reader) | `0c95cbb`; `tests/test_walkthrough_03_04.py::Doc03Test::test_lesson_03_predict_3_is_not_a_deadlock` (C81) |
| P8-R3-3 | minor, false claim | reproduced by reading the pinned `schema.ts:2485` (`number`), fixed: walkthrough 03 says `schema.ts` allows `number`, the generated JSON schema (`tap.check`) only `integer` | `0c95cbb`; `tests/test_walkthrough_03_04.py::Doc03Test::test_walkthrough_03_elicit_number_matches_schema_ts` (C82) |
| P8-R4-1 | minor, docs | reproduced by reading `schema.ts:159-163` (`id` optional on an error response), fixed: lesson 04's answer 1 says no id can be read, the schema allows an error without one, this server only logs | `0c95cbb`; `tests/test_walkthrough_03_04.py::Doc04Test::test_lesson_04_array_has_a_reply_form` (C83) |
| P8-R4-2 | minor, false claim | reproduced from the fixture (`{"id":1,...}`), fixed: walkthrough 04 says the SDK drops the message at validation and could have answered `-32600` with `id` 1 | `0c95cbb`; `tests/test_walkthrough_03_04.py::Doc04Test::test_walkthrough_04_missing_jsonrpc_has_an_id` (C84) |
| P8-R7-1 | major | fixing on `phase-08-fix-r7-1` | pending that branch |
| P8-R7-2 | major | pending (after Stage A) | pending |
| P8-R7-3 | major | Stage A | Stage A |
| P8-R7-4 | minor | pending (after Stage A) | pending |
| P8-R7-5 | minor | fixing on `phase-08-fix-r7-client` | pending that branch |
| P8-R7-6 | minor | fixing on `phase-08-fix-r7-client` | pending that branch |
| P8-R7-7 | minor | fixing on `phase-08-fix-r7-client` | pending that branch |
| P8-R7-8 | minor | fixing on `phase-08-fix-r7-client` | pending that branch |
| P8-R7-9 | minor | pending (after Stage A) | pending |
| P8-R7-10 | minor, test gap | fixing on `phase-08-fix-r7-client` | pending that branch |
| P8-R7-11 | minor, test gap | fixing on `phase-08-fix-r7-client` | pending that branch |
| P8-R7-12 | minor | pending (after Stage A) | pending |
| P8-R7-13 | minor | pending (after Stage A) | pending |
| P8-R7-14 | minor | reproduced (`fake_mcp_http.py`, DELETE `500` and never answered), fixed: `Lab.close` gives the DELETE `CLOSE_WAIT` (5 s), always closes the SDK client, and throws; `tour`, `server-tour` and the 2026 tour print that as a `FAILED` close step and exit 1 | branch `phase-08-fix-sdk`; `clients/sdk/test/close.test.ts` (C140) |
| P8-R7-15 | minor, false claim | fixing on `phase-08-fix-r7-client` | pending that branch |

### The report as written

The report follows unchanged except that its headings are three levels lower. The finding
numbers are as the reviewer wrote them.

**COMPLETE.** First pass stopped for usage before M07-14 to M07-19; a second pass (same day, a
fresh reviewer agent, Opus 5.5) ran them and the "Not covered" items it could reach within its
budget. What is still open is listed under *Not covered*.

#### Phase 8 final-pass review (LP4/RP): phase 7 in full, claim code of phases 3 and 4

Reviewer: an independent agent (Opus 5.5) that did not build this work; the builders were Sonnet.
Date: 2026-11-14. Scope, from `git log` on `main` at `bf650e7`: phase 7, `7ae71f5..2455768`
(`tap/http.py`, `client/http_wire.py`, `client/http_tour.py`, `client/modern_http.py`, the HTTP
parts of `clients/sdk/src/` with `stream.ts` and the C29 re-list, the `--http` block of
`scripts/record.sh`, `tests/test_tap_http.py`, `tests/test_client_http.py`,
`tests/test_e2e_http.py`, `docs/lessons/07-*`, `docs/walkthrough/07-*`); phase 3 claim code,
`c72ef4c..e9373d1` (`client/handlers.py`); phase 4 claim code, `83a74b2..2eb7a00`
(`tests/drive.py`, the fault path of `tap/__main__.py`); lessons 03 and 04 for false protocol
claims only. Contracts: `specs/phases/07-streamable-http/requirements.md` and `validation.md`,
the "Claim code" sections of `specs/phases/03-server-initiated/validation.md` and
`specs/phases/04-edge-lab/validation.md`, and the pinned spec (`vendor/spec`, 2025-11-25 and
2026-07-28 Streamable HTTP). The 2026-10-23 register row and A46 are taken as accepted and not
re-litigated.

##### What I ran

- Unit modules: `tests.test_client_http` (20 tests, OK) and `tests.test_tap_http` (30 tests, OK,
  run with `TMPDIR` pointed at a private folder so its leaks could be counted, P8-R7-3). The full
  gate and the full e2e suites were not run (another agent's stress run shares the machine). One
  e2e test, `HttpTourTest.test_without_the_stream_roots_list_never_arrives`, with
  `-W always::ResourceWarning -X tracemalloc` to find the ResourceWarning (P8-R7-4).
- One recording, `scripts/record.sh --http --client http-tour`: exit 0, 73 records, `tap.check
  --revision 2025-11-25` ok (19 frames), `tap.show --explain` with walkthrough 07 exits 0. Its
  statuses (seven `200`, four `202`), stream ends (five `by server`, one `by client`), the session
  header on every request after `initialize`, `roots/list` on the GET exchange,
  `sampling/createMessage` on its call's exchange before that call's response, and the GET
  stream ending before the DELETE's `200` all match lesson 07 and the walkthrough. The run folder
  was removed afterwards.
- Probe scripts (in the scratchpad, `review/p347/`): a fake Unix-socket upstream that delays its
  response head and watches for the peer's disconnect (P8-R7-2); a fake upstream that sends one
  large SSE event, timed through the tap, and the same parser fed directly (P8-R7-1); an
  in-process fake HTTP server for the raw client (P8-R7-5 to P8-R7-8); a fake wire for
  `Handlers` (P8-R3-1).
- 19 single-edit mutants of `tap/http.py` and `client/http_wire.py` (C2, C4, C11-C15, C24, C25),
  each run against the tests its row names, on a temporary copy of the tree with `vendor`
  linked: 13 of 19 were run in the first pass: 11 killed, 2 survived (M07-09, M07-10; P8-R7-10, P8-R7-11). The second pass ran M07-14 to M07-19 (below). The candidate list is in *Mutation candidates* and in `mutants-07.json`.

Second pass (scratch folder `b347/` in that agent's scratchpad; nothing in any checkout or worktree
was edited):

- A fresh copy of `main` at `bf650e7` by `git archive` (not a git repo; `vendor` and
  `clients/sdk/node_modules` symlinked to the real ones), and `tools/mutate.py` from branch
  `phase-08-mutate-tool` (`32a03c1`) run against it:
  `TMPDIR=<scratch>/tmp python3 tools/mutate.py --root <copy> --only M07-14,…,M07-19 --timeout 240 mutants-07.json`.
  The baselines were green, `runs/` was empty in the root and the copy, every target was restored
  byte-identical, and the run printed `mutants: 6 killed: 6 survived: 0 errors: 0`. Because the tool
  does not name failing tests, each mutant was then re-applied to a second copy and its command
  re-run with `-v` and a `faulthandler` watchdog to name the killing test (recorded per mutant in
  `mutants-07.json`, fields `result` and `killed_by`).
- One stdio recording, `scripts/record.sh --client server-tour w03` (node v24.22.0), to check
  lesson 03's and walkthrough 03's numeric claims: 21 tools after the capabilities, client ids 0 to
  17, four messages with `"id": 0`, six `tools/list_changed` and two `tools/list`, the first
  `roots/list` 363 ms after `initialized`, `number` answered as `3`. All held.
- An inline-handler experiment on a copy (`Handlers.handle_request` answering on the reader thread)
  for lesson 03's Predict 3 (P8-R3-2).
- Probe scripts: `p_load.py` (N concurrent POSTs through the tap to `tests/fake_servers/http_upstream.py`,
  half `/sse`, half `/slow`, each followed by a keep-alive `/json`; checks every reply and the
  trace: dense `seq`, dense exchange numbers, request before response, one `http-end` per stream)
  (P8-R7-12); `p_pipeline.py` (a stream with a pipelined request behind it, then a hang-up)
  (P8-R7-13); `fake_mcp_http.py`, a minimal Streamable HTTP server whose DELETE answers 200, 500
  or never, and whose requests may be answered with `application/json`, driven by the SDK client
  with `--url` and by `client.http_tour` (P8-R7-14, P8-R7-15).
- Every process started was stopped (the taps by SIGINT, which they forward); `pgrep` showed no
  leftover `http_upstream.py`, `fake_mcp_http.py` or SDK client of mine. The `runs/` folder of the
  recording and the scratch copies were removed at the end.
- Spec text checked for the claims below: 2025-11-25 `basic/transports.mdx` (POST, GET, `202`,
  `404`, DELETE, `MCP-Protocol-Version`), 2026-07-28 `basic/transports/streamable-http.mdx`
  (cancellation by closing the stream, `Mcp-Name` value encoding), the 2025-11-25 schema's
  `JSONRPCErrorResponse`.

Counts: 0 blockers, 3 majors, 17 minors (the first pass's count of 11 minors was a miscount of 10;
the second pass adds 7). Mutants: 19 run, 17 killed, 2 survived (P8-R7-10, P8-R7-11).

##### Majors

###### P8-R7-1: the tap's SSE parser rescans its whole buffer for every piece, so forwarding a large event takes quadratic time

- Severity: major (reproduced; the pinned server's own tours send small events, so no recorded
  tour is slowed today, but any server reply of about a megabyte through the tap is)
- File: `tap/http.py:107-124` (`SseParser.feed`), `tap/http.py:477-480` (`pump_stream` parses a
  piece before forwarding it)
- Claim: D3 and C4 say each piece of a response is "forwarded and flushed as soon as it is read",
  because streaming is "a correctness requirement here, not a speed-up". `feed` appends each piece
  to `self._buf` and then looks for the next line end with
  `next((i for i, b in enumerate(self._buf) if b in b"\r\n"), None)`, a Python-level loop over
  every byte from the start of the buffer. While one long `data:` line is arriving no line end is
  found, so each new piece rescans everything received so far, and `pump_stream` holds the piece
  until the scan ends (the record must precede the forwarding, D1). The cost grows with the square
  of the event's size, and it is paid on the proxy thread before the client gets any of the bytes.
- Reproduction: `p_sse.py` feeds one event of N bytes to `SseParser` in 64 KiB pieces: 256 kB
  0.17 s, 1 MB 1.89 s, 2 MB 6.66 s. Through the tap (`p_big.py`: a fake upstream on the tap's
  socket sends `data: {"jsonrpc":"2.0","id":1,"result":{"blob":"x…"}}` chunked in 16 KiB pieces;
  a plain `http.client` POST reads the reply): a 1 MB event took 17.9 s end to end, a 3 MB event
  132.7 s. The raw client's request timeout is 30 s (`client/wire.py:28`), so a 2 MB reply through
  the tap already times out a request that succeeds without it.
- Proposed fix: keep the parser linear. Scan only the bytes not yet scanned (keep an offset), find
  line ends with `bytes.find(b"\n", start)` and `bytes.find(b"\r", start)` (C speed) and take the
  smaller, and hold the buffer in a `bytearray` trimmed once per `feed`. Add a C2 test that feeds a
  4 MB event in 16 KiB pieces and requires it to parse in well under a second, and a C4 test that
  sends a 2 MB event through the tap within a few seconds.
- Disposition:
- Status:

###### P8-R7-2: a client that hangs up before the response head is not passed on, so the server never sees the disconnect and the trace shows a response the client never got

- Severity: major (reproduced; in the 2026-07-28 era closing the connection is the cancellation
  itself, and most of that era's replies are plain JSON, M13)
- File: `tap/http.py:323-342` (`open_upstream` blocks in `getresponse()` with no watch on the
  client), `tap/http.py:352-381` (`exchange`), `tap/http.py:430-466` (the disconnect watch runs
  only inside `pump_stream`)
- Claim: D3 says "When the client disconnects mid-stream the tap closes the upstream connection,
  so the server sees the disconnect as it would without the tap (`http-end` by `client`)". The
  watch thread that implements this starts only once an event-stream head has arrived. Before the
  head, and for every non-SSE body, nothing watches the client. A client that cancels a request
  whose head has not come yet is invisible to the server: the tap's upstream connection stays
  open, the server finishes the work and answers, and the tap records `http-response` and an `s2c`
  frame as if the client had read them, with no `http-end` saying it had gone. In the 2026-07-28
  era the transport spec makes that close the cancellation: "Closing the SSE response stream
  **MUST** be treated by the server as cancellation of that request"
  (`spec:docs/specification/2026-07-28/basic/transports/streamable-http.mdx:235`), and the pinned
  server answers most 2026 requests with `application/json`, whose head comes only with the result
  (M13; the 2026 tour measured 25 of 30 answers as JSON). A 2026 request cancelled before its
  answer is therefore never cancelled at the server when the session is recorded, and the trace
  misreports it. The shipped tours do not hit this today: their cancelled calls send progress
  first, so their heads have arrived.
- Reproduction: `p_slowhead.py`. `up_slowhead.py`, run by the tap as its server, holds the head of
  `POST /slowhead` for 4 s while it polls its socket with `recv(1, MSG_PEEK)` for the peer's close.
  The client posts, waits 0.5 s, then shuts down and closes its connection. Observed:
  `/slowhead disconnect_seen_after=None` (the server never saw the close), and the trace holds
  `tap http-response {'exchange': 0, 'status': 200, …}` and `s2c {"jsonrpc":"2.0","id":1,"result":{}}`
  for exchange 0, then `exit`, with no `http-end`.
- Proposed fix: start the client watch as soon as the request has been sent upstream, before
  `getresponse()`, and keep it running for every response kind, not just event streams. When it
  fires, shut down the upstream socket, which wakes `getresponse()` or `read1()` with an error. Then
  record `http-end` `by: client` for the exchange (D1 has no `http-end` for a non-stream body
  today; this case needs one, or a register row naming another record). Add a C5 test with an
  upstream that delays its head and reports whether it saw the disconnect.
- Disposition:
- Status:

###### P8-R7-3: `tests/test_tap_http.py` leaves orphan fake servers and temp directories behind on every run

- Severity: major (reproduced; eight `python3` processes that never exit and six directories per
  run of the module, on every developer gate run; CI hides it by killing orphan `python3` at job
  end)
- File: `tests/test_tap_http.py:79,89-92` (`Tap._kill` sends SIGKILL), `tap/http.py:569-577`
  (the child runs in its own process group), `tap/http.py:539,602` (the private directory is
  removed only on a normal exit)
- Claim: each test that does not call `tap.stop()` ends with the cleanup `_kill`, which
  SIGKILLs the tap. A killed tap cannot forward a signal or remove its directory. Its child, the
  fake upstream, runs in its own process group (`process_group=0`, D2), so nothing else reaches it.
  The fake serves forever, so it outlives the test run, and the tap's 0700 directory with its
  `server.sock` stays in the temp directory.
- Reproduction: `TMPDIR=<private dir> python3 -m unittest tests.test_tap_http` (30 tests, OK),
  then `pgrep -f 'fake_servers/http_upstream.py <private dir>'`: 8 processes still running;
  `find <private dir> -name server.sock`: 6 left. The same happens with two tests alone
  (`HttpForwardTest.test_upstream_host_is_localhost` and `…test_events_reach_client_before_stream_ends`):
  2 orphans, 2 directories. I killed them and removed the directories.
- Proposed fix: in `Tap._kill`, send SIGINT (the tap forwards it and cleans up, D2), wait a few
  seconds, and only then SIGKILL. Before that SIGKILL, read the child's pid from the trace's
  `listen` record or `/proc` and kill the child's process group too. Add a module-level check, for
  example a `tearDownModule` that fails if any `http_upstream.py` started by this module is still
  alive.
- Disposition:
- Status:

##### Minors

- **P8-R7-4** (minor) `tests/test_e2e_http.py:319-338`: the ResourceWarning in `test_e2e_http`.
  The tap's `stderr=subprocess.PIPE` is never closed: `ResourceWarning: unclosed file
  <_io.TextIOWrapper name=4>`, allocated at `test_e2e_http.py:319` `tap = subprocess.Popen(`
  (tracemalloc). The pipe is also never read after `tap: listening`, so a server that logs more
  than a pipe buffer (64 KiB) would block the tap's log relay (`relay_log` → `write_all(2, …)`) and
  then the server's own stdout. Fix: send the tap's stderr to a file in `tmp` (as `record.sh` and
  lesson 07 do) and poll it for the listening line, or close `tap.stderr` in the `finally`.
  Disposition: Status:
- **P8-R7-5** (minor) `client/http_wire.py:443-467`, `:213`: `HttpSession.close()` waits forever
  for a DELETE that is never answered. `_send` clears the socket timeout, and `terminate` calls
  `getresponse()` unbounded. D8 bounds a request's wait by phase 2 D2's timeout; nothing bounds
  this one, and `record.sh` then waits forever too. `p_wire.py`, with a fake that never answers
  DELETE: `close() … still running after 8.0 s: True`. Fix: give the DELETE's socket the session's
  timeout (`self.grace` or `self.timeout`) before `getresponse()`, and report a timeout as "no
  answer to DELETE". Disposition: Status:
- **P8-R7-6** (minor) `client/http_wire.py:193-194,238`, `client/wire.py:219-224`: the refusal of
  a non-ASCII `Mcp-Name` (C24) raises `ValueError` inside `_write`, but `start_request` cleans up
  only on `OSError`, so the request's `Pending` stays in the table until the session closes.
  `p_wire.py`: `pending entries left after the refusal: 1`. `Era2026Test.test_non_ascii_name_is_refused`
  checks only that nothing was sent. Fix: run the header check in an `HttpWire.start_request`
  override before the id is allocated, or raise an `OSError` subclass; extend the test to assert
  that the pending table is empty. Disposition: Status:
- **P8-R7-7** (minor) `client/http_wire.py:193`: a name with leading or trailing whitespace is sent
  as a plain `Mcp-Name`. The spec says such a value "**MUST** use Base64 encoding"
  (`spec:docs/specification/2026-07-28/basic/transports/streamable-http.mdx:481-483`, "has
  leading/trailing whitespace"). HTTP strips optional whitespace, so the header no longer matches
  the body. `p_wire.py`: for `{"name": " echo "}` the server received `Mcp-Name: 'echo '`. The
  Base64 form is out of scope (D14), so the client should refuse such a name as it refuses
  non-ASCII. Fix: also refuse a name whose first or last character is a space or tab.
  Disposition: Status:
- **P8-R7-8** (minor) `client/http_wire.py:354-357`: C12 says an error status "fails the posted
  request at once unless its body carries a non-null id". A body whose JSON-RPC error carries a
  *different* non-null id is handed to the line handler. That reports "a reply with an unknown id",
  and the posted request then waits its full timeout. `p_wire.py`, `400` with
  `{"id":999,"error":…}` for request id 1: `TimeoutError after 4.0 s` (timeout 4 s), where the
  request should fail at once. Fix: take the body as the reply only when its id equals the posted
  request's id; otherwise fail the post with `HttpStatusError` (and still hand the body to the
  handler if you want it reported). Disposition: Status:
- **P8-R7-9** (minor) `tap/http.py:114-116,126-131`: CR-only line endings at the end of a piece or
  of the stream. A stream whose last bytes are `data: x\r\r` has its blank line, so a client
  dispatches the event, but the tap records it `partial: true`: `finish()` strips the final `\r`
  as if it were half a CRLF and then sees no blank line (`p_sse.py`: `finish -> SseEvent(data=b'x',
  …, partial=True)`). The same wait-for-the-next-byte rule means that a CR that ends a piece delays
  the event's record until the next piece. That piece has been forwarded by then, so the record
  follows the bytes that completed the event, against D1's order. The pinned server writes LF only,
  so no recorded trace is affected. Fix: in `finish()`, treat a trailing lone `\r` as a line end
  (feed an empty line); accept the D1 order caveat for a CR split from its LF, or note it in
  *Accepted limits*. Disposition: Status:
- **P8-R7-10** (minor, test gap) `tests/test_client_http.py` (C11): no test negotiates a version
  other than the one the client asks for, so nothing checks that `MCP-Protocol-Version` carries
  the *negotiated* version, as the spec requires (`spec:docs/specification/2025-11-25/basic/transports.mdx:265`).
  Mutant M07-09 (`self.protocol_version = PROTOCOL_VERSION`, ignoring the server's choice)
  survives `HttpWireTest`. Fix: add a fake whose `initialize` result says `2025-06-18` and assert
  that header on the later POSTs, the GET and the DELETE. Disposition: Status:
- **P8-R7-11** (minor, test gap) `tests/test_client_http.py` (C14/C11): mutant M07-10 (the GET sent without `Accept: text/event-stream`) survives `HttpStreamTest` and `HttpWireTest`. The spec requires that header on the GET (`spec:docs/specification/2025-11-25/basic/transports.mdx`, "Listening for Messages from the Server"). Fix: assert the GET's `accept` header in `test_stream_opens_before_initialized`. Disposition: Status:
- **P8-R3-1** (minor) `client/handlers.py:148-156,173-175,207-209`: a server request with `params`
  that is not an object, or an elicitation whose schema property is not an object, gets no reply
  at all. `answer` raises `AttributeError` on the worker thread, `_respond` catches only `OSError`,
  and the server waits for an answer that never comes. JSON-RPC answers every request, and phase 3
  C1 says "Each server request is answered with its own id". `p_handlers.py`, four requests
  (`ping` with `params: [1]`, `roots/list` with `params: "x"`, `elicitation/create` with
  `properties: {"a": "notadict"}`, a plain `ping`): `replies sent for ids: [3]` and three worker
  `AttributeError`s. Fix: check `isinstance(params, dict)` in `answer`, and in `_respond` turn any
  exception from `answer` into `-32602` (invalid params) under the request's id. Add a C1 test with
  non-object params. Disposition: Status:
- **P8-R4-1** (minor, docs) `docs/lessons/04-edge-lab.md:164-166` (answer 1): "An array is not a
  valid message at all, so the parser throws before any id is read and there is nothing to reply
  to". There is a reply form for it. The 2025-11-25 schema's `JSONRPCErrorResponse` has an
  *optional* `id` (`vendor/spec/schema/2025-11-25/schema.ts:159-163`), and JSON-RPC 2.0 answers an
  invalid request with `-32600` and a null id. Lesson 07's experiment 6 shows this same server
  doing exactly that over HTTP (`"id":null`). The server's silence on stdio is allowed (no MUST),
  so walkthrough 04's verdict stands; only the lesson's reason is false. Fix: "…so no id can be
  read; the server could answer with an error that has no id (the schema allows one), but this one
  only logs to stderr". Disposition: Status:

Second-pass minors (reproduced unless marked):

- **P8-R7-12** (minor) `tap/http.py:220-224` (`Proxy` keeps `socketserver`'s default
  `request_queue_size = 5`): the tap's listen backlog is 5, so a burst of simultaneous connections
  is reset by the tap where the pinned server (Node, backlog 511) would accept them. The raw client
  opens one connection per message (`HttpWire._send`), so concurrent requests mean concurrent
  connects. D3 asks for the server to see what it would see without the tap. `p_load.py` (N
  concurrent POSTs, each with a keep-alive follow-up): N = 10 and 20, 3 runs each, all OK; N = 40:
  4, 1 and 0 of 40 failed with `ConnectionResetError(104)`; N = 60: 3, 13, 9; N = 100: 16, 27, 20;
  N = 200: 53, 41, 60. The same probe against a copy with only `request_queue_size = 128` added to
  `Proxy`: N = 200, 0 of 200 failed, twice. The failed connections never reach an exchange (the
  trace stays consistent: dense `seq`, dense exchange numbers, one `http-end` per completed stream).
  Fix: set `request_queue_size` on `Proxy` (128 or `socket.SOMAXCONN`). Test: a C3-style test that
  opens 64 connections at once through the tap and requires every reply.
  Disposition: Status:
- **P8-R7-13** (minor) `tap/http.py:437-442` (the watch in `pump_stream`): the disconnect watch
  stops for good as soon as the client sends any byte while the stream is open ("the client's next
  request is already queued; stop watching"). A client that pipelines its next request (HTTP/1.1
  allows it, RFC 9112 section 9.3) and then hangs up is not passed on: the upstream stays open and
  no `http-end` is written, against D3 ("the tap closes the upstream connection … `http-end` by
  `client`"). `p_pipeline.py`, POST `/hold` (one event, then silence): without a pipelined request,
  `http-end records 2 s after the client hung up: [{'exchange': 0, 'by': 'client', 'comments': 1}]`;
  with one, `[]`. No MCP client in the lab pipelines, so no recorded trace is affected. Fix: when
  data is queued, keep watching with `MSG_PEEK` on a timer (the bytes stay in the buffer) or detect
  the hang-up on the next forwarding write and record it; or add the case to *Accepted limits*.
  Disposition: Status:
- **P8-R7-14** (minor) `clients/sdk/src/tour.ts:172`, `clients/sdk/src/server_tour.ts:204`,
  `clients/sdk/src/client.ts:147-150` (`Lab.close`): over `--url`, `lab.close()` runs outside the
  `try` and awaits `terminateSession()` with no bound. A DELETE answered with an error throws out of
  `runTour`: Node prints the SDK's stack, the `close` step is never printed, and
  `client.close()` never runs. A DELETE that is never answered hangs the client (the lab sets no
  timeout; only undici's own header timeout would end it). `fake_mcp_http.py` (initialize answered,
  every other request `500`), `node clients/sdk/src/main.ts tour --url http://127.0.0.1:47811/mcp`:
  DELETE `200`: exit 1 after `2  close  closed`; DELETE `500`: exit 1, no `close` line, stderr
  `sdk: Failed to terminate session: Internal Server Error` then the stack from
  `@modelcontextprotocol/client/dist/index.mjs:5848`; DELETE never answered: still running when
  `timeout 25` killed it (exit 124). The raw client has the same unbounded wait (P8-R7-5). Fix: in
  `close`, wrap `terminateSession()` in `try`/`finally` (report the error, always `client.close()`),
  bound it with an `AbortSignal.timeout` passed through the `fetch` wrapper or a `Promise.race`;
  and call `lab.close()` inside a `try` in both tours. Test: a `node --test` with a fake DELETE that
  answers 500 and one that never answers.
  Disposition: Status:
- **P8-R7-15** (minor, false claim) `client/http_tour.py:12-15,45,205`,
  `docs/lessons/07-streamable-http.md:71-72`: "the tour exits 0 only if every step saw what the
  2025-11-25 transport predicts: `200` `text/event-stream` for a request, … `200` for DELETE". The
  transport predicts neither: a server "**MUST** either return `Content-Type: text/event-stream` …
  or `Content-Type: application/json`" and the client "**MUST** support both"
  (`spec:docs/specification/2025-11-25/basic/transports.mdx:101-104`), and it "**MAY** respond to
  this request with HTTP 405" for DELETE (`:219`). Those are the pinned server's choices. The tour
  fails a conforming server: `fake_mcp_http.py` answering with JSON,
  `python3 -m client.http_tour --url http://127.0.0.1:47812/mcp --slice` →
  `0  FAILED  TourFailure: request 0: expected HTTP 200 text/event-stream, saw 200 application/json`,
  exit 1. (The raw client itself handles the JSON body: `python3 -m client tour --url` against the
  same fake passes `initialize` and `initialized`.) Fix: say "what the pinned server does (the
  transport also allows `application/json` for a request and `405` for DELETE)" in the docstring,
  `TourFailure`, `run_http_tour` and lesson 07; the checks may stay strict, since the tour is
  written for the pinned server. Test: none needed beyond the text; `tests/test_lessons.py` keeps
  running the lesson.
  Disposition: Status:
- **P8-R3-2** (minor, false claim) `docs/lessons/03-server-initiated.md:250-252` (Predict answer 3,
  "A deadlock: the reader would wait for the handler to finish, and the handler's own reply path
  needs that reader to go on delivering the answer to the client's unanswered `tools/call`") and
  `:151-153` ("That is the answer to Predict 3: on one thread the client would wait for its own
  reader to deliver the reply to a request that the reader is itself busy answering"). In this
  client nothing in the answer path waits for the reader: `Handlers.answer` builds the reply
  locally and `send_message` writes it to the pipe. On a copy with `handle_request` changed to call
  `self._respond(message)` inline on the reader thread, `python3 -m client server-tour -- node
  vendor/servers/src/everything/dist/index.js stdio` exited 0 three times out of three with every
  step passed, and lesson 03's experiment 1 (`:sample typed by me`) still printed 2 lines. What the
  worker thread actually buys is shown by the C2 test, whose handler blocks
  (`tests/test_client_handlers.py:128-152`): a slow handler (a model, a user) would stall the
  reader, so the client's own replies, progress and cancellations would wait behind it, and a
  handler that itself sent a request and waited for its reply would deadlock. Fix: say that, and
  drop "A deadlock" as the answer for this client. Test: none (lesson text).
  Disposition: Status:
- **P8-R3-3** (minor, false claim) `docs/walkthrough/03-server-initiated.md:255-258`
  (`c2s.response.3`): "the schema's `ElicitResult` allows only strings, integers, booleans and lists
  of strings as values". The TypeScript schema, which the spec names as the source of truth
  (`spec:docs/specification/2025-11-25/basic/index.mdx:129`), allows `number`:
  `spec:schema/2025-11-25/schema.ts:2485` "content?: { [key: string]: string | number | boolean | string[] };".
  Only the generated `schema.json` says `integer` (`ElicitResult.content.additionalProperties`:
  `{"type": ["string", "integer", "boolean"]}`), because the generator maps a bare `number` to
  `integer` unless `@TJS-type number` is set. So `3.14` is valid by the spec and rejected only by
  `tap.check`, which validates against the JSON form. Fix: "the generated JSON schema (which
  `tap.check` uses) allows only integers there, though `schema.ts` says `number`; the client sends
  the integer part so the check passes". Test: none (walkthrough text).
  Disposition: Status:
- **P8-R4-2** (minor, false claim) `docs/walkthrough/04-edge-lab.md:92-93` (`stderr.1-106`,
  missing-jsonrpc): "the SDK never hands it to a request handler, so there is no `id` to put on an
  error reply". The message is `{"id":1,"method":"tools/list"}`
  (`tests/fixtures/edge-missing-jsonrpc.ndjson:3`): the id is there. The SDK drops it because its
  schema validation fails before routing, not for want of an id; JSON-RPC 2.0 would answer it
  `-32600` under that id (or `null` when none can be read). Same family as P8-R4-1. Fix: "the SDK
  drops it at validation, before any handler; it could have answered `-32600` with `id` 1, but this
  server only logs". Test: none (walkthrough text).
  Disposition: Status:

##### Mutation candidates

`mutants-07.json` (next to this report) holds 19 single-edit mutants in the `tools/mutate.py`
format, each `old` checked to occur exactly once in its file at `bf650e7`. (`tools/mutate.py`
is not on `main`; the first pass ran M07-01 to M07-13 with a small equivalent runner on a
temporary copy of the tree, the second pass ran M07-14 to M07-19 with `tools/mutate.py` from
branch `phase-08-mutate-tool`.) Results: M07-01 to M07-08 killed; M07-09 survived (P8-R7-10);
M07-10 survived (P8-R7-11); M07-11 to M07-19 killed. The second pass's six:

| id | row | result | killed by |
| --- | --- | --- | --- |
| M07-14 | C13 | killed (timeout, 240 s) | `tests/test_client_http.py::HttpWireTest::test_reply_to_server_request_while_its_stream_is_open` fails when run alone (`[False] != [True]`); in the module run `HttpWireTest::test_404_ends_the_session` runs first and blocks forever in the inline `_receive` (`http_wire.py:319` from `_write`, test line 286), so `tools/mutate.py` sees only its timeout |
| M07-15 | C14 | killed | `HttpStreamTest::test_stream_opens_before_initialized` |
| M07-16 | C15, C25 | killed | `HttpStreamTest::test_cancel_closes_the_response_stream`, `Era2026Test::test_cancel_closes_stream_without_notification` |
| M07-17 | C15 | killed | `HttpStreamTest::test_close_sends_delete_and_ends_streams` (ERROR) |
| M07-18 | C24 | killed | `Era2026Test::test_every_post_carries_the_request_headers` |
| M07-19 | C24 | killed | `Era2026Test::test_non_ascii_name_is_refused` |

M07-14 is killed, but only by a hang in the module run: `test_404_ends_the_session` has no
bounded wait, so a regression of this kind stalls the gate until its own timeout rather than
failing a named test. Not filed as a finding; the fix, if wanted, is a `timeout` on that test's
blocking call.

The list holds 19 entries rather than 10-15. Trim it by dropping M07-05, M07-06, M07-12 and
M07-17 if a shorter run is wanted.

One more mutant is equivalent and was left out: `session=not is_init` → `session=True` in
`HttpWire._write` changes nothing for a fresh wire, because `session_id` and `protocol_version`
are both `None` until the `initialize` reply. C11's "initialize carries neither" holds by state,
not by that argument.

##### Not covered

The six mutants are done; the first pass's list was worked through in this order, and this is
what is left.

- The SDK client over HTTP, beyond what P8-R7-14 shows: no SDK recording was made (`record.sh
  --http --client sdk-tour`, `sdk-server-tour`, `sdk-tour-2026`), so the C29 re-list and the 2026
  HTTP tour (`era.ts`, which builds its own transport without `watchStream`) were read, not run.
  `parseArgs`'s `--url` rules were read: `--url` must be last, and a value starting with `-` is a
  usage error; an invalid URL is not checked there and would throw from `new URL` at connect time
  (not run).
- `client/modern_http.py` was read and its method resolution checked
  (`ModernHttpSession.__mro__`: `close` and `initialize` come from `HttpSession`, `cancel` is its
  own, `discover` and `request` from `ModernSession`; a subscription's `close` goes through
  `cancel`, so it hangs up rather than sending `notifications/cancelled`). Not probed with a fake;
  `HttpSession.initialize`, a 2025 handshake, is reachable on a 2026 session but nothing calls it.
- The drain window at exit (an exchange still open 2 s after the server exits writes after `exit`
  and is dropped by `Trace`) was read, not probed. Keep-alive with sequential requests is covered by
  `p_load.py` (each connection carries a stream then a JSON exchange); only the pipelined case
  failed (P8-R7-13).
- Walkthrough 04 beyond reading: its per-experiment timings and stderr ranges (`about 280 ms`,
  `stderr.1-106`, `stderr.1-50`) were not re-recorded; the protocol claims were read against the
  fixtures and the spec (P8-R4-2). Walkthrough 03's frame notes were checked against one fresh
  trace (counts and the reply values), not note by note with `--explain` (the gate does that).
- `tap/show.py`'s HTTP summaries (C9, not claim code), and the `record.sh --http` port race (an
  accepted limit) were not probed.
- `tools/mutate.py` is phase 8's code and out of this scope, but one note for whoever reviews it:
  D8 asks it to record and print each mutant's failing tests and to honour an `equivalent` field;
  the version on `phase-08-mutate-tool` (`32a03c1`) prints neither (the killing tests above were
  found by hand).

##### Not reported

- The raw client's `sse_data` splits lines on LF only (`readline`), so a CR-only stream would
  never dispatch. Its docstring says "A line ends with LF or CRLF", which is honest, and the pinned
  server writes LF. Not a false claim.
- `tests/drive.py` matches ids with Python `==`, so a wanted id `1` also matches a reply with
  `"id": true` or `1.0`, and a server request that happens to reuse the id. No fixture uses such
  ids (edge fixtures use `0`-`3` and `"1"`, which stays distinct), so this is not reachable today.
- The tap's `--drop` path records the frame, then the `fault` record with its `seq`, and never
  forwards it; `--delay` records before holding. Both read correctly against C2 and C3. Phase 3's
  id echo keeps the id's type (C1 test checks `0`, `7`, `"s-1"`, `"7"`). The capability check
  refuses undeclared `roots` and `sampling` with `-32601` and an undeclared elicitation mode with
  `-32602`. The dispatch runs each answer on its own thread. I found no defect there beyond P8-R3-1.
- Lesson 07's protocol claims (one POST per message, `202` for notifications and replies, the
  session id first seen in the `initialize` response, `roots/list` only on the GET stream,
  `404` after DELETE through `sessionNotFound`, the GET stream ending before the DELETE's reply)
  match the spec text, the pinned source and my fresh trace.

#### Results of `mutants-07.json`

Nineteen single-edit mutants of `tap/http.py` and `client/http_wire.py`, in the `tools/mutate.py`
format (`links`: `vendor`, `clients/sdk/node_modules`), run on 2026-11-14 on a temporary copy of
the tree: 17 killed, 2 survived (M07-09 and M07-10, filed as P8-R7-10 and P8-R7-11).

| id | file | command | result | finding |
| --- | --- | --- | --- | --- |
| M07-01 | `tap/http.py` | `python3 -m unittest tests.test_tap_http.SseTest` | killed |  |
| M07-02 | `tap/http.py` | `python3 -m unittest tests.test_tap_http.SseTest` | killed |  |
| M07-03 | `tap/http.py` | `python3 -m unittest tests.test_tap_http.SseTest` | killed |  |
| M07-04 | `tap/http.py` | `python3 -m unittest tests.test_tap_http.SseTest` | killed |  |
| M07-05 | `tap/http.py` | `python3 -m unittest tests.test_tap_http.SseTest` | killed |  |
| M07-06 | `tap/http.py` | `python3 -m unittest tests.test_tap_http.SseTest` | killed |  |
| M07-07 | `tap/http.py` | `python3 -m unittest tests.test_tap_http.HttpForwardTest` | killed |  |
| M07-08 | `client/http_wire.py` | `python3 -m unittest tests.test_client_http.HttpWireTest` | killed |  |
| M07-09 | `client/http_wire.py` | `python3 -m unittest tests.test_client_http.HttpWireTest` | survived | P8-R7-10 |
| M07-10 | `client/http_wire.py` | `python3 -m unittest tests.test_client_http.HttpStreamTest tests.test_client_http.HttpWireTest` | survived | P8-R7-11 |
| M07-11 | `client/http_wire.py` | `python3 -m unittest tests.test_client_http.HttpWireTest` | killed |  |
| M07-12 | `client/http_wire.py` | `python3 -m unittest tests.test_client_http.HttpWireTest` | killed |  |
| M07-13 | `client/http_wire.py` | `python3 -m unittest tests.test_client_http.HttpWireTest` | killed |  |
| M07-14 | `client/http_wire.py` | `python3 -m unittest tests.test_client_http.HttpWireTest` | killed (timeout) |  |
| M07-15 | `client/http_wire.py` | `python3 -m unittest tests.test_client_http.HttpStreamTest` | killed |  |
| M07-16 | `client/http_wire.py` | `python3 -m unittest tests.test_client_http.HttpStreamTest tests.test_client_http.Era2026Test` | killed |  |
| M07-17 | `client/http_wire.py` | `python3 -m unittest tests.test_client_http.HttpStreamTest` | killed |  |
| M07-18 | `client/http_wire.py` | `python3 -m unittest tests.test_client_http.Era2026Test` | killed |  |
| M07-19 | `client/http_wire.py` | `python3 -m unittest tests.test_client_http.Era2026Test` | killed |  |

The JSON, with the exact `old` and `new` texts (also in `mutants-07.json` next to the review):

```json
{
 "links": [
  "vendor",
  "clients/sdk/node_modules"
 ],
 "mutants": [
  {
   "id": "M07-01",
   "file": "tap/http.py",
   "old": "                if end + 1 == len(self._buf):\n                    break  # a CR may be the first half of CRLF; wait for the next byte",
   "new": "                if False:\n                    break  # a CR may be the first half of CRLF; wait for the next byte",
   "command": "python3 -m unittest tests.test_tap_http.SseTest",
   "note": "C2: a CR at the end of a piece is taken as a line end at once, so a CRLF split across pieces makes a blank line and dispatches early",
   "result": "killed"
  },
  {
   "id": "M07-02",
   "file": "tap/http.py",
   "old": "            stop = end + 2 if self._buf[end + 1 : end + 2] == b\"\\n\" else end + 1",
   "new": "            stop = end + 1",
   "command": "python3 -m unittest tests.test_tap_http.SseTest",
   "note": "C2: CRLF read as CR then an empty line",
   "result": "killed"
  },
  {
   "id": "M07-03",
   "file": "tap/http.py",
   "old": "            value = value[1:]",
   "new": "            value = value.lstrip(b\" \")",
   "command": "python3 -m unittest tests.test_tap_http.SseTest",
   "note": "C2: every leading space removed, not just one",
   "result": "killed"
  },
  {
   "id": "M07-04",
   "file": "tap/http.py",
   "old": "        return SseEvent(b\"\\n\".join(self._data), self._id, self._event, self._retry)",
   "new": "        return SseEvent(b\"\".join(self._data), self._id, self._event, self._retry)",
   "command": "python3 -m unittest tests.test_tap_http.SseTest",
   "note": "C2: multi-line data joined without the newline",
   "result": "killed"
  },
  {
   "id": "M07-05",
   "file": "tap/http.py",
   "old": "        event.partial = True",
   "new": "        event.partial = False",
   "command": "python3 -m unittest tests.test_tap_http.SseTest",
   "note": "C2: an event cut off by the stream's end is not marked partial",
   "result": "killed"
  },
  {
   "id": "M07-06",
   "file": "tap/http.py",
   "old": "        if line.startswith(b\":\"):\n            self.comments += 1",
   "new": "        if line.startswith(b\":\"):\n            self.comments += 0",
   "command": "python3 -m unittest tests.test_tap_http.SseTest",
   "note": "C2: comments not counted in http-end",
   "result": "killed"
  },
  {
   "id": "M07-07",
   "file": "tap/http.py",
   "old": "                try:\n                    piece = resp.read1(CHUNK)",
   "new": "                try:\n                    piece = resp.read(CHUNK)",
   "command": "python3 -m unittest tests.test_tap_http.HttpForwardTest",
   "note": "C4: the event stream is read in 64 KiB blocks, so events wait for the block (buffering) and the M9 round trip stalls",
   "result": "killed"
  },
  {
   "id": "M07-08",
   "file": "client/http_wire.py",
   "old": "        extra = {\"Content-Type\": \"application/json\", \"Accept\": ACCEPT}",
   "new": "        extra = {\"Content-Type\": \"application/json\", \"Accept\": EVENT_STREAM}",
   "command": "python3 -m unittest tests.test_client_http.HttpWireTest",
   "note": "C11: POST Accept lists only text/event-stream",
   "result": "killed"
  },
  {
   "id": "M07-09",
   "file": "client/http_wire.py",
   "old": "            self.protocol_version = version if isinstance(version, str) else None",
   "new": "            self.protocol_version = PROTOCOL_VERSION",
   "command": "python3 -m unittest tests.test_client_http.HttpWireTest",
   "note": "C11: MCP-Protocol-Version is the requested version, not the negotiated one (fakes always negotiate the requested version)",
   "result": "survived",
   "finding": "P8-R7-10"
  },
  {
   "id": "M07-10",
   "file": "client/http_wire.py",
   "old": "        carrier = self._send(\"GET\", self._headers(session=True, extra={\"Accept\": EVENT_STREAM}))",
   "new": "        carrier = self._send(\"GET\", self._headers(session=True, extra={}))",
   "command": "python3 -m unittest tests.test_client_http.HttpStreamTest tests.test_client_http.HttpWireTest",
   "note": "C14/C11: the GET stream is sent with no Accept: text/event-stream (spec MUST)",
   "result": "survived",
   "finding": "P8-R7-11"
  },
  {
   "id": "M07-11",
   "file": "client/http_wire.py",
   "old": "            self._fail_post(message, kind, HttpStatusError(resp.status, text[:200]))",
   "new": "            self._report(f\"refused: {resp.status}\")",
   "command": "python3 -m unittest tests.test_client_http.HttpWireTest",
   "note": "C12: an error status no longer fails the request at once",
   "result": "killed"
  },
  {
   "id": "M07-12",
   "file": "client/http_wire.py",
   "old": "        if resp.status == 404 and self.session_id is not None:",
   "new": "        if resp.status == 410 and self.session_id is not None:",
   "command": "python3 -m unittest tests.test_client_http.HttpWireTest",
   "note": "C12: a 404 does not end the session",
   "result": "killed"
  },
  {
   "id": "M07-13",
   "file": "client/http_wire.py",
   "old": "                if data:  # the priming event has none",
   "new": "                if True:  # the priming event has none",
   "command": "python3 -m unittest tests.test_client_http.HttpWireTest",
   "note": "C12: the empty priming event is handed to the line handler",
   "result": "killed"
  },
  {
   "id": "M07-14",
   "file": "client/http_wire.py",
   "old": "        threading.Thread(target=self._receive, args=(carrier, message, kind, is_init),\n                         daemon=True).start()",
   "new": "        self._receive(carrier, message, kind, is_init)",
   "command": "python3 -m unittest tests.test_client_http.HttpWireTest",
   "note": "C13: each response read inline under the write lock, so a reply cannot be posted while its stream is open",
   "result": "killed (timeout)",
   "killed_by": "tests/test_client_http.py::HttpWireTest::test_reply_to_server_request_while_its_stream_is_open fails alone (Lists differ: [False] != [True]); in the module run tests/test_client_http.py::HttpWireTest::test_404_ends_the_session blocks first (no bounded wait), so the module run is killed only by the 240 s timeout"
  },
  {
   "id": "M07-15",
   "file": "client/http_wire.py",
   "old": "        if capabilities and stream:\n            self.http.open_stream()\n        self.wire.notify(\"notifications/initialized\")",
   "new": "        self.wire.notify(\"notifications/initialized\")\n        if capabilities and stream:\n            self.http.open_stream()",
   "command": "python3 -m unittest tests.test_client_http.HttpStreamTest",
   "note": "C14: the GET stream opens after notifications/initialized",
   "result": "killed",
   "killed_by": "tests/test_client_http.py::HttpStreamTest::test_stream_opens_before_initialized"
  },
  {
   "id": "M07-16",
   "file": "client/http_wire.py",
   "old": "            if carrier is not None:\n                carrier.hang_up()\n        return done",
   "new": "            if carrier is not None:\n                pass\n        return done",
   "command": "python3 -m unittest tests.test_client_http.HttpStreamTest tests.test_client_http.Era2026Test",
   "note": "C15/C25: cancelling does not close the request's stream",
   "result": "killed",
   "killed_by": "tests/test_client_http.py::HttpStreamTest::test_cancel_closes_the_response_stream, tests/test_client_http.py::Era2026Test::test_cancel_closes_stream_without_notification"
  },
  {
   "id": "M07-17",
   "file": "client/http_wire.py",
   "old": "            carrier = self._send(\"DELETE\", self._headers(session=True, extra={}))",
   "new": "            carrier = self._send(\"DELETE\", self._headers(session=False, extra={}))",
   "command": "python3 -m unittest tests.test_client_http.HttpStreamTest",
   "note": "C15: DELETE without the session headers",
   "result": "killed",
   "killed_by": "tests/test_client_http.py::HttpStreamTest::test_close_sends_delete_and_ends_streams (ERROR)"
  },
  {
   "id": "M07-18",
   "file": "client/http_wire.py",
   "old": "NAMED_METHODS = {\"tools/call\": \"name\", \"resources/read\": \"uri\", \"prompts/get\": \"name\"}",
   "new": "NAMED_METHODS = {\"tools/call\": \"name\", \"resources/read\": \"uri\"}",
   "command": "python3 -m unittest tests.test_client_http.Era2026Test",
   "note": "C24: no Mcp-Name for prompts/get",
   "result": "killed",
   "killed_by": "tests/test_client_http.py::Era2026Test::test_every_post_carries_the_request_headers"
  },
  {
   "id": "M07-19",
   "file": "client/http_wire.py",
   "old": "                if not all(0x20 <= ord(c) < 0x7F for c in name):",
   "new": "                if not all(0x20 <= ord(c) < 0x100 for c in name):",
   "command": "python3 -m unittest tests.test_client_http.Era2026Test",
   "note": "C24: Latin-1 names pass as plain ASCII",
   "result": "killed",
   "killed_by": "tests/test_client_http.py::Era2026Test::test_non_ascii_name_is_refused"
  }
 ]
}
```
