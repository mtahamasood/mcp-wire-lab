# Phase 6 — 2026-07-28 era, both clients (stdio): validation

Lean profile (LP1–LP6 in `mission.md`). Every C row names its checks in the G12 form (LP2);
none exists yet, so phase 06 is added to G12's `--phases` in `scripts/gate.sh` only when they
do (phase 2 D7). Inherited gates: G1–G5, G7–G12, green via `scripts/gate.sh`, locally and in
CI. G6 deferred (LP5). Rows C1–C12 and C16 are Part A (raw client); C13–C15 are Part B (SDK
client) and are removed together, by a register row, if Part B is not built. C11 is removed the
same way if the tasks run is cut; C16 (the extension schema, D14) stays, since it needs no tasks
run.

## Claim code (RP3)

`client/modern.py`: the envelope (D2), the discover gate and version check, the result-type
decision (D3), the multi-round loop (D4), the subscription correlation (D5); and the
`input_required` rule in `tap/check.py`'s definition choice (D10); the extension loader (merge,
name and method collision guard, `$ref` resolution) and the `resultType: "task"` rule in
`tap/check.py` (D14). The schema file `tap/schemas/2026-07-28/sep-2663-tasks.json` is authored
data checked by C16's tests, not code. Mutation testing (LP4) runs where the row's check is the
sole guard of a protocol rule: the discover gate (lifecycle order), the subscription id match
and the `inputResponses`/`requestState` echo (correlation), the result-type decision, the
`input_required` rule, and D14's collision guard and `resultType: "task"` rule (schema
validation). The envelope is not mutated: `tap.check` guards it too (2026-07-28 requires
`_meta` in every request's params).

## C. Phase-specific correctness

| Row | Claim | Checks | Mutation |
| --- | --- | --- | --- |
| C1 | Every request a `ModernSession` sends, retries and `subscriptions/listen` included, carries `_meta` with the protocol version, the client info and the declared capabilities (and the log level only when given); caller `_meta` keys are kept, the reserved keys are the client's; notifications carry no envelope | `tests/test_client_modern.py::EnvelopeTest::test_every_request_carries_the_envelope`, `tests/test_client_modern.py::EnvelopeTest::test_caller_meta_kept_reserved_keys_set_by_client`, `tests/test_client_modern.py::EnvelopeTest::test_log_level_only_when_given`, `tests/test_client_modern.py::EnvelopeTest::test_notifications_carry_no_envelope` | no (also guarded by `tap.check`, C9) |
| C2 | No request is sent before the `server/discover` reply; a reply without `2026-07-28` in `supportedVersions`, or a `-32022`, stops the session with the offered versions; another error stops it naming `--era 2025-11-25` | `tests/test_client_modern.py::DiscoverTest::test_no_request_before_discover_reply`, `tests/test_client_modern.py::DiscoverTest::test_unsupported_version_stops`, `tests/test_client_modern.py::DiscoverTest::test_unsupported_version_error_stops`, `tests/test_client_modern.py::DiscoverTest::test_other_error_suggests_2025_era` | yes |
| C3 | `resultType` decides the outcome: `complete` or absent → result; `input_required` → input-required outcome; `task` only when that request declared the tasks extension; anything else → `InvalidResult` | `tests/test_client_modern.py::ResultTypeTest::test_complete_and_absent_are_results`, `tests/test_client_modern.py::ResultTypeTest::test_task_only_with_tasks_extension`, `tests/test_client_modern.py::ResultTypeTest::test_unrecognized_result_type_is_invalid` | yes |
| C4 | A multi-round request is retried on a fresh id with the full envelope, one `inputResponses` entry per `inputRequests` key, and `requestState` echoed byte for byte; it stops after `max_rounds` and when an input request cannot be answered | `tests/test_client_modern.py::InputRequiredTest::test_retry_carries_responses_and_state_verbatim`, `tests/test_client_modern.py::InputRequiredTest::test_retry_uses_fresh_id_and_full_envelope`, `tests/test_client_modern.py::InputRequiredTest::test_round_limit`, `tests/test_client_modern.py::InputRequiredTest::test_unanswerable_request_raises` | yes |
| C5 | `listen()` returns only after the acknowledgment whose `subscriptionId` equals the listen id, type included; tagged notifications reach their subscription by that id alone; `close()` sends `notifications/cancelled` with the listen id and drops a late listen response | `tests/test_client_modern.py::ListenTest::test_ack_matched_by_subscription_id_type_included`, `tests/test_client_modern.py::ListenTest::test_notifications_routed_by_subscription_id`, `tests/test_client_modern.py::ListenTest::test_close_sends_cancelled_with_listen_id` | yes |
| C6 | `--era` defaults to 2025-11-25 and leaves every 2025 mode unchanged; `tour`, `tasks` and `manual` run in 2026-07-28; `server-tour` and `matrix` with `--era 2026-07-28`, `tasks` without it, and an unknown era exit 2 with the usage | `tests/test_client_modern.py::CliTest::test_era_option_parsing`, `tests/test_client_modern.py::CliTest::test_modes_without_a_2026_form_are_usage_errors`, `tests/test_help.py::HelpTest::test_bad_options_still_fail` | not claim code (RP3) |
| C7 | Manual mode in the new era discovers first, sends typed JSON lines exactly as typed, and wraps `:req` params in the envelope | `tests/test_client_manual.py::ManualTest::test_typed_line_in_2026_era_sent_verbatim`, `tests/test_client_manual.py::ManualTest::test_req_in_2026_era_carries_envelope` | not claim code (RP3) |
| C8 | The 2026 tour against the real server exits 0, its fresh trace holds every D6 step in order, opens with `server/discover`, holds no `initialize`, and holds all 21 methods of the 2026-07-28 schema (three inside `inputRequests`); `record.sh --client tour-2026` writes a run folder as the 2025 modes do | `tests/test_e2e.py::ModernTourTest::test_tour_2026_runs_every_step`, `tests/test_e2e.py::ModernTourTest::test_record_tour_2026`, `scripts/record.sh` | not claim code (RP3) |
| C9 | `tap.check --revision 2026-07-28` checks an `input_required` result against `InputRequiredResult` and other results as before; a 2026 request without `_meta` fails; the tour's fresh trace passes with no failure; 2025-11-25 checks are unchanged | `tests/test_check.py::CheckTest::test_input_required_result_checked_against_its_definition`, `tests/test_check.py::CheckTest::test_2026_request_without_envelope_fails`, `tests/test_e2e.py::ModernTourTest::test_tour_2026_trace_passes_schema_check`, `tests/test_check.py::CheckTest::test_valid_frames_pass`, `tests/test_e2e.py::RawClientTest::test_tour_trace_passes_schema_check` | yes |
| C10 | Walkthrough 06 `#tour` explains every frame of the tour's fresh trace (no missing, no extra note); `tap.diff --explain …#era-diff` on fresh 2025 `tour` and `tour-2026` traces passes (every entry has a note, every note an entry); its citations resolve | `tests/test_e2e.py::ModernTourTest::test_tour_2026_walkthrough_explains_fresh_trace`, `tests/test_e2e.py::ModernTourTest::test_era_diff_is_explained`, `tools/check_citations.py` | not claim code (RP3) |
| C11 | The tasks run exits 0 with the D7 statuses (`-32021`, `input_required`, `completed`, `working`, `cancelled`); walkthrough 06 `#tasks` explains its fresh trace; `tap.check --revision 2026-07-28` passes that trace and prints the SEP-2663 line counting its `tasks/*` frames, their results and the two task handles; with `--no-extensions` it fails that trace only on `tasks/*` frames and their responses (`unknown method`) | `tests/test_e2e.py::TasksTest::test_tasks_2026_runs_and_is_explained`, `tests/test_e2e.py::TasksTest::test_tasks_trace_passes_check_against_sep_2663`, `tests/test_e2e.py::TasksTest::test_tasks_trace_fails_pinned_only_check_on_extension_frames` | not claim code (RP3) |
| C12 | Lesson 06 has the L1 sections and its runnable blocks pass; it declares the 21 methods of 2026-07-28, each found in a fresh `tour-2026` trace (as a frame's method or inside a result's `inputRequests`); the atlas regenerates byte-identical | `tests/test_lessons.py`, `tools/check_lessons.py`, `tests/test_e2e.py::AtlasClaimsTest::test_lesson_declarations_appear_in_fresh_traces`, `tests/test_atlas.py::AtlasTest::test_regenerated_atlas_matches_committed` | not claim code (RP3) |
| C13 | (Part B) `main.ts` takes `--era` (default 2025-11-25; `server-tour` with 2026-07-28 and an unknown era are usage errors); the SDK client's 2026 tour exits 0 through `record.sh --client sdk-tour-2026`, its trace holding one tap `spawn` and opening with `server/discover` | `clients/sdk/test/era.test.ts`, `tests/test_e2e.py::SdkModernTourTest::test_sdk_tour_2026_runs_and_starts_with_discover` | not claim code (RP3) |
| C14 | (Part B) The SDK client's fresh 2026 trace passes `tap.check --revision 2026-07-28` | `tests/test_e2e.py::SdkModernTourTest::test_sdk_tour_2026_trace_passes_schema_check` | not claim code (RP3) |
| C15 | (Part B) `tap.diff --explain docs/walkthrough/06-sdk-2026.md` on fresh `tour-2026` and `sdk-tour-2026` traces passes: every entry has a note and every note an entry | `tests/test_e2e.py::SdkModernTourTest::test_raw_vs_sdk_2026_diff_is_explained` | not claim code (RP3) |
| C16 | (Part A, D14) `tap/schemas/2026-07-28/sep-2663-tasks.json` holds exactly D14's definitions, uses only the keywords `tap.check` implements, and every definition's `description` opens with a G8 citation that resolves to its SEP-2663 line (checked by the test after JSON decoding, since `tools/check_citations.py` reads raw text and the quotes are escaped); its `$ref`s resolve against the pinned 2026-07-28 schema. `tap.check --revision 2026-07-28` checks `tasks/get`, `tasks/update`, `tasks/cancel`, `notifications/tasks` and their results against it, and a `tools/call` result with `resultType: "task"` against `CreateTaskResult` (on another method it fails); valid and invalid synthetic frames of each definition pass and fail; failures name `SEP-2663:<Name>` and the run prints the SEP-2663 line; a definition name or method in both schemas stops it with exit 2; `--no-extensions` and 2025-11-25 ignore the file; a trace with no extension frame prints exactly as before | `tests/test_check.py::ExtensionSchemaTest::test_holds_exactly_the_sep_2663_definitions`, `tests/test_check.py::ExtensionSchemaTest::test_uses_only_implemented_keywords`, `tests/test_check.py::ExtensionSchemaTest::test_every_definition_cites_a_resolving_sep_line`, `tests/test_check.py::ExtensionSchemaTest::test_refs_resolve_against_pinned_2026_schema`, `tests/test_check.py::ExtensionCheckTest::test_tasks_frames_checked_against_sep_2663`, `tests/test_check.py::ExtensionCheckTest::test_task_result_checked_against_create_task_result`, `tests/test_check.py::ExtensionCheckTest::test_task_result_on_other_method_fails`, `tests/test_check.py::ExtensionCheckTest::test_findings_labelled_sep_2663`, `tests/test_check.py::ExtensionCheckTest::test_collision_with_pinned_schema_stops`, `tests/test_check.py::ExtensionCheckTest::test_no_extensions_and_2025_ignore_the_file`, `tests/test_check.py::ExtensionCheckTest::test_trace_without_extension_frames_prints_as_before`, `tap/schemas/2026-07-28/sep-2663-tasks.json` | yes |

## E. Not-done conditions

Not done if the raw client imports an MCP library, if any request in a fresh `tour-2026`
trace lacks the envelope, if that trace fails `tap.check --revision 2026-07-28`, if a recorded
2026 trace holds `initialize`, if a 2025-era test or lesson changes behaviour, if any C row
names a check that does not exist, or if run output is tracked.

## Result

Status: closed

Part A (raw client) and Part B (SDK client) built 2026-10-22 under LP7 (tests alongside code, no
mutation run, no review round); every C row's check passes on the merged tree. Part B measured
on this machine (Node 24.22.0) against the pinned, built server:

- Fresh `sdk-tour-2026` trace: 74 frames, one tap `spawn`, opens with `server/discover`
  (id `"server-discover-probe-1"`), passes `tap.check --revision 2026-07-28`; the SDK's stderr
  holds one `sdk:` line (the late progress of the cancelled call).
- `tap.diff` of fresh `tour-2026` and `sdk-tour-2026` traces: 74 pairs, 30 equal, 44 differ,
  none in one trace only; `docs/walkthrough/06-sdk-2026.md` has a note for each.
- Checks run: `python3 -m unittest discover -s tests -t .` 420 tests OK;
  `node --test "clients/sdk/test/*.test.ts"` 16 pass; `tsc -p clients/sdk` clean.
- Mutation testing deferred to the final pass (LP7).

### Accepted limits

- J rows, learner walk (L15) and G6 walk: deferred (LP5).
- No review round (LP4): the only changes to earlier claim code are the `input_required` rule
  and D14's extension loader and `resultType: "task"` rule in `tap/check.py`, inert for
  2025-11-25 and for traces without extension frames, and covered by C9 and C16.
- No automatic era fallback (`discover`, then `initialize` on a legacy server): the pinned
  server always answers discover, so the branch could not be recorded (requirements, scope).
- Tasks are reduced to one completed and one cancelled task with no polling loop.
- The pinned `schema/2026-07-28/schema.json` has no tasks definitions: against it alone
  (`--no-extensions`) every `tasks/*` frame is `unknown method`. Their check is against an
  authored transcription of SEP-2663 (D14), labelled `SEP-2663:` in every report, and only as
  faithful as that transcription (each definition cites its SEP line). It does not check the
  SEP's prose rules (ISO 8601 timestamps, integer milliseconds, `inputRequests` keys unique over
  a task's life), the `taskIds` listen filter, or whether a task went to a client that declared
  the extension.
- Lesson 06 does not declare `tasks/*` in the atlas, whose `tasks/*` rows are the 2025-11-25
  core methods.
- The SDK client (Part B) has no tasks run: SDK 2.3.1 rejects `resultType: "task"`.
- The pinned server's departures from the 2026-07-28 spec (progress after cancellation, a
  later request claiming another version served on a pinned connection, no listen response at
  shutdown) are recorded and explained, not worked around.
- Coverage (L8), measured at close (Part A, 2026-10-22): lesson 06 declares 21 of the 21
  methods of 2026-07-28, each found in a fresh `tour-2026` trace; the regenerated atlas marks
  0 of 21 methods of 2026-07-28 and 6 of 31 methods of 2025-11-25 `unexercised`.
- Mutation run (LP4): *to be filled* at close.

### Owner learning check (LP6)

Optional (register row 2026-10-21, learning check). Answers by the owner only.

1. *Explain.* Record `scripts/record.sh --client tour-2026 lc6` and, from `tap.show` alone,
   explain the three frames of `get-roots-list` after the `-32021` step: why the first reply is
   a result and not an error, what the client added to its second request, and why no request
   ever flows from the server to the client.
2. *Change.* On your own branch, make the raw client stop sending
   `io.modelcontextprotocol/clientCapabilities` on retries only (D4). Before running it,
   predict what the server answers to the second `get-roots-list` request and which line of
   `tap.check` output changes; then record, check and explain.
3. *Debug.* The agent plants one fault in `client/modern.py` on a local branch (for example,
   subscription notifications matched by method instead of by `subscriptionId`, or
   `requestState` re-encoded). From the tests and a fresh trace only, say what is wrong on the
   wire, which function causes it, and the fix. The agent reveals the fault after you answer.

Answers:
