# Tech stack

Locked choices. Changing a row means editing this document first, with a reason and a
dated register row in `mission.md`.

| Area | Choice | Source |
| --- | --- | --- |
| Server under study | `vendor/servers` — git submodule of `modelcontextprotocol/servers` at `51b6382a3e827aceb6bce430b1208d69b93d95ea` (everything server v2.0.0); built from its own lockfile; never modified | Register 2026-10-20 (server source) |
| Spec and schemas | `vendor/spec` — git submodule of `modelcontextprotocol/modelcontextprotocol` at `1155ca460e5097019f32769b38dcba194432e2fb`; never modified | P7 |
| Node | 24.22.0 | P2 (ratified 2026-10-20) |
| Python | 3.12 (stdlib only for runtime code) | Register 2026-10-20 (client language); P4 |
| Raw client | Python, no MCP library | Register 2026-10-20 (two clients; client language) |
| SDK client | TypeScript, `@modelcontextprotocol/client` 2.3.1 exact; test tool chosen in the phase 5 spec | Register 2026-10-20 (client language); P1 |
| Wire tap | Python, stdlib only | P4, P5 |
| Python lint | ruff 0.17.1, run via `uvx ruff@0.17.1` | P6 |
| Python typecheck | mypy 2.4.0 `--strict`, run via `uvx mypy@2.4.0` | P6 |
| Python tests | `unittest` (stdlib) | P4 |
| CI | GitHub Actions on `mtahamasood/mcp-wire-lab`, Ubuntu, Node 24, Python 3.12, submodules checked out. Accepted limit (R21): the actions are pinned by major tag, and the `uv` and Python patch versions CI installs float; CI prints the versions it used | Register 2026-10-20 (repo); register row 2026-10-21 (third and fourth of that date) |

## Quality gates

Every phase inherits these. One entry point, `scripts/gate.sh`, runs the automated ones in
order and fails on the first failure; CI runs exactly that script. Source: the SDD field
guide §3 (adopted by register row 2026-10-20, SDD).

| Gate | What | Kind |
| --- | --- | --- |
| G1 | Provenance lint: every decision record in `specs/phases/*/requirements.md` (any `##`-`####` D heading) has a `*Source:*` paragraph whose dates are all register row dates and that resolves to an ask (an `A<n>` that exists), a register row (written as `register row` or `registered in mission.md`), or a constitution file (any mention of `mission.md`, `roadmap.md` or `tech-stack.md`); a D heading without a Source fails. Accepted limit (B9): G1 matches words, not meaning, so a Source that negates its reference still resolves | check |
| G2 | Lint (ruff) | check |
| G3 | Typecheck (mypy `--strict`; `tsc --strict` from phase 5) | check |
| G4 | Unit tests | check |
| G5 | End-to-end: the phase's flows against the real, pinned, built server | check |
| G6 | Clean-clone walk: fresh `git clone --recurse-submodules` in a new directory, bootstrap, `scripts/gate.sh` | measurement, per phase |
| G7 | `CHANGELOG.md` has an entry for the phase once a phase's Result has the line `Status: closed` (any value other than open or closed fails) | check (G1 script) |
| G8 | Citations: every `` `<submodule>:<path>:<line>` "fragment" `` in `docs/`, `tap/`, and the clients resolves in the submodule as checked out (the path stays inside it) and a fragment of at least 6 characters is on that line (L2, L3, L13). The pin itself is checked by `scripts/bootstrap.sh`, not by G8 (accepted limit, R12) | check |
| G9 | Lessons: every lesson has the L1 sections, as headings outside fenced blocks and in order (a fence opens on a line of three or more backticks or tildes and closes only on a line of the same character, at least as long; an unclosed fence runs to the end of the file); every block marked runnable exits 0 under `bash -eo pipefail -c` and its expected-output block appears in its output (L1, L4) | check |
| G10 | Atlas: regenerating `docs/atlas.md` from the pinned schemas and the lessons' declared methods produces the committed file (L8; from phase 2) | check |
| G11 | No run output in git: no tracked file under `runs/`; every tracked trace-shaped file (a text file, whatever its name or case, whose JSON lines carry `seq`, `dir` and `t_ns`, or `*.jsonl` whose records carry `seq` and `dir`) is under `tests/fixtures/` and opens with a `{"dir":"tap","event":"synthetic"}` record; no tracked text file (read from the index and, where it differs, from the working tree, whatever either entry's type; undecodable bytes replaced; a symlink, in the index or the working tree, read as its target path and never followed) contains an environment dump (a JSON object, or three or more `KEY=VALUE` lines, each optionally indented and prefixed by `export` or `declare -x`, with three or more of `PATH`, `HOME`, `USER`, `SHELL`, `PWD`), a home-directory path (regex `/(home/[A-Za-z0-9._-]+|Users/[A-Za-z0-9._-]+|root)` not followed by a name character `[A-Za-z0-9._-]`), or a secret (regexes `gh[opsu]_[A-Za-z0-9]{30,}`, `github_pat_[A-Za-z0-9_]{30,}`, `sk-[A-Za-z0-9_-]{20,}`, `AKIA[0-9A-Z]{16}`, `xox[abprs]-[A-Za-z0-9-]{10,}`, `-----BEGIN [A-Z ]*PRIVATE KEY-----`). The patterns are written so this row does not match itself. Runs in `scripts/gate.sh`, in CI, and as a pre-push hook that `scripts/bootstrap.sh` installs in the repo's own hooks directory, which reads every file a pushed commit adds, modifies or changes the type of, and the files a merge commit adds against each parent. Accepted limits (B3): JSON with escaped slashes and a Windows-style home path are not recognized | check |

G8–G10 come from the learning-feature catalogue in `roadmap.md` (register row 2026-10-20, A4);
G11 from A5 (register row 2026-10-20, run output never committed).

## Standing conventions

- Specs live in `specs/`; phase specs in `specs/phases/NN-<name>/{requirements,plan,validation}.md`.
- Review corpora live in `audits/<lens>-review.md`; a learner walk's findings list in
  `audits/learner-walk-lesson-NN.md`.
- Runs are recorded by `scripts/record.sh` into `runs/` (git-ignored, never committed).
  Walkthroughs live in `docs/walkthrough/`, lessons in `docs/lessons/`, hand-written
  synthetic trace fixtures in `tests/fixtures/`.
- Citation form: `` `servers:src/everything/transports/stdio.ts:49` "serveStdio(" `` or
  `` `spec:docs/specification/2025-11-25/basic/lifecycle.mdx:57` "\"method\": \"initialize\"" ``.
  The submodule name is `servers` or `spec`. The fragment is short, verbatim, and on the
  cited line. (Incident, 2026-10-20: the agent first wrote both examples from memory with
  the wrong line numbers, 47 and 12; measured against the pins, they are 49 and 57. This is
  the case G8 exists for.)
- A runnable lesson block is a ` ```console ` block preceded by `<!-- run -->`; an expected
  block is a ` ```text ` block preceded by `<!-- expect -->` right after it.
- Work for a phase happens on branch `phase-NN-<name>`, merged to `main` with CI green.

## Standing laws

Laws are added only in response to named incidents, with their enforcement attached.

1. **Run output is never committed** (2026-10-20). Incident: the phase 1 draft planned to
   commit traces, and a side agent found the server's `get-env` tool returns its whole
   process environment; the owner then ruled that nothing a run produces belongs in git
   (A5). Enforcement: G11 in `scripts/gate.sh`, in CI, and as the pre-push hook — the hook
   matters because on a public repo CI runs after the data is already published.
   Admitted limit: G11 recognizes run output by shape and pattern; a pasted fragment that
   matches none of them passes (for example a home path written with JSON-escaped slashes, or
   a Windows-style one), so authored examples must also contain no environment-specific
   values (P9).
