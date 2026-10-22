# Changelog

All notable changes to this repository are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project publishes no releases;
each phase ends with a git tag named after its lesson (`lesson-NN`) instead of a version number.

## [Unreleased]

### Added

- Phase 5, SDK client (`specs/phases/05-sdk-client/`): `clients/sdk/`, the raw client's tour and
  server tour through `@modelcontextprotocol/client` 2.3.1 (TypeScript, run as source);
  `scripts/record.sh --client sdk-tour|sdk-server-tour`; `tap.diff`, a message-by-message trace
  diff with `--explain`; G3 `tsc`, G4 `node --test` and a G8 `sdk` citation root; lesson 05 and
  walkthrough 05; `scripts/bootstrap.sh` installs the SDK client's packages.

- Phase 6, the 2026-07-28 era in both clients (`specs/phases/06-era-2026/`): the raw client's
  `--era 2026-07-28` (`tour`, `tasks`, `manual`; `client/modern.py`), `tap.check`'s
  `input_required` rule and the SEP-2663 tasks extension schema, the SDK client's `--era` option
  and 2026 tour (`clients/sdk/src/era.ts`, on a member-less subclass of `StdioClientTransport` so
  the `server/discover` probe stays on one connection),
  `scripts/record.sh --client tour-2026|tasks-2026|manual-2026|sdk-tour-2026`; lesson 06 and
  walkthroughs 06 and 06b (the raw-vs-SDK diff of the new era); G12 now covers phase 06.

- Phase 7, Streamable HTTP (`specs/phases/07-streamable-http/`): the tap's HTTP mode
  (`python3 -m tap --http`, `tap/http.py`: a recording reverse proxy in front of a server on a
  private Unix socket) and `scripts/record.sh --http`; the raw client over HTTP
  (`client/http_wire.py`, `client/http_tour.py`, `--url` for `tour`, `server-tour` and `manual`,
  and `client/modern_http.py` for the 2026-07-28 era), the SDK client's `--url` in both eras;
  `tap.show` summaries of HTTP records; lesson 07 and walkthrough 07; G5 gains
  `tests.test_e2e_http` and G12 now covers phase 07. The SDK's server tour over HTTP is not
  recorded: its transport opens the GET stream too late for the server's first notifications
  (explained in lesson 07).

### Changed

- `-h` / `--help` on `tap`, `tap.show`, `tap.check`, `client`, `record.sh`, `bootstrap.sh` and
  `gate.sh` prints the usage on stdout and exits 0 (the two setup scripts no longer run on an
  unknown argument either); the usage texts explain every option.
- README: *Start here*, a tools table, *What is where*, *Troubleshooting*, *Status*, a recipe for
  comparing two recordings, and a note about the answers in the lessons.

- `tap.show --explain file.md#name` with a section the file does not have now lists the sections
  it does have.
- Lessons 02 to 04 and the README fixed after a learner walk (`audits/learner-walk-lessons-02-04.md`):
  Predict answers, clearer experiments (lesson 04 lists fixture and section names together and
  drops the unrunnable `oversized-frame`), revert steps after edits, notes on the gate time and
  the bootstrap `core.hooksPath` warning.

## [lesson-03] - 2026-10-21

Phase 3, raw client: server-initiated traffic (`specs/phases/03-server-initiated/`). It answers:
what does the server ask of the client, and how do the capabilities a client declares decide it?

### Added

- `client/handlers.py`: replies to `roots/list`, `sampling/createMessage` (canned content),
  `elicitation/create` (form values from the schema; URL mode declined) and `ping`, each with
  the request's own `id`, from a worker thread; undeclared capabilities refused.
- Reactions to notifications: one coalesced re-list per `list_changed` burst, a re-read on
  `resources/updated`, progress matched by token, log messages printed.
- `python3 -m client server-tour`, `--caps`, and `python3 -m client matrix` (the capability
  matrix, printed and never committed); `scripts/record.sh --client server-tour`.
- Walkthrough `docs/walkthrough/03-server-initiated.md` and lesson 03.
- The message atlas `docs/atlas.md`, generated from the pinned schemas by `tools/atlas.py`
  and checked by gate G10; lessons declare the methods they exercise.

## [lesson-02] - 2026-10-21

Phase 2, raw client, client-initiated (`specs/phases/02-raw-client/`). It answers: what does it
take to speak MCP over stdio with no library at all?

### Added

- The raw client `client/`: newline-delimited JSON-RPC framing, replies matched to requests
  by shape and exact `id`, the 2025 lifecycle (initialize, initialized, shutdown), cancellation.
- `python3 -m client tour` (every client-initiated method the server offers) and
  `python3 -m client manual` (type or build messages by hand); `scripts/record.sh --client`.
- `python3 -m tap.check`: validates every frame of a trace against the pinned schema with a
  stdlib validator.
- Gate G12: every validation row's named checks exist.
- Walkthrough `docs/walkthrough/02-raw-client-tour.md` with a source tour of `tools/call`, and
  lesson 02.

### Fixed

- Review findings P2-R1 to P2-R9 (`audits/phase-02-review.md`): a malformed reply no longer
  stops the reader, writes no longer hold the pending-table lock, a closed wire fails requests
  at once, timeouts cancel, and the schema check and G12 close their gaps.

## [lesson-04] - 2026-10-21

Phase 4, edge lab (`specs/phases/04-edge-lab/`). It answers: what does the everything server do
with malformed and out-of-order traffic, and where does that follow, tighten or loosen the spec?

### Added

- Eight edge experiments as fixtures (`tests/fixtures/edge-*.ndjson`, plus phase 1's
  `exp-list-first` and a 1 MiB frame generated by its test), each recorded fresh and explained
  in `docs/walkthrough/04-edge-lab.md` with a verdict: follows the spec, looser, or spec silent.
- Tap fault mode: `--delay <dir>:<ms>` and `--drop <dir>:<method>`, each fault on the trace's
  timeline as a `fault` record; without them the tap is unchanged.
- The driver's `_drive` member (`expect: none`, `wait_ms`) for messages that get no reply.
- Lesson 04, `docs/lessons/04-edge-lab.md`.

### Changed

- `tap.show --explain <file>#<section>` with a `## shared` section and range anchors such as
  `stderr.1-106`.
- `scripts/record.sh` finishes a fixture recording when the server exits non-zero, with a warning.

## [lesson-01] - 2026-10-21

Phase 1, wire tap (stdio) and learning scaffold (`specs/phases/01-wire-tap/`). It answers: what
exactly crosses the pipe between an MCP client and the everything server over stdio, and how
does a learner come to read it?

### Added

- `vendor/servers` (the everything server) and `vendor/spec` (the MCP specification) as
  submodules at fixed pins; `scripts/bootstrap.sh` checks the pins, builds the server and
  installs the pre-push hook.
- The wire tap, `python3 -m tap`: a transparent stdio wrapper that forwards bytes unchanged
  and writes a JSON Lines trace (every frame, the server's stderr, spawn and exit) with mode 0600.
  It keeps the child's exit code and forwards SIGINT, SIGTERM, SIGHUP and SIGQUIT. If the trace
  cannot be written, it keeps forwarding.
- The viewer, `python3 -m tap.show`: a timeline that pairs responses with requests by `id`, with
  `--full`, `--mermaid` (a sequence diagram) and `--explain <walkthrough>` (a note after every frame).
- `scripts/record.sh`: records a fixture against the built server into `runs/<timestamp>-<name>/`,
  with the server under a minimal environment (`PATH`, `HOME`, `LANG`, `MCP_WIRE_LAB` only).
- Walkthrough `docs/walkthrough/01-handshake-2025.md`: each frame of the 2025-era handshake with the
  spec section and server source line behind it.
- Lesson 01, `docs/lessons/01-the-wire-and-the-handshake.md`: predict, run, read the trace, read the
  source, three experiments (another `protocolVersion`, no `notifications/initialized`, `tools/list`
  before `initialize`), and check-yourself questions.
- `scripts/gate.sh`, run locally and in GitHub Actions CI: provenance (G1), ruff (G2), mypy
  `--strict` (G3), unit tests (G4), end-to-end against the real server (G5), the CHANGELOG check (G7),
  citations (G8), runnable lesson blocks (G9) and no run output in git (G11).
- `LICENSE` (MIT) for the repository's own content.

### Security

- Run output never reaches git: `runs/` is ignored, G11 rejects tracked traces, environment dumps,
  home-directory paths and secret-shaped strings, and the pre-push hook runs G11 over every pushed
  commit.

[Unreleased]: https://github.com/mtahamasood/mcp-wire-lab/compare/lesson-01...HEAD
[lesson-01]: https://github.com/mtahamasood/mcp-wire-lab/tree/lesson-01
