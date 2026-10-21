# Phase 3 — Raw client, 2025 era, server-initiated: requirements

Lean profile (LP1–LP6 in `mission.md`; register row 2026-10-21, lean profile). Builds on
phase 2's `client/` (D1–D8 there stand). Server facts read from the pinned source on
2026-10-21; the walkthrough cites them (G8).

## Learning objective

See the protocol run backwards: the server sends requests to the client (sampling,
elicitation, roots) and unsolicited notifications (progress, log messages, list changes,
resource updates), and what the client declares in `initialize` decides which of these the
server may use at all.

## Scope

In: handlers for every server-initiated request the 2025-era server sends (D1), the
client's reaction to notifications (D2), capability flags and the capability matrix
(D3, L10), the server tour (D4), walkthrough and lesson 03 (D5). Out: a real LLM (a
non-goal; sampling is answered with canned content); the 2026-07-28 tasks and async tools
(phase 6); the server's timer tools (`toggle-*`) in any recorded tour, since their
messages arrive at random levels and intervals.

### D1 — Answering server requests

`client/handlers.py` replaces phase 2's refuse-all handler with a table keyed by method.
Each reply carries the request's `id` unchanged (type included) and is sent on the
reader's behalf without blocking it (a handler runs on a worker thread so a client
request can still complete while a server request is pending):

- `roots/list` → `{"roots": [...]}` from the client's configured roots (default one root,
  `file:///wire-lab/project`, named `wire-lab`); the value is a fixed, authored URI, never a
  path from the machine;
- `sampling/createMessage` → a canned `CreateMessageResult`: role `assistant`, text
  content `canned reply from wire-lab-raw`, model `wire-lab-canned`, stop reason
  `endTurn`; in manual mode the owner may type the text instead;
- `elicitation/create` → form mode: `accept` with a value for each requested property
  from its `default`, else the first `enum` value, else a fixed value per type (`string`
  `"wire-lab"`, `number`/`integer` `1`, `boolean` `true`), a non-integer number default sent as its integer part because the 2025-11-25 `ElicitResult` content allows no floats; URL mode: `decline`; a request for an elicitation mode the client did not declare → error `-32602` (invalid params), as the spec's elicitation section requires;
- `ping` → `{}`;
- any other method, or a method whose capability the client did not declare (other than
  an undeclared elicitation mode, above) → error `-32601` with the same `id`.

*Source:* stakeholder ask A2, 2026-10-20; roadmap.md phase 3 row; mission.md non-goal
(no real LLM); amended by register row 2026-10-21, phase 3 build.

### D2 — Reacting to notifications

Every notification is printed. Beyond that: `notifications/tools/list_changed`,
`…/prompts/list_changed` and `…/resources/list_changed` make the client re-request the
matching list once (coalescing a burst that arrives before the re-list is sent);
`notifications/resources/updated` makes it re-read that URI; `notifications/progress` is
matched to the pending request by `progressToken`; `notifications/message` is printed with
its level and logger. The client sends `notifications/roots/list_changed` when its roots
change (the tour changes them once).

*Source:* stakeholder ask A2, 2026-10-20; roadmap.md phase 3 row.

### D3 — Capability flags and the matrix

`python3 -m client <mode> --caps <list>` declares exactly the listed client capabilities
in `initialize`, from `roots`, `sampling`, `elicitation` (form) and `elicitation-url`
(default for `server-tour`: all four; for `tour`: none). `python3 -m client matrix --
<server command…>` runs one short session per capability set (none, each one alone, all)
and prints a table: the capability set, the tools the server listed after the
`tools/list_changed` burst settled, and the server-initiated methods seen. The table is
printed, never committed (A5); the walkthrough explains what each capability adds, and
the e2e test checks the table's rows against D3's expectation: each gated tool appears
only with its capability.

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap
L10).

### D4 — The server tour

`python3 -m client server-tour -- <server command…>` declares all capabilities, then:
answers the server's `roots/list` sync after `initialized`; calls `get-roots-list`,
`trigger-sampling-request`, `trigger-elicitation-request`, `trigger-multi-step-elicitation`,
`trigger-url-elicitation`, `trigger-log-messages`, `trigger-list-changed` for each of
`tools`, `prompts`, `resources`; subscribes to a static resource and calls
`trigger-resource-update` on it; changes its roots and sends
`notifications/roots/list_changed`; waits for the resulting `roots/list`; and shuts down.
It exits 0 only if every step saw the server traffic it expects. `scripts/record.sh
--client server-tour [name]` records it (phase 2 D5).

*Source:* stakeholder ask A2, 2026-10-20; roadmap.md phase 3 row.

### D5 — Walkthrough and lesson 03

`docs/walkthrough/03-server-initiated.md` explains every frame of the server tour's fresh
trace (checked by `--explain`), including where the server's legacy shim turns a tool's
`input_required` into a real request, and the capability matrix. Because the message
order of server-initiated traffic can vary (the 350 ms roots sync, list-change bursts),
notes are keyed by identity (phase 1 D11), not position, and the e2e check accepts any
order the walkthrough's notes cover. `docs/lessons/03-server-initiated.md` has the L1
sections and runnable blocks (G9); `README.md` lists it.

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap
L1, L5, L10); per-phase walkthrough P3.

### D6 — The message atlas (moved here from phase 2)

`tools/atlas.py` generates `docs/atlas.md` from the pinned schemas of `2025-11-25` and
`2026-07-28` only (never from run output): one table row per method, with its kind
(request or notification), its direction (from membership in the schema's
`ClientRequest`, `ServerRequest`, `ClientNotification`, `ServerNotification` unions, and
`InputRequest` for the 2026-07-28 methods the server asks inside an `InputRequiredResult`), the
revisions that define it, and the lessons that declare it. A lesson declares the methods
it exercises in one line `<!-- exercises: <method>, <method>, … -->`; unexercised methods
are listed as such. The roadmap's "capability that gates it" column is not generated,
since the schemas do not encode it; it is an accepted limit. Gate G10 runs
`python3 tools/atlas.py --check`, which fails when the regenerated atlas differs from the
committed file or a lesson declares a method no schema defines. A lesson's declaration is
checked against a fresh trace of that lesson's recording in `tests/test_e2e.py`: every
declared method appears in it.

*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap
L8, G10); moved from phase 2 by register row 2026-10-21, atlas.

## Build order

1. Handlers and notification reactions with unit tests on fake servers (test first).
2. Server tour against the real server, recorded; capability flags; matrix.
3. The atlas (D6) is built in parallel with phase 2 on its own branch and merged first.
4. Walkthrough, lesson 03 with its `exercises` line, README; close (Result, CHANGELOG, tag `lesson-03`). No review
   round (LP4) unless claim code of phase 2 changes beyond its tests.

Builder: Sonnet, medium.

## Stop condition

Every C row passes, the gate is green locally and in CI, the server tour's fresh trace
passes `tap.check --revision 2025-11-25` and `--explain`.
