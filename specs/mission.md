# Mission

**mcp-wire-lab** is a public learning laboratory for the Model Context Protocol: for its
owner, a protocol-implementation engineer, and for anyone who wants to understand MCP in
depth, from first principles — the messages on the wire, the order they flow in, the
normative schema that defines them, and the code on both sides that produces them. Its
measure of success is learning value: a reader who follows it can predict, read, and
explain every message, and can check that claim against the running system. Lessons
assume the reader knows JSON, a terminal, and how to read Python or TypeScript, and
nothing about JSON-RPC 2.0 or MCP.

## Stakeholder asks

The owner's asks, verbatim (typos kept). Every requirement in this repository traces to
one of these, a constitution clause, or a dated register row below.

| Id | Date | Ask |
| --- | --- | --- |
| A1 | 2026-10-20 | "I want to understand and experiment with the MCP protocol. I have partially completed the MCP course on anthropc academy and now wanted to explore prorgrammatically. This is the example on the official page that I want to explore https://github.com/modelcontextprotocol/servers/tree/main/src/everything . I want to understand the source ,MCP and make sample client as well to understand in depth." |
| A2 | 2026-10-20 | "I have a background in protocol implementation and integration , and am a first principles thinking person. I want to understand the protocol , the implementation and see the requests and responses on the wire and underastand the entire flow" |
| A3 | 2026-10-20 | "I want both  of those made , and also want you to follow the SDD method in making them , as advocated by the file https://github.com/mtahamasood/agent-clinic/blob/main/SDD-FIELD-GUIDE.md" ("both" = a client written against the raw protocol with no SDK, and a client built on the official SDK) |
| A4 | 2026-10-20 | "I want this repo and the software it generates to have very high learning value for me as well as for anyone who wants to learn about MCP in depth. Add additional features that ensure this objective is achieved." |
| A5 | 2026-10-20 | "i still dont understand why any kind of learner log that is from a session of this tool needs to be maintained in the git repo. It should not. The learning lab is code and data of any kind should be generated during the actual execution on the users machine and no live file from the end user environment should be needed to be checked into version control git. It makes no sense. Change the design to ensure this , without the loss of learning" |

## Domain nouns

These nine nouns are the whole system. Anything that touches none of them is out of
scope until a spec says otherwise.

1. **Server** — the official "everything" server, at the pinned commit, unmodified.
2. **Client** — one of exactly two: the *raw client* (no SDK) and the *SDK client*.
3. **Message** — one JSON-RPC 2.0 request, response, or notification.
4. **Transport** — how messages move: stdio, or Streamable HTTP.
5. **Era** — a protocol revision family the server speaks: *2025 era* (`initialize`
   handshake, sessions) or *2026-07-28* (`server/discover`, per-request `_meta`, no
   sessions).
6. **Trace** — a recorded, timestamped, byte-faithful log of the messages on one connection.
   A trace exists only on the machine that recorded it; it is never committed (A5).
7. **Walkthrough** — a document mapping each message in a trace to the spec section that
   governs it and the source location that produced it.
8. **Schema** — the normative `schema.json` of a protocol revision, from the pinned spec
   repository.
9. **Lesson** — a learner-facing unit (one per phase) that walks a reader through predicting,
   running, reading, and explaining one part of the protocol, with runnable commands.

## Non-goals

Declined, so they need not be re-argued:

- Writing our own MCP server, or modifying the everything server (the submodule is
  read-only).
- Calling a real LLM. Server-initiated sampling is answered by the client with canned or
  owner-typed content.
- The deprecated HTTP+SSE transport (register row 2026-10-20, transports).
- Authorization flows (OAuth) for HTTP; the server does not require them.
- A GUI or web UI; third-party clients (e.g. MCP Inspector) as deliverables.
- Publishing packages, Docker images, or releases.
- A devcontainer or Codespaces setup; learners install natively (register row 2026-10-20, Q4).
- Teaching JSON, the command line, or Python/TypeScript themselves (register row
  2026-10-20, Q3).
- Committing anything a run produces — traces, logs, transcripts, tool output, learner-walk
  logs — or shipping such data any other way (A5).

## Review profile for phases 2–7

How review, mutation testing and hardening run from phase 2 on (register row 2026-10-21,
review profile). It sets how this project applies the field guide's review and mutation
steps; it does not drop any of them. Phase 1 ran a heavier profile (two review lenses, a
review of the fixes, mutation runs on every C row) and its records stay as they were.

- **RP1 Spec first, tests first, the gate.** A phase's requirements, plan and validation
  are approved by the owner before any of its code; each test is written before the code it
  checks; the phase closes only with `scripts/gate.sh` green on the inherited gates
  (G1–G11 in `tech-stack.md`) and the gates the phase adds.
- **RP2 One review round.** One adversarial review per phase, of the phase's new code only
  (its diff from the phase's base on `main`), by a different model from the builder, run
  after the phase's tests pass and before close; its corpus goes to
  `audits/<lens>-review.md`. The fixes get no second review round: each fix is verified by
  its own test and by the gate. Reviewer reports are model output: each finding is
  reproduced before it is fixed, and one that cannot be reproduced is recorded as such and
  not fixed.
- **RP3 Mutation testing on claim code only.** Each phase's `validation.md` names its
  *claim code*: the functions or files that carry the phase's central claim. Mutation
  testing runs on that code, not on docs, wording or glue; a C row that checks no claim
  code writes `not claim code (RP3)` in its Mutation column. A survivor is killed by a test
  that pins behaviour the spec specifies, or signed as an equivalent mutant with its
  reason; never by a test that pins unspecified behaviour only to kill the mutant. If a
  survivor shows a gap in the spec, the row is amended first (by a register row), then the
  test is written.
- **RP4 Severity triage.** Blockers and majors are fixed. A minor is fixed only when the fix
  is cheap or the finding touches claim code. Nits are not fixed: each is accepted as a
  documented limit, with a one-line reason, in the phase's one *Accepted limits* list in its
  `validation.md` Result; an unfixed minor goes on the same list.
- **RP5 No claim without its check.** A validation row may not name a sample, test or check
  that does not exist (incident: step (b) finding B1, `audits/step-b-review.md`, a C row
  whose cases were never written). Before close, a mechanical check confirms that every
  test, fixture or script each C row names exists: gate G12 (`tech-stack.md`) once the phase 2 plan
  implements it, and until then an explicit close-out step in the plan.
- **RP6 Review budget.** Each phase plan states its review budget, with the unit it is
  measured in (for example sessions or commits). The target: review plus hardening take at
  most about one third of the phase's effort. When the budget is spent, the work stops and
  a register row records why, instead of another round starting; the owner decides what
  follows.
- **RP7 Owner override.** The owner may override any of RP1–RP6 for one phase by a
  register row that names the rule and the phase.

Each phase plan's close group states the builder's model, the reviewer's model (a
different one), the review budget (RP6), and the RP5 check; its `validation.md` names the
claim code (RP3) and holds the *Accepted limits* list (RP4).

## Lean profile for phases 2–7

Amends the review profile above (register row 2026-10-21, lean profile; decision A24 in
`audits/autonomous-decisions.md`). Where an LP rule and an RP rule disagree, the LP rule
wins. Purpose: finish the clients within one working session, spending effort on the
protocol code the owner must be able to explain, change and debug, not on governance.

- **LP1 Two short spec files.** A phase is specified by `requirements.md` (learning
  objective, scope, D records with *Source* lines as G1 requires, build order, stop
  condition) and `validation.md` (C rows, claim code, Result with `Status:` and *Accepted
  limits*). No `plan.md`: its build order is a section of `requirements.md`. Mission,
  tech-stack and phase 1 decisions are referenced, not restated. Phases that will not be
  built in the current run are written as stubs (objective, scope, exit criteria) and say
  so.
- **LP2 Kept from RP1 and RP5.** Spec before code, tests before the code they check, the
  gate green before every push, and G12: every C row names its tests in the form
  `` `tests/<file>.py::<Class>::<method>` `` (or a whole file: `` `tests/<file>.py` ``,
  `` `tests/fixtures/<file>` ``, `` `scripts/<file>` ``, `` `tools/<file>` ``, or a
  module under `tap/` or `client/`), and each one named exists.
- **LP3 Vertical slice first.** Each client phase first lands the smallest exchange a
  learner can record and read (for the raw client: initialize, initialized, one
  `tools/call`, close), then widens.
- **LP4 Review only where it pays.** One review round, by a different model from the
  builder, at the close of phase 2 only (the first new protocol code); later phases rely on
  their tests and the gate, and a review round runs only if a phase changes claim code of
  an earlier one in a way its tests do not cover. Findings recorded are the reproduced
  blockers and majors; minors and nits go straight to *Accepted limits* in one line each.
  Mutation testing runs on claim code only, and only where the C row's check is the sole
  guard of a protocol rule (id correlation, lifecycle order, schema validation).
- **LP5 Deferred to a final pass.** Learner walks (L15), owner verdict rows (J rows),
  lesson polish beyond the L1 sections, and the clean-clone walk G6 for phases after 2. A
  deferred item is listed in the phase's *Accepted limits* as `deferred (LP5)`.
- **LP6 Learning check by the owner.** Each built phase's Result ends with an *Owner
  learning check*: three prompts (explain one exchange from a fresh trace without the
  walkthrough; make one stated change to the client and predict the new trace; diagnose
  one injected fault). The agent writes the prompts; only the owner writes the answers.
  The *change* answer is a commit the owner authors; the *debug* prompt is a fault the agent
  plants on a local exercise branch, revealed only after the owner answers. The agent then
  checks each answer against a fresh trace and adds a one-line verdict under it, never
  editing the owner's words. An unanswered check does not block a phase's close or tag
  (LP5), but the **phase 2 check must be answered before the project is called complete**;
  the other phases' checks are optional (register row 2026-10-21, learning check).
- **LP7 Lean build of phases 5–7.** Added 2026-10-22 (register row 2026-10-22, lean build of
  phases 5-7; A43). For phases 5, 6 and 7 only: tests may be written alongside the code they
  check, with no recorded red run (softens LP2's "tests before the code they check"); no
  mutation runs and no review round, both deferred to the final pass (softens LP4); a
  builder's departure from its spec is accepted or reversed by the agent at merge, with one
  register row per phase instead of one per change; lessons and walkthroughs need the L1
  sections, G9 and their `--explain` checks only (polish deferred, LP5); owner learning checks
  optional (softens LP6). Unchanged: spec approved before code, a test for every C row, the
  gate green on every merge to `main`, G12, no run output in git, and every deliverable of
  the approved specs: LP7 changes how the work is checked, never what is delivered.

## Decision register

Append-only. Never edit a row; correct by a new dated row that names the one it amends.

| Date | Decision | What prompted it |
| --- | --- | --- |
| 2026-10-20 | The project follows the SDD field guide (agent-clinic `SDD-FIELD-GUIDE.md`) at small-project scale (§13). | A3 |
| 2026-10-20 | Two clients are built: a raw client that speaks the protocol with no MCP library, and an SDK client. | A3 |
| 2026-10-20 | The raw client is written in Python; the SDK client in TypeScript. The owner chose this over the agent's recommendation (TypeScript for both). | Agent's question on client language |
| 2026-10-20 | Transports in scope: stdio first, then Streamable HTTP in its own phase; legacy HTTP+SSE is a non-goal. The owner took the agent's recommendation. | Agent's question on transports |
| 2026-10-20 | The server source is a git submodule of `modelcontextprotocol/servers` pinned at `51b6382a3e827aceb6bce430b1208d69b93d95ea`. The owner took the agent's recommendation. | Agent's question on how to bring in the server |
| 2026-10-20 | The project lives in a local git repo pushed to a new public GitHub repo, `mtahamasood/mcp-wire-lab`, with CI. The owner chose public; the name was the agent's proposal. | Agent's questions on repo location and name |
| 2026-10-20 | Both protocol eras are implemented by the clients, 2025 era first, then 2026-07-28. The owner took the agent's recommendation. | Recon found the pinned server speaks two eras |
| 2026-10-20 | The audience widens from the owner alone to the owner plus public learners, and learning value becomes the project's measure of success. The owner *delegated* the choice of learning features to the agent; the agent's catalogue is L1–L15 in `roadmap.md`. Each feature is a separate decision the owner may strike, and this entry installs no requirement beyond that catalogue. Roadmap reordered to fit them (a new edge-lab phase 4; former phases 4–6 become 5–7). | A4 |
| 2026-10-20 | Lesson reader baseline: JSON, the command line, and reading Python or TypeScript; JSON-RPC 2.0 and MCP are taught from zero. No devcontainer (a non-goal). Node 24 on the owner's machine is installed with `nvm`. The owner took the agent's recommendation on baseline and install method, and declined the devcontainer. | Q2, Q3, Q4 of the phase 1 spec |
| 2026-10-20 | **Run output is never committed.** The repository holds only authored content; everything a run produces is generated on the machine that runs it and stays there. The owner *articulated* this rule. It amends the A4 catalogue (L5, L8, L15 and the new L16 in `roadmap.md`), phase 1 D8 and D11, and the "committed traces" wording of the phase 1 draft spec; enforced by gate G11 and a pre-push hook (standing law 1 in `tech-stack.md`). Where it conflicts with the field guide's §9 "deposit the full review corpus", A5 wins for run output: reviewers' authored reports are deposited, raw run logs are not. | A5; prompted by a side agent's note that `get-env` (`tools/get-env.ts:33` at the server pin) returns the server's whole environment, so committed traces could leak secrets |
| 2026-10-20 | The owner ratified all proposals P1–P9 as written, kept all learning features L1–L16 (none struck), and approved the phase 1 spec (requirements, plan, validation). Implementation of phase 1 may begin. | Owner: "ratify all proposals and approve the spec" |
| 2026-10-21 | Phase 1 D1–D4 and validation rows C1, C2, C4, C5, C6 are amended, and row C17 is added, to dispose of tap review findings T1–T4, T6–T13 and T16 (`audits/tap-review.md`). The tap fails open: if the trace cannot be written, forwarding and the exit code are unchanged and the tap says so once on stderr. It forwards SIGINT, SIGTERM, SIGHUP and SIGQUIT; it creates the trace with mode 0600 and replaces an existing file. The owner took the agent's recommendation on each of those three, and approved the other dispositions as proposed. The group 8 fix step is split by model: tap core on Opus high first, the rest on Sonnet medium. | Closing review corpus `audits/tap-review.md`; the owner's answers to the agent's disposition questions |
| 2026-10-21 | Phase 1 rows C2, C4, C6 and C17 are amended after the step (a) mutation run left five survivors. Three gain checks: `t_ns` follows real time (a frozen clock passed), a child that closes stdout and then floods stderr has every stderr line recorded before `exit` (joining only the stdout thread passed), and the tap started with stdin, stdout or stderr closed keeps a strict trace and adds nothing to stderr (dropping `open_standard_fds` passed). C4's deep frame keeps its `raw` text, as D3 requires of valid UTF-8 (dropping the `RecursionError` catch passed only because a fallback wrote `raw_b64`). Dropping `parse_float` is signed as an equivalent mutant: `encode_record` already turns an infinite value into `json: null`; the first layer stays because its `parse_error` names the cause. The owner delegated these five decisions to the agent. | Step (a) mutation run; the owner: "decide on my behalf" |
| 2026-10-21 | Phase 1 D5, D8, D11, D13, D14, D15, validation rows C9, C12, C15, C16, and tech-stack G1, G7, G8, G9, G11 are amended to dispose of the viewer and rest review findings (`audits/show-review.md`, `audits/rest-review.md`) and tap findings T5, T14, T15, T17-T19. G11 now also: reads any trace-shaped file whatever its name, scans merge commits and the index, widens the text rules, and checks symlink targets. The pre-push installer follows `git rev-parse --git-path hooks` and warns when `core.hooksPath` is set elsewhere; R1 is downgraded because the owner's global hook chains to it. The viewer keeps ids typed, shows a non-conforming frame raw, and exits 2 on an unreadable file. G7 reads one `Status: open|closed` line. D8 says the walkthrough's examples are not machine-checked, and the Result lists them. Accepted as limits: S5, S8, S12, S14, R21; owner-only: R17, R18. The owner chose the options as proposed (R1 downgrade, G11 all four, viewer S1-S4/S6/S7/S10/S15, rest with R21/R22 accepted). | Closing review corpora; the owner's answers to the agent's disposition questions |
| 2026-10-21 | The owner delegated every remaining Phase 1 decision to the agent, to be reviewed by the owner at the end: no questions, the agent commits and pushes, and uses subagents at models and efforts it chooses. Every such decision is a row in `audits/autonomous-decisions.md` (id, choice, reason, confidence, what breaks, how to overrule); a decision that changes a requirement, validation row or gate also gets its own register row. The method is unchanged: spec first, then tests, then code. Owner-only items R17 and R18 are resolved provisionally (A2, A3) and stay open for the owner's overrule. | The owner: "do it entirely automatically with no input from me ... log it in relevant places" |
| 2026-10-21 | Phase 1 D7, D12, D13, D14, D15, validation rows C12, C15, C16, boundary check B5, and tech-stack CI, G1, G8, G9, G11 and standing law 1 are amended, and row C18 is added, to dispose of the step (b) review findings B1-B19 (`audits/step-b-review.md`; decisions A11-A18 in `audits/autonomous-decisions.md`). `record.sh` exits 1 with a `record: cannot create ` line when a run folder cannot be created, and a lesson takes its run folder from the `recorded:` line or the newest `runs/*-<name>*` (C18). G11's home rule becomes a negative lookahead; a KEY=VALUE env line may be indented or prefixed by `export` or `declare -x`; the hook reads every added, modified or type-changed file; gate mode reads a working-tree entry that differs from the index whatever its type, a symlink as its target path. G9 follows CommonMark fences. C16 requires exactly the allowlist (node adds no variable, measured). The installer fails on a directory that is not a repo and creates nothing. D7 and G1 describe G1 as the code has it. Accepted as documented limits: G1 matches words, not meaning (B9); JSON-escaped and Windows-style home paths (B3, in G11 and standing law 1); G8 reads the submodule as checked out and bootstrap checks the pin (R12); CI's action tags and `uv` and Python patch versions float (R21). B5 now also allows edits each named by a register row. This row amends the third row of this date: the pre-push installer does not follow `git rev-parse --git-path hooks`; it writes the repo's own hooks directory, `$(git rev-parse --git-common-dir)/hooks`, never a directory that `core.hooksPath` names, and warns when `core.hooksPath` resolves elsewhere (R1 as implemented by A4); and that row's claim that G9 was amended now holds. It also names the earlier tech-stack edits on this branch that no row named: the SDK client row and G3 (the SDK test tool and `tsc --strict` move from phase 4 to phase 5, after the A4 reorder) and the conventions line (`audits/<lens>-review.md`, `audits/learner-walk-lesson-NN.md`). It corrects the fourth row of this date: R17 and R18 are decided by the agent (A2, A3) but their records are not yet written; the close-out step writes `LICENSE` (MIT), the J2 note in `validation.md` ("agent-proposed, owner to confirm") and the acceptance of learner-walk items 3 and 7 before the phase-close merge, and both stay open for the owner's overrule. Decided by the agent under the owner's delegation (the fourth row of this date). | Independent review of step (b) (`audits/step-b-review.md`, B1-B18) and the C15 mutation run (B19); the owner's delegation |
| 2026-10-21 | The repository's own content is licensed MIT: `LICENSE` at the root, copyright 2026 M. Taha Masood (the git author name), and a licence line in `README.md`. The submodules under `vendor/` keep their upstream licences and are not relicensed. This resolves finding R18 provisionally: decided by the agent under the owner's delegation (A2 in `audits/autonomous-decisions.md`), open for the owner's overrule by a later row that names another licence and replaces `LICENSE`. No requirement, validation row or gate changes. | Finding R18 (`audits/rest-review.md`); A2 and A18; the owner's delegation (the fourth row of this date) |
| 2026-10-21 | **Review profile.** Phases 2–7 run the lighter review profile in this file's section *Review profile for phases 2–7* (RP1–RP7): spec first, tests first and the gate are kept; one adversarial review round per phase, on its new code, by a different model, with no review of the fixes; mutation testing on the phase's claim code only; blockers and majors fixed, minors when cheap or in claim code, nits accepted in one *Accepted limits* list; no validation row may name a check that does not exist, confirmed mechanically before close (gate G12, proposed in `tech-stack.md`, to implement in the phase 2 plan); a review budget in each plan, at most about one third of the phase's effort, and a register row instead of another round when it is spent; the owner may override any rule per phase by a register row. This amends how the field guide's review and mutation steps are applied (the SDD row of 2026-10-20) from phase 2 on; `tech-stack.md` and `roadmap.md` reference the section. Phase 1 ran the heavier profile and its records are unchanged. The owner articulated the rules; the agent wrote them as RP1–RP7, and its calls in the wording are A23 in `audits/autonomous-decisions.md`. | The owner, 2026-10-21: "I want to incorporate the things mentioned in My judgement ... customize the methodology accordingly for the remainder of the project". Phase 1's review and hardening were about two thirds of its work, with diminishing returns in the later rounds (step (b) review: 1 major, 7 minor, 10 nits; the major, B1, was a C row claiming tests that were never written) |
| 2026-10-21 | For phases 2-7 the owner approved a standing autonomous run: (1) the agent runs unattended and stops only for a blocker or when a phase's review budget (RP) is exceeded; (2) specs for phases 2-7 are written together and approved by the owner as one batch, or delegated; (3) Opus is used only for specs and the single review round per phase, Sonnet for build and fixes, no xhigh by default; (4) the human-judgement rows (owner verdicts, learner walks) are deferred to a final pass and do not block phases; (5) independent phases (for example 4 and 5) may run in parallel in separate worktrees; (6) review budgets are enforced (RP, G12); (7) the controlling agent keeps its context small and hands off at each phase boundary. Every judgement call is a row in `audits/autonomous-decisions.md` for the owner to overrule. | The owner: "i approve your plan numbered list under 'what would make it likely'" |
| 2026-10-21 | **Lean profile.** Phases 2–7 run under the section *Lean profile for phases 2–7* (LP1–LP6), which amends the review profile (RP1–RP7): two short spec files per phase and no `plan.md`; spec first, tests first, the gate and G12 kept; one review round at the close of phase 2 only; mutation on claim code that is a protocol rule's sole guard; learner walks, J rows and G6 after phase 2 deferred to a final pass; an owner learning check per built phase. Scope for this run: phases 2, 3 and 4 are specified in full and built (phase 4 in parallel with phase 2, since it needs no raw client); phases 5, 6 and 7 are specified as stubs and marked *specified, not built* in `roadmap.md`. Learning feature L8 (atlas, gate G10) moves from phase 2 to the final pass, and L13's server-side source tour is cut to one request (`tools/call`). The agent's calls are A24 in `audits/autonomous-decisions.md`. | The owner, 2026-10-21: wants the project completed within the current session and authorised softening strict SDD if documented; the owner approved the agent's lean plan ("proceed as per plan"), which weighed outside advice the owner pasted (shorter specs, smallest vertical slice, mutation only where a check is critical, assess learning not only code) |
| 2026-10-21 | The owner approved the phase 2–7 spec batch (the commit that adds this row: phases 2, 3 and 4 in full, 5, 6 and 7 as stubs) and delegated every later spec amendment and judgement call of this run to the agent, logged as A25 onward in `audits/autonomous-decisions.md` for review at the end. Implementation of phases 2, 3 and 4 may begin. | The owner, answering the agent's question: "Approve, delegate the rest" |
| 2026-10-21 | **Atlas.** The message atlas (L8) and gate G10 are built now, in parallel with phases 2 and 4, and specified as phase 3 D6 and C9 instead of in the final pass (amends the lean-profile row of this date). Its capability column is dropped as an accepted limit, because the schemas do not encode it. The agent's call under the owner's delegation, A25 in `audits/autonomous-decisions.md`. | The owner, 2026-10-21: "evaluate if anything else can be done in parallel safely" |
| 2026-10-21 | **Phase 4 build amendments.** Phase 1 D11 is amended: `tap.show --explain <file>#<section>` reads the notes under that `##` section plus a `## shared` section (shared notes are never reported as extra), and a note anchor may name a range such as `stderr.1-106`; without `#` the behaviour is unchanged. Phase 1 D14 is amended: `scripts/record.sh` prints its `recorded:` and `read it:` lines and exits 0 when the trace was written even if the server exited non-zero, warning on stderr; the trace's exit record carries the code. Phase 4 D1: the `batch-array` fixture ends with a plain `ping` so the driver keeps stdin open until the replies arrive. Builder calls accepted by the agent under the owner's delegation, A27 in `audits/autonomous-decisions.md`. | Phase 4 build: one walkthrough explains eight traces, and the pinned server exits 1 after a transport error (`missing-jsonrpc`, `batch-array`) |
| 2026-10-21 | **Phase 2 build amendments.** Phase 2 D7 is amended: G12 checks the phases listed in `scripts/gate.sh` (`--phases`), and a phase is added to that list when its named tests exist (phase 3 when it is built); this keeps the gate green between a spec and its build. Phase 1 D14 (as amended by the phase 4 row of this date) is refined: the non-fatal server exit applies to fixture recordings only; `record.sh --client` exits with the client's status after printing its lines. `tap.check` accepts `$schema`, `$defs` and `description` without checking them and a list-valued `type` (P8 extended to what the real schema uses), and has a `--spec-root` option for tests. Builder calls accepted by the agent under the owner's delegation, A28 in `audits/autonomous-decisions.md`. | Phase 2 build and its merge with phase 4 |
| 2026-10-21 | **Learning check.** LP6 is amended: the phase 2 owner learning check (explain, change, debug) must be answered before the project is called complete; it does not block phase 2's close or tag. The change answer is an owner-authored commit; the debug prompt is a fault planted by the agent on a local branch `learning-check-02-fault`, revealed after the answer; the agent records a one-line verdict under each answer. Checks of phases 3 and 4 stay optional. The owner chose this option (the agent's recommendation) and does the check while phase 3 builds. | A side note: under LP6 every phase could close with every learning check open, leaving no evidence the owner can explain and change the code, the evidence the outside advice named as what matters most |
| 2026-10-21 | **Phase 2 review.** The phase 2 review (`audits/phase-02-review.md`, Opus, P2-R1 to P2-R9: 0 blockers, 2 majors, 7 minors) is disposed: all nine are fixed, since each minor is cheap or in claim code (LP4). Phase 2 D2 is amended (a timed-out request is cancelled and forgotten; after EOF or close every request fails at once with `OSError`), and validation rows C1, C2, C3, C5, C9 and C10 gain the tests each disposition names. The fixes land after phase 3 merges, because phase 3 changes the same reader code. The agent's call under the owner's delegation, A30 in `audits/autonomous-decisions.md`. | Phase 2 review round (LP4) |
| 2026-10-21 | **Phase 3 build.** Phase 3 D1 is amended toward the spec: a request for an elicitation mode the client did not declare gets `-32602` (the builder followed D1's `-32601` and flagged the conflict with the spec's elicitation section), and a non-integer number default is sent as its integer part, because the 2025-11-25 `ElicitResult` content allows no floats. Row C1 gains a test for the `-32602` case. The other builder calls are accepted as made: `:sample <text>` in manual mode, a 50 ms re-list debounce, `logging/setLevel debug` before `trigger-log-messages`, the matrix printing the five gated tools only. The agent's calls under the owner's delegation, A32 in `audits/autonomous-decisions.md`. | Phase 3 build report |
| 2026-10-21 | **Learner walk dispositions.** The owner approved the agent's dispositions for `audits/learner-walk-lessons-02-04.md` (findings 2-13; finding 1 was resolved by making `main` the default branch) and the one behaviour change among them: phase 1 D11 is amended so that `tap.show --explain file.md#name` with a missing section exits 2 and lists the sections the file has. `oversized-frame` is dropped from the experiments a learner can pick in lesson 04. Everything else is lesson and README text. The owner also deferred the phase 2 learning check until they have used the finished project; feedback from that use may lead to a version update. | Owner: "Approve all, yes to --explain, drop oversized-frame"; "I will do them when the project is otherwise all complete and I actually use it" |
| 2026-10-21 | **Learning check run by an agent; prompts softened; priority is to finish.** At the owner's request a fresh agent did the phase 2 learning check (recorded apart from the owner's `Answers:`, A35). The owner then took the agent's recommendations on all open points: the owner's own check stays open and is not a gate on using or releasing the project (it is done after real use and may lead to a version update; this amends the learning-check row above, which required it before the project is called complete: the project is now called complete with that item listed open); the three friction fixes are applied to the three prompts (bootstrap time for a second worktree, a clearer prompt 2 hint with "expect red", and a warning that failing e2e tests print walkthrough notes); the agent's branch and worktrees are removed and `learning-check-02-fault` is kept. The owner's stated priority is to finish and start using the project. | Owner: "i will go for your recommendation against all the above ... log every decision ... my priority right now is to get this completed and try it" |
| 2026-10-21 | **Self-explanatory help.** Phase 1 D1 is amended and row C19 added: `-h` / `--help` on `tap`, `tap.show`, `tap.check`, `client` and `scripts/record.sh` prints the usage on stdout and exits 0, instead of being a usage error (exit 2). The usage texts also explain each option (A37). The owner took the agent's recommendation. | Owner: "yes please do it" |
| 2026-10-21 | **Help on the two setup scripts.** The newcomer walk (`audits/newcomer-walk-readme.md`, N1) found that `scripts/bootstrap.sh --help` and `scripts/gate.sh --help` ran the whole script, against the README. Phase 1 D1 and row C19 are extended to cover both scripts. The owner approved all of the walk's proposed dispositions (N1-N10). | Owner: "yes go ahead with all of it" |
| 2026-10-22 | **Phases 5, 6 and 7 are un-stubbed and built in this run.** This amends the lean-profile row of 2026-10-21 and A24 (5), which left phases 5-7 as stubs marked *specified, not built*. Each stub is expanded into a full `requirements.md` and `validation.md` under LP1-LP6 (G12 form for every C row, a *Source* line on every D record). The three specs are approved by the owner as one batch before any test or code; for these specs this narrows the delegation row of 2026-10-21 ("Approve, delegate the rest"), and later amendments made during the build stay delegated. Build order: phase 5 first; phase 6 after phase 5 is merged, since it extends the SDK client; phase 7's HTTP tap mode may be built beside phase 6. Ending the run with phases 5 and 6 built and phase 7 still a stub is acceptable. The owner's feedback on the project and the phase 2 learning-check answers are deferred to the end of this run. The agent's calls are A41 in `audits/autonomous-decisions.md`. | The owner, 2026-10-22, in session: build phases 5, 6 and 7 today, with feedback and learning-check answers at the end of the day |
| 2026-10-22 | **Phases 5-7 specs approved.** The owner approved the phase 5, 6 and 7 specs as one batch, with two amendments from the owner's answers. (1) Phase 6 keeps the tasks extension, documents that the pinned `schema.json` has no tasks types, and also adds a small hand-written tasks schema transcribed from SEP-2663 at the spec pin, so `tap.check` checks tasks traffic and labels those findings as checked against the extension. (2) Phase 7 takes the server's bind address from configuration: the tap starts the server with `PORT` set to a Unix-socket path in a short private temporary directory and proxies to it, so no recording exposes the server on a network interface (measured at the pin: no TCP listener, and `initialize` works over the socket). The approval also amends: tech-stack's *SDK client* row (`typescript` 5.9.3, `@types/node` 24.19.2, `node:test`, run as source), G3 (`tsc -p clients/sdk`), G4 (`node --test`), G8 and *Citation form* (a third root `sdk`, pinned by the lockfile's integrity hash) as phase 5 D1, D5 and D6 specify; phase 3 D6, so that a lesson's declared method also counts when it appears inside `result.inputRequests` (phase 6); and phase 1 D1-D5 and D14 and phase 2 D5 for HTTP mode only, as phase 7 specifies, with `PORT` added to the recording allowlist. The agent took its recommendation on the other open points: the `sdk` citation root rather than a third submodule, `wire-lab-sdk` as the SDK client's sampling name, discovery first with no fallback to the 2025 era, and phase 7 parts C and D built after phases 5 and 6 rather than dropped if those are late. The agent's calls are A42. | Owner's answers to the agent's batch questions: "Approve"; on tasks, "1 above and if anything else on top of it is possible then that too"; on the bind address, "get it from config" |
| 2026-10-22 | **Lean build of phases 5-7.** For the build of phases 5, 6 and 7 the lean profile is softened further, as on 2026-10-21, to finish within the owner's usage window. Kept: the approved specs, tests for every C row, the gate green on every merge to `main`, G12 once a phase is listed, and no run output in git. Softened: (a) tests may be written alongside the code they check, without a recorded red run; (b) no mutation runs, deferred to the final pass (LP5); (c) no review round; (d) a builder's departure from its spec is accepted or reversed by the agent at merge and logged in `audits/autonomous-decisions.md`, with one register row per phase naming the D records it amends, instead of a row per change; (e) lessons and walkthroughs need the L1 sections, G9 and their `--explain` checks, but polish is deferred (LP5); (f) the owner learning checks of phases 5-7 are optional (LP6, as for phases 3 and 4). Build order: phase 5 together with phase 7 parts A and B1, which do not depend on phase 5; phase 6 after phase 5 merges; phase 7 part C after phase 5 and part D after phase 6. The softening changes how the work is checked, never what is delivered: every part of the approved phase 5, 6 and 7 specs is built, including phase 6 part B and phase 7 parts C and D. If the usage window runs out, the work stops at a safe point and resumes in the next window; nothing is dropped. The agent's calls are A43. | The owner, 2026-10-22: "soften SDD strictness just like we did yesterday in the interests of time and session limits. use good judgement"; the owner's usage window was at 75% |
| 2026-10-22 | **Amendments named by the two approved spec changes.** Phase 6 D14 (the tasks schema transcribed from SEP-2663, `tap/schemas/2026-07-28/sep-2663-tasks.json`) amends phase 2 D6's choice of result definition for `tasks/*` and for a `resultType: "task"` result of `tools/call`, and widens P8 from "the two target schemas" to those two plus that hand-written extension schema, using only the keywords P8 lists. Phase 7 D7 amends phase 1 D14: in HTTP mode `scripts/record.sh` runs the tap itself under `env -i` with the allowlist, with `python3` linked into the run folder's `bin/` as `node` is, and the tap's `listen` record names its upstream as `unix:<path>` (committed docs use the placeholder `unix:<temp dir>/server.sock`, P9). This completes the approval row of this date. | The phase 6 and phase 7 amendment reports |

## Proposals awaiting ratification

Calls the agent made while writing the constitution. They are **not requirements** until
the owner ratifies them; ratification is recorded as a register row, overrule as a struck
proposal kept here.

**Status:** P1–P9 all ratified 2026-10-20 (register row of that date). Kept here as history.

| Id | Proposal | Why the agent made it |
| --- | --- | --- |
| P1 | The SDK client uses the v2 split package `@modelcontextprotocol/client` 2.3.1, not v1 `@modelcontextprotocol/sdk` 1.32.1. | The pinned server is built on the v2 packages at 2.3.1 (its lockfile, measured 2026-10-20); one SDK generation on both ends keeps the comparison honest. |
| P2 | Node 24 (24.22.0) is the project's Node, installed by the owner. | The pinned server declares `engines.node >=24`; this machine has 22.23.2 (measured 2026-10-20). |
| P3 | Each phase delivers its own walkthrough of the traces it introduces, instead of one walkthrough phase at the end. | A2 asks to understand "the entire flow"; per-phase walkthroughs give understanding at each step and keep each walkthrough next to the traffic it explains. |
| P4 | The wire tap, the raw client, and all gate scripts use Python's standard library only (no third-party runtime dependencies). Dev-only tools (ruff, mypy) are allowed. | The raw client must have no MCP library (A3); extending "no libraries" to the tap keeps every byte of observation in code the owner can read. |
| P5 | The tap is written in Python, not TypeScript. | Same language as the raw client and gates (one Python toolchain); the tap must not use the SDK, so TypeScript buys nothing. |
| P6 | Python lint is ruff 0.17.1 and typecheck is mypy 2.4.0 `--strict`, both run via `uvx` at those exact versions (dev-only, never imported). | The field guide's gates name lint and typecheck but no tools; these are the current releases (PyPI, 2026-10-20) and `uv` 0.12.5 is already installed. |
| P7 | `vendor/spec` is a second submodule: `modelcontextprotocol/modelcontextprotocol` pinned at `1155ca460e5097019f32769b38dcba194432e2fb`. | L6 needs the schema and spec text at a fixed commit; recon (2026-10-20) found `schema/<rev>/schema.json` for every revision, including `2025-11-25` and `2026-07-28`. |
| P8 | The schema check (L7) is a stdlib-only validator for exactly the JSON Schema keywords the two target schemas use, and it fails loudly on any keyword it does not implement. | Recon (2026-10-20) counted the keywords in both schemas: `type`, `$ref`, `properties`, `required`, `const`, `additionalProperties`, `items`, `anyOf`, `allOf`, `enum`, `minimum`, `maximum`, `maxItems`, `format` (annotation only) — small enough to own, and P4 forbids a third-party validator. |
| P9 | The line A5 draws: **authored** content may be committed — code, specs, docs (including hand-written example messages and diagrams that a gate checks against a live run), hand-written synthetic test fixtures marked as such, and reviewers' and the agent's written findings, measurements stated as values in a validation Result. **Produced** content may not — trace files, logs, transcripts, tool-output dumps, anything copied from `runs/`. Committed docs carry no environment-specific values (absolute paths, environment variables, hostnames, timestamps). | A5 says "data of any kind should be generated during the actual execution"; the agent reads it as forbidding run output, not as forbidding authored examples or recorded measurement values, which the SDD record needs. The owner may draw the line tighter. |
