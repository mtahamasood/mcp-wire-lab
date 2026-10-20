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
| J1 | Does the walkthrough make the 2025-era handshake understandable from first principles? | `docs/walkthrough/01-handshake-2025.md`, and `tap.show --explain` over a run the owner records with `scripts/record.sh` | Read every frame with its note; open at least two cited source locations and one cited spec section | The cited spec sections and source lines say what the walkthrough claims; the owner can say, for each frame, why it is sent and what would break without it (frame coverage itself is C14) | *owner, date* |
| J2 | Can a newcomer get through lesson 01 from the README alone? | The learner-walk log in its run directory on the owner's machine (never committed), the agent's findings list in `audits/`, and lesson 01 | Read the log; note every place the learner stalled, guessed, or answered a *Check yourself* question wrongly | The learner reached the end of lesson 01 without help from outside the repo, and every stall in the log has been fixed in the lesson or is signed as accepted | *owner, date* |

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
  - M6 (partial, this machine): node v24.22.0, Python 3.12.3, uv 0.12.5. CI values still to take.
- Checks seen to fail:
- Judgement verdicts:
- Findings beyond the rows:
- Where it stands:
