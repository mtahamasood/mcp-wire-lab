# Phase 1 — Wire tap (stdio) and learning scaffold: requirements

The question this phase answers: *what exactly crosses the pipe between an MCP client and
the everything server over stdio, and how does a learner come to read it?* It builds the
instrument (the tap and its viewer), the ground it stands on (repo, pinned server and
spec, gates, CI), and the learning scaffold every later phase reuses (lessons, verified
citations, runnable commands), then points all of it at a hand-written 2025-era handshake.

### D1 — The tap is a transparent stdio wrapper around the server command

Invoked as `python3 -m tap --trace <file> -- <server command…>`. It spawns the server
command as a child, copies its own stdin to the child's stdin and the child's stdout to its
own stdout, and writes a trace. Any client that launches a stdio server can launch the tap
instead, unchanged.

*Rationale:* observation must sit on the wire, outside both endpoints, so that the trace
records what was sent, not what either side thinks it sent, and so one instrument serves
the raw client, the SDK client, and anything else.
*Rejected:* logging inside each client (records intent, not the wire, and would differ per
client); a proxy built on the SDK (it parses and re-serializes, hiding the real framing);
MCP Inspector (third-party, does far more than observe — a non-goal).
*Cost accepted:* one more process in the path; if the tap mishandles buffering, EOF, or
exit codes, it changes the behavior it claims to observe (guarded by D2, D4 and their checks).
*Source:* stakeholder ask A2, 2026-10-20.

### D2 — Forwarding is byte-exact; parsing is for the trace only

The tap forwards bytes without decoding, re-encoding, or reframing them. It splits each
direction on `\n` only to cut trace records; the bytes forwarded are the bytes received,
including a final partial line with no trailing newline.

*Rationale:* the point of the instrument is to show the real framing; a tap that
normalizes JSON would hide exactly what A2 asks to see.
*Rejected:* parse-then-reserialize forwarding (changes key order, spacing and escapes);
line-buffered text-mode I/O (can translate newlines and decode).
*Cost accepted:* the tap cannot fix or annotate traffic in flight; all interpretation happens
after the fact, in the trace and the viewer.
*Source:* stakeholder ask A2, 2026-10-20.

### D3 — The trace is JSON Lines, one record per frame or event, on one timeline

Each record carries: `seq` (from 0, in the order the tap observed it), `t_ns` (monotonic
nanoseconds since the tap started), `dir` (`c2s`, `s2c`, `stderr`, or `tap`), `bytes`
(length of the raw frame including its newline), `raw` (the frame as text if it is valid
UTF-8; otherwise absent and `raw_b64` present), `json` (the parsed value if the frame is
valid JSON, else `null` plus a `parse_error` string), and `partial: true` on a final
frame with no newline. `tap` records mark `spawn` (with the argv) and `exit` (with the exit
code). The server's stderr is passed through to the tap's stderr and also recorded as
`stderr` frames.

*Rationale:* one timeline across both directions and stderr shows ordering, which is the
heart of "the entire flow" (A2); JSON Lines is greppable, `jq`-able, and appendable;
keeping `raw` beside `json` keeps the trace byte-faithful.
*Rejected:* separate files per direction (loses ordering); pcap-style binary (needs tools
to read); storing only parsed JSON (loses framing).
*Cost accepted:* traces are roughly twice the traffic size (raw + parsed), which is
acceptable at lab scale.
*Source:* stakeholder ask A2, 2026-10-20.

### D4 — The tap preserves the child's lifecycle

When the tap's stdin reaches EOF it closes the child's stdin and keeps relaying the child's
stdout and stderr until they close. SIGINT and SIGTERM are forwarded to the child. The tap
exits with the child's exit code (128 + signal number if the child was killed by a signal).

*Rationale:* a client that judges the server by its exit status or by EOF must see the
server's real behavior through the tap.
*Rejected:* killing the child at stdin EOF (would hide how the server actually shuts down,
which is itself something to measure).
*Cost accepted:* a server that never exits on EOF keeps the tap alive too; that is the
server's behavior, faithfully reproduced.
*Source:* stakeholder ask A2, 2026-10-20.

### D5 — A viewer renders a trace as a correlated timeline

`python3 -m tap.show <trace>` prints one line per record: `seq`, elapsed milliseconds, a
direction arrow, and for JSON-RPC messages the kind (request/response/notification/error),
`method`, and `id`. A response is paired with its request by `id` and per direction, not
by adjacency, and shows the request's `seq` and the latency. `--full` also pretty-prints
each message body.

*Rationale:* A2 asks to *see* requests and responses; a raw JSONL file shows bytes but
not which response answers which request once several are in flight.
*Rejected:* `jq` recipes alone (no correlation); an HTML viewer (parked in the backlog).
*Cost accepted:* a second tool to keep correct; its correlation logic needs its own
discriminating fixture (responses out of order).
*Source:* stakeholder ask A2, 2026-10-20.

### D6 — The pinned server is built from a fresh clone by one command

`vendor/servers` is a submodule at the commit pinned in `tech-stack.md`. `scripts/bootstrap.sh`
installs the server's dependencies from its own lockfile and builds the everything server,
producing `vendor/servers/src/everything/dist/index.js`. The submodule's working tree is
never modified.

*Rationale:* every source citation in a walkthrough must point at code that matches the
running binary.
*Rejected:* the published npm package (would mean reading compiled output, or a second
checkout that can drift from what runs).
*Cost accepted:* bootstrap installs the dependencies of the whole upstream npm workspace,
not just the everything server, unless measurement shows a narrower install works (M5).
*Source:* owner decision, 2026-10-20 — registered in mission.md (server source).

### D7 — One gate script, run locally and in CI

`scripts/gate.sh` runs G1–G5, G8, and G9 from `tech-stack.md` in order and stops at the
first failure.
`.github/workflows/ci.yml` checks out with submodules, sets up Node and Python, runs
`scripts/bootstrap.sh`, then `scripts/gate.sh`, on every push and pull request.
`tools/check_provenance.py` implements G1 (and G7): every `### D<n>` record in
`specs/phases/*/requirements.md` must carry a `*Source:*` line containing a `YYYY-MM-DD`
date and naming an ask `A<n>` that exists in `mission.md`, a register row whose date
exists in `mission.md`, or a constitution file; every phase directory with a `validation.md`
whose Result says closed must have a `CHANGELOG.md` entry. Missing inputs fail loudly.

*Rationale:* the field guide's rule — a rule in prose is not a gate — applied on day one to
the one rule this project already has (provenance).
*Rejected:* a third-party markdown linter (dependency, and it cannot check provenance);
CI-only gates (the owner must be able to run the same thing locally).
*Cost accepted:* about 100 lines of gate code that need their own seen-to-fail record.
*Source:* owner decision, 2026-10-20 — registered in mission.md (SDD; repo).

### D8 — The phase ships a walkthrough of the 2025-era handshake, checked against a fresh run

The fixture `tests/fixtures/handshake-2025.ndjson` holds hand-written `initialize`,
`notifications/initialized`, `tools/list`, and `ping` lines. `docs/walkthrough/01-handshake-2025.md`
explains every frame a run of that fixture produces: the spec section that governs it
(2025-11-25 revision) and the server or SDK source location that produced it (pinned
commit, file and line). No trace is committed (A5): the learner records their own with
`scripts/record.sh` (D14), and G5 records a fresh one on every gate run and requires
`tap.show --explain` to exit 0 on it (C14). Where the walkthrough shows a message, it is a
hand-written example with no environment-specific values (P9), checked by G9 against the
fresh run's output.

*Rationale:* the instrument is only worth its cost if it produces understanding (A1, A2);
the handshake is the first thing every connection does. Checking against a fresh run on
every gate proves the explanation still matches the pinned server, which a committed
trace could only prove once.
*Rejected:* deferring all walkthroughs to a final phase (see P3); committing the trace
the walkthrough explains (forbidden by A5; it also froze the docs to one recording).
*Cost accepted:* a reader browsing on GitHub sees the hand-written examples, not the full
trace, until they run the lesson; the fixture driver (D9) is the one place in this phase
that sends protocol messages, and must not grow into a client.
*Source:* stakeholder ask A2, 2026-10-20; A5, 2026-10-20 (no committed trace); per-phase
walkthroughs are proposal P3, valid only once the owner ratifies it.

### D9 — The fixture driver is not a client

`tests/drive.py` sends the lines of a fixture file through the tap one at a time. After each
line that carries an `id`, it reads stdout until a line with the same `id` arrives (or a
timeout passes), then sends the next. At the end it closes stdin. It never builds, inspects,
or decides on a message beyond matching `id`.

*Rationale:* the e2e gate and the walkthrough need deterministic traffic; sending the whole
fixture at once and closing stdin would race the server's shutdown against its replies.
*Rejected:* using the raw client (that is phase 2); `sleep`-based pacing (flaky).
*Cost accepted:* responses that the server sends unprompted (notifications) are relayed but
not waited for; the trace records whatever arrives.
*Source:* stakeholder ask A2, 2026-10-20.

### D10 — The pinned spec is a second submodule

`vendor/spec` is a submodule of `modelcontextprotocol/modelcontextprotocol` at the commit
pinned in `tech-stack.md`, and `scripts/bootstrap.sh` checks both submodules are at their
pins. The walkthrough cites spec text from it; later phases read schemas from it.

*Rationale:* spec citations must be as stable as source citations, and a learner must be
able to read the normative text offline at the exact revision the traces were made with.
*Rejected:* linking to modelcontextprotocol.io (pages move and change under the link);
copying spec files in (loses provenance and history).
*Cost accepted:* a second submodule to clone (measured in M5).
*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap
L6); the pin itself is proposal P7.

### D11 — The viewer draws the flow and explains it

`python3 -m tap.show <trace> --mermaid` prints a Mermaid `sequenceDiagram` with
participants `Client` and `Server`, one arrow per JSON-RPC message in `seq` order (solid
for requests and notifications, dashed for responses, labeled with `method` or
`id`), and stderr and `tap` records as notes. `--explain <walkthrough.md>` prints each frame
followed by its walkthrough note. A note is keyed by message identity, written as an anchor
`<dir>.<method-or-response>.<id-or-occurrence>` (e.g. `c2s.initialize.0`, `s2c.response.0`,
`s2c.notifications/message.1` for the second such notification); `stderr` and `tap`
records are keyed by occurrence. It prints `(no note)` for a frame with none and
`(no frame)` for a note that matches nothing, and exits non-zero on either.

*Rationale:* a sequence diagram is how protocol engineers draw flows, and GitHub renders
Mermaid natively; the explanation is most useful next to the bytes it explains. The
non-zero exit turns "every frame has an entry" (J1) into a check.
*Rejected:* hand-drawn diagrams (drift from the trace); generating images (needs a renderer
dependency).
*Cost accepted:* identity keys tolerate timing and interleaving changes but not a change in
what is sent; traffic the server emits unprompted and in varying number (e.g. simulated
log notifications) must be keyed by occurrence with a note that covers "any number", or
the check flaps.
*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap L5;
amended by A5 to identity keys).

### D12 — Lesson 01 and the learning path

`README.md` states what the repo is for and who it is for, the prerequisites, the bootstrap
commands, and the ordered lesson list. `docs/lessons/01-the-wire-and-the-handshake.md` has the
L1 sections: *Goal* (what crosses stdio, and the 2025 handshake); *Predict* (the reader
writes down what they expect the server to answer before running); *Run* (`scripts/record.sh`
with the fixture, into the learner's own `runs/`); *Read the trace* (`tap.show`, `--mermaid`, `--explain`); *Read the source* (the
stdio transport and `initialize` handling, cited); *Experiments* (at least three: change the
offered `protocolVersion`, drop `notifications/initialized`, send `tools/list` before
`initialize` — each a fixture the learner records and reads, with the outcome measured at
the pins stated in the lesson); *Check yourself* (questions answered by
the trace, with answers in a collapsed block). Phase close tags `lesson-01`.

*Rationale:* A4 widens the audience to learners who were not in this conversation; the
lesson is their way in, and predict-then-observe is the method A2's reader already uses.
*Rejected:* a README-only tutorial (cannot grow per phase); video or slides (not checkable).
*Cost accepted:* experiment outcomes are measurements taken on this phase's walk; the
lesson must say they were measured at the pins, not promised by the spec.
*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap
L1, L4, L14).

### D13 — Citations and lesson commands are gated

`tools/check_citations.py` (G8) finds every citation of the form in `tech-stack.md` in
`README.md`, `docs/`, and `tap/`, and fails, naming the citation, if the submodule file is
missing, the line does not exist, or the fragment is not on that line.
`tools/check_lessons.py` (G9) fails if a lesson lacks an L1 section, runs each block marked
runnable from the repo root with a timeout, and fails on a non-zero exit or an expected
block that does not appear in the output. Both fail loudly on missing inputs and are wired
into `scripts/gate.sh`.

*Rationale:* the first two citations written for this project were both wrong (incident
recorded in `tech-stack.md`, 2026-10-20); a learner who follows a dead command or line stops
learning.
*Rejected:* checking citations by hand at review (the incident shows it fails); link-checker
tools (they check URLs, not line content).
*Cost accepted:* lessons must avoid commands whose output is nondeterministic, or match it
only on stable fragments; runnable blocks lengthen `scripts/gate.sh`.
*Source:* owner decision, 2026-10-20 — registered in mission.md (A4, delegated; roadmap
L3, L4).

### D14 — One recording script, with a minimal environment

`scripts/record.sh <fixture> [name]` creates `runs/<UTC timestamp>-<name>/`, runs the tap
with D9's driver over the fixture against the pinned server, and writes `trace.jsonl` and
`stderr.txt` there, then prints the `tap.show` commands to read it. The server is started
under `env -i` with only an allowlist: a fixed `PATH` (the directory of the `node` found at
bootstrap, plus `/usr/bin:/bin`), `HOME` set to an empty directory inside the run folder,
`LANG=C.UTF-8`, and `MCP_WIRE_LAB=1`. The tap's `spawn` record shows argv relative to the
repo root. `runs/` is in `.gitignore`. G5, the lessons, and the learner walk all record
through this script.

*Rationale:* the learner's own run replaces every committed trace (A5) at one command's
cost; the minimal environment keeps the learner's secrets out of the trace even when they
share it, and makes environment-dependent output (e.g. `get-env`) identical on every
machine, so a lesson can show it.
*Rejected:* letting the server inherit the shell environment (leaks, and makes output
machine-specific); scrubbing traces after recording (a scrubber misses what it was not
told about; not recording the secret is stronger).
*Cost accepted:* a server feature that needs a variable from the user's environment will
not see it until the allowlist names it; the allowlist is part of each phase's spec.
*Source:* A5, 2026-10-20; owner decision, 2026-10-20 — registered in mission.md (A4,
delegated; roadmap L16).

### D15 — Run output cannot reach git

`tools/check_no_run_output.py` implements G11 exactly as written in `tech-stack.md`, over
`git ls-files` (and, as the pre-push hook, over the commits being pushed). Every hand-written
trace fixture opens with a `{"dir":"tap","event":"synthetic"}` record. `scripts/bootstrap.sh`
installs `.git/hooks/pre-push` running it, and refuses to overwrite a different existing hook.
The learner walk (L15) runs in a directory outside the repo; only the agent's written list
of findings is committed.

*Rationale:* standing law 1. On a public repo, CI runs after the push, so the hook is the
gate that actually prevents publication; CI catches a push made without the hook.
*Rejected:* `.gitignore` alone (`git add -f` and new paths bypass it); CI alone (too late).
*Cost accepted:* hooks are per-clone and skippable with `--no-verify`; CI is the backstop,
and the law's admitted limit (pattern-based recognition) is signed in `tech-stack.md`.
*Source:* A5, 2026-10-20 — standing law 1 in specs/tech-stack.md.

### D16 — Nothing else is added

Declined for this phase: an HTTP tap (phase 7); modifying, filtering, injecting, delaying,
or replaying messages (the fault mode is phase 4); schema validation (phase 2); the atlas
(phase 2); manual mode or any raw client beyond D9's driver (phase 2); an HTML viewer;
using the MCP SDK anywhere in the tap or gates; third-party runtime dependencies; any
change inside `vendor/servers` or `vendor/spec`; Claude Code or other real-world clients
(backlog); Docker or a devcontainer (a non-goal); packaging or releases; committing or
otherwise publishing any run output, including CI artifacts (A5); the 2026-07-28 era,
except as recorded measurement.

*Source:* constitution clause — specs/roadmap.md, phase 1 row and backlog, 2026-10-20.

## Open questions for the owner

- **Q1 (answered 2026-10-20: all ratified, none struck; registered in `mission.md`):** Ratify or overrule P1–P9 in `mission.md`, and strike any of L1–L16 in
  `roadmap.md` you do not want. D8 depends on P3 and P9; D10 on P7; the stack on P1, P2,
  P4–P6.
- **Q2–Q4:** answered 2026-10-20 and registered in `mission.md`: Node 24 via `nvm`; lessons
  assume JSON, the command line, and reading Python or TypeScript, and teach JSON-RPC 2.0
  and MCP from zero; no devcontainer.
