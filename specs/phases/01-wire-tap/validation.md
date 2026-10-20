# Phase 1 — Wire tap (stdio) and learning scaffold: validation

The phase's pass/fail bar, written before any code. Row types: **check** (automated,
re-runnable, gates the future), **measurement** (true at the time of the walk, never
re-run, no pass condition set in advance), **judgement** (the owner's verdict on named
evidence).

## A. Clean-environment walk (G6)

In a new, empty directory:

1. `git clone --recurse-submodules https://github.com/mtahamasood/mcp-wire-lab`
2. `cd mcp-wire-lab && scripts/bootstrap.sh`
3. `scripts/gate.sh`
4. `scripts/record.sh tests/fixtures/handshake-2025.ndjson walk`, then the `tap.show` command it prints
5. `git status --porcelain` — must be empty (the walk left nothing for git)

Record each step's exit code and wall time. Every step must exit 0.

## B. Inherited quality gates

G1, G2, G3, G4, G5, G8, G9, G11 green via `scripts/gate.sh`, locally and in CI. G6 is section A. G7 is
checked at close.

## C. Phase-specific correctness

| Row | Type | Check | Passes when | Mutation |
| --- | --- | --- | --- | --- |
| C1 | check | Byte-exact forwarding both ways | sha256 of bytes out equals sha256 of bytes in, in each direction, for a fixture containing non-canonical JSON (extra spaces, unsorted keys, `é` escapes, an embedded `\r`); concatenating the `raw` fields per direction equals the stream | *to record:* forward `json.dumps(json.loads(line))` instead of the bytes |
| C2 | check | Direction and order are recorded truly | `seq` is strictly increasing; each frame's `dir` matches its true direction; the child is a *transforming* echo (prefixes its output), so c2s and s2c frames differ | *to record:* swap the `dir` labels |
| C3 | check | A final partial line is forwarded and recorded | the output ends with the exact unterminated bytes; the last record has `partial: true` | *to record:* drop the buffer remainder at EOF |
| C4 | check | Non-UTF-8 and non-JSON frames | forwarded unchanged; recorded with `raw_b64` (non-UTF-8) or `json: null` and `parse_error` (non-JSON) | *to record:* decode with `errors="replace"` before forwarding |
| C5 | check | Exit code propagation | a child exiting 3 makes the tap exit 3; a child killed by SIGTERM makes the tap exit 143 | *to record:* always exit 0 |
| C6 | check | Server stderr is relayed and recorded | stderr bytes appear on the tap's stderr and as `stderr` records, and never on stdout | *to record:* send child stderr to the tap's stdout |
| C7 | check | E2E against the real server (G5) | driving the handshake fixture through the tap to the pinned built server yields: a response whose `id` matches `initialize` and whose `result` has `protocolVersion`, `capabilities`, and `serverInfo.name`; a `tools/list` response whose `result.tools` is non-empty; a `ping` response with `result` `{}`; every c2s request has exactly one s2c response with its `id` | *to record:* break stdout relay so nothing reaches the driver — C7 must fail on the missing `initialize` response, not on a crash in the test harness |
| C8 | check | Provenance linter (G1) | passes on the real specs; fails, naming the record, on each of: a D-record without `*Source:*`, an undated Source, an unknown `A<n>`, a register date not in `mission.md`; fails loudly when `specs/` is missing | *to record:* delete a Source line in a temp copy of a real requirements file → G1 red |
| C9 | check | Viewer correlates by `id` | on `out-of-order.jsonl` (requests 1 and 2 in flight, response 2 arrives first), each response shows its own request's `seq` and latency; the error response is labeled as an error; the notification shows no pairing | *to record:* pair each response with the immediately preceding request |
| C10 | check | CI runs the gate and can go red | a push on `main`/the phase branch shows a green run; a throwaway branch with a failing unit test shows a red run | *to record:* the throwaway failing branch itself |
| C11 | check | Citation gate (G8) | passes on the committed docs; fails, naming the citation, on each of: a missing file, a line past EOF, a fragment not on the cited line (but present one line away — so an off-by-one is caught), an unknown submodule name; fails loudly when a submodule is not checked out | *to record:* shift a real citation in the walkthrough by one line → G8 red |
| C12 | check | Lesson gate (G9) | passes on lesson 01; fails on a lesson missing *Predict*, on a runnable block that exits 1, on an expected block absent from the output; the fixture lesson contains a runnable block that *succeeds* but prints the wrong text, so exit-code-only checking would pass it | *to record:* change an expected block in lesson 01 to text the command does not print → G9 red |
| C13 | check | Mermaid output | on `out-of-order.jsonl`, the output starts with `sequenceDiagram`, declares `Client` and `Server`, has exactly one arrow per JSON-RPC record in `seq` order, uses `->>` for requests and notifications and `-->>` for responses, and renders stderr records as notes | *to record:* emit arrows in arrival order per direction instead of `seq` order (the fixture interleaves directions so this differs) |
| C14 | check | `--explain` coverage | on a fresh handshake run (G5) with the real walkthrough, exits 0 and prints a note after every frame; on a synthetic trace with a fixture walkthrough missing one note, prints `(no note)` and exits non-zero; with a fixture walkthrough holding an extra note for a frame that never occurs, prints `(no frame)` and exits non-zero | *to record:* make `--explain` exit 0 regardless |
| C15 | check | No run output reaches git (G11, D15) | passes on the clean repo; in a temp clone, fails, naming the file, on each of: a `git add -f`'d file under `runs/`, a trace-shaped `.jsonl` without the synthetic marker, a doc containing an environment dump, a home-directory path, and each secret regex's planted sample; the installed pre-push hook blocks a push of such a commit to a local bare remote | *to record:* `git add -f` a real `runs/` trace in the temp clone and push to the bare remote — hook red, push refused |
| C16 | check | Minimal environment (D14) | with `FAKE_SECRET_FOR_C16=leak` exported in the parent shell, a `record.sh` run of a fixture that calls `get-env` yields a trace in which `FAKE_SECRET_FOR_C16` and the parent's `HOME` appear nowhere, and `MCP_WIRE_LAB` appears in the `get-env` result (presence first, so an empty or failed result cannot pass) | *to record:* drop `env -i` from `record.sh` — the planted variable appears, C16 red |

### Measurements (no pass condition; the numbers are the result)

| Row | Measurement |
| --- | --- |
| M1 | Framing the server uses on stdout: line terminator bytes (`\n` vs `\r\n`), whether any frame contains a raw newline, byte size of the largest frame in the handshake |
| M2 | Server behavior when its stdin reaches EOF with no traffic and after the handshake: exit code and time to exit |
| M3 | Everything the server writes to stderr during the handshake |
| M4 | `initialize` negotiation: the `protocolVersion` the server answers when the client offers `2025-11-25`, `2024-11-05`, and `1999-01-01` |
| M5 | Bootstrap: the exact install and build commands that worked, wall time, `node_modules` size |
| M6 | `node --version`, `python3 --version`, and `uv --version` on the walk machine and in CI |
| M7 | Whether GitHub renders the `--mermaid` output of the committed handshake trace (a screenshot path or the rendered page URL) |
| M8 | Lesson 01's experiments at the pins, stated as values: the server's reply (or silence) when the client offers another `protocolVersion`, omits `notifications/initialized`, or sends `tools/list` before `initialize` |

### Judgement check

| Row | Question | Evidence | Procedure | Pass | Verdict |
| --- | --- | --- | --- | --- | --- |
| J1 | Does the walkthrough make the 2025-era handshake understandable from first principles? | `docs/walkthrough/01-handshake-2025.md`, and `tap.show --explain` over a run the owner records with `scripts/record.sh` | Read every frame with its note; open at least two cited source locations and one cited spec section | The cited spec sections and source lines say what the walkthrough claims; the owner can say, for each frame, why it is sent and what would break without it (frame coverage itself is C14) | **pass**, owner, 2026-10-21 (read every frame with its note via `--explain` on a fresh recording; checked cited source and spec locations) |
| J2 | Can a newcomer get through lesson 01 from the README alone? | The learner-walk log in its run directory on the owner's machine (never committed), the agent's findings list in `audits/`, and lesson 01 | Read the log; note every place the learner stalled, guessed, or answered a *Check yourself* question wrongly | The learner reached the end of lesson 01 without help from outside the repo, and every stall in the log has been fixed in the lesson or is signed as accepted | **pass**, owner, 2026-10-21. Signed by the owner's instruction ("consider j2 passed"); no learner-walk log or audit findings list existed when it was signed, so the evidence column was not exercised |

## D. Boundary checks

| Row | Check | Passes when |
| --- | --- | --- |
| B1 | Submodules untouched | `git -C vendor/servers status --porcelain` and `git -C vendor/spec status --porcelain` are empty, and `git submodule status` shows `51b6382a3e827aceb6bce430b1208d69b93d95ea` and `1155ca460e5097019f32769b38dcba194432e2fb` |
| B2 | No third-party runtime dependencies in Python | No `dependencies` in `pyproject.toml`, no `requirements*.txt`; `tap/`, `tools/` and `tests/` import only the standard library and each other (checked by a grep that has been seen to match a planted `import requests`) |
| B3 | No MCP SDK in tap or gates | No `modelcontextprotocol` import in `tap/` or `tools/` |
| B4 | No run output or secrets anywhere in the branch's history | G11's patterns, run over `git log -p main..phase-01-wire-tap` (every commit, not only the tip), match nothing; the same command seen to match in C15's temp clone |
| B5 | Constitution unchanged except by register rows and ratifications | `git diff main -- specs/mission.md specs/roadmap.md specs/tech-stack.md` shows only appended register rows and proposal status changes |

## E. Not-done conditions

Any of these standing means the phase is NOT done, whatever else passes:

- A C row without a recorded mutation or a signed stand-in.
- A measurement copied from recon or from documentation instead of taken on this phase's
  walk.
- The closing review run without its corpus deposited in `audits/`.
- J1 or J2 with no owner verdict, or with an agent's provisional verdict.
- The learner walk run without its findings list deposited in `audits/`, or with its log
  (or any other run output) committed.
- A lesson command or citation that the gates do not cover (outside the runnable/citation
  forms), unless it is listed in the Result as unchecked.
- Any change inside `vendor/servers` or `vendor/spec`, any secret, any unattributed
  requirement, or any scope beyond D14.
- D8 shipped without P3 ratified, or D10 without P7 ratified.

## Result

*Filled during the walk. Empty until then.*

- Measurements:
  - M5 (taken 2026-10-20, WSL2): the narrowest install that builds the everything server is
    `cd vendor/servers && npm ci --workspace=@modelcontextprotocol/server-everything --ignore-scripts`
    then `cd src/everything && npm run build`. Install 6.4 s and build 4.8 s by hand; clean
    `scripts/bootstrap.sh` run 9.5 s wall; `vendor/servers/node_modules` 141M. The whole-workspace
    install was not needed (D6's cost is avoided). Submodule worktrees: servers 4.7M, spec 59M;
    `.git/modules` 93M. The built server answers `initialize` over stdio with protocolVersion 2025-11-25.
  - M1-M4 (taken 2026-10-20, WSL2, pinned server `51b6382`, `scripts/record.sh` on the handshake fixture):
    M1: every stdout frame ends in a bare `\n` (no `\r\n`), no frame contains a raw newline or `\r`
    inside it, and the largest frame is 10184 bytes (the `tools/list` response).
    M2: stdin at EOF with no traffic: exit 0 in 0.31 s, nothing on stdout; after the handshake (fixture
    sent at once, then EOF): exit 0 in 0.37 s, all three responses present.
    M3: the whole handshake writes one stderr line, `Starting default (STDIO) server...`.
    M4: offering `2025-11-25` is answered `2025-11-25`; offering `2024-11-05` is answered `2024-11-05`;
    offering `1999-01-01` is answered `2025-11-25`.
  - M8 (taken 2026-10-20, pinned server `51b6382`, `scripts/record.sh` on the `exp-*` fixtures, WSL2):
    offering `2024-11-05` is answered `2024-11-05`; offering `1999-01-01` is answered `2025-11-25`, and the
    session carries on (tools/list returns 16 tools, ping returns `{}`). Omitting
    `notifications/initialized`: `tools/list` (16 tools) and `ping` are both answered, no error.
    Sending `tools/list` before `initialize`: answered first with 16 tools and no error, then `initialize`
    is answered normally. The server enforces none of the three spec rules; the lesson says so and its
    runnable blocks (G9) fail if a future pin changes it.
  - M7 (taken 2026-10-20 by the owner): `tap.show --mermaid` output of a fresh `handshake-2025` recording
    (2 participants, 11 lines of messages and notes), pasted in a fenced `mermaid` block into the Preview tab
    of a new GitHub issue on `mtahamasood/mcp-wire-lab` (not submitted). It rendered as a sequence diagram.
    No screenshot kept; nothing from the run was committed.
  - M6 (partial, this machine): node v24.22.0, Python 3.12.3, uv 0.12.5. CI (2026-10-20, ubuntu-latest): node v24.22.0, Python 3.12.15, uv 0.13.4.
- Checks seen to fail:
  - C10 (2026-10-20): `ci.yml` on `phase-01-wire-tap` finished green (bootstrap and gate, 34s). A throwaway
    branch adding one always-failing unit test finished red at the gate step; branch deleted locally and on origin.
  - C8 (2026-10-20): deleted D2's Source line in a temp copy of the real requirements.md; G1 exit 1,
    "D2: no *Source:* line". Baseline copy exit 0.
  - C11 (2026-10-20): the real citation `servers:src/everything/transports/stdio.ts:49` "serveStdio(" in
    `docs/walkthrough/01-handshake-2025.md` was shifted to line 50; G8 exit 1, "fragment is not on line 50".
    Baseline exit 0 (30 citations). Re-run on the real artifact in group 6; supersedes the provisional run.
  - C12 (2026-10-20): in `docs/lessons/01-the-wire-and-the-handshake.md` the expected `2024-11-05` line of
    experiment 1 was changed to `2024-11-06`; G9 exit 1, "expected output not found". Baseline exit 0.
    Supersedes the provisional run.
  - C15 (2026-10-20): in a temp clone with the installed pre-push hook, a clean push succeeded; after
    `git add -f runs/trace.jsonl` and a commit, the push was refused (exit 1) and the bare remote kept one
    commit. Real-trace variant (2026-10-20,
    group 4): a trace recorded by `scripts/record.sh` was `git add -f`'d in a temp clone; the push was refused
    (exit 1; G11 named the file for all three rules) and the bare remote kept only the earlier clean commit.
  - C1-C6 (2026-10-20): each mutation applied to `tap/__main__.py` in a temp copy of `tap/` and `tests/`, and
    that row's test class run; every baseline exit 0, every mutant exit 1.
    C1, forwarding `json.dumps(json.loads(frame))`: `test_both_directions_are_byte_exact` fails on the c2s sha256.
    C2, `dir` labels swapped: `test_direction_and_order` fails (c2s frames carry the `echo:` prefix).
    C3, remainder dropped at EOF: both partial-line tests fail (last record has no `partial`).
    C4, `decode(errors="replace")` before forwarding: both non-UTF-8 tests fail (U+FFFD bytes on the wire).
    C5, always exit 0: exit-code, SIGTERM-143 and both signal-forwarding subtests fail (`0 != 143`).
    C6, child stderr sent to the tap's stdout: `test_stderr_is_relayed_and_recorded_not_mixed` fails
    (tap stderr empty).
  - C7 (2026-10-20): baseline `tests.test_e2e` exit 0. Mutant: relay forwards nothing from the child's
    stdout to the tap's stdout (the trace still records it); C7 fails on `0 != 1 : responses with id 0
    reaching the driver`, an assertion on the missing `initialize` response, not a harness crash. C7 runs
    the driver and tap directly, because `record.sh` discards what reaches the driver and the trace alone
    would not show the break.
  - C16 (2026-10-20): baseline exit 0 with `FAKE_SECRET_FOR_C16=leak` exported. Mutant: `env -i` replaced by
    `env` in `record.sh`; C16 fails on `'FAKE_SECRET_FOR_C16' unexpectedly found` in the trace. First run of
    the real test also failed on the parent's `HOME`: nvm puts node under it and the spec put node's
    directory in `PATH`. Fixed in `record.sh` by linking node into the run folder and using that as `PATH`.
  - C9, C13, C14 (2026-10-20): baseline `tests.test_show` exit 0 (7 tests); every mutant exit 1.
    C9, pairing each response with the most recent request: `test_c9_responses_pair_by_id_not_adjacency`
    fails (`answers seq 2, 7.0 ms` where seq 1 and 8.0 ms were expected).
    C13, emitting c2s arrows before s2c arrows: `test_c13_diagram_shape_and_seq_order` fails on the arrow
    order. The first fixture did not catch this (no client message after a server message); the fixture
    gained a c2s `notifications/cancelled` between server records and the mutant then failed.
    C14, `--explain` always exits 0: both the missing-note and extra-note tests fail.
    C14's real-walkthrough half (2026-10-20, group 6): `tests.test_e2e.test_c14_explain_covers_a_fresh_run`
    records a fresh run and requires `--explain` over the real walkthrough to exit 0 with no `(no note)` or
    `(no frame)`. Mutant: the heading `c2s.ping.2` renamed to `c2s.ping.9` in the walkthrough; the test fails.
    Baseline passes.
- Judgement verdicts:
- Findings beyond the rows:
- Where it stands:
