# WIP status: phase-08-mutants-08 (D9 mutation of phase 8 claim code), stopped on STOP-USAGE

Merged main twice (last 2b6baec). Delete this file in the first real commit.

## Mutants (audits/mutants/phase-08.json, 175 mutants)
Last full run (after the 2b6baec merge, before the P8-MU-1 work): 175 mutants, 148 killed, 26
equivalent (reasons are the `equivalent` fields in the json), 1 survivor
(`p8-httpwire-post-wait-notifications-only`). That survivor has a new test
(`HttpWireTest::test_next_post_waits_for_a_reply_and_a_junk_line_too`) that passes on the real code;
NOT yet re-run against its mutant. Every other survivor of earlier partial runs got a test or a
signed reason (verified killed by `--only` re-runs: C168-C172 tests below, and the node tests via a
temp-copy runner). Node mutants: all killed or signed equivalent (6 signed). The 4 handler hang
mutants were fixed by a 5 s timeout in `tests/test_client_handlers.py` `Rig.read`.
Verdicts ran while a stray `node --test` (from my own scratch runner, not mutate.py) took a CPU; the
one verdict that changed between runs (`post-wait-notifications-only`) is the survivor above; kills
by timing tests (`test_join_*`, `test_next_post_waits_no_longer_*`) should be re-checked alone.

## Tests verified red -> green
C160-C167 (previous agent's): verified green on code, killing their mutants (run1).
C168 listen result, C169 control char / refused notification, C170 close wiring (node, needs the
`export` of `Tour`/`ServerTour`), C171 listen tag, C172 join/wait bounds: green on code, each
mutant killed in a `--only` / temp-copy run.
NOT verified: `test_next_post_waits_for_a_reply_and_a_junk_line_too` against its mutant (no C row yet).

## P8-MU-1 (mutate.py leaves a child that is in its own session/group alive after a timeout)
Fix written in `tools/mutate.py` (tag in env `MUTATE_RUN_TAG`, scan /proc/*/environ, SIGKILL all
tagged processes on timeout before communicate() and in a `finally` after every command).
Tests written in `tests/test_mutate.py`: `test_a_timeout_kills_a_child_in_a_session_of_its_own`,
`test_a_child_left_behind_by_a_command_that_ended_is_killed`. Red on the old code: both red
(verified). Green on the fix: the "left behind" test green; the "timeout" test FAILED because the
unmutated baseline also held the pipe (red baseline); the test was changed (child holds the pipe
only when mutated) and NOT re-run. ruff/mypy not re-run after these edits.
Not done: C row (use C173), audit row P8-MU-1 in `audits/final-pass-review.md`, mutants of the
new kill code (suggested: drop the early `kill_tagged` in the timeout branch; drop the `finally`;
drop the env tag; SIGTERM instead of SIGKILL; child that ignores SIGTERM is already in the tests),
a re-run of the whole `tools/mutate.py` mutant block (p8-mutate-*) against the new code.
A stray `time.sleep(300)` child may remain from the red runs: check `ps` and kill it.

## Remaining steps
1. Re-run the P8-MU-1 tests green; ruff (`uvx ruff@0.17.1 check .`), mypy (`uvx mypy@2.4.0`), tsc.
2. Add the P8-MU-1 mutants to the json, run them; re-run `p8-httpwire-post-wait-notifications-only`.
3. Add C rows (C173+: P8-MU-1; the junk/reply wait test) to `specs/phases/08-final-pass/validation.md`
   (C160-C172 are written) and the P8-MU-1 row to `audits/final-pass-review.md`.
4. Write the phase 8 section of `audits/mutation-final-pass.md` between the phase 8 markers:
   table from the final run (scratchpad generator `m8x/report.py`, output `m8x/final.txt`), survivors'
   dispositions (above), findings (P8-MU-1; `Rig.read` timeout; `export` of Tour/ServerTour as a test
   seam; flake of `test_manual_posts_typed_line_verbatim` found, fixed on main as P8-FL-2), update the
   summary table row for phase 8.
5. `scripts/gate.sh` once; squash the WIP into clean commits (the P8-MU-1 fix in its own commit, SHA
   to report), delete this file, push with --force-with-lease.
Symlinks (vendor/servers, vendor/spec, clients/sdk/node_modules) are removed in this commit.
