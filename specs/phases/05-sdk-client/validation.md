# Phase 5 — SDK client, 2025 era (TypeScript, stdio): validation

Lean profile (LP1–LP6 in `mission.md`). Every C row names its checks in the G12 form (LP2); the
named tests are written in the build, before the code they check, and `05` joins G12's
`--phases` list when they exist (phase 2 D7, as amended). Inherited gates: G1–G5, G7–G12, green
via `scripts/gate.sh`, locally and in CI, with D5's TypeScript additions to G3 and G4 and D6's
`sdk` root in G8. G6 (clean-clone walk) is deferred (LP5).

## Claim code (RP3)

`tap/diff.py`: the message keys (D4: identity by direction, method and occurrence; a response
keyed by the request it answers, by direction and typed id; the `requestId` mapping) and the
comparison (typed JSON equality, member order ignored, array order kept, bytes-only pairs kept
apart). These decide which frames are compared and whether they are equal, so they are the sole
guard of the phase's central claim that the CI-checked explanation covers every real difference;
the keying is id correlation (LP4). Mutation testing runs on those two parts only.

Not claim code: `clients/sdk/` (glue over the SDK, which carries the protocol; checked end to end
by C5–C9), `tap.diff`'s output formatting and its `--explain` matching (phase 1 D11's note
machinery, reused), and the docs.

## C. Phase-specific correctness

| Row | Claim | Checks | Mutation |
| --- | --- | --- | --- |
| C1 | `tap.diff` keys each request and notification by direction, method and occurrence, and each response by the request it answers (direction and id, type included); a `notifications/cancelled` `requestId` is mapped to its request's key; two traces that differ only in how ids are numbered show no difference; non-message frames get their own keys | `tests/test_diff.py::KeysTest::test_requests_and_notifications_keyed_by_occurrence`, `tests/test_diff.py::KeysTest::test_response_keyed_by_the_request_it_answers`, `tests/test_diff.py::KeysTest::test_response_pairing_keeps_the_id_type`, `tests/test_diff.py::KeysTest::test_renumbered_ids_are_not_a_difference`, `tests/test_diff.py::KeysTest::test_cancelled_request_id_is_mapped`, `tests/test_diff.py::KeysTest::test_non_message_frames_keyed_apart` | yes |
| C2 | Equal means the same JSON value: member order ignored, array order kept, `1`, `1.0` and `true` distinct; a pair equal as JSON but not as bytes is counted, not reported; `progressToken` is compared as is; timings, `seq`, `stderr` and `tap` records are not compared | `tests/test_diff.py::EqualityTest::test_member_order_is_a_bytes_only_difference`, `tests/test_diff.py::EqualityTest::test_number_and_boolean_types_differ`, `tests/test_diff.py::EqualityTest::test_array_order_matters`, `tests/test_diff.py::EqualityTest::test_progress_token_is_not_normalised`, `tests/test_diff.py::EqualityTest::test_timings_and_non_messages_ignored` | yes |
| C3 | Output: a differing pair lists each differing JSON path with both values (`(absent)` for a missing member, values escaped and cut); one-trace-only keys are listed; the summary line counts every class; exit 0 only when nothing differs, 1 otherwise, 2 on a usage error or unreadable trace; `-h` prints the usage and exits 0 | `tests/test_diff.py::OutputTest::test_paths_and_values_listed`, `tests/test_diff.py::OutputTest::test_only_in_one_trace_listed`, `tests/test_diff.py::OutputTest::test_summary_and_exit_codes`, `tests/test_diff.py::OutputTest::test_unreadable_trace_exits_2`, `tests/test_help.py::HelpTest::test_help_prints_usage_on_stdout_and_exits_0` | not claim code (RP3) |
| C4 | `--explain` prints each entry with its note, reads only the named section plus `## shared`, expands `#a-b` anchors, and exits 1 on an entry with no note or a note with no entry | `tests/test_diff.py::ExplainTest::test_every_entry_needs_a_note`, `tests/test_diff.py::ExplainTest::test_note_without_entry_fails`, `tests/test_diff.py::ExplainTest::test_section_shared_and_ranges` | no (phase 1 D11's note matching, reused) |
| C5 | The SDK `tour` against the real server exits 0; its fresh trace holds phase 2 D3's client-to-server methods in the raw tour's order, with no request the raw tour does not send, and passes `tap.check --revision 2025-11-25` | `tests/test_e2e.py::SdkClientTest::test_sdk_tour_runs_the_raw_tour_steps`, `tests/test_e2e.py::SdkClientTest::test_sdk_traces_pass_schema_check` | not claim code (RP3) |
| C6 | The SDK `server-tour` against the real server exits 0 and its fresh trace holds every phase 3 D4 server-initiated method; its handlers return phase 3 D1's values with the SDK's client name | `tests/test_e2e.py::SdkClientTest::test_sdk_server_tour_sees_every_server_initiated_method`, `clients/sdk/test/handlers.test.ts` | not claim code (RP3) |
| C7 | The raw client's walkthroughs explain every frame of the SDK's fresh traces: walkthrough 02 for `sdk-tour`, walkthrough 03 for `sdk-server-tour`, no missing and no extra note | `tests/test_e2e.py::SdkClientTest::test_raw_walkthroughs_explain_sdk_traces` | not claim code (RP3) |
| C8 | The raw-vs-SDK diff of fresh traces is explained difference by difference: `tap.diff --explain docs/walkthrough/05-sdk-client.md#tour` and `#server-tour` exit 0 | `tests/test_e2e.py::SdkClientTest::test_tour_diff_is_explained`, `tests/test_e2e.py::SdkClientTest::test_server_tour_diff_is_explained` | not claim code (RP3) |
| C9 | The SDK client speaks only through the SDK: `clients/sdk/src/` imports nothing but `@modelcontextprotocol/client` (and its `/stdio` entry) and `node:` modules, and contains no `jsonrpc` literal, no `.send(` call and no `.stdin` access | `tests/test_sdk_client.py::SourceTest::test_only_the_sdk_speaks` | not claim code (RP3) |
| C10 | The SDK is pinned: `package.json` names `@modelcontextprotocol/client` `2.3.1` exactly, and the lockfile's integrity for it equals the pinned server's lockfile entry; bootstrap installs with `npm ci` and fails on another version; `tsc --strict` passes (G3); the argument parser accepts the modes, `--caps`, `--` and `--help` | `tests/test_sdk_client.py::InstallTest::test_sdk_pinned_to_the_servers_tarball`, `clients/sdk/package-lock.json`, `clients/sdk/tsconfig.json`, `scripts/bootstrap.sh`, `clients/sdk/test/args.test.ts` | not claim code (RP3) |
| C11 | `record.sh --client sdk-tour` and `sdk-server-tour` write a run folder with the allowlisted server environment and pass on the client's status; without `clients/sdk/node_modules` it exits 1 naming bootstrap and creates no run folder; the raw modes and the fixture form are unchanged | `tests/test_e2e.py::SdkClientTest::test_record_sdk_client`, `tests/test_e2e.py::SdkClientTest::test_record_without_install_fails_fast`, `scripts/record.sh` | not claim code (RP3) |
| C12 | G8 resolves `sdk:<path>:<line>` under `clients/sdk/node_modules/@modelcontextprotocol/`, rejects a path that leaves it, fails with a bootstrap hint when it is missing, and scans `clients/sdk/src/` and `clients/sdk/test/` but not `node_modules/` | `tests/test_citations.py::CitationsTest::test_sdk_root_resolves`, `tests/test_citations.py::CitationsTest::test_sdk_root_missing_fails_with_hint`, `tests/test_citations.py::CitationsTest::test_node_modules_not_scanned`, `tools/check_citations.py` | not claim code (RP3) |
| C13 | Lesson 05 has the L1 sections and its runnable blocks pass; its `exercises` line is true of fresh traces of its two recordings | `tests/test_lessons.py`, `tools/check_lessons.py`, `tests/test_e2e.py::AtlasClaimsTest::test_lesson_declarations_appear_in_fresh_traces` | not claim code (RP3) |

## E. Not-done conditions

Not done if the SDK client writes a JSON-RPC message itself or imports any MCP code other than
`@modelcontextprotocol/client` 2.3.1; if a fresh SDK trace fails `tap.check`; if a raw-vs-SDK
difference has no note or a note names no difference; if any C row names a check that does not
exist; or if run output is tracked.

## Result

- Status: built on the builder's branch, awaiting merge and the gate (builder run 2026-10-22).

Built 2026-10-22 under LP7 (tests alongside code, no mutation run, no review round). Measured
on this machine (Node 24.22.0) against the pinned, built server:

- Fresh traces: SDK `tour` 41 frames, SDK `server-tour` 74 frames, both pass
  `tap.check --revision 2025-11-25`; walkthroughs 02 and 03 explain them with no missing or extra
  note.
- `tap.diff` of fresh raw and SDK traces: tour 41 pairs, 20 equal, 14 equal as JSON but not as
  bytes, 7 differ, none in one trace only; server tour 74 pairs, 45 equal, 24 bytes-only, 5
  differ, none in one trace only. Both match the spec's prototype counts.
- Tour wall time 3.5 s (SDK). The SDK tour's stderr holds one `sdk:` line (the late progress of
  the cancelled call).
- Checks run: `python3 -m unittest discover -s tests -t .` 315 tests OK (89 s, includes
  `SdkClientTest` 8 tests, `tests/test_diff.py` 18, `tests/test_sdk_client.py` 5);
  `node --test "clients/sdk/test/*.test.ts"` 13 pass; `tsc -p clients/sdk`, ruff, mypy clean;
  G8, G9, G10, G11, G12 (`--phases 05`) tools ok. `scripts/gate.sh` itself not run by the
  builder (shared machine).
- Mutation testing of `tap/diff.py` (RP3) deferred to the final pass (LP7).

### Accepted limits

- J rows, the learner walk (L15) and the G6 clean-clone walk: deferred (LP5).
- Lesson polish beyond the L1 sections: deferred (LP5).
- `tap.diff` does not compare message order (D4); `tap.show` shows it. Both measured tour pairs had the same order.
- `tap.diff` lists bytes-only pairs as a count, not by key; the walkthrough explains them in prose.
- G12 checks a TypeScript test by its file, not by test name (D5).
- No TypeScript linter; G3's `tsc --strict` is the only TypeScript static check (scope cut).
- G3 type-checks with `skipLibCheck`: the SDK's own declaration files are not re-checked on every gate (measured to pass without it, at about six times the time and twice the memory).
- The `sdk` citation root is pinned by the lockfile's integrity hash and bootstrap's version check, not by a git commit (D6).
- The server tour's diff can in principle change if a list-change burst is ever re-listed twice by one client and once by the other (both coalesce: 50 ms raw, 300 ms SDK; measured once each).

### Owner learning check (LP6)

Optional (register row 2026-10-21, learning check). Answers by the owner only; the agent adds a
one-line verdict under each after checking it against a fresh trace.

1. *Explain.* Record `scripts/record.sh --client tour lc5-raw` and
   `scripts/record.sh --client sdk-tour lc5-sdk`, run `python3 -m tap.diff` on the two traces
   (without `--explain`, without the walkthrough), and explain each difference: why the SDK's
   `progressToken` values are 15 and 16, where in the SDK they come from, and why the
   `notifications/cancelled` frames are equal although the progress tokens are not.
2. *Change.* On a branch of your own, make the SDK tour ask for progress the raw client's way:
   pass `_meta: { progressToken: "tour-done" }` in the `callTool` params and drop `onprogress`.
   **Before running it**, predict the new diff and what the SDK does with the two progress
   notifications (hint: `client.onerror`). Then record, diff, and explain every difference from
   your prediction. Commit the change yourself on that branch; do not merge it.
3. *Debug.* The local branch `learning-check-05-fault` has one planted fault in `clients/sdk/`.
   From `tap.diff` against a fresh raw trace, the trace and the test output only (no
   `git diff`, no `git log -p`), say what is wrong on the wire, which call causes it, and the
   fix. The agent reveals the fault after you answer.

Answers:
