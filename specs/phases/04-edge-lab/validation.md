# Phase 4 — Edge lab: validation

Lean profile (LP1–LP6 in `mission.md`). Every C row names its checks in the G12 form
(LP2). Inherited gates: G1–G5, G7–G9, G11, G12 green via `scripts/gate.sh`, locally and in
CI. G6 deferred (LP5).

## Claim code (RP3)

`tests/drive.py` (the `_drive` handling) and the fault mode in `tap/__main__.py` (delay,
drop, fault records). Mutation testing runs on the drop path and the `_drive` removal
only: they are the sole guards of "the dropped frame never reaches the child" and "the
server sees the fixture minus `_drive`" (LP4).

## C. Phase-specific correctness

| Row | Claim | Checks | Mutation |
| --- | --- | --- | --- |
| C1 | A `_drive` line is sent without its `_drive` member and otherwise unchanged; `expect: none` waits `wait_ms` and does not wait for an id; lines without `_drive` behave as in phase 1 | `tests/test_drive.py::DriveTest::test_drive_member_is_removed_and_rest_unchanged`, `tests/test_drive.py::DriveTest::test_expect_none_does_not_wait_for_id`, `tests/test_drive.py::DriveTest::test_plain_lines_unchanged` | yes |
| C2 | `--drop c2s:<m>` stops the first matching frame at the tap, records it as a frame plus a `fault` record with its `seq`, and forwards every later frame | `tests/test_tap.py::FaultModeTest::test_drop_first_matching_frame_only`, `tests/test_tap.py::FaultModeTest::test_drop_records_fault_with_seq` | yes |
| C3 | `--delay s2c:<ms>` delays each frame by at least `ms` and keeps order; a fault record per delayed frame | `tests/test_tap.py::FaultModeTest::test_delay_keeps_order_and_delays` | no (timing; checked by its test only) |
| C4 | Without fault options, tap output and trace are unchanged: phase 1's tap tests pass untouched | `tests/test_tap.py` | not claim code (RP3) |
| C5 | Every edge fixture records against the real server and its fresh trace is fully explained by the walkthrough (no missing, no extra note) | `tests/test_e2e.py::EdgeLabTest::test_every_edge_fixture_is_explained`, `tests/fixtures/edge-unknown-method.ndjson` | not claim code (RP3) |
| C6 | Lesson 04 has the L1 sections and its runnable blocks pass | `tests/test_lessons.py`, `tools/check_lessons.py` | not claim code (RP3) |

## E. Not-done conditions

The phase is not done if any walkthrough verdict is missing, if a fixture needs a server
change, or if the fault mode alters a run that did not ask for it.

## Result

- Status: open

### Accepted limits

- Learner walk L15, J rows, G6 walk: deferred (LP5).

### Owner learning check (LP6)

Prompts written at close; answers by the owner only.
