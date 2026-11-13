# Phase 8 — Final pass: validation

Every C row names its checks in the G12 form (LP2). Most do not exist yet: phase 08 is added to
the G12 list in `scripts/gate.sh` at Stage G's close, when every check named here exists
(`requirements.md` D1; phase 2 D7 as amended). Until then a builder closing a stage runs
`python3 tools/check_claims.py --phases 08` and shows that every error left belongs to a later
stage's row. Inherited gates: G1–G5, G7–G12 through `scripts/gate.sh`, locally and in CI; a stage
closes only on a passed GitHub CI run whose ID the Result cites (D2). G6 is Stage D's full-path
walk (D13). Rows are grouped by stage. The test names below are the ones the builders use; a
builder who must rename one changes the row in the same commit.

## Claim code (RP3)

`tools/mutate.py`: applying one exact replacement, the exactly-once rule, the restore and its
byte comparison, the `runs/` contamination guard, and the verdict (D8). These decide whether a
mutation run can be believed, so they are the sole guard of D9's results.
`clients/sdk/src/order.ts`, D4's fix where Stage A's measurement pointed: `inWireOrder()` hands
each response to the SDK one microtask after it is read, so a progress notification read in the
same chunk reaches its handler before the call settles; this decides whether the SDK tours'
long-running step passes under load. Mutation testing runs on both, from
`audits/mutants/phase-08.json`: on `tools/mutate.py` with itself, in a temporary copy; on
`order.ts`, a response handed over at once (the pre-fix order) is the mutant, and
`clients/sdk/test/order.test.ts` must fail on it.

Not claim code: the e2e helpers' failure messages, the CI workflow, the gate's split of G4 and
G5, lessons, walkthroughs, README and audit files. D9 mutates the claim code of phases 5–7,
named in their own `validation.md`; D10 reviews phases 3–7.

## C. Phase-specific correctness

| Row | Claim | Checks | Mutation |
| --- | --- | --- | --- |
| C1 | Stage A (D3). When `scripts/record.sh` exits non-zero in an e2e test of either module (one shared helper), the assertion message holds `record.sh`'s stderr and the run folder's `stderr.txt` (its last 200 lines when longer), or says no run folder was reported | `tests/test_e2e.py::RecordFailureTest::test_failed_record_shows_run_stderr` | not claim code (RP3) |
| C2 | Stage A (D3). CI uploads each run folder's `trace.jsonl` and `stderr.txt`, and nothing else from `runs/`, as an artifact only when a step fails, kept 7 days | `tests/test_gate.py::GateTest::test_ci_uploads_runs_on_failure`, `.github/workflows/ci.yml` | not claim code (RP3) |
| C3 | Stage A (D4). The SDK tours survive the measured race: a progress notification read in one chunk with its response reaches `onprogress` before the call settles. The node test (run by G4's `node --test`) holds a fake server that writes both in one write; it fails on the pre-fix code (failing run recorded) and passes after the fix, and 20 recordings under load pass (Result); the tour's trace is unchanged, so walkthroughs 02 and 05 still explain it | `clients/sdk/test/order.test.ts`, `tests/test_e2e.py::SdkClientTest::test_sdk_tour_runs_the_raw_tour_steps`, `tests/test_e2e.py::SdkClientTest::test_raw_walkthroughs_explain_sdk_traces`, `tests/test_e2e.py::SdkClientTest::test_tour_diff_is_explained` | yes (a response handed over at once is the mutant) |
| C4 | Stage A (D5). The gate runs each e2e module once: G4's run excludes `tests.test_e2e` and `tests.test_e2e_http`, G5 runs both, and every other test module is still run by G4 | `tests/test_gate.py::GateTest::test_e2e_runs_once` | not claim code (RP3) |
| C5 | Stage A (D6). No tap, server or client process started by a recording outlives it, and the logs of Stage A's three passed CI runs hold no `ResourceWarning` (Result; re-checked by D17) | `tests/test_e2e_http.py::RecordHttpTest::test_no_tap_process_left_after_record`, `audits/final-pass-pack-review.md` | not claim code (RP3) |
| C6 | Stage B (D8). `tools/mutate.py` applies each mutant as one exact replacement in a temporary copy, never in the real tree; a text that occurs zero or several times is an error, not a run; after each mutant the file is restored and compared byte for byte, and a mismatch stops the run; an entry left in the copy's `runs/` before a command stops the run; each mutant is reported `killed`, `survived`, `equivalent` or `error`, and the exit is 0 only when every mutant is killed or marked equivalent | `tests/test_mutate.py::MutateTest::test_applies_one_exact_replacement`, `tests/test_mutate.py::MutateTest::test_missing_or_ambiguous_text_is_an_error`, `tests/test_mutate.py::MutateTest::test_restores_original_and_checks_with_cmp`, `tests/test_mutate.py::MutateTest::test_refuses_when_runs_dir_has_leftovers`, `tests/test_mutate.py::MutateTest::test_reports_killed_and_survived`, `tests/test_mutate.py::MutateTest::test_marked_equivalent_does_not_fail_the_run` | yes |
| C7 | Stage B (D9). Every mutant of the phase 5–7 claim code and of this phase's is killed or signed equivalent with its reason; each `yes` row of phases 5–7 and 8 has at least one mutant; the mutants files are committed | `audits/mutation-final-pass.md`, `audits/mutants/phase-05.json`, `audits/mutants/phase-06.json`, `audits/mutants/phase-07.json`, `audits/mutants/phase-08.json`, `tools/mutate.py` | not claim code (RP3; this row is the mutation run) |
| C8 | Stage B (D10). The review of phases 3–7 is deposited, each finding reproduced or marked not reproduced, and disposed; each fix's test is named in a new row added below in the disposing commit | `audits/final-pass-review.md` | not claim code (RP3) |
| C9 | Stage C (D11). Every lesson's *Predict* section points to answers, and the answers are in the lesson | `tests/test_lessons.py::LearnerTextTest::test_every_lesson_has_predict_answers` | not claim code (RP3) |
| C10 | Stage C (D11). No lesson or walkthrough names a spec record id (D, C, G, J, L, A, M, LP or RP followed by a number, alone or as `phase N D<n>`) outside code blocks and citations | `tests/test_lessons.py::LearnerTextTest::test_no_spec_ids_in_learner_text` | not claim code (RP3) |
| C11 | Stage C (D11). Every lesson has the L1 sections and its runnable blocks pass, including lesson 05's new experiments and its server-tour section | `tools/check_lessons.py`, `tests/test_lessons.py` | not claim code (RP3) |
| C12 | Stage C (D11). After the polish every walkthrough still explains every frame of its fresh traces, walkthrough 06b included, and every citation resolves | `tests/test_e2e.py::E2ETest::test_c14_explain_covers_a_fresh_run`, `tests/test_e2e.py::RawClientTest::test_tour_walkthrough_explains_fresh_trace`, `tests/test_e2e.py::ServerTourTest::test_server_tour_trace_checks_and_is_explained`, `tests/test_e2e.py::EdgeLabTest::test_every_edge_fixture_is_explained`, `tests/test_e2e.py::SdkClientTest::test_raw_walkthroughs_explain_sdk_traces`, `tests/test_e2e.py::SdkClientTest::test_tour_diff_is_explained`, `tests/test_e2e.py::SdkClientTest::test_server_tour_diff_is_explained`, `tests/test_e2e.py::ModernTourTest::test_tour_2026_walkthrough_explains_fresh_trace`, `tests/test_e2e.py::ModernTourTest::test_era_diff_is_explained`, `tests/test_e2e.py::TasksTest::test_tasks_2026_runs_and_is_explained`, `tests/test_e2e.py::SdkModernTourTest::test_raw_vs_sdk_2026_diff_is_explained`, `tests/test_e2e_http.py::HttpTourTest::test_walkthrough_explains_fresh_trace`, `tools/check_citations.py` | not claim code (RP3) |
| C13 | Stage C (D12). The README links every lesson, every walkthrough (06b included) and the atlas on the learning path, and its gate list names G10; the feedback issue template exists | `tests/test_lessons.py::LearnerTextTest::test_readme_links_every_lesson_walkthrough_and_atlas`, `.github/ISSUE_TEMPLATE/feedback.md` | not claim code (RP3) |
| C14 | Stage C (D12). The generated atlas says why its tasks rows are `unexercised`, and regenerating it still gives the committed file | `tests/test_atlas.py::AtlasTest::test_tasks_rows_carry_their_reason`, `tests/test_atlas.py::AtlasTest::test_regenerated_atlas_matches_committed` | not claim code (RP3) |
| C15 | Stage D (D13). Both learner walks are recorded with every stall and wrong answer fixed or signed; the full-path walk includes the clean-clone bootstrap and gate (G6) | `audits/learner-walk-lessons-05-07.md`, `audits/learner-walk-full-path.md` | not claim code (RP3) |
| C16 | Stage E (D14). No closed phase's `validation.md` Result holds a placeholder (`to be filled`, `not yet dispositioned`), and every *Owner learning check* section of phases 2–7 is marked superseded by phase 8 | `tests/test_provenance.py::RecordsSweepTest::test_closed_results_have_no_placeholders`, `tests/test_provenance.py::RecordsSweepTest::test_owner_learning_checks_marked_superseded` | not claim code (RP3) |
| C17 | Stage E (D15). The review pack holds A23 onward one line each, J rows for phases 2–7, the rubric for lessons 01–07 and the combined learning check | `audits/owner-review-pack.md` | not claim code (RP3) |
| C18 | Stage E (D17). The review before the sitting is deposited and its findings disposed before the pack goes to the owner | `audits/final-pass-pack-review.md` | not claim code (RP3) |
| C19 | Stages F and G (D18, D19). The owner's rubric, answers, J-row marks and A-row rulings are in the pack with the agent's verdicts; the disposition list is owner-approved; the changelog has the `[1.0.0]` section | `audits/owner-review-pack.md`, `CHANGELOG.md` | not claim code (RP3) |
| C20 | Every stage (D1, D2, D7, D19). Each stage's Result names the commit it closed on and cites passed run IDs (a `ci` push run on `main`, attempt 1, conclusion `success`, on that commit), Stage A three consecutive; D17 checks the IDs of Stages A–E with `gh run view`, and the closing commit's run is checked the same way before the tags; at the close, phase 08 is in G12's `--phases` list and the gate passes | `scripts/gate.sh`, `audits/final-pass-pack-review.md` | not claim code (RP3) |
| C21 | Stage E (D16). The final fault is on the local branch `learning-check-final`, cut from `main` once the rest of Stages A–E is merged, and never pushed; its commit message names no fault; the fault and its answer are in the agent's project memory and in no committed file until the owner has answered (checked by D17), and then the pack records the fault, the answer and the verdict | `audits/final-pass-pack-review.md`, `audits/owner-review-pack.md` | not claim code (RP3) |
| C22 | Stage B (D10, P8-R7-1). The tap's SSE parser takes time linear in its input: one 4 MB event fed in 16 KiB pieces, and 80,000 lines fed in one chunk, take under 8 times what a quarter of that takes (with a one-second noise floor), where the old parser took about 16 times (a 1 MB event: 0.53 s then, 0.01 s now, fed in 64 KiB pieces); the framing is unchanged: LF, CRLF and CR line ends, a CR at a chunk end, multi-line data, an event split at any byte, comments counted, an unterminated last event returned as `partial` | `tests/test_tap_sse.py::SseParserScalingTest::test_large_event_in_small_pieces_scales_linearly`, `tests/test_tap_sse.py::SseParserScalingTest::test_many_lines_in_one_chunk_scale_linearly`, `tests/test_tap_sse.py::SseParserScalingTest::test_many_small_events_scale_linearly`, `tests/test_tap_sse.py::SseParserScalingTest::test_large_event_is_parsed_whole`, `tests/test_tap_sse.py::SseParserFramingTest::test_line_ends_lf_crlf_cr_all_frame_events`, `tests/test_tap_sse.py::SseParserFramingTest::test_mixed_line_ends_in_one_event`, `tests/test_tap_sse.py::SseParserFramingTest::test_multi_line_data_joined_with_newline`, `tests/test_tap_sse.py::SseParserFramingTest::test_event_split_at_every_byte_boundary`, `tests/test_tap_sse.py::SseParserFramingTest::test_cr_at_chunk_end_waits_for_a_possible_lf`, `tests/test_tap_sse.py::SseParserFramingTest::test_finish_returns_the_cut_off_event_as_partial`, `tests/test_tap_sse.py::SseParserFramingTest::test_comments_are_counted_and_not_events` | not claim code (RP3) |

## E. Not-done conditions

Not done if: a stage's Result cites no passed GitHub CI run, or cites a local gate run instead
(D2); a cited run is not a passed run (another branch, a tag, a pull request, a re-run attempt
or another commit; D2); fewer than three consecutive passed CI runs on `main` are cited for
Stage A; the D4 stress evidence is missing; a C row names a check that does not exist once phase
08 is listed; any mutant of D9 is left without a verdict; a blocker or major of D10 is unfixed;
a learner walk ends with an unresolved stall; the final fault or its answer appears in any
committed file before the owner has answered (D16); `learning-check-final` is pushed; `v1.0.0`
is tagged before the owner approves the disposition and the tag; anything under `vendor/` is
changed; run output is tracked, including `tools/mutate.py` output and the walkers' logs; or a
package, image or GitHub Release is published.

## Result

Status: open

Each stage adds its result here when it closes, with the IDs of the passed GitHub CI runs it
closed on (D2).

### Accepted limits

- A failed CI run's artifact (each run folder's `trace.jsonl` and `stderr.txt`) is downloadable
  by readers of the public repository for 7 days: the one exception to the non-goal on shipping
  run output, approved with the plan, made on the CI machine under the recording allowlist and
  never committed (D3; register row 2026-11-14, phase 8 final pass).
- `tools/mutate.py` mutants are hand-written exact replacements; the tool generates none (D8).
- Phases 3 and 4 are reviewed on their claim code only (D10).
- Learner-walk agents stand in for newcomers; the owner's sitting is the human check (D13, D18).
- The combined learning check gives evidence across the whole path, not per phase (register row
  2026-11-14, learning check superseded).
- Phase 8's own rows are not guarded by G12 until its close (D1).
