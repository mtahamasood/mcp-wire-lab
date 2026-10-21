# Phase 2 — Raw client, 2025 era, client-initiated: validation

Lean profile (LP1–LP6 in `mission.md`). Every C row names its checks in the G12 form
(LP2). Inherited gates: G1–G5, G7–G9, G11 and the new G12, green via `scripts/gate.sh`,
locally and in CI. G6 (clean-clone walk) runs once at this phase's close; for later
phases it is deferred (LP5).

## Claim code (RP3)

`client/wire.py` (line classification, id correlation, the write lock), `client/session.py`
(lifecycle order, version check, shutdown, cancellation) and `tap/check.py` (definition
choice, keyword validation, the unknown-keyword failure). Mutation testing runs on line
classification and correlation, the "no request before initialized" rule, and the
validator's definition choice and keyword checks (LP4).

## C. Phase-specific correctness

| Row | Claim | Checks | Mutation |
| --- | --- | --- | --- |
| C1 | A response completes only the pending request with the same id, type included; a server request with an id equal to a pending client id is not taken as its response and gets `-32601` with its own id; notifications are queued; junk lines are reported and ignored | `tests/test_client_wire.py::ClassifyTest::test_response_matches_same_id_and_type_only`, `tests/test_client_wire.py::ClassifyTest::test_server_request_with_overlapping_id_is_not_a_response`, `tests/test_client_wire.py::ClassifyTest::test_notification_is_queued`, `tests/test_client_wire.py::ClassifyTest::test_junk_line_is_reported_and_ignored` | yes |
| C2 | Each message is one compact JSON object per line with no embedded newline; concurrent sends never interleave | `tests/test_client_wire.py::FramingTest::test_one_compact_line_per_message`, `tests/test_client_wire.py::FramingTest::test_concurrent_sends_do_not_interleave` | yes |
| C3 | Lifecycle: no request is sent before `notifications/initialized`; an unsupported `protocolVersion` in the reply stops the session; an error reply raises with its error object | `tests/test_client_session.py::LifecycleTest::test_request_before_initialized_raises_without_sending`, `tests/test_client_session.py::LifecycleTest::test_unsupported_version_stops`, `tests/test_client_session.py::LifecycleTest::test_error_reply_raises_with_error_object` | yes |
| C4 | Shutdown closes stdin, then escalates to SIGTERM and SIGKILL on a child that does not exit, and returns its status | `tests/test_client_session.py::ShutdownTest::test_close_then_escalate` | no (timing; checked by its test only) |
| C5 | Cancellation sends `notifications/cancelled` with the request's id and a late reply is dropped and reported | `tests/test_client_session.py::CancelTest::test_cancel_sends_notification_and_drops_late_reply` | yes |
| C6 | The tour against the real server exits 0 and its fresh trace holds every D3 method in order | `tests/test_e2e.py::RawClientTest::test_tour_runs_every_client_initiated_method` | not claim code (RP3) |
| C7 | Manual mode sends typed lines exactly as typed, builds `:req` and `:note` messages, and shuts down on `:quit` and on end of input | `tests/test_client_manual.py::ManualTest::test_typed_line_sent_verbatim`, `tests/test_client_manual.py::ManualTest::test_req_and_note_commands`, `tests/test_client_manual.py::ManualTest::test_quit_and_eof_shut_down` | not claim code (RP3) |
| C8 | `record.sh --client tour` writes a run folder with the allowlisted server environment, and the fixture form is unchanged | `tests/test_e2e.py::RawClientTest::test_record_client_tour`, `scripts/record.sh` | not claim code (RP3) |
| C9 | `tap.check` validates the tour's fresh trace with no failure; a hand-made invalid frame fails with its `seq`, path and definition; an unimplemented keyword exits 2 naming it; an unknown method is reported, not passed | `tests/test_check.py::CheckTest::test_valid_frames_pass`, `tests/test_check.py::CheckTest::test_invalid_frame_reports_seq_path_definition`, `tests/test_check.py::CheckTest::test_unimplemented_keyword_fails_loudly`, `tests/test_check.py::CheckTest::test_unknown_method_is_reported`, `tests/test_e2e.py::RawClientTest::test_tour_trace_passes_schema_check` | yes |
| C10 | G12 fails on a C row that names nothing, a missing file, a missing class or a missing method, and passes this file | `tests/test_check_claims.py::ClaimsTest::test_row_naming_nothing_fails`, `tests/test_check_claims.py::ClaimsTest::test_missing_targets_fail`, `tests/test_check_claims.py::ClaimsTest::test_repository_passes`, `tools/check_claims.py` | yes |
| C11 | The walkthrough explains every frame of the tour's fresh trace (no missing, no extra note) and its citations resolve | `tests/test_e2e.py::RawClientTest::test_tour_walkthrough_explains_fresh_trace`, `tools/check_citations.py` | not claim code (RP3) |
| C12 | Lesson 02 has the L1 sections and its runnable blocks pass | `tests/test_lessons.py`, `tools/check_lessons.py` | not claim code (RP3) |

## E. Not-done conditions

Not done if the client imports any MCP library, if the tour's trace fails `tap.check`, if
any C row names a check that does not exist, or if run output is tracked.

## Result

- Status: open

### Mutation run (LP4, builder, hand-applied)

33 single-edit mutants on the claim code: 13 on `client/wire.py` (type-blind id key, response
shape tested before method, notification taken as request, boolean and float ids accepted, late
replies not recognised, wrong refusal code and id, notifications not queued, no write lock, ids
not advanced, non-ASCII output, junk not reported), 8 on `client/session.py` (no guard before
initialized, ready set early, version check removed, `initialized` not sent, cancel without
abandon, wrong `requestId`, `initialize` cancellable, no SIGTERM step) and 12 on `tap/check.py`
(result definition choice, `required`, unknown keywords ignored, `anyOf`, `const`, integer, error
frame definition, unknown method passing, `additionalProperties`, response envelope, partial
frames, `minimum`). First run: 30 killed, 3 survived: boolean ids on a server request (M4),
non-ASCII output of `notify` (M12) and the response envelope check (K10). Each got a test
(`ClassifyTest.test_junk_line_is_reported_and_ignored`, `FramingTest.test_one_compact_line_per_message`,
`CheckTest.test_invalid_frame_reports_seq_path_definition`) and was re-run: 33 of 33 killed. The
write-lock mutant is killed by a concurrent writer that splits each write; it was run three
times. C4 (shutdown timing) is not mutated, as the table says.

### Accepted limits

- Learner walk L15 and J rows: deferred (LP5).
- Atlas L8 and gate G10: deferred to the final pass (register row 2026-10-21, lean profile).

### Owner learning check (LP6)

Prompts written at close; answers by the owner only.
