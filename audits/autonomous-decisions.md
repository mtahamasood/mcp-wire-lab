# Autonomous decisions (owner review at the end)

On 2026-10-21 the owner delegated every remaining Phase 1 decision to the agent ("no input from me"), asking
only to review at the end which decisions to overrule. This file is that list. Each row: what was decided,
why, confidence, what breaks if wrong, and how to overrule. Spec-level decisions also get a register row in
`specs/mission.md`.

| Id | Decision | Reason | Confidence | If wrong | Overrule |
|---|---|---|---|---|---|
| A1 | The remaining work runs locally with subagents, not in a Claude web session. | The owner dropped the web requirement mid-session. | high | none | n/a |
| A2 | R18 licence: MIT (pending, see below). | Common default for a public learning lab; replaceable. | medium | wrong licence published | Replace `LICENSE`, amend the register row. |
| A3 | R17: J2 sign-off is kept as the owner's earlier pass; learner-walk items 3 and 7 stay accepted; recorded as "agent-proposed, owner to confirm". | These were already the agent's recommendation. | medium | a sign-off the owner did not give | Re-sign or reject in `validation.md` and `audits/learner-walk-lesson-01.md`. |
| A4 | Slice 2 of step (b), R1: the installer always writes the repo's own hooks directory, found through `git rev-parse --git-common-dir` (shared by linked worktrees; equal to `--git-path hooks` when `core.hooksPath` is unset), and warns when `core.hooksPath` resolves elsewhere. It never writes into the configured directory. | A shared or global hooks directory must not receive a repo-specific hook; the owner's `_dispatch` chains to `.git/hooks/pre-push`. `--git-path hooks` alone would resolve to the configured path. | high | an installer that writes elsewhere than a reader expects | Change `scripts/install-pre-push.sh` and its `InstallerTest` cases. |
| A5 | R3: a text file is trace-shaped when any JSON line carries `seq`, `dir` and `t_ns`, or when the name ends in `.jsonl` (any case) and a line carries `seq` and `dir`. R10: the KEY=VALUE env form counts toward the same 3-of-5 window as the JSON form, and `export ` prefixes are accepted. R11: gate mode checks the index blob and, when different, the working-tree file. R2: merge commits are scanned against each parent and deduped by path and blob. | Smallest reading of the approved dispositions. | medium | a missed leak form, or a false positive on a fixture | Edit `tools/check_no_run_output.py` and the matching tests. |
