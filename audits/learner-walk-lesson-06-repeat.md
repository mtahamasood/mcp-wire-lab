# Learner walk: lesson 06, repeat (phase 8 D13, walk 2)

Fresh clone of `main` at 313a19b (with submodules), Node 24.22.0 via nvm, bootstrap per the README
(about 16 s, "found 0 vulnerabilities", "bootstrap: ok"). Lesson 06 walked end to end: Goal, Predict,
every Run, Read the trace (including the SDK section and walkthrough 06b's `sdk-diff`), Experiments
1 to 4, Check yourself. Raw logs stay on the machine (A5). Outside MCP or JSON-RPC knowledge needed:
none (SEP, envelope, `_meta`, MRTR, task handle are all defined in the Goal).

Reached the end: yes. No stalls, no wrong instructions, no wrong answers.

## Outputs against the lesson

Every `expect` block matched exactly: `check: ok (74 frames)`; discover count 1, initialize count 0;
"every frame has a note" (tour and tasks); "every difference has a note" (era-diff and sdk-diff);
tasks check two lines (`12 of 18 frames ... not the pinned schema.json`, `check: ok (18 frames)`);
Experiment 1 three `-32601` errors (ids 1 to 3, and `tap.check` says `unknown method` for all three);
Experiment 2 `FAILED  RpcError`, tour stops at step 21 with `-32021` (step 20 passes), as the answer
says; Experiment 3 prints `10`; Experiment 4: the quoted two lines are at client/modern.py 337 to
338, deleting them gives "the run ended with exit code 1", `TooManyRounds` at step 24,
`check: ok (77 frames)`, and `git checkout client/modern.py` restores it. The plain tour exits 0
and prints `round <n>: <keys>` lines as stated.

## Status of the previous walk's lesson 06 findings

| # | Previous finding | Status |
| --- | --- | --- |
| 1 | `sdk-tour-2026` fails about 1 in 5 under load (race, "expected two progress notifications") | Fixed as far as seen: 7 recordings of `sdk-tour-2026` (1 in the lesson flow, 6 extra back to back) all exit 0, the sdk-diff passed. Other agents were running on the machine. No retry was needed |
| 2 | tasks `tap.check` expect showed one line | Fixed (two lines present and matching) |
| 3 | Experiment 4 did not mention exit code 1 | Fixed (says so; matches) |
| 4 | Experiment 4 "delete the two lines" unnamed | Fixed (both lines quoted; found by grep at 337 to 338) |
| 6 | Goal used `classify` | Fixed (reworded) |
| 7 | "member-less subclass" and "probe" undefined | Fixed in place, with the 06b pointer. Minor: the sentence is long ("a small subclass of the transport (one with no members of its own, only the one inherited call changed)") but understandable |
| 5 | README npm vulnerabilities sentence | Fixed (SDK install reports 0, README says so) |

## Minor findings (new)

| # | Where | Finding | Suggested fix |
| --- | --- | --- | --- |
| 1 | README / bootstrap | A shell with the default node (v26.12.0 here) gets `bootstrap: need node v24.22.0, found v26.12.0` after 0.02 s: clear and matches the README, so not a defect. Noted only because `nvm use 24.22.0` is needed in every new shell, which the README says | None |
| 2 | Lesson 06, Run (plain tour) | The output is long (about 30 lines); the lesson names no step numbers, so a reader cannot tell "good" except by exit 0 | Optional: add "the last line is `25  notifications/cancelled  closed subscription 15`". **Fixed:** the Run section says the last step closes the subscription |
| 3 | Lesson 06, Experiment 4 | The answer's step-24 failure shows only in `stderr.txt`, and the lesson does not say where to see "TooManyRounds" | Optional: add "(see `stderr.txt` in the run folder)". **Fixed:** the answer says so |

## Effort

Setup about 1 min wall, lesson 06 about 5 min of commands (the walk is mostly mechanical: all
commands are pasteable). No timing-related failure, so no retries.
