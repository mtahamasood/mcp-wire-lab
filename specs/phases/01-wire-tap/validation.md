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
| C1 | check | Byte-exact forwarding both ways | sha256 of bytes out equals sha256 of bytes in, in each direction, for a fixture containing non-canonical JSON (extra spaces, unsorted keys, `é` escapes, an embedded `\r`); concatenating the `raw` fields per direction equals the stream; in each direction, a frame split across two writes with a pause between them and a frame over 128 KiB are forwarded unchanged and each recorded as exactly one record holding the whole frame | *to record:* forward `json.dumps(json.loads(line))` instead of the bytes |
| C2 | check | Direction and order are recorded truly | `seq` is strictly increasing; each frame's `dir` matches its true direction; the child is a *transforming* echo (prefixes its output), so c2s and s2c frames differ; in an in-process run of the relay, every frame is recorded before the chunk that completes it is forwarded; on a child that writes 20000 stdout lines and 2000 stderr lines and exits at once, all of them are recorded, `seq` is contiguous, and `exit` is the last record; every record's `t_ns` is above 0 and below the run's wall time, two frames the child writes 0.5 s apart are recorded at least 0.25 s apart, and every frame record's `bytes` equals the length of its raw bytes | *to record:* swap the `dir` labels |
| C3 | check | A final partial line is forwarded and recorded | the output ends with the exact unterminated bytes; the last record has `partial: true` | *to record:* drop the buffer remainder at EOF |
| C4 | check | Non-UTF-8 and non-JSON frames | forwarded unchanged; recorded with `raw_b64` (non-UTF-8, including CESU-8 surrogate bytes) or `json: null` and `parse_error` (non-JSON, `1e999`, and a frame nested 20000 deep, in each direction, which keeps its `raw` text, with the frames after it still forwarded and recorded); every trace line parses as strict JSON (no `NaN` or `Infinity`), and a frame holding U+0085, U+2028 and U+2029 gives trace lines that contain none of them raw | *to record:* decode with `errors="replace"` before forwarding |
| C5 | check | Exit code and lifecycle (D4) | a child exiting 3 makes the tap exit 3; a child killed by SIGTERM makes the tap exit 143; SIGINT, SIGTERM, SIGHUP and SIGQUIT sent to the tap each reach the child once, and a SIGTERM sent to the tap's process group reaches it once; a signal that arrives before the child starts reaches it; a child that closes stdout and lives on gives the client EOF before the child exits; usage errors and an unopenable trace path exit 2 with no traceback; a failing signal test fails within seconds and leaves no process behind | *to record:* always exit 0 |
| C6 | check | Server stderr is relayed and recorded | stderr bytes appear on the tap's stderr and as `stderr` records, and never on stdout; on the flood child of C2, and on a child that closes stdout and then writes 20000 stderr lines, every stderr line is recorded before `exit` | *to record:* send child stderr to the tap's stdout |
| C7 | check | E2E against the real server (G5) | driving the handshake fixture through the tap to the pinned built server yields: a response whose `id` matches `initialize` and whose `result` has `protocolVersion`, `capabilities`, and `serverInfo.name`; a `tools/list` response whose `result.tools` is non-empty; a `ping` response with `result` `{}`; every c2s request has exactly one s2c response with its `id` | *to record:* break stdout relay so nothing reaches the driver — C7 must fail on the missing `initialize` response, not on a crash in the test harness |
| C8 | check | Provenance linter (G1) | passes on the real specs; fails, naming the record, on each of: a D-record without `*Source:*`, an undated Source, an unknown `A<n>`, a register date not in `mission.md`; fails loudly when `specs/` is missing | *to record:* delete a Source line in a temp copy of a real requirements file → G1 red |
| C9 | check | Viewer correlates by `id` | on `out-of-order.jsonl` (requests 1 and 2 in flight, response 2 arrives first), each response shows its own request's `seq` and latency; the error response is labeled as an error; the notification shows no pairing; ids keep their JSON type (`1`, `"1"`, `true` do not pair); a fixture where a stack pairing and id pairing differ in both directions; a U+2028 inside a frame leaves the view intact; a malformed JSON-RPC frame is shown raw; an in-flight id reuse is flagged; control characters are escaped; an unreadable file exits 2; a closed pipe ends quietly | *to record:* pair each response with the immediately preceding request |
| C10 | check | CI runs the gate and can go red | a push on `main`/the phase branch shows a green run; a throwaway branch with a failing unit test shows a red run | *to record:* the throwaway failing branch itself |
| C11 | check | Citation gate (G8) | passes on the committed docs; fails, naming the citation, on each of: a missing file, a line past EOF, a fragment not on the cited line (but present one line away — so an off-by-one is caught), an unknown submodule name, a path that leaves the submodule, a fragment under 6 characters; fails loudly when a submodule is not checked out | *to record:* shift a real citation in the walkthrough by one line → G8 red |
| C12 | check | Lesson gate (G9) | passes on lesson 01; fails on a lesson missing *Predict*, on a runnable block that exits 1, on an expected block absent from the output, a block whose first command fails inside a pipe, headings out of order or only inside a fence (a three-backtick fence, a `~~~` fence, a four-backtick fence holding a three-backtick line, or an unclosed fence running to the end of the file), and an empty root or a sleeping block under a short timeout; the fixture lesson contains a runnable block that *succeeds* but prints the wrong text, so exit-code-only checking would pass it | *to record:* change an expected block in lesson 01 to text the command does not print → G9 red |
| C13 | check | Mermaid output | on `out-of-order.jsonl`, the output starts with `sequenceDiagram`, declares `Client` and `Server`, has exactly one arrow per JSON-RPC record in `seq` order, uses `->>` for requests and notifications and `-->>` for responses, and renders stderr records as notes | *to record:* emit arrows in arrival order per direction instead of `seq` order (the fixture interleaves directions so this differs) |
| C14 | check | `--explain` coverage | on a fresh handshake run (G5) with the real walkthrough, exits 0 and prints a note after every frame; on a synthetic trace with a fixture walkthrough missing one note, prints `(no note)` and exits non-zero; with a fixture walkthrough holding an extra note for a frame that never occurs, prints `(no frame)` and exits non-zero | *to record:* make `--explain` exit 0 regardless |
| C15 | check | No run output reaches git (G11, D15) | passes on the clean repo; in a temp clone, fails, naming the file, on each of: a `git add -f`'d file under `runs/`; a trace-shaped `.jsonl` without the synthetic marker, and a trace-shaped `.ndjson` and `.JSONL`; a doc containing a JSON environment dump, a three-key JSON dump that includes `PWD`, or three KEY=VALUE lines (plain, with `export`, indented, or as `declare -x` lines); a home-directory path, with more path after it or bare (followed by whitespace, a quote, a backtick, `:`, `,`, `)` or the end of the text), the root home included; a planted sample of each secret regex, `github_pat_` included; a symlink whose target is such a path. In gate mode also: a staged change that the working tree hides, and a working-tree entry that replaced a tracked symlink or retargets one. As the pre-push hook also: a leak added by modifying a tracked file, a file turned into a symlink to a home path (and a symlink turned into a file holding a token), a leak in a root commit pushed on a new branch, and a file added only by a merge commit. The lookalikes of `test_home_lookalikes_pass` pass. The installer writes the repo's own hooks directory, also from a linked worktree; with `core.hooksPath` set to another directory it leaves that directory unchanged and warns; on a directory that is not a repo it fails and creates nothing; the hook tests run it with isolated git configuration and it prints nothing on stderr; the installed pre-push hook blocks a push of such a commit to a local bare remote. Accepted, not checked: JSON-escaped slashes and a Windows-style home path (G11 row) | *to record:* `git add -f` a real `runs/` trace in the temp clone and push to the bare remote — hook red, push refused |
| C16 | check | Minimal environment (D14) | with `FAKE_SECRET_FOR_C16=leak` exported in the parent shell, a `record.sh` run of a fixture that calls `get-env` yields a trace in which `FAKE_SECRET_FOR_C16` and the parent's `HOME` appear nowhere, and `MCP_WIRE_LAB` appears in the `get-env` reply frame, found by its request id, and the variable names equal the allowlist exactly, as node adds none (presence first, so an empty or failed result cannot pass) | *to record:* drop `env -i` from `record.sh` — the planted variable appears, C16 red |
| C17 | check | Trace file and trace failure (D2, D3) | a new trace has mode 0600 under umask 022, and an existing file at the path is replaced; with the tap's file size limit set below the trace's size, every byte is still forwarded, the tap exits with the child's code within the test's timeout, and its stderr holds one `tap:` line about the trace; with a non-blocking stdin that gets data late, the data is forwarded and recorded; started with its stdin, stdout or stderr closed, the tap exits 0, its trace parses as strict JSON from `spawn` to `exit`, and it writes nothing of its own on stderr | *to record:* let the trace write error propagate out of the relay — the run hangs or loses output, C17 red |
| C18 | check | Run folders (D12, D14) | `record.sh` run twice on one name under a pinned timestamp gives two folders, the second with the suffix `-2`; a name whose parent folder does not exist (`sub/name`) exits 1 within 10 s, its last stderr line starts `record: cannot create runs/`, and no folder is left; in lesson 01, no command picks a run folder by name order (`ls -d ... \| tail -1`), every `run=` line in a block that records reads that call's `recorded:` line, and every other `run=` line, over an older `runs/<ts>-<name>` and a newer `runs/<ts>-<name>-2`, selects the `-2` folder | *to record:* the `mkdir` loop without its existence test — the `sub/name` case times out, C18 red |

### Measurements (no pass condition; the numbers are the result)

| Row | Measurement |
| --- | --- |
| M1 | Framing the server uses on stdout: line terminator bytes (`\n` vs `\r\n`), whether any frame contains a raw newline, byte size of the largest frame in the handshake |
| M2 | Server behavior when its stdin reaches EOF with no traffic and after the handshake: exit code and time to exit |
| M3 | Everything the server writes to stderr during the handshake |
| M4 | `initialize` negotiation: the `protocolVersion` the server answers when the client offers `2025-11-25`, `2024-11-05`, and `1999-01-01` |
| M5 | Bootstrap: the exact install and build commands that worked, wall time, `node_modules` size |
| M6 | `node --version`, `python3 --version`, and `uv --version` on the walk machine and in CI |
| M7 | Whether GitHub renders the `--mermaid` output of a fresh handshake recording (a screenshot path or the rendered page URL) |
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
| B5 | Constitution unchanged except by register rows and ratifications | `git diff main -- specs/mission.md specs/roadmap.md specs/tech-stack.md` shows only appended register rows, proposal status changes, and edits each named by a register row |

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
  requirement, or any scope beyond D16.
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
    is answered normally. The server tolerates all three (the rules cited bind the client, and the spec gives the server no duty to refuse); the lesson says so and its
    runnable blocks (G9) fail if a future pin changes it.
  - M7 (taken 2026-10-20 by the owner): `tap.show --mermaid` output of a fresh `handshake-2025` recording
    (2 participants, 10 lines of messages and notes), pasted in a fenced `mermaid` block into the Preview tab
    of a new GitHub issue on `mtahamasood/mcp-wire-lab` (not submitted). It rendered as a sequence diagram.
    No screenshot kept; nothing from the run was committed.
  - M6 (partial, this machine): node v24.22.0, Python 3.12.3, uv 0.12.5. CI (2026-10-20, ubuntu-latest): node v24.22.0, Python 3.12.15, uv 0.13.4.
- Unchecked (no gate covers them; the rule in section E allows this only when listed here):
  - Lesson 01 commands outside the runnable form: the bootstrap command (line 11), "the same
    command without the redirect" and the `--full ... | less` command (lines 90-92).
  - The Mermaid claim in lesson 01 ("yours will match", lines 56-73): matched by hand against a fresh
    `--mermaid` output on 2026-10-21; no gate compares them.
  - The console blocks in the walkthrough (the record and `--explain` commands) and in the README (clone,
    bootstrap, record, read), and the walkthrough's hand-written JSON examples (D8).
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
    After the G11 fixes of step (b) (b8ca145; 2026-10-21): 43 mutants of the added behaviour, each applied
    in place to `tools/check_no_run_output.py` or `scripts/install-pre-push.sh` (restored and `git diff`
    clean after each), with `PYTHONDONTWRITEBYTECODE=1` and no `__pycache__`, then the whole of
    `tests.test_no_run_output` run; baseline exit 0 (30 tests). First run: 26 killed, 17 survived.
    Killed at once, with the tests that fail: R10 home path, the bare-name boundary dropped, or without
    whitespace, a quote or end of text: `test_bare_home_directory_forms`. R10 env, the KEY=VALUE form
    dropped, `export` dropped, `re.M` dropped, or only `group(1)` read: `test_key_value_env_dump`.
    R10 decode, the old skip on `UnicodeDecodeError`: `test_undecodable_byte_does_not_hide_a_secret`.
    R3, the content rule dropped or limited to `.jsonl`, or matched by exact key set: the name-and-case and
    fixtures-marker tests; `t_ns` not required: the `seq`-and-`dir` test; `.lower()` dropped: the same;
    `all` for `any` in the `.jsonl` rule: `test_each_leak_is_named_by_file`. R11, the index not read: the
    staged, deleted-from-disk and symlink tests; the working tree not read: the working-tree test; gitlinks
    not skipped: `test_real_repo_is_clean` (error). R2, no `-m`: both merge tests and the merge push test;
    no dedupe: the not-duplicated test; symlinks skipped again: the symlink test. R1, the old
    `--absolute-git-dir`: the linked-worktree test; writing into `--git-path hooks`: 7 installer and hook
    tests; no warning: the warns test; a warning whenever `core.hooksPath` is set: the own-directory test;
    `|| true` dropped from `config --get`: the unset and linked-worktree tests.
    The 17 survivors, and the test that now kills each (41 tests, baseline exit 0): an unanchored KEY=
    (MANPATH=, OLDPWD=, SUDO_USER= counted): `test_key_value_env_key_is_the_whole_name`; `export ` with one
    space only: `test_export_with_any_whitespace_is_an_env_dump`; `errors="ignore"`:
    `test_marker_line_with_an_undecodable_byte_is_not_the_marker`; strict decode of the `ls-files` and
    `diff-tree` output, and `git show commit:path` for the blob: `test_non_utf8_file_name_is_checked`
    (crash); `all` for `any` in the content rule: `test_one_trace_record_among_other_json_lines_is_trace_shaped`;
    the index-and-working-tree dedupe dropped: `test_leak_in_index_and_working_tree_is_named_once`;
    working-tree symlinks followed: `test_working_tree_symlink_content_is_not_read`; gitlinks not skipped in
    the hook: `test_commit_adding_a_submodule_gitlink_is_skipped` (crash); `pwd` for `pwd -P`:
    `test_no_warning_when_the_repo_is_reached_through_a_symlink`; no `mkdir -p` of the hooks directory:
    `test_missing_hooks_directory_is_created`; `|| true` dropped from the active-path lookup:
    `test_hooks_path_to_a_missing_directory_warns_and_installs`.
    Signed equivalent: comparing index and working tree unconditionally (the dedupe drops the identical
    problems); deduping merge entries by path alone (every per-parent entry of a path carries the merge
    commit's blob, seen in `diff-tree -m -z` output); `not parts` for `len(parts) < 4` (without `-M` or `-C`
    every record has five fields; the trailing empty field is unpaired and dropped by `zip`).
    Survived, open: dropping `mode != "120000"` in gate mode. Not equivalent: the mutant also reads a
    working-tree regular file that replaced a tracked symlink, which G11 ("as well as the working tree")
    asks for and the tool skips; a probe found a token there, and a tracked link retargeted at a home path
    but not staged, both missed (`[]`). Not killed, as a killing test would pin the gap; the push hook still
    reads the committed blob. Totals: 43 run, 39 killed, 3 signed equivalent, 1 open. The gap is
    finding B19 in `audits/step-b-review.md`, disposed there (fix; register row 2026-10-21, fifth).
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
    Extended after the review (T14, R15/T17; 2026-10-21): the test now finds the `get-env` reply frame by id,
    asserts `MCP_WIRE_LAB` in that frame, and compares the variable names with the allowlist (plus `PWD`,
    `SHLVL`, `_` if node adds them). A second test records the same name twice with a pinned timestamp
    and requires two run folders; it failed before the `record.sh` change (one `ln` error) and passes after.
    The mutants of review T14 (C16.5-C16.8) were not re-run.
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
  - C9, C13, C14 after step (b) (2026-10-21), the viewer fixes of `cecc630` (S1-S4, S6, S7, S10, S13, S15, T5):
    each mutant applied to `tap/show.py` in place with `PYTHONDONTWRITEBYTECODE=1` and no `__pycache__`, the
    whole of `tests.test_show` run, and the file restored after each (`git diff` empty); baseline exit 0 (18
    tests). 66 mutants (52 C9, 10 C13, 4 C14). Killed at first, with the tests that fail:
    C9, the row's mutation (each response paired with the most recent request): the pairing, id-type and stack
    tests; first-in-first-out: the same three; a stack, global or per direction (S15): the stack test; Python
    equality as the pairing key, `str()` for ids, or float ids made raw (S6): the id-type test; latency from the
    trace start, or no `error` kind: the pairing test; batch made raw, no id, method or `error` type check, null
    ids allowed (S2, S13, T5): the malformed-frame test; the binary label dropped, `--full` raw dropped or
    unescaped: the binary-and-unparsed test; in-flight never flagged, its label dropped, or the first request
    kept on reuse (S7): the reuse test; trace split by `splitlines()` (S1): the line-separator test and two
    escape tests; notes split by `splitlines()`: the notes-split test; `esc` without `Cc` or without `Zl`/`Zp`,
    method or stderr unescaped (S4): the escape tests; `OSError`, `UnicodeDecodeError` or `ValueError` not turned
    into a `show:` line, or `ShowError` uncaught or exiting 1 (S3): the unreadable-trace test and the notes
    exit-2 test; `BrokenPipeError` uncaught or exiting 1 (S10): the closed-pipe test.
    C13, the row's mutation (c2s arrows before s2c arrows): the diagram test; all arrows solid, the stderr note
    keeping its newline: the diagram test; raw frames drawn as arrows: the malformed-frame test (crash); labels not
    escaped: the escape test; the notes file read without `read_text`, or exit 1 on unreadable notes: the notes
    exit-2 test.
    C14, the row's mutation (`--explain` always exits 0): the missing-note, extra-note and notes exit-2 tests.
    25 survived. In the escape tests `lines()` split stdout with `splitlines()`, which drops a leaked `\r` or
    U+2028, so their checks for those two were empty: ids not escaped, and `--full` JSON not escaped, passed.
    Also passed: id pairing or the in-flight check ignoring direction (no fixture had one id in flight both ways
    at once); a frame with an `id` but neither `result` nor `error` shown as a response; `describe`'s batch
    branch dropped (a batch holding `"method"` or `"id"` as an item then crashes); tap events, `parse_error` and a string error `code` not escaped;
    `--full` JSON on one escaped line, and `--full` printing a stderr record's text a second time; `load`'s
    shape check dropped whole or in part (a non-object record, an unknown `dir`, a non-numeric `t_ns`: each a
    traceback, exit 1); `main` without its flush or without the `/dev/null` redirect (the closed-pipe test only
    closes after the viewer has written into the pipe); a batch drawn as an arrow, ids in labels as Python `str()`,
    and `tap` records left out of `--mermaid` (C13); request and response anchors with Python `str()` ids, and a
    batch anchored as `raw` (C14). After `lines()` split on `\n` and 8 new tests (26), each is killed:
    `test_c9_pairing_and_in_flight_ids_are_per_direction`, `test_c9_batch_and_result_less_response_do_not_crash`,
    `test_c9_every_printed_field_is_escaped`, `test_c9_full_pretty_prints_json_and_adds_nothing_to_stderr`,
    `test_c9_records_of_the_wrong_shape_exit_two_with_one_line`, `test_c9_output_pipe_closed_before_start_ends_quietly`
    (read end closed before the viewer starts; 8 runs of 8), `test_c13_frames_that_are_not_messages_are_notes_and_ids_keep_json_type`
    and `test_c14_anchors_keep_json_id_type_and_name_a_batch`; the two unescaped mutants by the existing escape test.
    Signed equivalent: the pairing key without the id's type name (`id_text` already tells the types apart: an
    int is digits, a float's JSON has `.`, `e`, `NaN` or `Infinity`, a string starts with `"`, a bool is
    `true`/`false`); the error `code` without `esc` (`json.dumps` with its default `ensure_ascii=True` escapes
    every character outside printable ASCII, so `esc` has nothing left to change).
    Not fixed here, found while mutating (S3 still open for these inputs): a record with no `t_ns` passes `load`
    (its default is for the synthetic marker) and crashes `line_for` with `KeyError`; a record whose `dir` is a
    list crashes `load` with `TypeError: unhashable type`. Both exit 1 with a traceback. `--mermaid` still notes
    a batch as `not JSON-RPC` (S13's second half); the new C13 test does not pin that text.
  - C9, C13 viewer fixes (2026-10-21, S3 and S13 as dispositioned): the three defects above are fixed in `tap/show.py`.
    A record with no `t_ns` (the synthetic marker keeps its default) or a non-string `dir` exits 2 with one
    `show:` line; `--mermaid` notes a batch as `<dir> batch`, as the plain view does. Tests, written first and seen
    failing: `test_c9_record_without_t_ns_or_with_listy_dir_exits_two_with_one_line`,
    `test_c9_synthetic_marker_may_omit_t_ns`, `test_c13_mermaid_labels_a_batch_as_a_batch`. Not re-mutated.
  - C1-C6, C17 after step (a) (2026-10-21): each mutant applied to `tap/__main__.py` in a temp copy of
    `tap/` and `tests/` with `PYTHONDONTWRITEBYTECODE=1` and no `__pycache__`, then the whole of
    `tests.test_tap` run; baseline exit 0 (36 tests). Killed, with the tests that fail:
    C1, a frame's head dropped when a newline completes it (review G1): both split-and-large tests and the
    flood test; `pending` replaced instead of extended: both split-and-large tests; every forwarded chunk cut to
    4096 bytes (C1.5): 6 tests, among them both split-and-large tests and the flood.
    C2, record after forward (G11): `test_frames_are_recorded_before_they_are_forwarded`; no join of the
    stdout and stderr threads (G8): the flood, partial-line and s2c split tests; `t_ns` absolute (G5) or
    always 0 (G6): 22 tests through the shared trace check; stderr records not advancing `seq` (G7): the flood
    and stderr tests; `bytes` one short on a terminated frame (G4): 19 tests.
    C4, `surrogatepass` (C4.5): the CESU-8 test; U+0085/U+2028/U+2029 left raw: the line-breaks test; the
    `RecursionError` catch dropped in `encode_record`: the too-deep-to-write test; dropped in `frame_fields`
    together with `frame()`'s fallback: both deep-frame tests.
    C5, `process_group=0` dropped (G9): the process-group test; early signals not replayed (G10): the
    early-signal test, by `TimeoutExpired` after 5 s rather than an assertion; SIGHUP not forwarded: the
    SIGHUP subtest; `close_stdout` dropped: the EOF-at-once test; usage errors exit 1: both usage tests; an
    unopenable trace exits 1: the unwritable-path test.
    C17, a trace write error propagates out of the relay (the row's mutation): the file-size-limit test; no
    `O_TRUNC`: the replace test; mode 0644 without `fchmod`: both mode tests; no `fchmod` alone: the replace
    test; `read_some` without its wait on `BlockingIOError`: the non-blocking stdin test.
    Five survived, and C2, C4, C6 and C17 were amended (register row 2026-10-21, decided by the agent on the
    owner's delegation). Joining only the stdout thread (C6.6) passed because the flood child's last stderr
    lines are drained while the stdout thread still works; `t_ns` always 1 passed every bound C2 set; dropping
    the `RecursionError` catch in `frame_fields` passed because `frame()`'s fallback still gave `json: null`,
    though as `raw_b64`; dropping `open_standard_fds` had no test. After the new tests (39), each is killed:
    C6.6 by `test_stderr_written_after_stdout_closes_is_recorded_before_exit` (5 runs of 5), `t_ns` 1 by
    `test_t_ns_follows_real_time`, the `frame_fields` catch by both deep-frame tests (`raw` missing), and
    `open_standard_fds` by all three subtests of `test_closed_standard_descriptors_do_not_reach_the_trace`.
    Signed equivalent: dropping `parse_float` (`1e999` then parses to infinity, and `encode_record`'s
    `allow_nan=False` turns it into `json: null` with a `parse_error`, so C4 holds; the first layer stays
    because its message names the cause).
  - C8, C11, C12 after step (b) (2026-10-21): the G1, G7, G8 and G9 changes of `baf9054` (R7-R9, R12, R20,
    T15, T19). Each mutant applied in place to its tool with `PYTHONDONTWRITEBYTECODE=1`, the matching test
    file run, the tool restored and `git diff` seen empty. G8 is C11's gate, recorded here with its batch.
    Baselines exit 0. 42 mutants (G8 14, G1 8, G7 9, G9 11): 29 killed by the tests of `baf9054`, 13
    survived; 11 of those were killed by new tests (passing on the real tools first), 2 signed equivalent.
    Whole set re-run on the final tests: 40 killed, the 2 equivalents pass.
    C11 (G8, `tests.test_citations`, 16 tests): killed with no new test: containment check off, target not
    resolved (escape test); minimum 5 or 7, `<=` or no length check (short- and six-character tests); no
    `continue` after the length error (the scanned-files count); final-newline `pop` dropped (phantom-line
    test); undecodable doc skipped silently, or not skipped (undecodable test). Survived, then killed:
    base not resolved, by `test_root_reached_through_a_symlink_passes`; length of the raw text instead of
    the unescaped fragment, by `test_fragment_length_counts_unescaped_characters`; no `continue` after the
    outside error (the outside file is read), by `test_escaping_path_gets_one_error_and_is_not_read`.
    C8 (G1 and G7, `tests.test_provenance`, 25 tests): killed with no new test: record headings `###` only,
    `##`-`###` or `###`-`####`; the old `register` substring; the register phrases ignored; the next-section
    search starting on `## Result` itself; `len(values) < 1`; any Status value accepted; a bulleted
    `- Status:` not matched; an open phase sent to the CHANGELOG check. Survived, then killed: case-sensitive
    phrases, by `test_register_row_at_sentence_start_resolves`; no word boundary before `register row`, by
    `test_register_row_inside_a_longer_word_does_not_resolve`; the Result not cut at the next `##`, by
    `test_status_in_a_later_section_is_ignored`; trailing blanks kept in the value, by
    `test_trailing_whitespace_after_status_value_is_ignored`; `Status:` matched mid-line, by
    `test_status_mentioned_mid_line_is_not_the_field`; `status:` in any case, by
    `test_lowercase_status_is_not_the_field`.
    C12 (G9, `tests.test_lessons`, 16 tests): killed with no new test: fences not stripped, or `^` only at
    the string start (fence test); order check off (reverse test); `-e` alone (pipe test); `-o pipefail`
    alone (not-last test); default `--min-lessons 0`; the timeout uncaught, unreported or not patched
    (timed-out test). Survived, then killed: a greedy fence (first fence to last), by
    `test_headings_between_fenced_blocks_count`; a fence closed by a ```` ```text ```` line, by
    `test_fence_closes_only_on_a_bare_fence_line`.
    Signed equivalent: G8 `if lines and lines[-1] == ""` without `lines and` (`str.split` never returns an
    empty list); G1 without the `registered in mission.md` phrase (`"mission.md" in source` already
    resolves any Source holding it).
  - C12, C15, C16, C18 after the step (b) fixes (2026-10-21; `ff09e5b` for B10, `53df051` for B1, B3, B4,
    B6, B16 and B19, `92721d0` for B2, B7 and B11). The builders' handbacks reported every mutant killed;
    the close-out agent re-ran them on the merged tree at `7c6e983` and these are its results. Each mutant
    was applied in place with `PYTHONDONTWRITEBYTECODE=1` and no `__pycache__`, the whole named test module
    run, the file restored and `git diff` seen clean after each. Baselines exit 0: `tests.test_no_run_output`
    52 tests, `tests.test_lessons` 20, `tests.test_lesson_01` 3, `tests.test_e2e` 5. 25 mutants, 25 killed.
    C12 (G9, B10): the old three-backtick regex: the tilde, four-backtick, tilde-not-closed-by-backticks
    and unclosed-fence tests; only backticks open a fence: the tilde test; any bare run of 3 or more closes
    (fence length ignored): the four-backtick test; a line of either character closes: the
    tilde-not-closed-by-backticks test; an unclosed fence kept as prose: the unclosed-fence test.
    C15 (G11 and the installer): G11-pat (`github_pat_` regex removed) and G11-pwd-json (`PWD` dropped from
    the JSON env keys): `test_each_leak_is_named_by_file`; G11-addonly (`--diff-filter=A`): the
    edited-README push test and the three typechange tests; G11-AM (`--diff-filter=AM`): the three
    typechange tests (two over `check_commit`, one push); G11-noroot (`--root` dropped):
    `test_leak_in_the_root_commit_of_a_new_branch_is_refused` and the dispatcher test, so the root case is
    no longer caught only by accident (B1); the old home lookahead (whitespace, quote or end only):
    `test_home_directory_before_any_delimiter` (7 subtests); the KEY=VALUE form without leading
    whitespace, or without `declare -x`: `test_indented_and_declared_env_dumps`; B19, the old
    `mode != "120000"` regular-file-only read: the three working-tree tests; only the index symlink
    skipped: the file-replacing-a-symlink and retargeted-symlink tests; a working-tree link followed instead
    of read as its target: four tests, `test_working_tree_symlink_content_is_not_read` among them; B16, the
    old one-line `own=` assignment: `test_outside_a_repo_the_installer_stops_before_mkdir`; B6, the
    installer in `PrePushHookTest.setUp` run without `env=self.env`: 8 tests, on the empty-stderr assertion
    (this machine's global configuration sets `core.hooksPath`, so the installer warns). The mutant left
    open by the earlier C15 run (dropping `mode != "120000"`) is now killed. Not covered by B6's fix: the
    tests' in-process `check_tracked` and `check_commit` calls run read-only git plumbing (`ls-files -s -z`,
    `cat-file blob`, `diff-tree -z`) with the process environment; accepted (A20).
    C16 (B7): REC-shlvl (`SHLVL=1 _=/usr/bin/env PWD=/` added to the `env -i` list) and REC-user (`USER=x`
    added): both killed by `test_c16_minimal_environment`, which now requires the exact allowlist. This
    supersedes the `PWD`, `SHLVL`, `_` allowance in the C16 line above.
    C18 (B2, B11): the `mkdir` loop without its existence test (the row's mutation):
    `test_c18_unusable_name_fails_fast` (the 10 s timeout); both reading `run=` lines put back to
    `ls -d runs/*-lesson01 | tail -1`: the name-order and newest-by-mtime tests; the same lines picking by
    `ls -d ... | sort | head -1`: the newest-by-mtime test; the `exp-list-first` block taking its folder by
    glob instead of its `recorded:` line: `test_recording_blocks_read_the_recorded_line`.
    Also seen: `git check-ignore -q .claude/worktrees/agent-x/file` exits 0 (B18); the G8 docstring reads
    "resolves in the checked-out submodule (bootstrap checks the pin)" (B13); lesson 01 line 103 and
    question 5 with its answer agree with the walkthrough and M8 (B12).
- Judgement verdicts:
  - J1: pass, owner, 2026-10-21 (the row above).
  - J2: pass, owner, 2026-10-21 (the row above), signed before the learner-walk findings list existed
    (finding R17). Close-out note, agent-proposed, owner to confirm (A3; not an owner signature): read
    against `audits/learner-walk-lesson-01.md`, the learner reached the end of lesson 01 without outside
    help; of its stalls, items 1, 2, 4, 5, 6, 8, 9 and 10 are fixed in the README, lesson and walkthrough
    (`2634b41`), item 11 needs no change, and items 3 (the Predict answers can be read further down the
    page) and 7 (no explicit prompt to guess each experiment's outcome) are accepted as teaching-design
    choices. The agent proposes that J2's pass stands on that evidence. The walk's log stays on the
    owner's machine and was not read for this note.
- Findings beyond the rows:
- Status: open
- Where it stands:
