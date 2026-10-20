# Phase 1 — Wire tap (stdio) and learning scaffold: plan

Dependency-ordered task groups. Each ends where the repository is coherent and the work
could stop. Steps marked **[human]** only the owner can perform.

## 0. Prerequisites [human]

- [x] **[human]** Install Node 24.22.0 with `nvm` in a separate terminal; confirm `node --version`
  prints `v24.22.0` in a new shell.
- [x] **[human]** Answer Q1 (ratify or overrule P1–P9, strike any of L1–L16); the agent
  records the answer as register rows.
- [x] **[human]** Approve this spec. The agent then commits the constitution and phase spec
  to `main`, before any phase code.

## 1. Repository, pinned server and spec (D6, D10)

- [x] `git init` (branch `main`), `.gitignore` (`node_modules/`, `__pycache__/`, `runs/`).
- [x] Commit the constitution and this phase's spec on `main`; create branch `phase-01-wire-tap`.
- [x] `git submodule add https://github.com/modelcontextprotocol/servers vendor/servers`,
  check out `51b6382…`; `git submodule add https://github.com/modelcontextprotocol/modelcontextprotocol vendor/spec`,
  check out `1155ca4…`.
- [x] Measure the narrowest install that builds the everything server (M5), then write
  `scripts/bootstrap.sh` around it.
- [x] Bootstrap verifies both submodules are at their pins and fails otherwise.
- [x] Run bootstrap; record M5 (commands, wall time, `node_modules` size) and M6 (Node
  version) in the validation Result.

*Stop point: the server builds and runs by hand.*

## 2. Gate skeleton, provenance, citation and lesson gates (D7, D13)

- [x] `pyproject.toml` with ruff and mypy configuration only (no dependencies).
- [x] `tools/check_provenance.py` with its own tests in `tests/test_provenance.py`
  (good spec passes; missing Source, undated Source, unknown ask, unknown register date,
  and missing `specs/` all fail).
- [x] `tools/check_citations.py` (G8) and `tools/check_lessons.py` (G9), each with tests
  over small fixture docs and fixture submodule trees.
- [x] `tools/check_no_run_output.py` (G11, D15) with tests; `scripts/bootstrap.sh` installs
  it as `.git/hooks/pre-push`.
- [x] `scripts/gate.sh` running G1–G4, G8, G9, G11 (G5 is a no-op until group 4).
- [x] Stage the C8, C11, C12, C15 mutations; record them.

Note: the lesson gate runs with `--min-lessons 0` in `scripts/gate.sh` until lesson 01 exists; C11 and C12
mutations are provisional until re-run on the real walkthrough and lesson (groups 5-6).

*Stop point: `scripts/gate.sh` is green and its gates have been seen red.*

## 3. Tap core (D1–D4)

- [x] `tap/__main__.py`: spawn, three relay threads (stdin→child, child stdout→stdout,
  child stderr→stderr), a single trace writer that orders records under a lock, and
  signal and exit-code handling.
- [x] `tests/fake_children/`: small Python children (transforming echo, exit-with-code,
  stderr writer, partial-final-line writer, non-UTF-8 writer).
- [x] `tests/test_tap.py`: C1–C6.
- [x] Stage the C1–C6 mutations; record them.

Note: the fake children include a `signal_waiter.py` beyond the five listed, to prove SIGINT and SIGTERM
forwarding (D4). The child runs in its own process group, so a terminal's Ctrl-C reaches it once, through
the tap, rather than twice.

*Stop point: the tap is proven against fake children.*

## 4. End to end against the real server (D8, D9)

- [x] `tests/fixtures/handshake-2025.ndjson` and `tests/drive.py`.
- [x] `scripts/record.sh` (D14) with the minimal environment; C16 and its mutation.
- [x] `tests/test_e2e.py`: C7; wire it into G5.
- [x] Take measurements M1–M4 with `scripts/record.sh`; record the values (not the traces)
  in the Result.

Note: C7 runs the driver and tap directly rather than through `record.sh`, which discards what reaches the
driver. `record.sh` links node into the run folder as `PATH` so the caller's home directory stays out of the
trace (C16). `tests.test_e2e` runs in G4's discovery as well as in G5.

*Stop point: one command records a real handshake trace into `runs/`.*

## 5. Viewer (D5, D11)

- [x] `tap/show.py`, plus `tests/fixtures/out-of-order.jsonl` (two requests in flight with
  responses reversed, plus one notification and one error response).
- [x] `--mermaid` and `--explain` (D11), with a fixture walkthrough that is missing one note.
- [x] `tests/test_show.py`: C9, C13, C14; stage their mutations.
- [ ] Paste one `--mermaid` output into a scratch GitHub issue preview or the README and
  confirm GitHub renders it (measurement M7, after group 7).

Note: a `--explain` walkthrough note is a heading ``#### `<anchor>` `` plus its text. `out-of-order.jsonl`
carries a c2s `notifications/cancelled` between server records, so C13's ordering mutant is caught. The
Mermaid paste check (M7) is still open.

## 6. Walkthrough, lesson 01, README (D8, D12)

- [ ] `docs/walkthrough/01-handshake-2025.md`: every frame of a fresh handshake run → spec
  section (2025-11-25) and source location (pinned commit, file:line), verified by opening
  each cited location; identity anchors (D11) so `tap.show --explain` exits 0 on a fresh run;
  wire that into G5.
- [ ] Lesson 01's experiments as fixtures under `tests/fixtures/`; record each with
  `scripts/record.sh`; state the outcomes as M8 values in the Result and in the lesson.
- [ ] `docs/lessons/01-the-wire-and-the-handshake.md` and `README.md` (D12); G8 and G9 green on them;
  drop `--min-lessons 0` from `scripts/gate.sh`; re-run the C11 and C12 mutations on the real artifacts.

## 7. CI and GitHub [human gate before push]

- [ ] `.github/workflows/ci.yml` (D7).
- [ ] **[human]** Confirm creating the public repo `mtahamasood/mcp-wire-lab`; the agent then
  runs `gh repo create` and pushes `main` and the phase branch.
- [ ] Watch CI go green on the branch; stage C10 (a deliberately failing push on a
  throwaway branch, seen red, branch deleted).

## 8. Close the phase

- [ ] G6 clean-clone walk in a new directory; fill the Result with measurements.
- [ ] Confirm every C row has a recorded mutation or a signed stand-in.
- [ ] Boundary checks (section D of validation).
- [ ] Closing review: one adversarial pass plus a falsifiability audit, by a fresh reviewer
  (a different model from the builder); corpus deposited in `audits/`; every finding
  dispositioned.
- [ ] Learner walk (J2): a fresh agent, given only the clone URL and "follow the README
  to the end of lesson 01", run in a new directory outside the repo; its log stays there
  for the owner to read; the agent's written findings list goes into `audits/`.
- [ ] **[human]** Owner verdicts on J1 and J2.
- [ ] `CHANGELOG.md` entry; merge the phase branch to `main` with CI green; tag `lesson-01`
  on the merge commit and push the tag.
