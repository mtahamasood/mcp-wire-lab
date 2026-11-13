# Phase 8 — Final pass: requirements

**Status: approved 2026-11-14.** The owner approved the agent's plan for the final pass, and
that approval stands as approval of this spec (register row 2026-11-14, phase 8 final pass); an
Opus xhigh review of the spec replaces a second sign-off (done 2026-11-14,
`audits/phase-08-spec-review.md`). Phases 1–7's decisions stand unless a
record below names one it amends. This phase adds no lesson and no protocol code: it does the
work LP5 and LP7 deferred, fixes CI, and ends in one owner review.

## Learning objective

Make the finished lab worth trusting and worth learning from. A learner who follows lessons
01–07 from the README meets no stall, no undefined term and no build history; every check the
records claim has run, on GitHub CI as well as locally; and the owner has judged the teaching and
shown, in one combined learning check, that they can explain, change and debug the system.

## Scope

In: CI that can be trusted (Stage A, D3–D7); the deferred verification, a repeatable mutation
tool, mutation of phase 5–7 claim code and one review round over phases 3–7 (Stage B, D8–D10);
teaching polish (Stage C, D11–D12); learner walks (Stage D, D13); the records sweep, the owner
review pack, the final fault branch and a review before the sitting (Stage E, D14–D17); the
owner's review sitting (Stage F, D18); disposition, close and tags (Stage G, D19). D1 and D2 set
how the phase runs.

Out: new protocol features, lessons or transports; anything in the roadmap backlog; publishing
packages, images or GitHub Releases (mission non-goal; a tag names a snapshot only, as for
`v0.7.0`); changes to `vendor/` (read-only).

## Facts at the start (read 2026-11-14)

| Id | Fact |
| --- | --- |
| F1 | GitHub CI failed at the phase 5, 6 and 7 closes and on the `v0.7.0` commit (runs 39810847144, 39810847420, 39819778591, 39855110778, 39855690084), and is red on `main`; the local gate was green. The same commits passed on other refs (39819778388 on `main` at the phase 6 close, 39855110685 on `lesson-07`, 39855690674 on `v0.7.0`), so the failure is intermittent (register row 2026-11-14, correction). |
| F2 | In each failed run a `scripts/record.sh --client` recording exited 1 (`record: the run ended with exit code 1`). In the phase 5 and 6 runs it is the SDK tour (`SdkClientTest.test_record_sdk_client`); in the phase 7 and `v0.7.0` runs the log does not say which recording (`SdkClientTest`'s setup records four, `AtlasClaimsTest` several). `tests/test_e2e.py`'s `record_client` asserts on `record.sh`'s own stderr only; the client's error goes to the run's `stderr.txt`, which CI never prints. The plan's first suspect is the cancel step of `clients/sdk/src/tour.ts` (`cancelled()`, the wait for the late progress notification); Stage A measures before fixing. |
| F3 | `scripts/gate.sh` runs `unittest discover -s tests` under G4, which also runs `tests.test_e2e` and `tests.test_e2e_http`, and then runs both again under G5. |
| F4 | G12 checks only the phases listed in `scripts/gate.sh` (`--phases 02,03,04,05,06,07`; phase 2 D7 as amended by register row 2026-10-21, phase 2 build amendments). |
| F5 | Deferred and still open: mutation runs and review for phases 5–7 (LP7), review for phases 3–4 (LP4), learner walks of lessons 05–07, J rows of phases 2–7, the G6 walk after phase 2, lesson polish (LP5), the owner's review of A23–A46, the learning checks (LP6), the `SdkClientTest` setup flake (A45, A46). |

## How this phase runs

### D1 — The phase's profile

The spec has the two LP1 files. LP7 does not apply. Each test is written before the code it
checks, and for Stage A's tests the failing run is recorded in the Result (RP1). One adversarial
review round runs, in Stage B, by a different and stronger model than the builders (RP2, LP4).
Mutation runs on the claim code named in `validation.md` and in phases 5–7's `validation.md`
(RP3), with `tools/mutate.py` (D8). Findings are triaged as LP4 and RP4 say. The review budget
is stated below (RP6). Every C row names its checks in the G12 form (LP2). Phase 08 is added to
G12's `--phases` list in `scripts/gate.sh` at Stage G's close, when every check its C rows name
exists; until then the list stays `02,03,04,05,06,07`, and a builder closing a stage runs
`python3 tools/check_claims.py --phases 08` and shows that each error left belongs to a later
stage's row.

*Rationale:* the deferred checks are the point of this phase, so the softenings that deferred
them cannot apply to it.
*Rejected:* listing phase 08 in G12 now (its Stage D–F rows name audit files that the stages
write, so the gate would be red until then).
*Cost accepted:* G12 does not guard phase 8's rows until its close.
*Source:* register row 2026-11-14 (phase 8 final pass); mission.md RP1–RP6, LP1–LP5; register
row 2026-10-21 (phase 2 build amendments: G12 lists a phase when its named tests exist).

### D2 — A stage closes on a passed GitHub CI run

A *passed run* is a run of the `ci` workflow (`.github/workflows/ci.yml`, which runs
`scripts/gate.sh`) for a push to `main`, first attempt, conclusion `success`. Runs on other
branches, on tags or on pull requests, and re-run attempts, do not count. A stage of this phase,
and the phase, closes only when the commit that completes its work is on `main` and has a passed
run; the Result names that commit and cites the run's ID (`gh run list --branch main`; `gh run
view <id> --json conclusion,headSha,attempt`). A local `scripts/gate.sh` run is necessary but not
enough. Stage A cites three consecutive passed runs: three run IDs, the first on the commit that
merges the last of D3–D6, with no failed run on `main` between them; a failed run restarts the
count. Every failed run on `main` during the phase is read before the next stage closes, and is
never re-run to get a pass: its cause is read from its log (and from the run artifact, D3) and
either fixed or, if it is a flake, recorded with its cause before a later run counts.

*Rationale:* the "gate green" closes of phases 5–7 were true only locally (F1).
*Rejected:* trusting a local run on a quiet machine (CI is the gate the public sees and the one
that differs: other CPU, no warm caches).
*Cost accepted:* a stage waits for CI, about four minutes per run.
*Source:* register row 2026-11-14 (close on CI); register row 2026-11-14 (correction).

## Stage A — make CI trustworthy

### D3 — A failed recording shows its cause, locally and in CI

When `scripts/record.sh` exits non-zero in an e2e test (`tests/test_e2e.py`'s `record` and
`record_client`, and the matching helpers in `tests/test_e2e_http.py`, through one shared helper
so one test covers both), the assertion message holds `record.sh`'s stderr and the run folder's
`stderr.txt` (its last 200 lines when longer), or says that no run folder was reported.
`.github/workflows/ci.yml` uploads each run folder's `trace.jsonl` and `stderr.txt` as an
artifact only when a step fails (`if: failure()`), kept 7 days; not `bin/` (its links point at
the runner's `node` and `python3`) and not `home/`.

*Rationale:* the SDK tour's error has been in `stderr.txt` all along (F2); nobody could see it.
*Rejected:* printing `stderr.txt` on success (noise in every run); committing run output (A5);
uploading the whole of `runs/` (the `bin/` links would pull interpreters into the artifact).
*Cost accepted:* a failed CI run's traces and stderr files are downloadable by readers of the
public repository for 7 days. This is the one exception to the non-goal on shipping run output
(A5), approved with the plan (register row 2026-11-14, phase 8 final pass): the output is made on
the CI machine, the server runs under the recording allowlist (phase 1 D14), the workflow holds
no secret, and nothing from a learner's or the owner's machine is in it. It is never committed,
and the owner may withdraw it (A47).
*Source:* register row 2026-11-14 (phase 8 final pass); A5, 2026-10-20.

### D4 — The SDK tours survive load

First the race is reproduced: `scripts/record.sh --client sdk-tour` under CPU load (four busy
processes, for example `stress -c 4`), until it fails, and the cause is read from `stderr.txt`
and recorded in the Result. If `sdk-tour` does not fail, the other recordings the failed runs
made (F2) are tried the same way. The fix goes where the measurement points, which need not be
the plan's suspect (the cancel step, F2); the Result says where. Then a test that reproduces the
measured cause is written and its failing run recorded: deterministically where it can be (for
example a fake server, or holding frames back with the tap's `--delay`), otherwise under load.
Then the cause is fixed. The fix makes the step wait on, or receive, what it depends on, not a
longer fixed delay; a bound that is only widened is acceptable only when the measurement shows
the step correct but slow, as A45 did for the large-write test, and the Result says so. The
traces the tours produce do not change, so walkthroughs 02 and 05 still explain them;
walkthrough 05 may gain a note on the cause. Evidence in the Result: 20 consecutive `sdk-tour`
recordings under the same load with 0 failures (and the same for any other recording the
measurement implicated), and whether the `SdkClientTest` setup flake (A45) appeared.

*Measured* (by the Stage A builder, 2026-11-14, before this spec merged): `sdk-tour` failed 27
of 30 runs under load, and `sdk-tour-2026` 8 of 12, at the long-running step ("expected two
progress notifications"), not the cancel step. The pinned SDK runs a notification's handler one
microtask after it is read (`sdk:client/dist/src-WCy6ifGf.mjs:5903`) but settles a response at
once, removing the request's progress handler (`:6055`), so a progress notification read in one
chunk with its response is reported for an unknown token. The fix is `clients/sdk/src/order.ts`,
which hands responses to the SDK one microtask late, for both eras and both transports; its test
is `clients/sdk/test/order.test.ts` (C3). The Result records the failing run and the stress
evidence.

*Rationale:* a flaky test that fails in CI and passes locally is what let the false greens in.
*Rejected:* skipping or retrying the test (hides the race); a longer timeout without a measured
cause.
*Cost accepted:* the stress run costs local CPU time once.
*Source:* register row 2026-11-14 (phase 8 final pass); register rows 2026-10-22 (phase 5 build,
where the SDK tour was built; phase 6 build, where the setup flake was seen).

### D5 — The e2e tests run once per gate

G4's unit-test run no longer runs the modules G5 runs (`tests.test_e2e`, `tests.test_e2e_http`);
G5 runs them, as now. No test is dropped: every test G4 and G5 ran before still runs exactly once.
`tech-stack.md` G4 and G5 are unchanged in meaning (unit tests; end-to-end tests).

*Rationale:* the duplicate run costs about 90 s per gate and doubles the exposure to a flake (F3).
*Source:* register row 2026-11-14 (phase 8 final pass); tech-stack.md G4, G5.

### D6 — No leaked processes or open files

No tap, server or client process started by a test outlives the test, and no test module run by
G4 or G5 emits a `ResourceWarning` (CI's log shows them today, for example in `tests.test_e2e_http`,
`tests.test_tap_http` and `tests.test_show`). Each leak found is fixed where it starts (a process
not waited for, a pipe or socket not closed), not silenced. Evidence in the Result: the logs of
Stage A's three passed runs (D7) hold no `ResourceWarning` (`gh run view <id> --log`).

*Rationale:* leaked `python3` tap processes and the `ResourceWarning` in the e2e and HTTP tests
load the machine the next test runs on, which feeds the race in D4.
*Rejected:* making the gate fail on a `ResourceWarning` (a new gate rule the plan did not ask for,
and a new source of red runs while Stage A needs three green ones; the owner may add it by a
register row).
*Source:* register row 2026-11-14 (phase 8 final pass).

### D7 — Stage A's exit

Stage A closes when D3–D6 are merged and three consecutive GitHub CI runs on `main` have passed
(D2), with their IDs in the Result, and the evidence of D4 and D6 is recorded. The correcting
register row for the phase 5–7 closes is added with this spec (register row 2026-11-14,
correction).

*Source:* register row 2026-11-14 (phase 8 final pass); register row 2026-11-14 (close on CI).

## Stage B — deferred verification

### D8 — `tools/mutate.py`, a repeatable mutation run

`python3 tools/mutate.py <mutants file>` runs the hand method of phase 1 (`audits/show-review.md`
section 3; `specs/phases/01-wire-tap/validation.md`, the mutation notes of C1–C16) as a tool,
with the standard library only (P4). The mutants file is authored JSON: per mutant an id, a file,
the exact text to replace, its replacement, the test command that should catch it, and, once the
report signs it equivalent, an `equivalent` field with the reason. The tool:

- copies the repository's tracked files (and the built server and SDK packages the tests need,
  by link or copy) to a temporary directory and works only there; the real tree is never written;
- runs the baseline test command once per distinct command and stops if a baseline fails;
- applies each mutant as one exact text replacement; the text must occur exactly once in the file,
  else the mutant is an error and is not run;
- runs the mutant's command, records its exit code and failing tests, then restores the file and
  checks it byte for byte against the original (`cmp`, or the same comparison in Python); a
  mismatch stops the run;
- empties the copy's `runs/` before every command and stops if an entry is still there (the S17
  contamination: a run that fails for a stale folder looks like a killed mutant);
- prints one line per mutant (`killed`, `survived`, `equivalent` or `error`, with the failing
  tests) and a summary, and exits 0 only when every mutant is killed or marked equivalent and
  survives; a survivor not marked equivalent, or an error, exits 1.

The tool's output is run output (A5) and is not committed; what is committed is the mutants
files and the authored report (D9).

*Rationale:* phases 1 and 2 ran mutation by hand; the deferred runs for phases 5–7 should be
repeatable by anyone.
*Rejected:* a third-party mutation framework (P4, and AST operators would mutate code that is not
claim code); mutating the real tree in place (a crash would leave a mutant behind).
*Cost accepted:* exact-text mutants are hand-written; the tool finds no mutant by itself.
*Source:* register row 2026-11-14 (phase 8 final pass); mission.md RP3; register row 2026-10-21
(the step (a) mutation run).

### D9 — Mutation of the phase 5–7 claim code

Mutants are written for the claim code each phase's `validation.md` names, where a C row's check
is the sole guard of a protocol rule (LP4): phase 5, `tap/diff.py`'s message keys and
comparison; phase 6, `client/modern.py`'s discover gate, subscription id match, `inputResponses`
and `requestState` echo and result-type decision, and in `tap/check.py` the `input_required`
rule, the extension loader's collision guard and the `resultType: "task"` rule; phase 7,
`tap/http.py`'s SSE parser and streaming forwarder and `client/http_wire.py`'s rows marked
`yes`. The mutants files are `audits/mutants/phase-05.json`, `phase-06.json` and
`phase-07.json`; at least one mutant per `yes` row. This phase's own claim code
(`validation.md`: `tools/mutate.py` and D4's fix, `clients/sdk/src/order.ts`) goes in
`phase-08.json`. Each survivor is killed by a test that pins behaviour the spec specifies, or
signed as an equivalent mutant with its reason (RP3); a survivor that shows a spec gap gets a
register row first. The report, `audits/mutation-final-pass.md`, lists every mutant with its
verdict and the test that killed it, and each phase's `validation.md` Result gains one line
pointing to it.

*Source:* register row 2026-11-14 (phase 8 final pass); mission.md RP3, LP4; register row
2026-10-22 (lean build of phases 5-7: mutation deferred to the final pass).

### D10 — One review round over phases 3–7

One adversarial review by Opus at high effort (the builders were Sonnet): phases 5, 6 and 7 in
full, each on its diff from the phase's base on `main`; phases 3 and 4 on their claim code only
(`client/handlers.py` and the notification reactions; `tests/drive.py`'s `_drive` handling and
the tap's fault mode). Two reviewer runs, splitting the phases between them, may run in
parallel. The corpus goes to `audits/final-pass-review.md`, with findings numbered
`P8-R<phase>-<n>` (`P8-R5-1` is phase 5's first, as the reviewers wrote them), a severity, a
reproduction and a proposed fix. Each finding is reproduced before it is fixed; one that cannot
be is recorded so and not fixed (RP2). Disposition (LP4, RP4): blockers and majors fixed; a
minor fixed when cheap or in claim code; other minors and nits to *Accepted limits* in one line
each. Each fix gets a test, named in a new C row of this phase in the disposing commit. A
finding whose fix would change scope is a stop point.

*Source:* register row 2026-11-14 (phase 8 final pass); mission.md RP2, RP4, LP4; register row
2026-10-22 (lean build of phases 5-7: review deferred to the final pass).

## Stage C — teaching polish

### D11 — Lessons and walkthroughs

- Lessons 01 and 04 gain *Predict* answers at the end, as lessons 02, 03, 05, 06 and 07 have
  them, as the README promises; every lesson's *Predict* section points to its answers, as 02, 05
  and 06 do (03 and 07 gain the pointer).
- Lesson 05 gains runnable experiments with expected output (G9 runs them) and a section that
  uses the SDK server tour (`sdk-server-tour`).
- Lesson 06 defines each term at its first use (`_meta` envelope, MRTR, SEP, `-32021`, task
  handles, and any other the walk finds) and points to the walkthrough's "five shifts" table and
  its `#tasks` section. This rewrite is done by Opus at high effort.
- Lesson 07 loses its build history ("before the fix…" and the like), defines terms before using
  them, and has fewer, simpler experiments, each with its measured outcome.
- Walkthrough 06b (`docs/walkthrough/06-sdk-2026.md`) replaces its filler notes (about 15, notes
  that say nothing about the frame) with what each frame shows.
- Spec record ids (`D2`, `C14`, `G5`, `LP4`, `phase 4 D2` and the like) leave learner text: the
  lessons and walkthroughs say what the rule or check is instead. The README keeps the gate list.

A changed walkthrough still explains every frame of its fresh traces (`--explain`), and every
changed citation still resolves (G8).

*Source:* register row 2026-11-14 (phase 8 final pass); mission.md LP5 (lesson polish deferred);
roadmap.md L1, L4, L5.

### D12 — README, atlas and feedback

`README.md`: the stale lines are fixed (the newcomer walk and the learner walks name them), the
atlas is a step on the learning path, walkthrough 06b is listed beside lesson 06, the gate list
names G10, and a feedback route points to the issue template. A new
`.github/ISSUE_TEMPLATE/feedback.md` asks for the lesson, the step, what was expected and what
happened. The atlas says why its tasks rows are `unexercised` (they come from the 2025-11-25
schema, and no 2025-era run uses tasks; the lab's tasks run is 2026-07-28, whose pinned schema has
no tasks types, so that run is checked against the SEP-2663 extension, phase 6 D14), in its
generated text so G10 still holds.

*Source:* register row 2026-11-14 (phase 8 final pass); roadmap.md L1, L8.

## Stage D — learner walks

### D13 — Two walks by fresh agents

Each walker is a fresh agent with no project context, working in a clean clone outside the
repository (`git clone --recurse-submodules`), following L15:

1. Lessons 05–07, from the README.
2. The whole path, lessons 01–07, from the README; this is also the G6 clean-clone walk for
   phases 3–7 (bootstrap and `scripts/gate.sh` in the clone).

The walkers' logs stay on the machine (A5). What is committed is each walk's list of stalls and
wrong answers, each with its fix or signature: `audits/learner-walk-lessons-05-07.md` and
`audits/learner-walk-full-path.md`. Every stall and wrong answer is fixed; then a walk is
repeated once, by a new fresh agent, for the lessons that had a stall. A stall left after the
repeat is a stop point.

*Source:* register row 2026-11-14 (phase 8 final pass); roadmap.md L15; mission.md LP5;
tech-stack.md G6.

## Stage E — records sweep and the owner's review pack

### D14 — Records sweep

The records are brought in line with each other and the register: phase 6's mutation line
("*to be filled*") points to D9's report; phase 7's Result no longer reads as if parts B2, C and
D were unbuilt; phase 2's agent-run friction notes say they were applied to the prompts (A36;
register row 2026-10-21, learning check run by an agent), not "not yet dispositioned"; phase 7's
learning check stops naming `learning-check-07-fault`, which does not exist; the owner
learning-check sections of phases 2–7 are marked *superseded by phase 8* (not removed); the
`SdkClientTest` flake of A45 and A46 is closed by D4's result. A closed record's text is
corrected in place, wording only, with a pointer to the register row that authorises it; one
register row at Stage E's close names every closed record so corrected. A register row is never
edited, and is corrected by a new row. Before deleting `learning-check-02-fault` the agent checks
that it holds only the fault described in phase 2's validation file and records its tip commit
in the Result.

*Source:* register row 2026-11-14 (phase 8 final pass); register row 2026-11-14 (learning check
superseded); register row 2026-10-21 (learning check run by an agent); mission.md decision
register (append-only).

### D15 — The owner review pack

`audits/owner-review-pack.md`, written for one sitting, holds:

- decisions A23–A46 (and A47 onward from this phase), one line each, with a place to accept or
  overrule;
- J rows drafted for phases 2–7 (judgement checks the owner marks pass or fail, in the form of
  phase 1's J rows);
- a teaching rubric per lesson 01–07: clarity, whether *Predict* worked, where the owner stalled,
  a score 1–5 and a free comment;
- the combined learning check: *Explain* a fresh trace from lessons 02 and 03 from `tap.show`
  alone; *Change* the client in a stated way, predict the new trace in writing, then run it, on
  an owner-authored commit on a branch of the owner's own; *Debug* the fault on
  `learning-check-final` (D16) from test output and a fresh trace, without `git diff` or
  `git log -p`.

Only the owner writes answers. The agent checks each answer against a fresh trace and adds a
one-line verdict under it, never editing the owner's words.

*Source:* register row 2026-11-14 (phase 8 final pass); register row 2026-11-14 (learning check
superseded); mission.md LP6.

### D16 — The final fault branch

The agent plants one fault in protocol code on a local branch `learning-check-final`, cut from
`main` once the rest of Stages A–E is merged (Build order 5). The branch is never pushed, and its
commit message names no fault. The fault and its model answer are kept outside the repository, in
the agent's project memory (a scratchpad does not outlive its session), and described in no
committed file until the owner has answered; then the pack records the fault, the answer and the
verdict.

*Source:* register row 2026-11-14 (learning check superseded).

### D17 — A review before the sitting

Before the owner's sitting, Opus at xhigh effort reviews the phase 8 result (Stages A–E, against
this spec) and the review pack (is every A row, J row and rubric item there; are the prompts
answerable; does any committed file hint at the fault). It also checks each CI run ID the
Results of Stages A–E cite with `gh run view <id> --json conclusion,headSha,attempt` (D2), and
that the logs of Stage A's three runs hold no `ResourceWarning` (D6). The report goes to
`audits/final-pass-pack-review.md`; its findings are disposed as D10's are before the pack goes
to the owner.

*Source:* register row 2026-11-14 (phase 8 final pass).

## Stage F — the owner's sitting

### D18 — One review sitting

The owner, in one sitting of about 3–4 hours that may be split by lesson: follows each lesson
01–07 as a learner and fills its rubric; does the combined learning check; marks the J rows;
accepts or overrules A23–A46 (and A47 onward). The agent then adds its verdicts (D15) and reveals
the fault (D16).

*Source:* register row 2026-11-14 (phase 8 final pass); register row 2026-11-14 (learning check
superseded); the owner, 2026-10-21 (register row 2026-10-21, learner walk dispositions).

## Stage G — disposition and close

### D19 — Disposition, close and tags

Opus at high effort triages every comment and overrule from Stage F into *fix now*, *accepted
limit* or *backlog*, as a list in the pack. The owner approves the list and the tags in one
answer (the third touchpoint, a stop point). The fixes are applied (Sonnet, medium), each fix
that changes behaviour with its test and C row. Then: phase 08 is added to G12's list (D1); the
Result is filled with every stage's CI run ID and `Status: closed`; `CHANGELOG.md` gains a
`[1.0.0]` section; the roadmap marks phase 8 done; an overruled A row gets its register row. Once
the closing commit has a passed run (D2), `lesson-08` and the annotated tag `v1.0.0` are created
on it and pushed, under that approval. No package, image or GitHub Release is published.

*Source:* register row 2026-11-14 (phase 8 final pass); register row 2026-10-23 (version tag);
mission.md non-goals.

## Build order

Stages run A → G. Within that order:

1. **A** first. `tools/mutate.py` (D8, a new file) and the Stage C polish may be built beside A,
   since they share no file with it; no other stage closes before A has closed (D2 needs a CI
   that can be trusted).
2. **B.** The two reviewer runs of D10 and the C polish may overlap, since the review reads code
   and the polish edits docs; a review fix that touches a lesson or walkthrough waits for the
   polish branch to merge. Mutation runs (D9) start once D8 is merged.
3. **C** closes when G9, G8 and every `--explain` check pass on fresh traces, in CI (D2).
4. **D** after C merges (the walkers read the polished lessons).
5. **E** after D's fixes merge; D16's branch is cut last, from that `main`.
6. **F**, the owner.
7. **G** after the owner's disposition approval.

The agent offers a handoff at every stage boundary and before launching the parallel review and
walk agents.

## Models and effort

| Stage | Work | Model, effort |
| --- | --- | --- |
| A | CI fixes, the race, stress run | Opus, high; fresh session |
| B | `tools/mutate.py`, mutants, survivor tests, review fixes | Sonnet, medium |
| B | Review round (D10) | Opus, high |
| C | Polish | Sonnet, medium; lesson 06's concept rewrite Opus, high |
| D | Learner walks | fresh agents with no project context; Sonnet, medium |
| E | Records sweep, review pack, fault branch | Sonnet, medium |
| E | Review before the sitting (D17) | Opus, xhigh |
| F | Review sitting | the owner |
| G | Triage | Opus, high |
| G | Applying fixes, close | Sonnet, medium |

## Review budget (RP6)

Unit: agent runs. Review: two Opus reviewer runs for D10 and one Opus xhigh run for D17, with no
second round of either. Hardening: at most four fixer runs for D10's dispositions and D9's
survivors together, and at most one for D17's. Mutation: one run of `tools/mutate.py` per
mutants file, plus one re-run per file after its survivors are disposed. Learner walks: one
repeat per walk (D13). These caps are the budget; they are sized to keep review and hardening
near RP6's target of about one third of the phase's agent runs (Stages A–E). When a cap is
reached with work left, the work stops and a register row records why; the owner decides what
follows.

## Stop points

The agent runs unattended (register row 2026-11-14, phase 8 final pass) and stops for the owner
only at:

- the owner's two remaining touchpoints: the Stage F sitting, and the Stage G approval of the
  disposition list together with the `lesson-08` and `v1.0.0` tags (one answer, D19);
- a blocker it cannot resolve within the spec, including a Stage B finding whose fix changes
  scope and a learner-walk stall left after its repeat (D13);
- a scope change, or a change to a constitution rule beyond the register rows of 2026-11-14;
- an irreversible or outward-facing action not already approved: pushing a tag before the Stage G
  approval, deleting a branch other than `learning-check-02-fault` (D14), force-pushing,
  publishing anything;
- a budget cap reached with work left.

A pause is not a stop point. When the owner's usage window nears its limit, the agent stops at a
safe point (work committed and pushed, a handoff written) and resumes from memory in the next
window, with no owner input needed.

## Stop condition

Every C row passes; every stage's Result cites its passed CI run IDs (D2); the owner has done the
sitting and approved the disposition; phase 08 is listed in G12 and the gate passes locally and
in CI; `lesson-08` and `v1.0.0` exist.
