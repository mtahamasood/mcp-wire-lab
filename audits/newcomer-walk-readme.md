# Newcomer walk from the README

A fresh Sonnet agent with no knowledge of the project cloned the public repository and followed
the README only (no `specs/`, no `audits/`, no local checkout, no memory). It kept its own log
(kept on the machine that ran it, not committed: run output is not committed). This file is
its report, condensed by the controller. Run on `main` at `63eb9f9`, 2026-10-21.

## Path followed

1. Clone with submodules; README in full.
2. `scripts/bootstrap.sh` (10 s).
3. README *Record and read a trace*: `record.sh` on `handshake-2025.ndjson`, `tap.show` (plain
   and `--mermaid`), `tap.check`, `--help` on the three.
4. Lesson 01 with walkthrough 01: every run block, three experiments, one variant of its own.
5. Lesson 02 with walkthrough 02 and `client/wire.py`: tour, check, experiments 1 to 3.
6. Lesson 03 with walkthrough 03: server tour, `matrix`, experiments 1 to 3.
7. Lesson 04 with walkthrough 04: `--drop`, `--delay`, `drive.py --timeout`.
8. `--help` on every remaining tool.

About 6 minutes of command time, 25 to 30 minutes in all.

## Verdicts

| Part | Verdict |
| --- | --- |
| Setup | satisfactory |
| Reading a trace (README) | satisfactory |
| Lessons 01, 02, 04 | satisfactory (every `expect` block matched) |
| Lesson 03 | partly: experiment 3's hint is wrong |
| Help texts | partly: 6 of 8 tools fine; `bootstrap.sh` and `gate.sh` ignore `--help` and run |

Overall: a newcomer can complete the lessons unaided. The agent's own summary of MCP afterwards
(JSON-RPC lines over a child's stdio, id matching by shape, the `initialize` handshake and
capabilities deciding what the server may use, server-initiated requests, lenient servers and
the need for timeouts) was correct.

## Findings, with proposed dispositions (not yet approved)

| # | Finding | Severity | Proposed disposition |
| --- | --- | --- | --- |
| N1 | README says every command takes `--help`; `scripts/bootstrap.sh --help` re-ran the whole bootstrap and `scripts/gate.sh --help` started the 2-minute gate | wrong | Add `-h`/`--help` to both scripts (extend D1 and C19). Harmless today, but it is a README claim that is false |
| N2 | Lesson 03 experiment 3 says the server's last log line changes; it carries only a count, so it does not. A random `elicitationId` UUID also differs per run, against "same on every run" | wrong | Correct the hint (only the client's `roots/list` answer changes) and name the UUID as the one varying value |
| N3 | Answers sit under `<details>` in the same file; in a terminal they show before the learner predicts | unclear | One sentence in the README *Start here*: in a terminal the answers are visible, so cover them |
| N4 | Lesson 04's "which part of a delayed run is the tap and which the server?" has no answer in the answer block | unclear | Add the answer (the gaps and fault rows are the tap; reply latencies are the server) |
| N5 | Lesson 01 experiment 2 never says what work the `oninitialized` hook does | unclear | One sentence |
| N6 | Lessons 02 and 03 experiment 3: no recipe for comparing two traces | unclear | One-line recipe (`tap.show --full` of both, then `diff`) |
| N7 | README `<the path it printed>` is explained after the code block | nit | Reorder |
| N8 | Lesson 03 `matrix` expect block shows one row, not the table | nit | Accepted: the gate matches a line, and the text now says to compare rows |
| N9 | Lesson 04: walkthrough batch section repeats about 45 "(continues the note on stderr.1)" lines; `tap fault` rows hide `frame_seq`/`forwarded` unless you grep the JSONL | nit | Accepted limit: range anchors keep the explain check exact; `tap.show --full` shows the fields |
| N10 | `env -i` in the spawn line and ids starting at 0 not explained at first sight | nit | Accepted limit |
