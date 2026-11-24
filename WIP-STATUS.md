# WIP-STATUS (phase-08-fix-fl5, review fixes round)

Review: .claude/review-pending/review-fl5.md (in the main checkout). Stopped by STOP-USAGE.

## Done (uncommitted work committed as WIP; none of it run or gated yet)
- F4: `CANCEL_FIRST_WAIT` = NOTE_WAIT + step, used for the first-progress wait in client/tour.py
  (`wait_for_progress(..., wait)`), clients/sdk/src/tour.ts and era.ts. Not yet run.
- F3 and N4: CancelWindowTest (tests/test_e2e.py) asserts the cancelled call's arguments ==
  {"duration": 4, "steps": 2}, and checks stderr per tour (raw: no "late reply"; SDK: exactly
  one "sdk:" error). Written, not yet run. The red run with duration 2 was started and stopped.

## Remaining
- F3: show it red with duration 2 in the three files (edit temporarily, run
  `python3 -m unittest tests.test_e2e.CancelWindowTest`, revert), then green with 4.
- F4: check `python3 -m tap --delay c2s:3200 -- ...` with the raw tour exits 0 as on main.
- F1: tests/test_fake_servers.py: replace sleep(0.5) with a wait for "fake upstream listening on"
  on the stand-in's stderr (under a timeout); add FAKE_PARENT_PID (env, set by the stand-in) to
  tests/fake_servers/http_upstream.py so a parent that dies during startup is seen; add a test
  that kills the parent right after the fake's pid is printed (red first).
- F2, F5, N1, N2, F6: wording in audits/autonomous-decisions.md (A51: (3) the stdio tours do wait
  for the second progress; HTTP runs also use CANCEL_CALL, +1.3 to 2.7 s; flag A51 for the owner's
  Stage F like A49), C206 and the P8-FL-5 row (HTTP cost, file paths and commit hashes, C206 covers
  the SDK stderr check now), docs/walkthrough/02-raw-client-tour.md ("with 2 seconds to spare"
  instead of "even on a slow machine"). No p8-cancel-* mutants (another branch owns phase-08.json).
- Run ruff, mypy, tsc, then the full gate once at the end (scripts/gate.sh, about 7 min; symlink
  vendor/servers, vendor/spec, clients/sdk/node_modules from the main checkout, remove before commit).
