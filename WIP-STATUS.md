# WIP status: phase-08-mutants-07 (D9 mutation, stopped on STOP-USAGE 2026-11-16)

The agent was stopped mid-run by the orchestrator at 5h usage 100%. Partial outputs are committed as they were (mutants json, any tests/C rows written so far); no verdicts are final.

Resume: re-read the D9 brief in project memory, check `audits/mutants/phase-*.json` for mutants already decided, verify each new test is red on its mutant and green on the code, finish the rest, record in audits/mutation-final-pass.md, then ruff/mypy/gate. Delete this file in the first real commit.
