# Step (b) review, phase 1: gates, G11, docs and `record.sh` against their dispositions

Reviewer: an independent agent (Opus 5.5) that did not build this work. The commit trailers show
every commit in the range was built by Sonnet 5.5. Branch `phase-01-wire-tap` at `47a6f16`. Date
of review: 2026-10-21. Scope: `git diff cecc630..47a6f16`. That is slice 2, G11 (`b8ca145`,
`aa7d27b`), the gates (`baf9054`), the docs and `record.sh` (`72177a5`), the two merges
(`03a0003`, `bce6674`) and the autonomy records (`71c9694`, `47a6f16`). I checked it against the
approved dispositions in `audits/rest-review.md`, `audits/show-review.md` and
`audits/tap-review.md`, and against `specs/` (requirements, validation, tech-stack, the mission
register). The viewer slice (`cecc630`) is outside the range and I did not review it.

## 1. Scope and what I ran

Read in full: the three review corpora, `audits/autonomous-decisions.md`, `requirements.md`,
`validation.md`, `tech-stack.md`, the register in `mission.md`, lesson 01, the walkthrough, the
README, `scripts/{install-pre-push,record,gate,bootstrap}.sh`, `tools/check_{no_run_output,
lessons,provenance,citations}.py`, and the changed tests. Both merges are clean (no hand
resolution; `git show --cc` is empty). Both side branches forked from `cecc630`, so they were
first tested together only after the merge.

Where I ran things:

- In a scratch copy of the tree at `47a6f16`, with its own `git init` and the built
  `vendor/servers` and `vendor/spec` linked from the main checkout and left untracked:
  `scripts/gate.sh` exited 0. G4 ran 137 tests, G5 4 tests, G8 checked 32 citations, G9 checked 1
  lesson, and G11 printed ok.
- In the real worktree, read-only: `tools/check_no_run_output.py` and `tools/check_provenance.py`,
  both ok.
- 37 single-edit mutants of the step (b) code, each followed by the test module that should
  catch it. Bytecode caches were cleared before every run. The table is in section 4.
- Small probe scripts against the scratch copy's `check_file`, `check_commit`, `check_tracked`,
  `check_requirements` and `check_sections`. Throwaway repos for the typechange case.
- `record.sh` in the scratch copy: a fresh handshake and `get-env` recording, a name with a `/`,
  a read-only `runs/`, and two recordings under a fake `date` that pins the timestamp.
- History scan: G11's regexes over `git log -p main..47a6f16`, plus a home-path form that accepts
  any delimiter, the login name, scratch-directory paths and e-mail addresses. Only the tests'
  `example.invalid` identities matched. The env-dump rule matched nothing. No secret, home path or
  run output is committed in the range.
- Checks that hold: every ```json line in the walkthrough equals a `raw` frame of a fresh run (so
  R4 holds). The lesson's Mermaid block equals a fresh `--mermaid` output line for line. A fresh
  `get-env` reply holds exactly `PATH`, `HOME`, `LANG` and `MCP_WIRE_LAB`. Experiment 1's new
  pipeline, run under `bash -eo pipefail` over a trace with every `s2c` record removed, exits 1
  (R7 holds). The control run prints `2024-11-05` and exits 0.

Not done: a macOS run; anything as root (the root half of B16 is argued); CI on GitHub; the
viewer slice.

## 2. Findings

Counts: 0 blocker, 1 major, 7 minor, 10 nit. B16 is CONFIRMED for a normal user and PLAUSIBLE
for root; the other 17 are CONFIRMED.

Dispositions were written on 2026-10-21 by the agent, under the owner's delegation (register row
2026-10-21, fifth of that date; decisions A11 to A18 in `audits/autonomous-decisions.md`). B19
was added then, from the C15 mutation run. Fixed: B1-B8, B10-B16, B18 and B19. Accepted as a
documented limit: B9. Already done after the review: B17. The spec and record parts (B5, B8, B13,
B14, B15) are done in the disposing commit. Section 6 says who builds the rest.

### B1 (major, CONFIRMED). T18 was not implemented, though the C15 row now says its cases are tested

- Location: `tests/test_no_run_output.py:29-40` (`LEAKS`) and `:309-400` (`PrePushHookTest`);
  `validation.md:43` (C15).
- Defect: T18's disposition, approved for step (b), asks for these: a planted sample of every
  secret regex, a three-key env dump, a `PWD` dump, a root-home path, and two hook tests (a leak
  added by modifying a file, and a leak in the first pushed commit). The amended C15 row lists all
  of them, "including `github_pat_`". `LEAKS` still has no `github_pat_` sample. No hook test
  modifies an existing file. `PWD` is planted only in the KEY=VALUE form. No commit message in
  the range mentions T18.
- Reproduction (mutants, section 4): removing the `github_pat_` regex from `SECRETS` leaves all of
  `tests.test_no_run_output` green (G11-pat). So does `--diff-filter=A` in `check_commit`, which
  makes the hook skip modified files (G11-addonly), and dropping `PWD` from the JSON half of
  `ENV_KEY` (G11-pwd-json). The first-pushed-commit case is covered only by accident: dropping
  `--root` is killed by `InstallerTest.test_a_dispatcher_that_chains_to_the_repo_hook_blocks_a_push`,
  whose leak happens to be in a root commit. The three-key and root-home items are covered.
- Why it matters: C15 is the falsifiability claim for standing law 1. A reader of the row
  believes the hook's "modified file" path and every secret regex are pinned, and they are not. A
  regression to `--diff-filter=A` would let a leak that is edited into an existing doc reach the
  public remote, with the suite green.
- Proposed fix: add a `github_pat_` sample to `LEAKS`, assembled from parts like the others. Add a
  three-key JSON dump that includes `PWD`. Add `PrePushHookTest` cases that edit `README.md` to
  hold a token and push, and that push a token in the root commit. Re-run the six T18 mutants and
  record them under C15.
- Disposition: fix (A11; C15 amended by register row 2026-10-21, fifth of that date). Tests
  first, in `tests/test_no_run_output.py`: (a) a `github_pat_` sample in `LEAKS`, assembled from
  parts like the others, named `GitHub fine-grained token`; (b) a JSON environment dump of exactly
  three keys, one of them `PWD`, named as an environment dump; (c) a `PrePushHookTest` case that
  pushes a clean base, then commits an edit that puts a token into the tracked `README.md`, and is
  refused with `README.md` named; (d) a `PrePushHookTest` case that pushes a new branch whose only
  commit is a root commit holding a token, and is refused with the file named and the branch absent
  from the bare remote. Passes when: (a)-(d) pass, and the mutants G11-pat, G11-addonly,
  G11-pwd-json and G11-noroot (section 4) each fail at least one test of the module, G11-noroot
  failing (d) and not only the dispatcher test. The run is recorded under C15.

### B2 (minor, CONFIRMED). `record.sh` now loops forever when the run folder cannot be created

- Location: `scripts/record.sh:21-24` (the `until mkdir ...` loop).
- Defect: the loop treats every `mkdir` failure as "name taken" and tries the next suffix. A
  failure for any other reason never ends. That happens with a missing parent (a name with a
  `/`), a read-only `runs/`, or a full disk. The script also spawns `mkdir` in a busy loop.
- Reproduction (scratch copy): `timeout 5 scripts/record.sh tests/fixtures/handshake-2025.ndjson sub/name`
  gives exit 124 (killed). The `cecc630` version of the script, run the same way, exits 0 and
  records into a nested folder. With `runs/` made read-only, the new script gives exit 124, and
  the old one gives exit 1 with `mkdir: cannot create directory ... Permission denied`.
- Why it matters: this is the learner's main command, and D14 lets them choose the name. Before
  the change, a bad name or folder gave a clear error. Now the terminal hangs, and G5 and G9 only
  stop it at their timeouts (120 s).
- Proposed fix: stop when `mkdir` fails and the folder does not exist, e.g.
  `until mkdir "$dir" 2>/dev/null; do [ -e "$dir" ] || { echo "record: cannot create $dir" >&2; exit 1; }; ...`.
  Optionally reject a name containing `/`. Add a test with a read-only `runs/` or a slash in the
  name.
- Disposition: fix (A13; D14 amended, new row C18). Rule: when `mkdir` of the run folder fails
  and the folder does not exist afterwards, `record.sh` prints one line starting
  `record: cannot create ` on stderr and exits 1; only an existing folder moves on to the next
  suffix. A name holding `/` gets no rule of its own: its missing parent is such a failure, and so
  are a read-only `runs/` and a full disk (those two are not tested). Test first, in
  `tests/test_e2e.py`: `scripts/record.sh tests/fixtures/handshake-2025.ndjson sub/name`. Passes
  when: it exits 1 within 10 s (a subprocess timeout counts as a failure), the last stderr line
  starts `record: cannot create runs/`, no `runs/*-sub` folder exists afterwards, and
  `test_r15_same_name_twice_in_one_second` still passes. Mutant to record under C18: the loop
  without the existence test (the new test times out).

### B3 (minor, CONFIRMED). G11's bare-home rule misses the delimiters a doc or a paste puts after a path; two R10 forms have no disposition

- Location: `tools/check_no_run_output.py:26-28` (`HOME_PATH`), `:29-31` (`ENV_KEY`); the G11 row
  in `tech-stack.md`.
- Defect: the lookahead after the user name accepts only whitespace, a quote or the end of the
  text. A bare home directory followed by a backtick, a colon, a comma or a parenthesis is not
  reported. R10 named six forms. The disposition covers four, and the Windows-style home path and
  JSON with escaped slashes are neither fixed nor recorded as accepted limits. The env rule's
  KEY=VALUE form needs the key at the start of the line, so an indented block or `declare -x`
  output is missed.
- Reproduction (probe script over `check_file`, path `docs/a.md`): each of these is unreported: a
  bare home directory in a Markdown code span, an `/etc/passwd`-style line, one followed by a
  comma, one in parentheses, one followed by `:` (PATH style), the same path with JSON-escaped
  slashes, a Windows home path, a four-line indented KEY=VALUE env block, and three
  `declare -x` lines. The control, the same bare path followed by a space, is caught.
- Why it matters: this repo's docs are Markdown and put paths in backticks. A learner writing
  "your HOME is `...`" is exactly the bare-HOME leak R10 was approved to catch.
- Proposed fix: replace the lookahead with a negative one, `(?![A-Za-z0-9._-])`, which keeps the
  lookalikes in `test_home_lookalikes_pass` passing. Allow leading whitespace and `declare -x ` in
  the KEY=VALUE form. Either add the Windows and escaped-slash forms, or list them as accepted
  limits in the G11 row and standing law 1. Add one test per form.
- Disposition: fix (A12; G11 row amended). New home rule: the regex
  `/(home/[A-Za-z0-9._-]+|Users/[A-Za-z0-9._-]+|root)` not followed by a name character
  `[A-Za-z0-9._-]` (a negative lookahead, so `/` plus more, any delimiter, and the end of the text
  all count). New KEY=VALUE form: optional leading spaces or tabs, then optionally `export` or
  `declare -x` and whitespace, then the key and `=`. Tests first, in `tests/test_no_run_output.py`
  over `check_file("docs/a.md", ...)`, each sample assembled from parts: reported as a
  home-directory path, a bare home directory inside a Markdown code span, followed by `:`, by `,`,
  by `)`, inside parentheses, and as the home field of a passwd-style line; reported as an
  environment dump, three KEY=VALUE lines indented by spaces, the same indented by a tab, and three
  `declare -x` lines. Passes when: those are reported; `test_home_lookalikes_pass` still passes,
  extended with the home prefix followed by `<you>` (a doc placeholder); `test_real_repo_is_clean`
  passes; and the old lookahead restored fails the code-span test. Accepted as documented limits,
  not reported (G11 row and standing law 1): JSON with escaped slashes (no JSON encoder this
  project runs escapes `/`) and a Windows-style home path (the README supports Linux and macOS
  only).

### B4 (minor, CONFIRMED). The pre-push hook does not check a file that becomes a symlink

- Location: `tools/check_no_run_output.py:121-123` (`--diff-filter=AM`).
- Defect: R10 asked G11 to check symlink targets. Gate mode does, because `check_tracked` reads
  every index entry. In hook mode, a regular file replaced by a symlink is a typechange (`T`),
  and the filter drops it.
- Reproduction: in a throwaway repo, commit a file `note`, then replace it with a symlink whose
  target is a path under a home directory, and commit. `git diff-tree` shows status `T`.
  `check_commit` on that commit returns `[]`, and `check_tracked` returns
  `note: contains a home-directory path`.
- Why it matters: the hook is the gate that runs before publication. Gate mode and CI see the
  symlink only after the push.
- Proposed fix: `--diff-filter=AMT`, and a hook test for the typechange.
- Disposition: fix (A11; G11 row and D15 amended). The hook reads `--diff-filter=AMT`: a pushed
  commit's added, modified and type-changed files. Tests first, in `tests/test_no_run_output.py`:
  in `TrackedAndMergeTest`, a committed clean regular file `note` replaced by a symlink whose
  target is a home path and committed, then `check_commit(HEAD)` names `note`; a committed symlink
  to a clean relative target replaced by a regular file holding a token and committed, also named;
  in `PrePushHookTest`, the first case pushed is refused with `note` named. Passes when: those pass
  and the mutant `--diff-filter=AM` fails each of them.

### B5 (minor, CONFIRMED). D15 and the register say the installer writes to `git rev-parse --git-path hooks`; the code never does

- Location: `requirements.md:307-308` (D15); `mission.md:83` (register row 2026-10-21, third of
  that date: "follows `git rev-parse --git-path hooks`"); `audits/rest-review.md:59` (R1);
  `scripts/install-pre-push.sh:7-18`; `audits/autonomous-decisions.md:13` (A4).
- Defect: R1's disposition, D15 and the register row all say the hook is installed in
  `git rev-parse --git-path hooks`. With `core.hooksPath` set, that is the configured (often
  global) directory. The code installs in `$(git rev-parse --git-common-dir)/hooks` and never
  writes to the configured path, by design (A4). A4 is logged only in the autonomy file. The
  delegation row (`mission.md:84`) says a decision that changes a requirement "also gets its own
  register row", and none was added. The installer's header comment ("into a repo's .git/hooks")
  matches the code, not D15.
- Reproduction: read side by side. Running the code: `InstallerTest.test_warns_and_still_writes_the_repo_hook_when_hooks_path_is_elsewhere`
  asserts that the configured directory stays empty, which is the opposite of D15. The mutant
  that installs where D15 says (INST-gitpath) fails 7 tests.
- Why it matters: in this project the records are the specification. A later builder who follows
  D15 rebuilds the dangerous version (see B6). A4's choice is the safer one and should be the
  record.
- Proposed fix: add a register row that amends D15 and the earlier row to A4's behaviour. Reword
  D15 to say the installer writes the repo's own hooks directory (shared by linked worktrees) and
  warns when `core.hooksPath` points elsewhere. Note R1 as implemented differently, by A4.
- Disposition: fix in the records, done in this commit (A15). The code and A4 are right; the
  records follow them. D15 now says the installer writes the repo's own hooks directory
  (`git rev-parse --git-common-dir`, shared by linked worktrees, the same place as
  `--git-path hooks` when `core.hooksPath` is unset), never a directory that `core.hooksPath`
  names, and warns when `core.hooksPath` resolves elsewhere. C15 says the same. The register row
  2026-10-21 (fifth of that date) amends the third row's "follows `git rev-parse --git-path
  hooks`" and records R1 as implemented by A4. No behaviour change; the existing `InstallerTest`
  cases already pin it.

### B6 (minor, CONFIRMED). `PrePushHookTest` runs the installer with the developer's real git configuration

- Location: `tests/test_no_run_output.py:333-338` (`setUp`), `:391-397`.
- Defect: every `git` call in the class uses the isolated env (`GIT_CONFIG_GLOBAL=/dev/null`),
  but the installer subprocess gets no `env`. It therefore reads the developer's global
  `core.hooksPath`, which is set on this machine. So the outcome of `setUp` depends on host
  configuration. With an installer that follows D15 to the letter (B5), the suite itself would
  target the developer's global hooks directory.
- Reproduction: with the INST-gitpath mutant, `PrePushHookTest.test_clean_push_succeeds` fails in
  `setUp` with `install-pre-push: <global hooks dir>/pre-push exists and is different; not
  overwriting it`. It is refused only because that directory already holds a `pre-push`
  dispatcher. I checked afterwards that the directory was unchanged (no G11 body, timestamps from
  the day before). On a machine with a global `core.hooksPath` and no `pre-push` there, the suite
  would install a repo-specific hook globally, and every push in every other repo would then
  fail. With the current installer, the same `setUp` prints the `core.hooksPath` warning on this
  machine.
- Proposed fix: pass `env=self.env` to both installer calls in `PrePushHookTest`, as
  `InstallerTest.install` already does.
- Disposition: fix, test code only (A11). Both installer calls in `PrePushHookTest` get
  `env=self.env`. Test first: `setUp` asserts that the installer's stderr is empty. Passes when: on
  a host whose global git configuration sets `core.hooksPath` (this machine), that assertion fails
  before the change (the installer prints its `core.hooksPath` warning) and passes after it, and
  no test in the module runs a subprocess with the host's git configuration. INST-gitpath is still
  killed by `InstallerTest`.

### B7 (minor, CONFIRMED). C16 allows three variables that node does not add, so an allowlist that leaks them passes

- Location: `tests/test_e2e.py:19-21` (`NODE_ADDS = {"PWD", "SHLVL", "_"}`), `:94-95`;
  `validation.md:44` (C16), `:166-170`.
- Defect: T14's disposition says "the variable names equal the allowlist plus what node adds". A7
  guessed `PWD`, `SHLVL` and `_`. These are shell variables, and the server is started by
  `env -i ... node` with no shell in between. A fresh `get-env` reply holds exactly `PATH`, `HOME`,
  `LANG` and `MCP_WIRE_LAB`, so node adds nothing.
- Reproduction: mutant REC-shlvl appends `SHLVL=1 _=/usr/bin/env PWD=/` to the `env -i` list in
  `record.sh`, and `tests.test_e2e` stays green. Adding `USER=x` (REC-user) is killed, as
  expected.
- Why it matters: `PWD` and `_` carry the caller's directory and command path, which the minimal
  environment (D14) exists to keep out of shared traces. They are caught today only when that
  path happens to contain the parent's `HOME`.
- Proposed fix: assert `set(variables) == ALLOWLIST`. If a platform is later measured to add a
  variable, name it in D14 with the measurement. Update C16's Result line.
- Disposition: fix (A16; D14 and C16 amended). Node adds no variable (measured by the reviewer
  and stated in D14). Test first: `test_c16_minimal_environment` asserts
  `set(variables) == ALLOWLIST`, and `NODE_ADDS` is removed. Passes when: the test passes on the
  current `record.sh`, the mutant REC-shlvl (section 4) fails it, and REC-user still fails it. If
  a platform is later measured to add a variable, D14 names it with the measurement.

### B8 (minor, CONFIRMED). Some constitution edits on the branch are named by no register row, and B5 now fails as written

- Location: `specs/tech-stack.md:13,30,28-37,46-47`; `mission.md:83`; `validation.md:75` (B5).
- Defect: `git diff main 47a6f16 -- specs/tech-stack.md` shows edits to the SDK client row and G3
  (phase 4 to 5), G1, G7, G8, G11, and the `audits/` convention line (in this range, `72177a5`).
  The covering row (2026-10-21, third) names only G1, G7, G8, G9 and G11. The SDK row, G3 and the
  conventions line are named by no row, although R16's own disposition said the tech-stack lines
  go "by register row". The same row says G9 was amended, but the G9 row is unchanged from
  `main`. B5's pass condition ("shows only appended register rows and proposal status changes")
  is now false.
- Reproduction: the diff command above, read against `mission.md:83`.
- Why it matters: `mission.md:15` allows a requirement only by an ask, a constitution clause or a
  dated register row. B5 is a phase-close boundary check, and as written it now fails.
- Proposed fix: add a register row that names the SDK, G3 and conventions edits, and either amend
  the G9 row (order, fences, `-eo pipefail`) or correct the row's list. Amend B5 to "only appended
  register rows, proposal status changes, and edits each named by a register row".
- Disposition: fix in the records, done in this commit (A11). The register row 2026-10-21
  (fifth of that date) names the SDK client row and G3 (phase 4 to 5), the `audits/` conventions
  line, and every tech-stack edit of this commit. The G9 row is amended now (headings outside
  fences and in order, `bash -eo pipefail`, the fence rule of B10), so the third row's claim that G9
  was amended holds. Boundary check B5 now reads "only appended register rows, proposal status
  changes, and edits each named by a register row". No code.

### B9 (nit, CONFIRMED). G1 still resolves negated Sources that mention `mission.md`, a register row or a constitution file

- Location: `tools/check_provenance.py:53-58`; the G1 row in `tech-stack.md`.
- Defect: R9's phrase match closes only the "registered" and "unregistered" wording. The bare
  substring `mission.md`, any constitution file name, and the phrase `register row` all still
  resolve a Source whatever the words around them say. The G1 row says a register row must be
  "written as `register row` or `registered in mission.md`". The code also accepts any mention of
  `mission.md`.
- Reproduction (probe script over `check_requirements`): "agent idea, not yet registered,
  2026-10-20." fails, as intended. These four pass: "agent idea, not yet in mission.md,
  2026-10-20.", "agent idea, not yet registered in mission.md, 2026-10-20.", "agent idea; no
  register row yet, 2026-10-20." and "agent idea; contradicts tech-stack.md, 2026-10-20.".
- Proposed fix: require a positive reference: `register row YYYY-MM-DD`, an `A<n>`, or
  `constitution clause — <file>`. Drop the bare-substring checks. Add the four Sources above as
  failing tests.
- Disposition: accepted as a documented limit (A17). G1 checks that a reference is present, not
  what the sentence says about it; every Source is written by the agent and read at review, and a
  positive-reference grammar would rewrite every Source for a case no one has hit. The G1 row now
  states the forms the code accepts (an `A<n>`, `register row` or `registered in mission.md`, or
  any mention of `mission.md`, `roadmap.md` or `tech-stack.md`) and this limit. Reversible: the
  reviewer's positive-reference fix, with the four Sources above as failing tests. No code.

### B10 (nit, CONFIRMED). G9 strips only three-backtick fences

- Location: `tools/check_lessons.py:42` (`FENCE`).
- Defect: CommonMark fences can also be tildes, or longer runs of backticks. Headings inside those
  still count as sections.
- Reproduction (probe over `check_sections`): the seven headings inside a ```` ```markdown ````
  fence give 7 errors (control). Inside a `~~~` fence, or a four-backtick fence holding a ```
  line, they give 0.
- Proposed fix: match an opening fence of three or more backticks or tildes, and close it on the
  same character with at least as many. Add a tilde test.
- Disposition: fix (A11; G9 row and D13 amended). Fence rule (CommonMark): a line that starts
  with three or more backticks or three or more tildes opens a fence (an info string may follow);
  only a line of the same character, at least as long, with nothing after it but spaces or tabs,
  closes it; a fence with no closing line runs to the end of the file. Tests first, in
  `tests/test_lessons.py`: the seven headings inside a `~~~markdown` fence are reported missing;
  inside a four-backtick fence that holds a three-backtick line, missing; a `~~~` fence is not
  closed by a three-backtick line; headings after an unclosed fence are missing. Passes when: those
  pass, the existing fence tests still pass, and G9 passes on lesson 01.

### B11 (nit, CONFIRMED). The lesson's run-folder glob misses the new numeric suffix

- Location: `docs/lessons/01-the-wire-and-the-handshake.md:45,81,120,142,163`
  (`ls -d runs/*-<name> | tail -1`); `scripts/record.sh:21-24`.
- Defect: after R15, a second recording in the same second goes to `runs/<ts>-<name>-2`, which
  `runs/*-<name>` does not match. The lesson then reads the older trace.
- Reproduction (scratch copy, fake `date` printing a fixed future timestamp): record the
  handshake as `lesson01`, then `exp-old-version` as `lesson01`. `record.sh` reports
  `runs/<ts>-lesson01-2`, and the lesson's command selects `runs/<ts>-lesson01`.
- Proposed fix: take the folder from `record.sh`'s own `recorded:` line, or glob
  `runs/*-<name> runs/*-<name>-[0-9]*` and sort by modification time.
- Disposition: fix (A11; D12 amended, new row C18). A lesson block that records takes its run
  folder from the `recorded:` line of that `scripts/record.sh` call; a block that reads an earlier
  recording takes the newest folder by modification time among `runs/*-<name>*`; no lesson command
  picks a folder by name order (`ls -d ... | tail -1`). Tests first, in a new
  `tests/test_lesson_01.py` over the lesson text: no line holds `| tail -1` after `ls -d runs/`;
  every `run=` line in a runnable block that calls `scripts/record.sh` contains `recorded:`; every
  other `run=` line, with `<name>` taken from it, run under `bash -eo pipefail -c` in a temporary
  directory holding `runs/19990101T000000Z-<name>` and a newer `runs/19990101T000000Z-<name>-2`,
  sets `run` to the `-2` folder. Passes when: those pass and G9 passes on the lesson.

### B12 (nit, CONFIRMED). Lesson 01 keeps two statements that step (b) corrected elsewhere

- Location: `docs/lessons/01-the-wire-and-the-handshake.md:103-104`, `:185`.
- Defect: line 103 says the SDK is something "this repository does not pin". The walkthrough now
  says, per R14, that the SDK is fixed by the server's lockfile (2.3.1) and only not citable.
  Check-yourself question 5 asks which experiment "proved the spec's words are stronger than the
  server's behaviour", but its answer, rewritten for R13, now says the rules bind the client and
  the server's leniency is allowed.
- Reproduction: read the lesson lines beside walkthrough lines 16-21 and answer 5.
- Proposed fix: "lives in the SDK, which the server's lockfile fixes but which is not a submodule,
  so it is not cited". For question 5: "In experiments 2 and 3, whose duty was the rule the
  server did not enforce?".
- Disposition: fix, lesson text only (A11). Line 103 becomes "lives in the SDK, which the
  server's lockfile fixes at 2.3.1 but which is not a submodule here, so it is not cited".
  Question 5 becomes "In experiments 2 and 3, whose duty was the rule the server did not
  enforce?", and its answer says the client's, with the server's leniency allowed (M8). No
  behaviour change and no new test. Passes when: G8 and G9 pass and the two lines agree with the
  walkthrough and M8 when read side by side.

### B13 (nit, CONFIRMED). Two accepted limits are not written where their dispositions say

- Location: `specs/tech-stack.md` (R21); `tools/check_citations.py:1`, the G8 row, D13 (R12).
- Defect: R21 was "accepted as a documented limit ... noted in tech-stack", and tech-stack says
  nothing about action tags or uv floating. R12's pin check was "accepted as a limit (bootstrap
  owns the pins)", but nothing records it. The G8 row and the tool's docstring still promise
  resolution "in the pinned submodule", which a local run checks only after bootstrap.
- Reproduction: `grep -n -i "float\|major tag\|setup-uv" specs/tech-stack.md` and a search for
  the pin limit in `specs/` and the tool find nothing.
- Proposed fix: one sentence each, in tech-stack's CI row and in D13's cost accepted (or the G8
  row).
- Disposition: fix in the records, done in this commit (A11). The tech-stack CI row says the
  action major tags and the `uv` CI installs float (R21, accepted). The G8 row and D13's cost
  accepted say G8 checks the submodule as checked out, and that `scripts/bootstrap.sh`, not G8,
  checks the pin (R12, accepted). Left for the build: `tools/check_citations.py`'s docstring
  "resolves in the pinned submodule" becomes "resolves in the checked-out submodule (bootstrap
  checks the pin)". Comment only, no test.

### B14 (nit, CONFIRMED). Decision records amended in step (b) do not say so, and D7 still describes the old G1

- Location: `requirements.md` D5, D7, D8, D11, D13, D14, D15 (`*Source:*` lines); D7 at `:142-146`.
- Defect: D1 to D4 name their amending register row in the Source line. D5, D7, D8, D11, D13, D14
  and D15 were amended (`git diff e5effb6~1 47a6f16`), and their Sources are unchanged. D7 still
  says G1 reads "every `### D<n>` record" and that a "Result says closed". G1 now reads `##` to
  `####` headings and a `Status: open|closed` line.
- Proposed fix: append "amended by register row 2026-10-21 (findings ...)" to each Source, and
  bring D7 in line with the G1 and G7 rows.
- Disposition: fix in the records, done in this commit (A11). Not accepted as a limit: D7
  describing a G1 that no longer exists is a wrong record, and the fix is text only. D7 now
  describes G1 and G7 as the tech-stack rows and the code have them (`##` to `####` D headings,
  the Source paragraph, one `Status: open|closed` line in the Result). The Sources of D5, D7, D8,
  D11, D12, D13, D14 and D15 name their amending register rows. No code.

### B15 (nit, CONFIRMED). The autonomy log claims records that do not exist

- Location: `audits/autonomous-decisions.md:11-12` (A2, A3); `mission.md:84`.
- Defect: A3 says R17 is "recorded as 'agent-proposed, owner to confirm'". `validation.md`'s J2
  row and `audits/learner-walk-lesson-01.md` hold no such text. A2 reads "MIT (pending, see
  below)", but nothing follows it and there is no `LICENSE`. The delegation row says R17 and R18
  are "resolved provisionally (A2, A3)". `rest-review.md` still has both as "open, owner", which
  is the accurate state.
- Reproduction: `grep -rn -i "agent-proposed\|owner to confirm" specs audits` matches only A3
  itself, and `git ls-files | grep -i licen` is empty.
- Proposed fix: write the J2 note in the row and add `LICENSE`, or reword A2, A3 and the register
  row to "not done; open for the owner". The licence faces outward, so the owner should see it
  before it is published.
- Disposition: fix in the records, done in this commit (A18). A2 and A3 now say that their
  records do not exist yet. The register row 2026-10-21 (fifth of that date) corrects the
  delegation row: R17 and R18 are decided by the agent but not yet written. The close-out step
  writes all three before the phase-close merge: a `LICENSE` file (MIT); the J2 note in
  `validation.md` ("agent-proposed, owner to confirm"); and the acceptance of learner-walk items 3
  and 7 in `audits/learner-walk-lesson-01.md`. The owner sees them in the end review, before
  `main`.

### B16 (nit, CONFIRMED as a normal user, PLAUSIBLE as root). The installer run on a directory that is not a repo tries to create `/hooks`

- Location: `scripts/install-pre-push.sh:9`.
- Defect: inside the command substitution, the failure of `git rev-parse --git-common-dir` does
  not stop `mkdir -p "$(...)/hooks"`, so it runs with an empty prefix.
- Reproduction: `scripts/install-pre-push.sh <empty dir>` prints `fatal: not a git repository`,
  then `mkdir: cannot create directory '/hooks': Permission denied`, and exits 1. As root, which
  is common in containers, I expect `mkdir` to succeed and the hook to be written to
  `/hooks/pre-push` with exit 0 (argued, not run). `bootstrap.sh` cannot reach this path because
  its pin checks fail first.
- Proposed fix: compute `common="$(git -C "$repo" rev-parse --git-common-dir)"` in its own
  assignment so that `set -e` stops the script, then build `own` from it.
- Disposition: fix (A11). `install-pre-push.sh` sets the common directory in an assignment of its
  own (`common="$(git -C "$repo" rev-parse --git-common-dir)"`) so that `set -e` stops the script,
  then builds the hooks path from it. Test first, in `InstallerTest`: the installer run on an
  empty temporary directory outside any repo (`GIT_CEILING_DIRECTORIES` set to its parent). Passes
  when: it exits non-zero, its stderr holds `not a git repository` and no `mkdir`, and the
  directory stays empty. The current code fails the `mkdir` part.

### B17 (nit, CONFIRMED). Step (b)'s new gate clauses have no recorded mutation run

- Location: `validation.md:132-212` ("Checks seen to fail").
- Defect: step (a) recorded the mutants of its new clauses. Step (b) extended C8, C9, C11, C12 and
  C15 and recorded nothing for them. Only C16's extension is recorded, and it notes that the T14
  mutants were not re-run. Section E is formally met, because each row still has its original
  mutation. Section 4 below supplies the missing run: 32 of 37 killed. Besides B1 and B7, one more
  survives. Bounding `Status:` to the Result section is unpinned: searching from `## Result` to
  the end of the file (PRO-status-whole) passes, because no test puts a `Status:` line in a later
  `##` section.
- Proposed fix: record section 4's run, or one of your own, in the Result, and add a test with a
  `Status:` line in a section after Result.
- Disposition: done after this review, by `ddb0611` (the C8, C11 and C12 step (b) mutation record,
  and `test_status_in_a_later_section_is_ignored`, which kills PRO-status-whole) and `e4536cc`
  (C15's G11 run). What is left belongs to other findings: the T18 mutants (B1) and the mutants of
  B2-B4, B7, B10, B16 and B19 are run and recorded under C12, C15, C16 and C18 after the build.

### B18 (nit, CONFIRMED). The guard against committing agent worktrees is local only

- Location: `.gitignore`; `audits/autonomous-decisions.md:17` (A8).
- Defect: `b8ca145` pushed three `.claude/worktrees/agent-*` gitlinks, and `aa7d27b` removed them.
  A8 says `.claude/worktrees/` "is now excluded locally". That means `.git/info/exclude`, which no
  other clone inherits. `.gitignore` holds only `node_modules/`, `__pycache__/`, `*.pyc` and
  `runs/`.
- Reproduction: read `.gitignore` at `47a6f16`.
- Proposed fix: add `.claude/worktrees/` to `.gitignore`.
- Disposition: fix (A11). Add `.claude/worktrees/` to `.gitignore`; A8 now points to it.
  Passes when: `git check-ignore -q .claude/worktrees/agent-x/file` exits 0 at the repo root and
  G11 passes.

### B19 (minor, CONFIRMED; added when disposing, from the C15 mutation run). Gate mode does not read a working-tree entry that replaced or retargets a tracked symlink

Not found by this review. The C15 mutation run of `e4536cc` left it as "survived, open" (I6). It
is recorded here so that it has a disposition.

- Location: `tools/check_no_run_output.py:107-111` (`check_tracked`: `mode != "120000" and
  path.is_file() and not path.is_symlink()`); `validation.md`, Result, the C15 paragraph on the G11
  fixes of step (b) ("Survived, open: dropping `mode != "120000"` in gate mode").
- Defect: G11 says gate mode reads every tracked file "from the index as well as the working
  tree". For an index entry with mode `120000` (a tracked symlink), `check_tracked` reads only the
  index blob. A working-tree regular file that replaced the symlink is never read, and neither is
  a working-tree symlink whose target was changed but not staged. For a tracked regular file
  replaced by a working-tree symlink, nothing of the working tree is read either: not following the
  link is right (`test_working_tree_symlink_content_is_not_read`), but its target path, which git
  would store, is skipped too.
- Reproduction (from the C15 record): a probe found a token in a working-tree regular file that
  replaced a tracked symlink, and a tracked link retargeted at a home path but not staged.
  `check_tracked` returned `[]` for both.
- Why it matters: gate mode runs before a commit is made, so it is the earliest check. The
  pre-push hook still reads the committed blob, so a commit made from either state is stopped at
  push. The gap is in the early warning, not in the last gate.
- Proposed fix: read the working-tree entry whenever it differs from the index entry, whatever
  either one's type. A working-tree symlink is read as its target path (`os.readlink`, as bytes),
  never followed. A working-tree regular file is read as its content.
- Disposition: fix (A14; G11 row amended). Tests first, in `TrackedAndMergeTest`: (a) a committed
  symlink to a clean relative target, replaced in the working tree (not staged) by a regular file
  holding a token: `check_tracked` names it; (b) the same committed symlink retargeted in the
  working tree (not staged) at a home path: named as a home-directory path; (c) a committed clean
  regular file replaced in the working tree by a symlink whose target is a home path: named.
  Passes when: (a)-(c) pass, `test_working_tree_symlink_content_is_not_read` still passes (its link
  target must not itself lie under a home directory), every other test of the module passes, and
  the C15 mutant left open (dropping the mode test) is re-run against the new code and recorded as
  killed or signed equivalent.

## 3. Disposition status for the step (b) items

| Finding | Disposition says | At `47a6f16` |
| --- | --- | --- |
| R1 | install in `--git-path hooks`, warn, test with `core.hooksPath` | implemented differently (A4): repo's own hooks dir, warns, tested; records not amended (B5, B6) |
| R2 | hook reads files a merge adds | done (`-m`, deduped); killed by 3 tests |
| R3 | trace shape by content, any name or case | done |
| R4 | D8 says unchecked; `ping` example fixed | done; all three examples equal fresh frames |
| R5 | unchecked list in the Result | done; line numbers hold at `47a6f16` |
| R6, S16 | "largest frame after the tool list" | done |
| R7 | `-eo pipefail`; experiment 1 selects `s2c` | done; the stripped-trace run exits 1 |
| R8 | one `Status: open\|closed` field | done (Result bound unpinned, B17) |
| R9 | phrases only | done as worded; negations still pass (B9) |
| R10 | four text-rule changes, symlinks | partly: bare-home misses common delimiters (B3); hook misses typechange (B4) |
| R11 | gate reads index and working tree | done |
| R12, T15 | containment, 6-character fragment, undecodable doc; pin as limit | done; the limit is not written (B13) |
| R13 | answer 5, M8, line 132 | done; question 5 still frames it the old way (B12) |
| R14 | SDK fixed by lockfile; cite `index.ts:134` | done in the walkthrough; lesson line 103 not (B12) |
| R15, T17, S17 | numeric suffix | done; new hang (B2), glob misses suffix (B11) |
| R16 | each listed line | done, except constitution edits without a register row (B8) |
| R19, S11 | three wordings | done |
| R20 | strip fences, require order | done for three-backtick fences (B10) |
| R21 | accepted, noted in tech-stack | not noted (B13) |
| R22 | README platform line | done |
| S9 | D11 cost sentence | done |
| T14 | reply by id; names equal the allowlist plus node's | done; node's set is a guess that admits 3 variables (B7) |
| T18 | plant every regex, PWD, root home, two hook tests | not done (B1) |
| T19 | `main` on empty root and a sleeping block | done; both mutants killed |
| R17, R18 | open, owner | open; the autonomy log overstates them (B15) |

## 4. Mutations run

Each mutant is one exact text replacement in the scratch copy, followed by the named test module,
with caches cleared. Killed means at least one test failed for the reason the mutant breaks.

| Id | Mutation | Module | Result |
| --- | --- | --- | --- |
| G11-pat | `github_pat_` regex removed | test_no_run_output | **survived** (B1) |
| G11-addonly | hook `--diff-filter=A` | test_no_run_output | **survived** (B1) |
| G11-pwd-json | `PWD` dropped from the JSON env keys | test_no_run_output | **survived** (B1) |
| G11-noroot | `--root` dropped | test_no_run_output | killed (dispatcher test, by accident) |
| G11-thresh4 | env threshold 3 to 4 | test_no_run_output | killed |
| G11-no-m | `-m` dropped | test_no_run_output | killed (3) |
| G11-skip-symlink-commit | hook skips mode 120000 | test_no_run_output | killed |
| G11-tree-only | gate ignores the index blob | test_no_run_output | killed (3) |
| G11-index-only | gate ignores the working tree | test_no_run_output | killed |
| G11-tns-only-jsonl | shape only for `.jsonl` | test_no_run_output | killed |
| G11-case | `.jsonl` case-sensitive | test_no_run_output | killed |
| G11-export | `export` prefix not accepted | test_no_run_output | killed |
| G11-strict-utf8 | undecodable file skipped again | test_no_run_output | killed |
| G11-nodedupe | merge findings not deduped | test_no_run_output | killed |
| G11-bare-ws-only | bare home only before whitespace | test_no_run_output | killed |
| G11-root-alt | root-home alternative removed | test_no_run_output | killed |
| INST-gitpath | install in `--git-path hooks` (D15's letter) | test_no_run_output | killed (7; see B6) |
| INST-nowarn | never warn | test_no_run_output | killed |
| INST-gitdir | `--git-dir` instead of `--git-common-dir` | test_no_run_output | killed |
| REC-nosuffix | `record.sh` back to `mkdir -p`, no suffix | test_e2e | killed |
| REC-shlvl | `SHLVL`, `_`, `PWD` added to `env -i` | test_e2e | **survived** (B7) |
| REC-user | `USER` added to `env -i` | test_e2e | killed |
| LES-no-e | `-o pipefail` without `-e` | test_lessons | killed |
| LES-no-pipefail | `-e` without `pipefail` | test_lessons | killed |
| LES-nofence | fences not stripped | test_lessons | killed |
| LES-noorder | order not checked | test_lessons | killed |
| LES-min0 | default `--min-lessons 0` | test_lessons | killed |
| LES-timeout-pass | timed-out block passes | test_lessons | killed |
| PRO-register | back to `"register" in source` | test_provenance | killed |
| PRO-depth | back to `###` only | test_provenance | killed |
| PRO-status-any | any non-empty status accepted | test_provenance | killed (2) |
| PRO-status-whole | `Status:` searched to end of file | test_provenance | **survived** (B17) |
| CIT-contain | containment check removed | test_citations | killed |
| CIT-min5 | minimum fragment 5 | test_citations | killed |
| CIT-min7 | minimum fragment 7 | test_citations | killed |
| CIT-nopop | phantom last line kept | test_citations | killed |
| CIT-undecodable | undecodable doc skipped silently | test_citations | killed |

37 run, 32 killed, 5 survived: G11-pat, G11-addonly, G11-pwd-json, REC-shlvl and
PRO-status-whole. G11-noroot counts as killed, but only incidentally (B1).

## 5. Summary

The gate is green at `47a6f16`. Most step (b) dispositions are implemented, and their tests are
falsifiable: 32 of 37 mutants are killed, including every new G9, G8 and G7 clause, and R2, R3
and R11 in G11. Nothing secret, no home path and no run output was committed in the range.

What is not right:

- T18 was dropped. The C15 row says its cases are tested, and three of its mutants survive (B1).
- R15's fix brings a hang for any `mkdir` failure (B2).
- R10's bare-home rule misses the Markdown code span, the most likely form in this repo (B3).
  The hook misses a file turned into a symlink (B4).
- The installer is safer than D15 and the register say, but the records were not amended (B5).
  One test class reads the developer's global git configuration, which would make a D15-literal
  installer target the global hooks directory (B6).
- The rest are record drift and small gaps (B7 to B18).

Fix before the phase-close merge: B1, B2, B5 and B6.

## 6. Implementation partition

The code and test work left by the dispositions, split into three groups that share no file, so
three Sonnet agents (medium effort) can build them in parallel, each in its own worktree. No agent
edits `specs/` or `audits/`. Each agent reports its failing-first output and its mutation results
in its handback. After the merge, the orchestrator writes them into the `validation.md` Result
(C12, C15, C16, C18) and runs `scripts/gate.sh` once on the merged tree.

| Group | Findings | Files (only these) |
| --- | --- | --- |
| 1. G11 and the installer | B1, B3, B4, B6, B16, B19 | `tools/check_no_run_output.py`, `tests/test_no_run_output.py`, `scripts/install-pre-push.sh` |
| 2. Recording, e2e and lesson 01 | B2, B7, B11, B12 | `scripts/record.sh`, `tests/test_e2e.py`, `tests/test_lesson_01.py` (new), `docs/lessons/01-the-wire-and-the-handshake.md` |
| 3. Gate tools and ignore file | B10, B13 (docstring), B18 | `tools/check_lessons.py`, `tests/test_lessons.py`, `tools/check_citations.py` (docstring only), `.gitignore` |

Nothing left to build: B5, B8, B9, B14, B15 and B17 (spec and records, or already done). The
close-out step writes B15's three records (`LICENSE`, the J2 note, the learner-walk acceptance).

Rules for every group:

- Test first. For each finding, write the tests its Disposition names, run them, and see each one
  fail for the reason the finding gives, not by a crash in the test harness. Keep the failing
  output for the handback. Then change the code until they pass. B6, B7, B12 and B13 have no code
  change, or only a test or comment change: for B6 and B7, show the new assertion failing on the
  old test code (B6 on this machine, whose global configuration sets `core.hooksPath`) or on the
  named mutant (B7).
- Then run the mutants the Disposition names, one at a time, in place, with
  `PYTHONDONTWRITEBYTECODE=1` and no `__pycache__`. Run the whole test module, restore the file,
  and check that `git diff` is empty. Report each mutant as killed (and by which test), survived or
  signed equivalent (with the reason).
- The Disposition's "Passes when" is the contract. If it cannot be met as written, stop and report
  the mismatch. Do not edit the spec.
- Before handing back, run `scripts/gate.sh` and see it green. G5 records against the built
  server and is the heavy step: this machine has 4 CPUs, so run the groups' G5 one at a time.
  Group 2 needs `vendor/servers` built in its worktree (`scripts/bootstrap.sh`) or linked from the
  main checkout and left untracked.
- Commit only the files of your group. The message ends with the attribution trailer.
