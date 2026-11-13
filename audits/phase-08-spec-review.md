# Phase 8 spec review (Opus xhigh): the final pass

Reviewer: Opus 5.5 at xhigh effort, an agent that did not write the spec. Date: 2026-11-14, in two
sessions (the first stopped at the owner's usage limit and left a WIP commit; the second finished
it). This review replaces a second owner sign-off of the spec (register row 2026-11-14, phase 8
final pass). Scope: the spec commit, `specs/phases/08-final-pass/requirements.md` and
`validation.md`, the four register rows of 2026-11-14 and the LP5 and LP6 pointer sentences in
`specs/mission.md`, and A47 in `audits/autonomous-decisions.md`. Contract: the plan the owner
approved on 2026-11-14 (kept outside the repository), `specs/mission.md` (RP1–RP6, LP1–LP7, the
non-goals, the append-only register) and `specs/tech-stack.md` (G1–G12).

## What I ran

- Every CI run the spec cites, with `gh run view <id> --json conclusion,headSha,headBranch,event,attempt`,
  and every run of the four close commits with the Actions API (`runs?head_sha=`). All are `ci`
  push runs, attempt 1:

  | Commit | What it closed | Failed | Passed |
  | --- | --- | --- | --- |
  | `d219dc8` | phase 5 | 39810847144 (`main`), 39810847420 (`lesson-05`) | none |
  | `18a1c49` | phase 6 | 39819778591 (`lesson-06`) | 39819778388 (`main`) |
  | `284cc48` | phase 7 | 39855110778 (`main`) | 39855110685 (`lesson-07`) |
  | `bf650e7` | `v0.7.0` | 39855690084 (`main`) | 39855690674 (`v0.7.0`) |

  The latest run on `main` is 39855690084, a failure: `main` is red.
- The failed jobs' logs (`gh run view <id> --log-failed`): phases 5 and 6 fail in
  `SdkClientTest.test_record_sdk_client`; phase 7 in `AtlasClaimsTest`, which records several
  tours, `sdk-tour` among them; `v0.7.0` in `SdkClientTest`'s `setUpClass` and `AtlasClaimsTest`.
  Each says only `record: the run ended with exit code 1`. The `v0.7.0` run's log holds 8
  `ResourceWarning`s, from `tests.test_tap_http`, `tests.test_show`, `tests.test_tap` and
  `tests.test_e2e_http`.
- The pinned SDK's dispatch, `clients/sdk/node_modules/@modelcontextprotocol/client/dist/src-WCy6ifGf.mjs`:
  line 5903 runs a notification handler in `Promise.resolve().then(...)`; line 6055 deletes the
  request's progress handler as its response is settled.
- The parallel builds, read only, to check the spec against what is being built: Stage A's
  branch (the fix, its node test, the CI step, the failure helper, the gate split), the
  `tools/mutate.py` branch and its tests, and the reviewers' pending corpora for D10.
- After the fixes: `python3 tools/check_provenance.py` (G1, G7): ok;
  `python3 tools/check_claims.py --phases 02,03,04,05,06,07` (G12): ok;
  `python3 tools/check_no_run_output.py` (G11): ok; `python3 -m unittest tests.test_provenance
  tests.test_check_claims`: 32 tests, OK. `python3 tools/check_claims.py --phases 08` lists only
  checks that later stages write (Stage A's tests, `tools/mutate.py`, the audit files, the Stage
  C and E tests), as D1 expects before Stage G.

Counts: 0 blockers, 7 majors, 15 minors. All are fixed in the spec commit that this file ships
with; none is deferred.

## Majors

### S8-1: the run facts and the cause were stated beyond the evidence (F1, F2, correction row)

F1 and the correction row said CI failed at each close and called the cause the SDK tour's
cancel step. The same commits passed on other refs (39819778388, 39855110685, 39855690674), so
the failure is intermittent, and at the phase 6 close `main` was green; only the phase 5 and 6
logs name the SDK tour, and nothing yet measured the cancel step. *Fixed:* F1 lists the passes;
F2 names what each log shows and keeps the cancel step as the plan's suspect; the correction
row lists the passes and leaves the cause to Stage A (D4).

### S8-2: the close rule did not say which run counts (D2)

"A passed GitHub Actions run" let a tag or branch run, a re-run attempt or a run on another
commit close a stage, and Stage A's "three consecutive" had no start or reset. *Fixed:* D2
defines a passed run (the `ci` workflow, a push to `main`, attempt 1, `success`, on the commit
that completes the work), how Stage A counts three (the first on the commit that merges the last
of D3–D6, a failed run restarts the count) and forbids re-running for a pass. New row C20 and a
not-done condition check it.

### S8-3: "the gate fails on a `ResourceWarning`" was a new gate rule (D6, C5)

The plan asked to fix the leaks, not to change G4 and G5, and D5 keeps their meaning. The rule
would also add a source of red runs while Stage A needs three green ones. *Fixed:* D6 asks for the
leaks to be fixed where they start, with the logs of Stage A's three passed runs as evidence
(re-checked by D17); C5 names that evidence; the rule is recorded as rejected, for the owner to
add by a register row if wanted.

### S8-4: C12 and C3 named too few or the wrong explain checks

C12 left out the explain checks of walkthrough 05 (`SdkClientTest::test_tour_diff_is_explained`,
`test_server_tour_diff_is_explained`) and of walkthrough 06's era diff and tasks section
(`ModernTourTest::test_era_diff_is_explained`, `TasksTest::test_tasks_2026_runs_and_is_explained`),
so a polish edit to those sections would pass C12. C3 named the walkthrough-02 test only.
*Fixed:* C12 names all four; C3 names the tests for walkthroughs 02 and 05.

### S8-5: C3 named a test that does not exist, and D4 fixed code the measurement cleared

C3 cited `SdkClientTest::test_cancel_step_survives_load`, and D4 and the claim-code section
required the cancel step of `clients/sdk/src/tour.ts` to be fixed and mutated. The Stage A
measurement found the race elsewhere: under load the long-running step fails ("expected two
progress notifications") because the pinned SDK runs a progress handler one microtask late but
removes it when the response settles (the two SDK lines above); the cancel step is not involved.
The fix, `clients/sdk/src/order.ts`, hands responses to the SDK one microtask late, and
`clients/sdk/test/order.test.ts` reproduces the race deterministically with a fake server (red
before the fix, green after). No Python test wraps the node tests: G4 runs them with
`node --test`, so the node test file is the check, as phase 5 C6 and phase 7 C29 cite theirs.
*Fixed:* C3 cites `clients/sdk/test/order.test.ts` with the walkthrough tests; D4 lets the fix go
where the measurement points, records the measurement, and no longer forbids the walkthrough-05
note that explains it; the claim code and D9 name `order.ts`, whose mutant is a response handed
over at once.

### S8-6: C16 checked something CI cannot see

C16 required that no closed Result "names a learning-check branch that does not exist". The
learning-check branches are local only and never pushed, so the check would pass or fail by
machine. *Fixed:* C16 now checks what D14 asks of the records: every *Owner learning check*
section of phases 2–7 is marked superseded, by a new test
`tests/test_provenance.py::RecordsSweepTest::test_owner_learning_checks_marked_superseded`.

### S8-7: the phase's process rules had no C row (D1, D2, D7, D16)

The close-on-CI rule, phase 08's entry into G12 and the secrecy of the final fault were claims
with no row, so G12 and the not-done list could not reach them. *Fixed:* C20 (Results cite passed
run IDs, checked by D17 and before the tags; phase 08 in G12 at the close) and C21 (the final
fault branch: local, cut last, no hint in commits or committed files until the owner answers).

## Minors

- S8-8 (D3, C2): uploading all of `runs/` would follow the `bin/` links to the runner's `node`
  and `python3`. *Fixed:* the artifact is each run folder's `trace.jsonl` and `stderr.txt`.
- S8-9 (D3, A47 (3), phase 8 register row, *Accepted limits*): the artifact was justified as the
  agent's reading of A5. It is a plan-approved exception to the non-goal on shipping run output
  (the plan says "upload `runs/` as a CI artifact on failure"). *Fixed:* framed so in D3, A47,
  the phase 8 register row and the accepted limit.
- S8-10 (D3, C1): D3 covers the helpers of both e2e modules, but C1's one test is in
  `tests/test_e2e.py`. *Fixed:* one shared helper, so one test covers both.
- S8-11 (D4): only `sdk-tour` was to be measured, and the test could only run under load.
  *Fixed:* the other recordings the failed runs made are tried if `sdk-tour` does not fail; a
  deterministic test is preferred.
- S8-12 (D8, C6): no way to sign an equivalent mutant without failing the run, and the `runs/`
  guard was worded two ways. *Fixed:* an `equivalent` field, an `equivalent` verdict and test
  `test_marked_equivalent_does_not_fail_the_run`; one guard wording ("an entry left in the
  copy's `runs/` before a command stops the run"); a typo in C6 corrected.
- S8-13 (D9, C7): this phase's own claim code had no mutants file. *Fixed:* `phase-08.json`.
- S8-14 (D10): the finding ids (`FP-R<n>`) and "one run per scope" did not match the two review
  runs already made, which number findings `P8-R<phase>-<n>` and split the phases 05–06 and
  03, 04, 07. *Fixed:* D10 takes the reviewers' ids and split.
- S8-15 (D11): lessons 03 and 07 have *Predict* answers but no pointer to them. *Fixed:* they
  gain the pointer, checked by C9.
- S8-16 (D12): the atlas reason for `unexercised` tasks rows was inaccurate (the rows come from
  the 2025-11-25 schema; the lab's tasks run is 2026-07-28). *Fixed.*
- S8-17 (D13): "repeat until none is left" had no bound. *Fixed:* one repeat by a new agent; a
  stall left after it is a stop point.
- S8-18 (D14): phase 2's friction notes were applied to the prompts (A36), not left open; the
  sweep had no register row. *Fixed:* D14 says so, and one register row at Stage E's close names
  every corrected record.
- S8-19 (D16): the fault and its answer were to be kept in "the agent's scratchpad and memory",
  but a scratchpad does not outlive its session; the branch was cut "after Stages A–D are
  merged", against the build order (cut last, in Stage E); the commit message was not stated.
  *Fixed:* the answer is kept in the agent's project memory; the branch is cut once the rest of
  Stages A–E is merged; its commit message names no fault.
- S8-20 (D17, D19, stop points, budget): D17 did not re-check run IDs or logs; the stop points
  listed the disposition list and the `v1.0.0` tag as two touchpoints, where the plan and the
  register row make them one answer, and made any tag push a stop although D19 pushes the tags
  under that approval; nothing said what a usage-window pause is; the budget left out D17's run
  and the walk repeats. *Fixed:* D17 checks each cited run and Stage A's logs; the plan approval,
  the sitting and one disposition-and-tags answer are the three touchpoints; only a tag pushed
  before that approval is a stop; a pause is not a stop point; the budget counts D17 and the
  repeats, and A47 (7) states the same budget.
- S8-21 (validation *Not-done*): a cited run that is not a passed run was not a not-done
  condition. *Fixed.*
- S8-22 (register row *Learning check superseded*): it amended the 2026-10-21 learning-check rows
  but not the 2026-10-23 version-tag row, whose "below 1.0 until the final pass and the phase 2
  learning check are done" it also changes. *Fixed:* the row names it.

## Notes for the builds now running (not spec defects)

The spec is the contract; these are places where a branch built in parallel does not yet meet
it. Each must be closed before that stage closes, or the spec amended by a register row.

1. Stage A's `.github/workflows/ci.yml` uploads `path: runs/`, the whole folder. D3 and C2 allow
   only each run folder's `trace.jsonl` and `stderr.txt` (S8-8).
2. Stage A's failure helper shows the last 40 lines of `stderr.txt` and the exit record; D3 and
   C1 say the last 200 lines. When no run folder is reported it returns `record.sh`'s stderr
   without saying so; D3 asks for that line.
3. Stage A has not yet written C2's `GateTest::test_ci_uploads_runs_on_failure` or C5's
   `RecordHttpTest::test_no_tap_process_left_after_record`.
4. The `tools/mutate.py` branch was built before S8-12: it has no `equivalent` field or verdict
   and no `test_marked_equivalent_does_not_fail_the_run`. It reports a timeout as
   `killed (timeout)`, which D8 does not name; a timeout counted as a kill is the usual reading
   and needs no amendment, only a line in the report.
5. The phase 3, 4 and 7 review corpus is partial by its own account (some mutants not run, a
   *not covered* list). D10 is met only when every scope it names is reviewed or its gap is
   recorded under the budget rule.

## Verdict

Approved for build. No blocker or major is open in the spec. The notes above bind the builders,
not the spec.
