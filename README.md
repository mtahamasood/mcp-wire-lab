# mcp-wire-lab

A hands-on lab for learning the Model Context Protocol by watching it. A small tap sits between
an MCP client and a real, pinned MCP server, records every byte that crosses the connection,
and a viewer replays the recording with the spec section and the server source behind each
frame. You learn by predicting what the wire will carry, recording it, and reading what it did.

It is for anyone who wants to understand MCP below the SDK: how a connection opens, what each
message means, and where the spec and a real implementation agree or differ. Nothing here is a
client or a server you would ship.

## What you need

- Linux, macOS or WSL, with `bash`, `git` and `python3` (3.12 or newer)
- Node `v24.22.0`, exactly (`scripts/bootstrap.sh` checks); `npm`
- [`uv`](https://docs.astral.sh/uv/) for the lint and type gates (only needed to run `scripts/gate.sh`)

## Set up

```console
git clone --recurse-submodules https://github.com/mtahamasood/mcp-wire-lab
cd mcp-wire-lab
scripts/bootstrap.sh
```

The bootstrap checks both submodules are at their pinned commits (the reference server and the
specification) and builds the server. The pins are why line numbers cited in the lessons stay true.

## Record and read a trace

```console
scripts/record.sh tests/fixtures/handshake-2025.ndjson
python3 -m tap.show runs/<the folder it printed>/trace.jsonl
```

`python3 -m tap.show` also takes `--full` (whole bytes), `--mermaid` (a sequence diagram) and
`--explain <walkthrough.md>` (a note after every frame).

Recordings go to `runs/`, which git ignores. This repository never holds run output: your traces
stay on your machine, and `scripts/gate.sh` fails if one is about to be committed.

## Lessons

Do them in order.

1. [The wire and the handshake](docs/lessons/01-the-wire-and-the-handshake.md): what crosses
   stdio, the 2025 opening exchange, and three ways to break it.
   Walkthrough: [the handshake, frame by frame](docs/walkthrough/01-handshake-2025.md).

More lessons arrive with later phases; [`specs/roadmap.md`](specs/roadmap.md) lists what each
phase adds.

## How it is checked

`scripts/gate.sh` runs every automated check: the unit and end-to-end tests, a check that every
`servers:path:line "fragment"` citation in the docs resolves in the pinned source, and a check that
every runnable block in a lesson runs and prints what the lesson says it prints.

The reasoning behind the project lives in [`specs/`](specs/).
