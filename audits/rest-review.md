# Closing review, phase 1: everything except the tap's internals

Reviewer: an independent agent (Opus 5.5, high effort) that did not build any of this work.
Branch `phase-01-wire-tap` at `6659123`. Date of review: 2026-10-21. The tap itself (`tap/`)
and the C1-C16 falsifiability audit are a separate review (`audits/tap-review.md`) and are
not repeated here.

## 1. Scope and what I ran

Read in full: `specs/mission.md`, `specs/roadmap.md`, `specs/tech-stack.md`, the phase's
`requirements.md`, `validation.md`, `plan.md`, `audits/learner-walk-lesson-01.md`, `README.md`,
`docs/lessons/01-the-wire-and-the-handshake.md`, `docs/walkthrough/01-handshake-2025.md`,
`scripts/{gate,bootstrap,install-pre-push,record}.sh`, `.github/workflows/ci.yml`,
`.gitignore`, `.gitmodules`, `pyproject.toml`, `tools/check_{citations,lessons,no_run_output,provenance}.py`,
`tests/test_{citations,lessons,no_run_output,provenance}.py`, `tests/drive.py`, every fixture in
`tests/fixtures/`, and every spec and server line the walkthrough and lesson cite.

Commands run in the real repo (read-only apart from the git-ignored `runs/`):

- `scripts/gate.sh`, once: exit 0 in 10.8 s. G4 ran 64 tests, G5 3 tests, G8 checked 31
  citations, G9 checked 1 lesson, G11 ok. It added 9 run folders to `runs/`.
- `python3 -m tap.show` (plain and `--mermaid`) on the fresh `lesson01` run the gate recorded,
  plus a small stdlib script that printed each record's `seq`, `dir`, byte length, method and id.
- Section D checks (table in section 4), `git log -p` scans, `git grep` for identities.
- `git rev-parse --git-path hooks` and `git config --get core.hooksPath` (only to learn whether
  the hook is live; I did not read or print the configured path).

Experiments were run in a scratch copy (`tap tests tools scripts specs docs README.md
pyproject.toml .github .gitignore` copied, `vendor/` symlinked) with its own `git init`, and in
throwaway repos with local bare remotes, using `GIT_CONFIG_GLOBAL=/dev/null`.

Not done: the G6 clean-clone walk (the maintainer's step); any review of `tap/` internals;
checking CI on GitHub (no network; I relied on the C10 and M6 records); re-measuring M2, M4, M5
and M6; testing on macOS.

## 2. Findings

Counts: 0 blocker, 5 major, 13 minor, 4 nit.

### R1 (major, CONFIRMED). The G11 pre-push hook does nothing when `core.hooksPath` is set, and it is set in this clone

- Location: `scripts/install-pre-push.sh:7`
- Defect: the installer writes `$(git rev-parse --absolute-git-dir)/hooks/pre-push`, but git
  runs hooks from `core.hooksPath` when that is set, so the installed hook never runs, and
  neither the installer nor bootstrap says so.
- Reproduction: in a throwaway repo with a bare remote, `git config core.hooksPath .githooks`,
  then `scripts/install-pre-push.sh "$PWD"` (exit 0, file written), commit `git add -f
  runs/trace.jsonl`, `git push`: exit 0, the remote has the commit. The same steps without
  `core.hooksPath`: push refused, exit 1. In the real repo, `git rev-parse --git-path hooks`
  is not `.git/hooks`, and `git config --get core.hooksPath` succeeds, so the hook bootstrap
  installed here is inert on the owner's own machine.
- Why it matters: standing law 1 and D15 make this hook "the gate that actually prevents
  publication" on a public repo. On the clone that pushes most, it is off. C15 did not catch
  this because `tests/test_no_run_output.py:79` sets `GIT_CONFIG_GLOBAL` to `/dev/null`.
- Suggested fix: install to `$(git rev-parse --git-path hooks)/pre-push`, and if
  `core.hooksPath` is set, fail with a message that tells the user to chain G11 from that hooks
  directory (or add a test that runs with `core.hooksPath` set). Whatever global hook is
  in use on this machine also needs to call `tools/check_no_run_output.py --pre-push`.
- Disposition: downgraded: overstated on this machine. The global `_dispatch` hook chains to `.git/hooks/pre-push`, re-verified 2026-10-21 in a throwaway repo (push refused by the local hook). Real gap kept: other clones or other `core.hooksPath` values. Fix in step (b): the installer writes to `git rev-parse --git-path hooks` and warns when `core.hooksPath` is set and that path is not the repo's own hooks directory; a test runs with `core.hooksPath` set (D15; register row 2026-10-21 (third of that date); checked by C15).

### R2 (major, CONFIRMED). The pre-push hook does not check files that a merge commit adds

- Location: `tools/check_no_run_output.py:99-101`
- Defect: `git diff-tree -r` with no `-m`/`--cc`/`--first-parent` prints nothing for a merge
  commit, so any file that only the merge introduces (a conflict resolution, a
  `merge --no-commit` followed by `git add`) is never checked.
- Reproduction: throwaway repo, hook installed, `git merge --no-ff --no-commit side`, then
  `git add -f runs/trace.jsonl` (a trace-shaped line), `git commit`, `git push`: the hook
  prints `no-run-output: ok (pushed commits)`, push exit 0, and the bare remote's `main`
  contains `runs/trace.jsonl`.
- Why it matters: phase close is a merge into `main`. CI would then go red at the tip, but only
  after the file is public.
- Suggested fix: for merge commits, use `git diff-tree -r --diff-filter=AM -z --first-parent`
  (or diff against each parent), and add a merge case to `PrePushHookTest`.
- Disposition: fix in step (b): the pre-push scan reads files that a merge commit adds (G11 and D15 amended; register row 2026-10-21 (third of that date); checked by C15).

### R3 (major, CONFIRMED). A real recorded trace passes G11 under any name but `*.jsonl`

- Location: `tools/check_no_run_output.py:64` (and the G11 row in `specs/tech-stack.md`)
- Defect: the trace-shape rule only looks at paths ending in lowercase `.jsonl`, and a trace
  recorded by `scripts/record.sh` matches none of the text rules (it has no home path, and the
  `get-env` result holds only PATH, HOME, LANG and MCP_WIRE_LAB, two of the five keys the
  env-dump rule counts).
- Reproduction: in the scratch repo, `scripts/record.sh tests/fixtures/get-env.ndjson getenv`,
  then copy its `trace.jsonl` to `plant/e1-trace.ndjson` and to `plant/e2-trace.JSONL`,
  `git add -f`, commit, `python3 tools/check_no_run_output.py`: neither file is reported (only
  the two copies kept under their original name `trace.jsonl` were caught).
- Why it matters: `.ndjson` is this repo's own fixture extension, so it is the natural name for
  "a real trace as an example". A5 forbids exactly this, and the law's admitted limit is about
  pasted fragments, not whole traces with a different suffix.
- Suggested fix: apply the shape rule to any text file whose JSON lines carry `seq`, `dir` and
  `t_ns`, whatever its name (case-insensitive), and add `.ndjson` and `.JSONL` cases to the tests.
  Amend the G11 row in `tech-stack.md` by a register row.
- Disposition: fix in step (b): the trace-shape rule applies to any text file whose JSON lines carry `seq`, `dir` and `t_ns`, whatever its name or case (G11 amended; register row 2026-10-21 (third of that date); checked by C15).

### R4 (major, CONFIRMED). D8 says the walkthrough's example messages are checked by G9; nothing checks them, and one has already drifted from the wire

- Location: `specs/phases/01-wire-tap/requirements.md:131-133`; `docs/walkthrough/01-handshake-2025.md:22,125-127`
- Defect: G9 reads only `docs/lessons/*.md`, and the walkthrough has no runnable blocks, so its
  hand-written JSON examples are not checked against anything. The `ping` reply example shows
  `jsonrpc, id, result` key order, but the pinned server sends `result` first.
- Reproduction: a short script compared each ```json block in the walkthrough with the `raw`
  frames of the gate's fresh `lesson01` run: the `initialize` and `notifications/initialized`
  examples match byte for byte, but the `ping` reply does not. The real frame is
  `{"result":{},"jsonrpc":"2.0","id":2}`. `grep walkthrough tools/check_lessons.py` finds nothing.
- Why it matters: the lab's premise (D2) is that the bytes matter and normalizing JSON hides
  them. An example that reorders keys while line 22 calls it only "trimmed" teaches the opposite.
  The learner walk's item 5 (`clientInfo.name` drift) shows these examples do drift when nothing
  checks them.
- Suggested fix: either add a check, e.g. a G5 test asserting that every ```json line in the
  walkthrough equals some fresh frame's `raw` (minus the newline), or change D8 to say the
  examples are unchecked and list them in the Result. Then fix the `ping` example, or say that the
  key order is the SDK's (result first).
- Disposition: fix in step (b): D8 now says the walkthrough's JSON examples are not machine-checked and the Result lists them as unchecked; the `ping` example is corrected to the real key order (register row 2026-10-21 (third of that date)).

### R5 (major, CONFIRMED). Section E's "lesson command not covered by a gate" condition stands now

- Location: `specs/phases/01-wire-tap/validation.md:87-88`; `docs/lessons/01-the-wire-and-the-handshake.md:11,56-73,90-92`; `docs/walkthrough/01-handshake-2025.md:6-9`; `README.md:20-24,37-40`
- Defect: lesson commands outside the runnable form are not listed in the Result as unchecked.
  These are bootstrap at line 11, "the same command without the redirect" and `--full ... | less`
  at lines 90-92, and the Mermaid block that claims "yours will match" at lines 56-73. The
  walkthrough's and README's console blocks are not gated either.
- Reproduction: `python3 tools/check_lessons.py` runs only the six `<!-- run -->` blocks. The
  Result section (`validation.md:93-171`) has no "unchecked" entry. By hand, the gate's fresh
  `--mermaid` output does match the lesson's diagram today, line for line.
- Why it matters: section E says the phase is not done while this stands. The fix is cheap.
- Suggested fix: list these in the Result as unchecked, or gate the Mermaid claim by turning
  it into a runnable block with the diagram as its expect block.
- Disposition: fix in step (b): the lesson commands outside the runnable form, the Mermaid claim, and the walkthrough and README console blocks are listed in the Result as unchecked (register row 2026-10-21 (third of that date)).

### R6 (minor, CONFIRMED). The walkthrough says the `initialize` reply is the largest frame; the `tools/list` reply is nearly three times larger

- Location: `docs/walkthrough/01-handshake-2025.md:63-65`
- Defect: "The reply is the largest frame of the handshake because it also carries the server's
  `instructions` text" is false. It also contradicts M1 (`validation.md:105-106`).
- Reproduction: in the gate's fresh `lesson01` trace, seq 3 (the `initialize` reply) is 3533
  bytes and seq 6 (the `tools/list` reply) is 10184 bytes.
- Why it matters: a learner who checks the claim against their own trace finds it wrong in the
  frame J1 cares about most. It also undercuts the plan's tick that every cited location was
  verified (`plan.md:93-96`).
- Suggested fix: "the largest frame after the tool list; much of it is the `instructions`
  text read at ...".
- Disposition: fix in step (b), docs only: the `initialize` reply is "the largest frame after the tool list".

### R7 (minor, CONFIRMED). G9 checks only a block's last exit status, and half of experiment 1's check passes with no server reply

- Location: `tools/check_lessons.py:57-67`; `docs/lessons/01-the-wire-and-the-handshake.md:116-129`
- Defect: blocks run as `bash -c` with no `set -e` and no `pipefail`, so a failing command
  that is not last is ignored. In experiment 1, `record.sh`'s status is discarded inside the
  loop, and `grep ... | tail -1` falls back to the *request's* `protocolVersion` when there is no
  response. The `2024-11-05` line is the same value the client offered.
- Reproduction: a temp lesson with a block `$ false` / `$ echo ok` (expect `ok`) and a block
  `$ cat no-such-file | wc -l`: `lessons: ok (1 checked)`. Separately, I took a fresh
  `exp-old-version` trace with every `s2c` record removed. The lesson's pipeline over it still
  prints `"protocolVersion": "2024-11-05"`.
- Why it matters: "every block marked runnable exits 0" (G9) is weaker than written, and the
  lesson says its commands "fail if a future pin changes" the outcome. An SDK that answered
  `2024-11-05` with an error would pass the first half of the check.
- Suggested fix: run blocks with `bash -eo pipefail -c`. In experiment 1, select the `s2c`
  response, e.g. grep the `<-  response id=0` line in plain `tap.show` and the
  `"protocolVersion"` inside `result`, or use a short `python3 -c` over the trace.
- Disposition: fix in step (b): G9 runs each block under `bash -eo pipefail -c`, and experiment 1 selects the `s2c` response (D13 amended; register row 2026-10-21 (third of that date); checked by C12).

### R8 (minor, CONFIRMED). G7 only notices a closed phase if "closed" is on the same line as "Where it stands:"

- Location: `tools/check_provenance.py:68`
- Defect: `.` does not match a newline, so a nested bullet (the format the Result already uses
  for Measurements) or wording such as "complete" skips the CHANGELOG check.
- Reproduction: in the scratch copy with no `CHANGELOG.md`, setting the Result line to
  `- Where it stands: closed 2026-10-21` gives exit 1 (good). With `- Where it stands:` and then
  a sub-bullet `- closed 2026-10-21, merged and tagged` it gives `provenance: ok`, exit 0. With
  `phase complete, merged, tagged lesson-01` it also gives exit 0.
- Why it matters: the CHANGELOG step is the last box in the plan and the only thing G7 guards.
- Suggested fix: require CHANGELOG once a `lesson-01` tag or merge is claimed, or make the
  Result's status a fixed single-line field (`Status: open|closed`) and fail on any other value.
- Disposition: fix in step (b): G7 reads the Result's status from one fixed single-line field `Status: open|closed` and fails on any other value (tech-stack G7 amended; register row 2026-10-21 (third of that date); checked by C8).

### R9 (minor, CONFIRMED). G1 accepts any Source that contains the substring "register"

- Location: `tools/check_provenance.py:54`
- Defect: `"register" in source.lower()` matches "not yet registered", "unregistered" and so on,
  so a Source that admits it has no provenance passes.
- Reproduction: in the scratch copy, append `### D17` with
  `*Source:* agent idea, not yet registered, 2026-10-20.`: `provenance: ok`. A record written
  as `## D18` with no Source at all is not seen either, because `RECORD` requires `###`.
- Why it matters: G1 is the gate behind "every requirement traces to an ask or a register row".
- Suggested fix: match `register row` / `registered in mission.md` as phrases (or require
  the Source to name `mission.md`, an `A<n>`, or a constitution file), and flag any `#{2,4} D\d+`
  heading.
- Disposition: fix in step (b): G1 matches `register row` or `registered in mission.md` as phrases and flags any `##`-`####` D heading without a Source (tech-stack G1 amended; register row 2026-10-21 (third of that date); checked by C8).

### R10 (minor, CONFIRMED). G11's text rules miss common leak forms

- Location: `tools/check_no_run_output.py:26-27,61-63,92`
- Defect: G11 misses all of these:
  - A bare home directory with no further component, e.g. the value of HOME. The regex needs
    a `/x` after the user name.
  - Shell `env` output (KEY=VALUE lines). `ENV_KEY` only knows the JSON form.
  - Any file with a single non-UTF-8 byte: every text rule is skipped for it.
  - Windows-style home paths.
  - JSON with escaped slashes.
  - A tracked symlink whose target is a home path.
- Reproduction: in the scratch repo I committed six files, one per form above. `env`-style
  output was USER, HOME (a bare home directory), SHELL and PATH lines. The non-UTF-8 file was a
  Latin-1 log line followed by a GitHub-token-shaped string and a full home path. G11 reported
  none of them, exit 0 apart from the unrelated `trace.jsonl` copies of R3.
- Why it matters: the bare HOME value and `env` output are the most likely things to be pasted
  from a terminal. The non-UTF-8 skip turns a stray byte into a full bypass of the secret rules.
- Suggested fix: allow end of string, whitespace or a quote after the user name; add a KEY=VALUE
  form to the env rule; decode with `errors="replace"` for the text rules and keep "binary"
  only for the trace-shape rule; check symlink targets (`git cat-file -p` of mode 120000).
  Each change amends the G11 row by a register row.
- Disposition: fix in step (b): G11's text rules allow end of string, whitespace or a quote after the user name, add the KEY=VALUE env form, decode with `errors="replace"`, and check symlink targets (G11 amended; register row 2026-10-21 (third of that date); checked by C15).

### R11 (minor, CONFIRMED). G11 in gate mode reads the working tree, not what git will commit

- Location: `tools/check_no_run_output.py:92-93`
- Defect: `check_tracked` lists files from the index but reads their content from disk, so a
  staged leak whose working copy was reverted passes. A tracked file deleted from disk is skipped.
- Reproduction: scratch repo, `git add` a doc containing a token-shaped string, then overwrite
  the working copy with `clean`. G11 says `ok (tracked files)`, exit 0, while
  `git show :docs/staged.md` still holds the token.
- Why it matters: small, because the pre-push hook reads commit content. But with R1 and R2 the
  hook cannot be relied on, and README line 48 says the gate catches what is "about to be committed".
- Suggested fix: read `git show :<path>` (the index), or both index and working tree.
- Disposition: fix in step (b): G11 in gate mode reads the index (`git show :path`) as well as the working tree (G11 amended; register row 2026-10-21 (third of that date); checked by C15).

### R12 (minor, CONFIRMED). G8 accepts citations that escape the submodule or have an empty fragment, skips non-UTF-8 docs, and never checks the pin

- Location: `tools/check_citations.py:12,44,51,57-60,64-67`
- Defect: the path is joined without containment, so `servers:../../README.md:1` resolves to the
  repo's own README. An empty fragment `""` is a substring of every line. A doc that is not
  valid UTF-8 is silently skipped. `check()` tests only that the submodule directory is
  non-empty, and `scripts/gate.sh` has no pin check, so locally G8 checks whatever commit is
  checked out.
- Reproduction: in the scratch copy, a doc with
  `` `servers:../../README.md:1` "# mcp-wire-lab" `` and `` `servers:src/everything/transports/stdio.ts:3` "" ``
  gives `citations: ok (33 checked)`. A doc with a Latin-1 byte and an off-by-one
  `stdio.ts:50 "serveStdio("` citation gives `citations: ok (31 checked)`. `grep -n pin scripts/gate.sh`
  finds nothing. Today all 31 citation-shaped strings in `README.md` and `docs/` are in the
  checked form, so there is no live false negative.
- Why it matters: the tool's docstring promises "resolves in the pinned submodule". CI is safe
  because bootstrap checks the pins first, but a local gate run after a `git pull` that moved a
  pin, without `git submodule update`, checks the wrong revision.
- Suggested fix: resolve the target and require it to stay under the submodule; require a
  non-empty fragment (perhaps three or more characters); fail on undecodable docs; check
  `git -C vendor/<x> rev-parse HEAD` against the pins (one shared constant with bootstrap).
- Disposition: fix in step (b): G8 requires the target to stay inside the submodule, a fragment of at least 6 characters, and fails on an undecodable doc; the pin check is accepted as a limit (bootstrap owns the pins) (D13 amended; register row 2026-10-21 (third of that date); checked by C11). Same as T15.

### R13 (minor, CONFIRMED). The lesson's Check-yourself 5 and M8 suggest that the server broke the spec; the rules cited bind the client

- Location: `docs/lessons/01-the-wire-and-the-handshake.md:183,195,131-132`; `specs/phases/01-wire-tap/validation.md:117`
- Defect: answer 5 says "the spec says MUST or SHOULD NOT, and this server answered anyway". M8
  says "the server enforces none of the three spec rules". But `lifecycle.mdx:147` (MUST send
  `initialized`) and `:157` (SHOULD NOT send requests before the reply) are duties of the client,
  the spec gives the server no duty to refuse, and in experiment 1 there is no client rule to
  enforce at all. Separately, line 132's "replies with the newest version it speaks" is an
  inference: the pinned server also speaks 2026-07-28 (mission, Era). 2025-11-25 is the
  installed SDK's `LATEST_PROTOCOL_VERSION` for `initialize`.
- Reproduction: `grep -n -i -E "before (the|receiving)|reject|-32600|-32002"` over
  `vendor/spec/docs/specification/2025-11-25/basic/lifecycle.mdx` finds only the two client- and
  server-sending rules at 157-163, and nothing about rejecting. The SDK constant is in
  `vendor/servers/node_modules/@modelcontextprotocol/core/dist`.
- Why it matters: a learner could conclude that the reference server is non-conformant, when it
  is just lenient. That misreads MUST and SHOULD NOT, which is what the experiments teach. Lines
  151-153 and 173 of the lesson already say this correctly; answer 5 undoes it.
- Suggested fix: reword answer 5 along the lines of "the rules bind the client; the server is
  lenient and the spec allows that", and M8 to "the server tolerates all three". Change line 132
  to "replies with `2025-11-25`, the newest `initialize`-era version it speaks".
- Disposition: fix in step (b), docs only: the lesson's answer 5 and M8 say the rules bind the client and the server is lenient; line 132 as the reviewer wrote.

### R14 (minor, CONFIRMED). The walkthrough says the SDK is not pinned; it is version-locked by the server's lockfile and installed on disk

- Location: `docs/walkthrough/01-handshake-2025.md:17-20`
- Defect: `npm ci` installs `@modelcontextprotocol/server` and `core` 2.3.1 exactly, as the
  pinned `vendor/servers/package-lock.json` records (P1 says the same). What is missing is a
  citable source tree, not a pin: only `dist/` is installed, and it is not a submodule, so G8
  cannot check it.
- Reproduction: `grep '"version"' vendor/servers/node_modules/@modelcontextprotocol/{server,core}/package.json`
  gives 2.3.1 for both. The lockfile has the same.
- Why it matters: a learner is told the SDK's code and version are unknown, when they can open
  it after bootstrap. The walkthrough's one SDK claim stated as fact (line 71, the `tools`
  capability is added by the first registration) can be backed by the pinned comment at
  `servers:src/everything/server/index.ts:134`, which it does not cite.
- Suggested fix: "the SDK is fixed by the server's lockfile (2.3.1) but is not a submodule, so
  its lines cannot be cited and checked here; its compiled code is under
  `vendor/servers/node_modules/@modelcontextprotocol/`". Cite index.ts:134 for line 71.
- Disposition: fix in step (b), docs only: the walkthrough says the SDK is fixed by the server's lockfile but is not a submodule; cite `index.ts:134`.

### R15 (minor, CONFIRMED). `record.sh` fails if run twice with the same name in the same second

- Location: `scripts/record.sh:15-19`
- Defect: the run folder is named to the second; `mkdir -p` reuses it and `ln -s` then fails on
  the existing `bin/node`, so under `set -e` the script exits 1 with an `ln` error.
- Reproduction: in the scratch copy, four back-to-back
  `scripts/record.sh tests/fixtures/exp-list-first.ndjson dup` runs: run 1 exit 0, runs 2-4 exit 1
  with `ln: failed to create symbolic link 'runs/<ts>-dup/bin/node': File exists`.
- Why it matters: a learner re-running a command quickly gets a confusing failure. Without
  the `ln` failure the second run would overwrite the first trace.
- Suggested fix: `mktemp -d "runs/<ts>-<name>-XXXX"`, or refuse a folder that already exists
  with a clear message.
- Disposition: fix in step (b): `record.sh` adds a numeric suffix until the run folder is new (D14 amended; register row 2026-10-21 (third of that date); checked by C16). Same as T17, S17.

### R16 (minor, CONFIRMED). The records contradict the code or each other in several places

- Location: these lines (each is a one-line fix):
  - `requirements.md:244-246`: D14 says PATH is "the directory of the node found at
    bootstrap". `record.sh:85-91` finds node at record time and links it into the run folder.
    The validation C16 entry explains the change, but D14 was not amended.
  - `requirements.md:106`: D7 says gate.sh runs "G1-G5, G8, and G9". It also runs G11
    (`scripts/gate.sh:16`).
  - `validation.md:90`: the condition "any scope beyond D14" is literally met by D15 and D16.
  - `validation.md:56`: M7 still says "the committed handshake trace".
  - `validation.md:120`: M7 says "11 lines of messages and notes". The fresh diagram has 10.
  - `plan.md:88-89`: "The Mermaid paste check (M7) is still open", though its box is ticked and
    M7 is recorded.
  - `tech-stack.md:13,30`: the SDK client and `tsc --strict` are "phase 4". The roadmap
    renumbered the SDK client to phase 5.
  - `tech-stack.md:46`: corpora go in `audits/YYYY-MM-DD-<phase>-<lens>.md`. None of the three
    corpus files (including this one) follows it.
  - `README.md:48,63-65`: says the gate "fails if one is about to be committed" (nothing runs it
    at commit time; the hook runs at push), and lists only some of the gates.
- Reproduction: read side by side. The M7 count is from `python3 -m tap.show <fresh run> --mermaid`.
- Why it matters: in this project the records are the specification. Each contradiction is a
  place where a later phase reads the wrong rule.
- Suggested fix: amend each line. The tech-stack lines need a register row, under the
  constitution's own rules.
- Disposition: fix in step (b): each listed line is amended, the tech-stack lines by register row 2026-10-21 (third of that date); the `audits/` file-name rule is amended to the names in use.

### R17 (minor, CONFIRMED). J2's verdict still rests on no evidence, though the evidence now exists

- Location: `specs/phases/01-wire-tap/validation.md:64`
- Defect: the verdict says it was signed before any walk log or findings list existed. The walk
  and its dispositions came later (`audits/learner-walk-lesson-01.md` section 5), and the row
  was not re-read against them. The audit's statement that the owner accepted items 3 and 7 is
  in an agent-written section, not the owner's signature.
- Reproduction: `git log --format='%h %s'` shows 014527e (verdict) before 080218b (walk) and
  2634b41 (fixes). The row's text is unchanged.
- Why it matters: section E is technically met (there is an owner verdict), but J2's own Pass
  column (every stall fixed or signed as accepted) has not been judged on its evidence.
- Suggested fix: the owner re-signs J2 against the findings list and the local log, and signs
  the acceptance of items 3 and 7 in the row.
- Disposition: open, owner: the owner re-signs J2 against the findings list and signs the acceptance of learner-walk items 3 and 7. Not done by the agent.

### R18 (minor, CONFIRMED). The public repository has no licence

- Location: repo root (`git ls-files | grep -i licen` is empty)
- Defect: there is no LICENSE file, so by default nobody may reuse the lessons or code, which
  fits badly with "for anyone who wants to learn MCP in depth". The vendored material is
  referenced as submodules (MIT/Apache-2.0/CC-BY-4.0 upstream), not copied, so it raises no issue.
- Reproduction: the command above. `README.md` and `specs/` do not mention a licence.
- Why it matters: this decision faces outward and belongs to the owner. I raise it, not decide it.
- Suggested fix: the owner picks a licence; add LICENSE and a register row.
- Disposition: open, owner: the owner picks a licence; the agent then adds `LICENSE` and a register row. Not done by the agent.

### R19 (nit, CONFIRMED). The walkthrough's wording is looser than the spec or the code in three places

- Location: `docs/walkthrough/01-handshake-2025.md:91-92,98,105-106`
- Defect: in line 91-92, "Until it arrives the server should only send pings and log messages":
  the spec (`lifecycle.mdx:160-163`) limits the server's *requests*, and the server sends
  responses (including the `initialize` reply) before `initialized`. Line 98 says "registers its
  tools in one place", but `servers:src/everything/server/index.ts:197` registers more in
  `oninitialized`, as the walkthrough itself says at line 84-85. Line 105-106 says "the viewer
  truncates it by default", but the default view prints no body at all.
- Reproduction: read the cited spec and server lines. The plain `tap.show` output shows
  `<-  response id=1 (answers seq 5, ...)` and no body.
- Suggested fix: "should not send requests other than pings, and may send log notifications",
  "registers the tools every client gets at ..." and "the default view shows only one line per
  frame".
- Disposition: fix in step (b), docs only: the three wordings as the reviewer wrote.

### R20 (nit, CONFIRMED). G9's section check ignores order and code fences

- Location: `tools/check_lessons.py:42-48`
- Defect: L1 fixes the order "Goal -> Predict -> ... -> Check yourself", but sections in reverse
  order pass, and so do headings that exist only inside a fenced code block.
- Reproduction: `check_sections` returned `[]` for both cases (scratch copy, `python3 -c`).
- Suggested fix: strip fenced blocks before matching, and require the seven headings in order.
- Disposition: fix in step (b): G9 strips fenced blocks before matching and requires the seven headings in order (D13 amended; register row 2026-10-21 (third of that date); checked by C12).

### R21 (nit, CONFIRMED). CI pins actions by mutable major tag and lets uv and the Python patch version float

- Location: `.github/workflows/ci.yml:14,17,20,22-23`
- Defect: `actions/checkout@v4`, `setup-node@v4`, `setup-python@v5` and `astral-sh/setup-uv@v5`
  are tags, not SHAs. `setup-uv` has no `version:`, and `python-version: "3.12"` floats (M6
  records uv 0.13.4 and Python 3.12.15 in CI against 0.12.5 and 3.12.3 locally). Permissions are
  `contents: read` and no secrets are used, which is good.
- Reproduction: read the workflow. Compare M6 at `validation.md:123`.
- Suggested fix: pin the actions by commit SHA, set `version: "0.12.5"` on setup-uv, or record
  in tech-stack that these may float.
- Disposition: accepted as a documented limit: CI actions are pinned by major tag and uv floats; noted in tech-stack. The Python and node versions are already recorded by CI output.

### R22 (nit, PLAUSIBLE). The README claims macOS support that nothing has tested

- Location: `README.md:14`
- Defect: "Linux, macOS or WSL", but CI runs only `ubuntu-latest` and the measurements are from
  WSL2. I did not test macOS.
- Suggested fix: "Linux or WSL (tested); macOS untested", or add a macOS CI job.
- Disposition: fix in step (b), docs only: the README says "Linux or WSL (tested); macOS untested".

## 3. Gate bypass experiments

Everything below ran in the scratch copy or in throwaway repos, never in the real repo.

| # | Gate | What I tried | Result |
| --- | --- | --- | --- |
| 1 | G11 | Real `record.sh` trace of `get-env`, renamed `.ndjson` | passed G11 (R3) |
| 2 | G11 | The same trace renamed `.JSONL` | passed (R3) |
| 3 | G11 | A real run folder committed as `docs/runs/r1/` and `Runs/r1/` | caught, via the `trace.jsonl` name; its `stderr.txt` passed |
| 4 | G11 | `env`-style KEY=VALUE dump with a bare home directory | passed (R10) |
| 5 | G11 | JSON object with only HOME (bare home directory) and USER | passed (R10) |
| 6 | G11 | Latin-1 byte, plus a token-shaped string and a full home path | passed: the whole file is skipped (R10) |
| 7 | G11 | Windows-style home path | passed (R10) |
| 8 | G11 | Tracked symlink whose target is under a home directory | passed (R10) |
| 9 | G11 | JSON with escaped slashes in a home path | passed (R10) |
| 10 | G11 | Leak staged in the index, working copy reverted | passed in gate mode (R11) |
| 11 | G11 hook | `core.hooksPath` set, then install, then push a `runs/` file | push accepted (R1) |
| 12 | G11 hook | `runs/` file added only by a merge commit | push accepted (R2) |
| 13 | G11 hook | Plain push of a `runs/` file, the control | refused, exit 1 |
| 14 | G11 | `get-env` keys under `record.sh` | PATH, HOME, LANG, MCP_WIRE_LAB: the minimal environment holds |
| 15 | G8 | Path escaping the submodule (`servers:../../README.md:1`) | passed (R12) |
| 16 | G8 | Empty fragment on an arbitrary line | passed (R12) |
| 17 | G8 | Off-by-one citation with curly quotes / no fragment / no backticks | not counted, so not checked; none exist in the docs today |
| 18 | G8 | Off-by-one citation in a non-UTF-8 doc | silently skipped (R12) |
| 19 | G8 | A citation pointing to the wrong line, the control | caught, "fragment is not on line 3" |
| 20 | G9 | `$ false` then `$ echo ok`; `cat missing \| wc -l` | both passed (R7) |
| 21 | G9 | Experiment 1's pipeline over a trace with no server frames | still printed `2024-11-05` (R7) |
| 22 | G9 | Sections reversed; sections only inside a code fence | both passed (R20) |
| 23 | G1 | Source "not yet registered, 2026-10-20" | passed (R9) |
| 24 | G1 | Decision headed `## D18` with no Source | not seen (R9) |
| 25 | G7 | "closed" on a nested bullet; "complete" wording | passed with no CHANGELOG (R8) |
| 26 | G7 | "closed" on the same line, the control | caught, CHANGELOG missing |

## 4. Section D and E status

Section D (boundary checks), run 2026-10-21 in the real repo:

| Row | Status | How I checked |
| --- | --- | --- |
| B1 | holds | `git -C vendor/servers status --porcelain` and the same for `vendor/spec`: 0 lines each, also after the gate ran. `git submodule status` shows `51b6382a...` and `1155ca46...` |
| B2 | holds | no `requirements*.txt`; `pyproject.toml` has no `dependencies`. An AST import scan with `sys.stdlib_module_names` over `tap/ tools/ tests/` found 0 non-stdlib imports, and the same scan found a planted `import requests` |
| B3 | holds | `grep -rn modelcontextprotocol tap tools --include=*.py`: 0 hits |
| B4 | holds, within G11's limits | G11's own regexes over `git log -p main..phase-01-wire-tap` (168k chars) and over `git log -p --all` (232k chars): 0 hits. The same scanner flagged a planted home path. Also `git log -p --all` has 0 hits for the login name. Caveat: the gaps in R3 and R10 apply to this check too |
| B5 | holds | `git diff --stat main -- specs/mission.md specs/roadmap.md specs/tech-stack.md` is empty: the constitution is unchanged on the branch |

Section E (not-done conditions); "stands" means the phase is not done:

| Condition | Status | How I checked |
| --- | --- | --- |
| A C row without a recorded mutation or signed stand-in | does not stand, as far as I checked | C1-C16 each have an entry under "Checks seen to fail". Whether each is falsifying is the tap review's job |
| A measurement copied from recon, not taken on this phase's walk | cannot be evaluated yet | M1-M8 were taken during the build (2026-10-20), and M6 is "partial". The G6 walk has not happened. I re-checked M1 (largest frame 10184 B), M3 (one stderr line) and M8's 16 tools on a fresh run: they hold |
| Closing review without its corpus in `audits/` | stands until both corpora land | this file is deposited; `audits/tap-review.md` was not present when I looked |
| J1 or J2 with no owner verdict, or a provisional one | does not stand | both carry owner verdicts. See R17 for J2's evidence |
| Learner walk without findings in `audits/`, or with its log committed | does not stand | `audits/learner-walk-lesson-01.md` is tracked. No walk log in `git ls-files` or in history |
| A lesson command or citation the gates do not cover, unless listed as unchecked | **stands** | see R5. All 31 citations are in the checked form |
| A change in vendor, a secret, an unattributed requirement, or scope beyond D14 | partly cannot be evaluated | vendor: clean (B1). Secrets: none found (B4). Attribution: G1 passes, with R9's weakness. "Beyond D14" is stale text (R16): D15 and D16 exist and are attributed |
| D8 without P3, or D10 without P7 ratified | does not stand | register row 2026-10-20 ratifies P1-P9 |

Plan boxes: every ticked box I could check matches the record, with two exceptions. The group
5 note still calls M7 open (R16). The group 6 tick that every cited location was verified
is undercut by R6. Group 8's unticked boxes are correctly unticked.

## 5. Cross-cutting notes

- Tap, in passing: nothing beyond R15 (`record.sh` is in my scope). The spawn record's argv uses
  repo-relative PATH and HOME as D14 requires.
- Review independence: commit trailers show `tap/show.py` (group 5) was built by Sonnet and
  `tap/__main__.py` (group 3) by Opus. A Sonnet tap review is therefore same-model for the
  viewer, against `plan.md:129-130` ("a different model from the builder"). The constitution and
  phase spec (db64bbd) were written by Opus, the same model as this review. The rest of my scope
  (gates, docs, CI, groups 1-2 and 4-7) was built by Sonnet.
- R1, R2 and R11 together mean the only reliable G11 backstop today is CI, which runs after
  publication, plus the manual B4 scan. That is the situation standing law 1 was written to avoid.
- `runs/` grows by about 9 folders per gate run (183 folders, 7.8 MB here). Harmless, but a
  `scripts/clean-runs.sh` or a note would help learners.
- G4's discovery also runs `tests.test_e2e`, so G5 repeats it. The plan notes this; it costs
  about 1.5 s.

## 6. Summary

The gates run and are green (64 + 3 tests, 31 citations, 1 lesson, G11 ok), and the boundary
checks B1-B5 hold. The docs are mostly accurate against the pinned spec and server. The weak
point is G11, the gate that enforces the project's one standing law. Its pre-push hook is inert
on this clone because `core.hooksPath` is set (R1), it skips merge commits (R2), and a real
trace under any suffix but `.jsonl` passes it (R3). On the records side, D8 promises a check of
the walkthrough's examples that does not exist, and one example already differs from the wire
(R4). Section E's "uncovered lesson command" condition currently stands (R5). The rest are
precision fixes to gates, teaching wording and records. I would fix R1-R5 before the phase-close
merge, since R2 bites exactly on that merge.
