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
| C1 | A response completes only the pending request with the same id, type included; a server request with an id equal to a pending client id is not taken as its response and gets `-32601` with its own id; notifications are queued; junk lines are reported and ignored | `tests/test_client_wire.py::ClassifyTest::test_response_matches_same_id_and_type_only`, `tests/test_client_wire.py::ClassifyTest::test_server_request_with_overlapping_id_is_not_a_response`, `tests/test_client_wire.py::ClassifyTest::test_notification_is_queued`, `tests/test_client_wire.py::ClassifyTest::test_junk_line_is_reported_and_ignored`, `tests/test_client_wire.py::ClassifyTest::test_bad_id_or_deep_line_does_not_stop_reader` | yes |
| C2 | Each message is one compact JSON object per line with no embedded newline; concurrent sends never interleave | `tests/test_client_wire.py::FramingTest::test_one_compact_line_per_message`, `tests/test_client_wire.py::FramingTest::test_concurrent_sends_do_not_interleave`, `tests/test_client_wire.py::FramingTest::test_large_write_does_not_block_reader` | yes |
| C3 | Lifecycle: no request is sent before `notifications/initialized`; an unsupported `protocolVersion` in the reply stops the session; an error reply raises with its error object | `tests/test_client_session.py::LifecycleTest::test_request_before_initialized_raises_without_sending`, `tests/test_client_session.py::LifecycleTest::test_unsupported_version_stops`, `tests/test_client_session.py::LifecycleTest::test_error_reply_raises_with_error_object`, `tests/test_client_session.py::LifecycleTest::test_request_after_eof_or_close_fails_fast` | yes |
| C4 | Shutdown closes stdin, then escalates to SIGTERM and SIGKILL on a child that does not exit, and returns its status | `tests/test_client_session.py::ShutdownTest::test_close_then_escalate` | no (timing; checked by its test only) |
| C5 | Cancellation sends `notifications/cancelled` with the request's id and a late reply is dropped and reported | `tests/test_client_session.py::CancelTest::test_cancel_sends_notification_and_drops_late_reply`, `tests/test_client_session.py::CancelTest::test_timeout_sends_cancel_and_forgets`, `tests/test_client_session.py::CancelTest::test_cancel_after_completion_returns_false` | yes |
| C6 | The tour against the real server exits 0 and its fresh trace holds every D3 method in order | `tests/test_e2e.py::RawClientTest::test_tour_runs_every_client_initiated_method` | not claim code (RP3) |
| C7 | Manual mode sends typed lines exactly as typed, builds `:req` and `:note` messages, and shuts down on `:quit` and on end of input | `tests/test_client_manual.py::ManualTest::test_typed_line_sent_verbatim`, `tests/test_client_manual.py::ManualTest::test_req_and_note_commands`, `tests/test_client_manual.py::ManualTest::test_quit_and_eof_shut_down` | not claim code (RP3) |
| C8 | `record.sh --client tour` writes a run folder with the allowlisted server environment, and the fixture form is unchanged | `tests/test_e2e.py::RawClientTest::test_record_client_tour`, `scripts/record.sh` | not claim code (RP3) |
| C9 | `tap.check` validates the tour's fresh trace with no failure; a hand-made invalid frame fails with its `seq`, path and definition; an unimplemented keyword exits 2 naming it; an unknown method is reported, not passed | `tests/test_check.py::CheckTest::test_valid_frames_pass`, `tests/test_check.py::CheckTest::test_invalid_frame_reports_seq_path_definition`, `tests/test_check.py::CheckTest::test_unimplemented_keyword_fails_loudly`, `tests/test_check.py::CheckTest::test_unknown_method_is_reported`, `tests/test_e2e.py::RawClientTest::test_tour_trace_passes_schema_check`, `tests/test_check.py::CheckTest::test_keywords_are_checked`, `tests/test_check.py::CheckTest::test_error_frames_are_validated`, `tests/test_check.py::CheckTest::test_notification_checked_against_its_method`, `tests/test_check.py::CheckTest::test_unknown_revision_exits_2` | yes |
| C10 | G12 fails on a C row that names nothing, a missing file, a missing class or a missing method, and passes this file | `tests/test_check_claims.py::ClaimsTest::test_row_naming_nothing_fails`, `tests/test_check_claims.py::ClaimsTest::test_missing_targets_fail`, `tests/test_check_claims.py::ClaimsTest::test_repository_passes`, `tools/check_claims.py`, `tests/test_check_claims.py::ClaimsTest::test_pipe_in_claim_cell_does_not_shift_columns` | yes |
| C11 | The walkthrough explains every frame of the tour's fresh trace (no missing, no extra note) and its citations resolve | `tests/test_e2e.py::RawClientTest::test_tour_walkthrough_explains_fresh_trace`, `tools/check_citations.py` | not claim code (RP3) |
| C12 | Lesson 02 has the L1 sections and its runnable blocks pass | `tests/test_lessons.py`, `tools/check_lessons.py` | not claim code (RP3) |

## E. Not-done conditions

Not done if the client imports any MCP library, if the tour's trace fails `tap.check`, if
any C row names a check that does not exist, or if run output is tracked.

## Result

- Status: closed

Closed 2026-10-21 by the agent under the owner's delegation (register row 2026-10-21, spec batch approval): every C row passes on `main` with the gate green (G1-G5, G7-G12; G12 checks this phase). G6 (clean-clone walk) was run later the same day (`audits/learner-walk-lessons-02-04.md`, Part A): on `main` the clone, bootstrap, gate (about 113 s), a recorded tour and `git status` all pass, about 2.5 minutes in total; the walk's findings are fixed (A34).
Review round done (`audits/phase-02-review.md`: 0 blockers, 2 majors, 7 minors, all fixed and re-tested). The owner learning check below is open by the owner's choice (register row 2026-10-21, "Learning check run by an agent"): the project is complete without it, and it is done after real use.

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

Review fixes P2-R1 to P2-R5 (hand-applied, 8 single-edit mutants on the new code in `client/wire.py`):
any id accepted as a response (M1), `RecursionError` not caught (M2), no per-line guard in the
reader (M3), the refusal written on the reader thread (M4), `abandon` always True (M5), the table
lock held across the write (M6), `_fail_all` after the loop instead of in `finally` (M7), and
`abandon` checking `done` outside the table lock (M8). First run: 5 killed, 3 survived: M2 (the
per-line guard caught the `RecursionError` anyway), M7 (no test made the reader's stream raise) and
M8 (the forced interleaving could not tell a check inside the lock from one outside it). Each got an
assertion (`handle_line` returns `junk` for a 100000-deep line; a reader whose stream raises still
fails the pending request with `ConnectionError`; a request the reader has taken from the table but
not yet completed is not cancellable) and was re-run: 8 of 8 killed, by
`ClassifyTest.test_bad_id_or_deep_line_does_not_stop_reader`,
`FramingTest.test_large_write_does_not_block_reader` and
`CancelTest.test_cancel_after_completion_returns_false`.

### Accepted limits

- Learner walk L15 and J rows: deferred (LP5).
- Atlas L8 and gate G10: deferred to the final pass (register row 2026-10-21, lean profile).

### Owner learning check (LP6)

**Required before the project is called complete** (register row 2026-10-21, learning
check). Answers by the owner only; the agent adds a one-line verdict under each answer
after checking it against a fresh trace. Set aside about 45 minutes, plus a few minutes of
bootstrap if you use a second worktree for prompt 3 (`git worktree add ../lc-02 <branch>`,
then `git submodule update --init --recursive` and `scripts/bootstrap.sh`).

1. *Explain.* Run `scripts/record.sh --client tour lc-explain` and open the trace with
   `python3 -m tap.show <trace>` (not `--explain`, and without the walkthrough open). Pick the
   cancelled `trigger-long-running-operation` call. In your own words: which frames belong to
   it, why a `notifications/progress` frame still arrives after `notifications/cancelled`, why
   no response ever arrives for that request, and how `client/wire.py` decides that each of
   those incoming lines is not the reply to a pending request.
2. *Change.* On a branch of your own, change the raw client so request ids start at 100 and
   go up in steps of 10. **Before running it**, write down what you expect to change in the
   tour's trace and what stays the same (hint: think about `notifications/cancelled`, and about
   the server's own request ids, which only the server tour, lesson 03, shows). Then run the tests and the tour, compare, and explain
   every difference from your prediction. Expect red: a dozen or so tests hard-code ids 0 to 16,
   so failing tests are part of the answer, not a sign you broke something. Commit the change yourself (it is evidence you
   authored), on that branch; do not merge it.
3. *Debug.* The local branch `learning-check-02-fault` has one planted fault in `client/`.
   Check it out, run `python3 -m unittest discover -s tests -t .` and record the tour. From
   the test output and the trace only (no `git diff`, no `git log -p`; a failing e2e test also
   prints walkthrough notes, so skip those lines), say what is wrong on
   the wire, which function causes it, and the fix. The agent reveals the fault after you
   answer.

Answers:

### Agent-run learning check (2026-10-21, on the owner's instruction)

Not the owner's answers: the owner's `Answers:` above stay empty and the owner still intends to
do the check themselves after using the finished project. At the owner's request a fresh Sonnet
agent, in its own worktree and without the walkthrough, the memory or `git diff`, did the three
prompts as a learner would. The controller checked its answers against the trace and the planted
fault.

1. *Explain.* Correct. Frames of the cancelled call: seq 39 (`tools/call` id 16), 40 (progress),
   41 (`notifications/cancelled`), 42 (the late progress). It said a cancellation is advisory, so
   the server's loop still sends its second progress; no reply for id 16 (it called this an
   inference, and it is: no source was read); and that `classify` decides by shape, with
   `Wire._complete` matching only a `result`/`error` line by `(type, value)` of the id.
2. *Change.* Two lines in `client/wire.py` (`_next_id = 100`, `+= 10`), commit `2618dc7` on
   `lc-02-change` (not merged, not pushed). The written prediction matched the trace on every
   point (same 43 records, ids 100 to 260, `requestId` 260 in the cancel, tokens and
   `tap.check` unchanged). It under-predicted the tests: 10 failures and 3 errors, from
   hard-coded ids, fake servers that answer a fixed id (timeouts, not assertion failures) and
   walkthrough notes keyed by id.
3. *Debug.* Correct. The cancel carries `requestId` 15 while the call is 16, the server runs it
   to completion and answers id 16, the cause is `Session.cancel` and the fix is `pending.id`
   (the agent named the `- 1`). It also flagged, unconfirmed, that `cancel` ignores
   `Wire.abandon`'s return value; that is original design, not part of the fault.

Friction the agent met (not yet dispositioned; changing the prompts is a spec change, so it
waits for the owner): the failing e2e tests print walkthrough notes, which can leak hints in
prompt 3; prompt 2's hint about the server's own ids has nothing to show in the tour trace
(only the server tour has them) and does not say that about 13 hard-coded tests going red is
expected; the 45-minute estimate omits the several minutes a second worktree needs to bootstrap.
