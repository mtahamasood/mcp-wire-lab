# Final-pass review (phase 8, D10): the corpus and its dispositions

One adversarial review round over phases 3 to 7 (`specs/phases/08-final-pass/requirements.md`
D10; row C8 of `validation.md`). Findings are numbered `P8-R<phase>-<n>`, as the reviewers wrote
them. Each was reproduced by the reviewer and, where it is fixed here, reproduced again before the
fix: a code defect by a probe or the failing test, a test gap by a surviving mutant that the new
test now kills (`python3 tools/mutate.py` on the survivor, run in a temporary copy).

Sections:

1. Phases 5 and 6 (reviewer: Opus 5.5): disposition table, then the report as written.
2. Phases 3, 4 and 7: not yet deposited (another reviewer is still finishing).

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
| P8-R6-4 | minor | not fixed on this branch: the fix is in `clients/sdk/src/era.ts`, which this branch does not touch (owned by another agent). Open; see the note below | none yet; a C row is added with the fix |
| P8-R6-5 | minor | reproduced by reading the pinned lines (`stdio.mdx:82`, `subscriptions.mdx:122`), fixed in `docs/walkthrough/06-era-2026.md` | `cb0f335`; `tests/test_walkthrough_06.py::EraDocTest::test_cancelled_listen_is_not_a_departure`, `::test_notification_is_never_given_an_error_code` (C27) |

Note on P8-R6-4: the SDK's `listen()` result holds only `honoredFilter`, `close` and `closed`; the
listen id the SDK sends (a string, `sdk:client/dist/index.mjs:4056`) is not exposed. The fix has
to read it from the traffic the tour already marks (the `subscriptions/listen` request's `id` on
the transport), then `expect` each list change and the resource update to carry it. That is a
small change to the SDK tour with a node test, not a one-liner, so it is handed to whoever owns
`clients/sdk/`. It does not change scope.

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

<!-- PLACEHOLDER: the phase 3, 4 and 7 corpus and its dispositions go here when the other
reviewer finishes. Number findings P8-R3-n, P8-R4-n, P8-R7-n. -->

Not yet deposited: another reviewer is still finishing phases 3, 4 and 7. This section is left
empty on purpose.
