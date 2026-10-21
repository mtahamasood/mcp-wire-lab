# Roadmap

One phase at a time. A phase starts only when the previous phase's exit criteria are met,
and its spec (requirements, plan, validation) is committed and owner-reviewed before any
of its code. Every phase after the first ends with something demonstrable. Exit criteria
are binary. Every phase also ships its lesson (L1) and walkthrough, and closes with a
`lesson-NN` tag (L14) and a learner walk (L15). Nothing a run produces is ever committed
(A5): learners record their own traces with `scripts/record.sh` (L16), and CI records
fresh ones to check the docs against. Phases 2–7 are reviewed under the review profile in
`mission.md` (RP1–RP7; register row 2026-10-21, review profile): one adversarial review
round on the phase's new code before close, mutation testing on its claim code only, and
a review budget stated in its plan. Phase 1 ran a heavier profile. That profile is amended
by the lean profile (LP1–LP6 in `mission.md`; register row 2026-10-21, lean profile): two
short spec files per phase, one review round at phase 2's close only, and learner walks,
J rows and the atlas (L8, G10) deferred to a final pass. In this run phases 2, 3 and 4 are
built; phases 5, 6 and 7 are **specified, not built** (stub specs in `specs/phases/`).

| # | Phase | Learning features | Exit criteria (all must hold) |
| --- | --- | --- | --- |
| 1 | **Wire tap (stdio) and learning scaffold** | L1, L3, L4, L5, L6, L14, L15, L16 | From a fresh clone, one command builds the pinned server; the tap records every byte both ways while forwarding them unchanged; the viewer shows the trace as a correlated timeline, a Mermaid sequence diagram, and with walkthrough notes inline; a hand-written 2025-era handshake fixture, recorded fresh by `scripts/record.sh`, is fully explained by the walkthrough, and lesson 01's commands and citations pass their gates; no run output is tracked by git (G11); `scripts/gate.sh` passes locally and in GitHub Actions. |
| 2 | **Raw client, 2025 era, client-initiated** (Python, stdio) | L2, L7, L8, L9, L13 (server side) | The raw client completes the 2025 lifecycle (initialize → initialized → … → shutdown) and exercises every client-initiated request the server offers (tools, resources, resource templates, prompts, completion, logging level, ping, cancellation), in scripted and manual mode; every frame it sends validates against the 2025-11-25 schema; the atlas exists and is current. |
| 3 | **Raw client, 2025 era, server-initiated** | L10 | The raw client handles every server-initiated request and notification the server sends (sampling, elicitation, roots, progress, log messages, list-changed, resource updates); the capability matrix is recorded. |
| 4 | **Edge lab** | L11 | Every edge-lab experiment is a recordable fixture whose fresh trace is fully covered by a walkthrough entry explaining the server's behavior against the spec; the tap's fault mode is proven by its checks. |
| 5 | **SDK client, 2025 era** (TypeScript, stdio) | L12, L13 (SDK side) | The SDK client runs the tour of phases 2–3; `tap.diff` between fresh traces of both clients is explained, difference by difference, in the walkthrough, and CI checks that explanation against fresh traces. |
| 6 | **2026-07-28 era, both clients** (stdio) | — | Both clients speak 2026-07-28 (`server/discover`, `_meta` envelope, `subscriptions/listen`, tasks, multi-round); a walkthrough diffs it against the 2025 era message by message; atlas coverage measured (L8). |
| 7 | **Streamable HTTP** | — | The tap observes HTTP traffic (requests, responses, SSE streams, session headers); both clients run both eras over HTTP; the lesson covers what HTTP adds; final atlas coverage measured. |

## Learning features (A4)

The agent's catalogue, chosen under the owner's delegation (register row 2026-10-20, A4),
amended by A5 (register row 2026-10-20, run output never committed).
Each is one decision the owner may strike. A feature with a gate is enforced by that gate
from the phase that introduces it.

| Id | Feature | Why it carries learning value | Gate |
| --- | --- | --- | --- |
| L1 | **Lessons and a learning path.** `README.md` is the entry point and lists the lessons in order. `docs/lessons/NN-<topic>.md`, one per phase, each with the fixed sections *Goal → Predict → Run → Read the trace → Read the source → Experiments → Check yourself*. | Predict-then-observe is how a protocol engineer learns a wire format; a fixed shape lets a reader skim, and lets a gate check it. | G9 checks the sections exist |
| L2 | **Literate protocol code.** Every function in the tap and the raw client that builds, sends, or handles a protocol message carries a verified citation of the spec section it implements. | The code itself becomes a reading companion to the spec. | G8 |
| L3 | **Verified citations.** Docs and code cite sources as `` `<submodule>:<path>:<line>` "fragment" ``; a gate checks the file exists in the pinned submodule and the fragment appears on that line. | Citations into fast-moving upstream code rot silently; a learner who follows a stale line gives up. | G8 |
| L4 | **Runnable lessons.** Every command block a lesson marks runnable is executed by a gate; an expected-output block after it must appear in the output. | A published command nobody runs is a dead check (field guide §7, shape 4); a lesson whose commands fail loses the reader at step one. | G9 |
| L5 | **Self-explaining traces.** `tap.show --mermaid` emits a Mermaid sequence diagram; `tap.show --explain <walkthrough>` prints each frame of the learner's own trace with its walkthrough note inline. Notes are keyed by message identity (direction, method, `id`, occurrence), not by position, so they fit any fresh trace; `--explain` fails on a frame with no note and on a note that matches no frame. | A picture of the flow, and the explanation next to the bytes the learner just produced. | C13, C14 |
| L6 | **Pinned spec.** The spec repository is a submodule (P7), so spec text and schemas are cited at a fixed commit and available offline. | Learners read the normative text, not a page that changed since. | B1 |
| L7 | **Schema check.** `tap.check <trace> --revision <rev>` validates every frame against the normative schema with a stdlib validator (P8), naming the failing path and the schema definition it violated. | It connects each message on the wire to its normative definition, and catches the raw client's mistakes the way a conformance suite would. | G5 (raw client traffic must validate) |
| L8 | **Message atlas.** `docs/atlas.md`, generated from the schemas: every method of both target revisions (31 in 2025-11-25, 21 in 2026-07-28, counted 2026-10-20), its direction, the capability that gates it, and the lessons that exercise it. A lesson's claim to exercise a method is checked by CI against that lesson's fresh trace. Unexercised methods are listed as such. Generated from pinned source only, never from run output. | One map of the whole protocol, honest about what this repo has and has not shown. | G10 (regenerated atlas matches the committed one) |
| L9 | **Manual mode.** `raw-client --manual`: a REPL to type or pick JSON-RPC messages, send them, and see the replies, with the tap recording. | Hand-crafting a message and reading the reply is the fastest way to learn what the server accepts. | phase 2 checks |
| L10 | **Capability matrix.** The same tour run with client capabilities toggled (no sampling, no roots, no elicitation, each alone); the change in server behavior is recorded and explained. | Capability negotiation is the protocol's core contract; toggling it shows what each capability actually buys. | phase 3 checks |
| L11 | **Edge lab.** Malformed and out-of-order traffic (missing `jsonrpc`, request before `initialize`, unknown method, duplicate `id`, string vs number `id`, notification with an `id`, a JSON-RPC batch array, an oversized frame) recorded as measurements and explained against the spec; plus an opt-in tap fault mode (`--delay`, `--drop`), marked in the trace, to study timeouts, cancellation, and progress. | Error paths are where a protocol's real contract shows; reading only happy paths teaches half the protocol. | phase 4 checks |
| L12 | **Trace diff.** `tap.diff a b` normalizes ids and timings and shows message-level differences. | Raw vs SDK, and 2025 vs 2026-07-28, are best learned as diffs. | phase 5 checks |
| L13 | **Source tours.** For each feature area, one request traced through the code: transport → protocol layer → handler registry → feature implementation, with verified citations (server side in phase 2, SDK client side in phase 5). | Answers A1 ("understand the source") directly, rather than only through scattered citations. | G8 |
| L14 | **Lesson checkpoints.** A git tag `lesson-NN` at each phase close. | A learner can check out the repo exactly as it stood after any lesson and build from there. | phase-close checklist |
| L15 | **Learner walk.** At each phase close, a fresh agent with no project context follows the lesson from the README in a clean clone, outside the repo. Its log stays on the machine that ran it (A5); what is committed is the agent's written list of stalls and wrong answers, each with its fix or signature. The owner reads the log locally and judges. | A stand-in for a newcomer, the reader whose confusion the author cannot see. | judgement check, per phase |

| L16 | **One-command recording.** `scripts/record.sh <fixture-or-client> [name]` records a trace into `runs/<timestamp>-<name>/` (git-ignored), starting the server with a minimal allowlisted environment, then prints the `tap.show` commands to read it. CI and the gates use the same script. | Every learner gets their own real trace in one step, with identical environment-dependent output (e.g. `get-env`) to compare against the lesson, and their secrets never enter it. | C15, C16 |

## Backlog — parked, not promised

- Point a real-world MCP client (e.g. Claude Code) at the tap and walk through its traffic.
- An HTML trace viewer.
- Resumability over Streamable HTTP (`Last-Event-ID`) as its own study.
- The raw client against a second, independent server implementation.
