# mcp-wire-lab

A hands-on lab for learning the Model Context Protocol by watching it. A small tap sits between
an MCP client and a real, pinned MCP server, records every byte that crosses the connection,
and a viewer replays the recording with the spec section and the server source behind each
frame. You learn by predicting what the wire will carry, recording it, and reading what it did.

It is for anyone who wants to understand MCP below the SDK: how a connection opens, what each
message means, and where the spec and a real implementation agree or differ. Nothing here is a
client or a server you would ship.

## What you need

- Linux or WSL (tested); macOS untested. You need `bash`, `git` and `python3` (3.12 or newer)
- Node `v24.22.0`, exactly (`scripts/bootstrap.sh` checks); `npm`
- [`uv`](https://docs.astral.sh/uv/) for the lint and type gates (only needed to run `scripts/gate.sh`)

## Set up

```console
git clone --recurse-submodules https://github.com/mtahamasood/mcp-wire-lab
cd mcp-wire-lab
scripts/bootstrap.sh
```

The bootstrap checks both submodules are at their pinned commits (the reference server and the
specification) and builds the server. The pins are why line numbers cited in the lessons stay true. `npm` may report high-severity
vulnerabilities while it installs; that is expected for a pinned reference server that only ever
runs locally under the tap, and nothing here is exposed.

Citations in the docs look like `servers:path:line "fragment"` or `spec:path:line "fragment"`.
`servers:` means under `vendor/servers/` and `spec:` means under `vendor/spec/`; the quoted
fragment is the text you should find on that line.

## Record and read a trace

```console
scripts/record.sh tests/fixtures/handshake-2025.ndjson
python3 -m tap.show <the path it printed>
```

To record the raw client instead of a fixture, use `scripts/record.sh --client tour` (or
`--client manual` to type messages yourself), and validate a recording against the spec's schema
with `python3 -m tap.check <the path> --revision 2025-11-25`.

`record.sh` prints that path ending in `trace.jsonl` (and a ready `read it:` line to copy).

`python3 -m tap.show` also takes `--full` (every frame's decoded JSON, pretty-printed), `--mermaid` (a sequence diagram) and
`--explain <walkthrough.md>` (a note after every frame).

Recordings go to `runs/`, which git ignores. This repository never holds run output: your traces
stay on your machine. Nothing runs at commit time: the pre-push hook refuses a push that would
publish one, and `scripts/gate.sh` fails if one is tracked.

## Lessons

Do them in order.

1. [The wire and the handshake](docs/lessons/01-the-wire-and-the-handshake.md): what crosses
   stdio, the 2025 opening exchange, and three ways to break it.
   Walkthrough: [the handshake, frame by frame](docs/walkthrough/01-handshake-2025.md).
4. [The edge lab](docs/lessons/04-edge-lab.md): malformed and out-of-order messages, what the
   server answers against what the spec says, and losing a message at the tap.
   Walkthrough: [the edge experiments](docs/walkthrough/04-edge-lab.md).

2. [A client with no library](docs/lessons/02-raw-client.md): a raw Python client speaks MCP over
   stdio, you check its recording against the spec's JSON Schema, then type messages by hand.
   Walkthrough: [the raw client's tour, frame by frame](docs/walkthrough/02-raw-client-tour.md).

More lessons arrive with later phases; [`specs/roadmap.md`](specs/roadmap.md) lists what each
phase adds.

## How it is checked

`scripts/gate.sh` runs every automated check: the provenance of each recorded decision (G1), lint
and type checks (G2, G3), the unit and end-to-end tests (G4, G5), a check that every
`servers:path:line "fragment"` citation in the docs resolves in the pinned source (G8), a check that
every runnable block in a lesson runs and prints what the lesson says it prints (G9), a check
that no run output is tracked (G11), and a check that every test a validation row names exists (G12). Some things are not checked by any gate: see the Result in
[`specs/phases/01-wire-tap/validation.md`](specs/phases/01-wire-tap/validation.md).

The reasoning behind the project lives in [`specs/`](specs/).

## Licence

This repository's own content is under the MIT licence: see [`LICENSE`](LICENSE). The
submodules under `vendor/` are upstream projects and keep their own licences.
