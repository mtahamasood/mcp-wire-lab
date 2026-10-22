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

- Status: closed

Closed 2026-10-21 by the agent under the owner's delegation (register row 2026-10-21, spec batch approval): every C row passes on `main` with the gate green (G1-G5, G7-G12; G12 checks this phase). G6, the learner walk and J rows are deferred (LP5).

### Mutation (LP4)

15 hand-applied mutants on the `_drive` removal (`tests/drive.py`, M1-M8) and the drop path
(`tap/__main__.py`, M9-M15), run against `tests/test_drive.py` and `FaultModeTest`. 14 killed on
the first run; 1 survived: M15 (a drop that matches any frame whose text contains the method, not
its `method` member). Resolution: added `FaultModeTest::test_drop_matches_the_method_member_only`;
M15 is then killed. No mutant survives. Killed: the `_drive` member left in; no handling of a
first, middle or last member; `expect: none` treated as `reply`; `wait_ms` ignored; the id wait
kept after the timed wait; the cut line re-serialized; every matching frame dropped; the drop
recorded but the frame forwarded; client-to-server faults ignored; a fault record naming the wrong
frame or claiming `forwarded: true`; the first non-matching frame dropped.

### Builder decisions (candidates for the register)

- `tap.show --explain <file>#<section>` (notes under `## <section>` plus `## shared`) and range
  anchors (`stderr.1-106`): one walkthrough explains eight traces, and the server's stack traces
  on stderr are over a hundred records. Phase 1's behaviour without `#` is unchanged.
- `scripts/record.sh` reports a non-zero server exit instead of failing, because the pinned
  server exits 1 after a transport error (`servers:src/everything/transports/stdio.ts:66`).
- `before-initialize` is walkthrough section for phase 1's `exp-list-first.ndjson` (no copy).
- The fault record's fields: `kind`, `on`, `frame_seq`, plus `ms` (delay) or `method` and
  `forwarded: false` (drop).

### Accepted limits

- J rows and G6 walk: deferred (LP5). The learner walk L15 was done in the final pass for lessons 02-04 (A34, `audits/learner-walk-lessons-02-04.md`).

### Owner learning check (LP6)

Answers by the owner only; open until answered (LP5).

1. *Explain.* Record `edge-duplicate-id` fresh and, without the walkthrough, say which reply
   answers which request and why the client could not tell them apart.
2. *Change.* Predict the trace of `edge-string-id` if the second request used `"id": 1.0`
   instead of `1`, then record it and explain any difference from your prediction.
3. *Debug.* Run the handshake fixture through the tap with `--drop c2s:notifications/initialized`
   and explain, from the trace alone, what the server did with the requests that followed.

Answers:
