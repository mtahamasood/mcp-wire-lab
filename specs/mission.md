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
