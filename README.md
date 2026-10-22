# mcp-wire-lab

A hands-on lab for learning the Model Context Protocol by watching it. A small tap sits between
an MCP client and a real, pinned MCP server, records every byte that crosses the connection,
and a viewer replays the recording with the spec section and the server source behind each
frame. You learn by predicting what the wire will carry, recording it, and reading what it did.

It is for anyone who wants to understand MCP below the SDK: how a connection opens, what each
message means, and where the spec and a real implementation agree or differ. Nothing here is a
client or a server you would ship.

## Start here

1. Set up once (below): clone, then `scripts/bootstrap.sh`.
2. Open [lesson 01](docs/lessons/01-the-wire-and-the-handshake.md) and do the lessons in order.
   Each one has the same shape: *Goal*, *Predict* (write your answers down first), *Run*,
   *Read the trace*, *Read the source*, *Experiments*, *Check yourself*. Every command in a
   lesson is meant to be pasted at the repository root.
3. If you only want to poke at it, jump to *Record and read a trace* below.

The answers to a lesson's *Predict* and *Check yourself* questions sit at the end of the same
file, inside a collapsed `<details>` block on GitHub. In a terminal or an editor they are plain
text, so stop reading at the heading *Answers* until you have written your own.

A lesson's commands print what the lesson says they print; `scripts/gate.sh` checks that.
After setup nothing needs a network, and the lessons write only inside this folder (setup itself uses npm's cache in your home folder).

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
specification) and builds the server, then installs the SDK client's npm packages (`clients/sdk/`, lesson 05). The pins are why line numbers cited in the lessons stay true. `npm` may report high-severity
vulnerabilities while it installs; that is expected for a pinned reference server that only ever
runs locally under the tap, and nothing here is exposed. Bootstrap may also warn that
`core.hooksPath` is set, so git might not run the repo's pre-push hook; that matters only if you
push, and it is safe to ignore otherwise.

If bootstrap stops, it says why in one line. The common causes are in *Troubleshooting* below.

Citations in the docs look like `servers:path:line "fragment"` or `spec:path:line "fragment"`.
`servers:` means under `vendor/servers/` and `spec:` means under `vendor/spec/`; the quoted
fragment is the text you should find on that line.

## Record and read a trace

```console
scripts/record.sh tests/fixtures/handshake-2025.ndjson
python3 -m tap.show <the path it printed>
```

`record.sh` prints the path of the recording, ending in `trace.jsonl` (and a ready `read it:` line
to copy); put that path where `<the path it printed>` stands.

To record the raw client instead of a fixture, use `scripts/record.sh --client tour` (or
`--client manual` to type messages yourself), and validate a recording against the spec's schema
with `python3 -m tap.check <the path> --revision 2025-11-25`.

`python3 -m tap.show` also takes `--full` (every frame's decoded JSON, pretty-printed), `--mermaid` (a sequence diagram) and
`--explain <walkthrough.md>` (a note after every frame). A walkthrough that explains several
experiments has one section per experiment: add `#<section>`, as in
`--explain docs/walkthrough/04-edge-lab.md#unknown-method`. A wrong section name lists the right ones.

Reading a trace line: `->` is the client's frame, `<-` the server's, `!!` the server's stderr and
`..` an event of the tap itself (spawn, exit, an injected fault). The number on the left is the
frame's `seq`; walkthrough notes and citations refer to frames by it.

To compare two recordings (the lessons' "change it, predict the difference" experiments), strip the
timings and diff the decoded frames; no output means they are identical:

```console
strip() { python3 -m tap.show "$1" --full | sed -E 's/^ *[0-9]+ +[0-9.]+ ms +//; s/, [0-9.]+ ms\)/)/; s#runs/[^/ ]+#runs/X#g'; }
diff <(strip runs/<first>/trace.jsonl) <(strip runs/<second>/trace.jsonl)
```

Recordings go to `runs/`, which git ignores. This repository never holds run output: your traces
stay on your machine. Nothing runs at commit time: the pre-push hook refuses a push that would
publish one, and `scripts/gate.sh` fails if one is tracked.

## The tools, in one place

Every command prints a usage text with `--help` (or `-h`). With a wrong or missing argument it
prints the same text on stderr and exits non-zero.

| Command | What it does |
| --- | --- |
| `scripts/bootstrap.sh` | Checks Node and the two pinned submodules, builds the reference server, installs the SDK client's packages. Run once. |
| `scripts/record.sh <fixture> [name]` | Plays a scripted conversation from `tests/fixtures/` through the tap against the real server; prints the trace path. |
| `scripts/record.sh --client <tour\|manual\|server-tour\|sdk-tour\|sdk-server-tour> [name]` | The same, with a client as the conversation: the raw Python client, or (`sdk-…`) the TypeScript SDK client. `manual` reads your typed lines on stdin; in a terminal, end it with `:quit` or Ctrl-D. |
| `python3 -m tap.show <trace> [--full\|--mermaid\|--explain <file>]` | Reads a trace: one line per frame, with replies paired to their requests and latencies. |
| `python3 -m tap.check <trace> --revision 2025-11-25` | Validates every frame against the spec's JSON Schema. |
| `python3 -m tap.diff <trace-a> <trace-b> [--explain <file>]` | Compares two traces message by message (ids normalised) and lists what differs (lesson 05). |
| `python3 -m tap --trace <file> [--delay\|--drop ...] -- <server command>` | The tap itself, for when you want to put it in front of your own command. `--drop` and `--delay` inject faults (lesson 04). |
| `python3 -m client <tour\|manual\|server-tour\|matrix> -- <server command>` | The raw client without the tap. `--caps` chooses the capabilities it declares. |
| `node clients/sdk/src/main.ts <tour\|server-tour> -- <server command>` | The SDK client without the tap. `--caps` chooses the capabilities it declares. |
| `scripts/gate.sh` | Every automated check; needs `uv`. Contributors run it before a commit. |

## What is where

- `docs/lessons/`, `docs/walkthrough/`: the lessons and the frame-by-frame notes. `docs/atlas.md` is a generated table of every protocol method.
- `tap/`: the recorder (`python3 -m tap`), the viewer (`tap.show`), the schema checker (`tap.check`) and the trace diff (`tap.diff`).
- `client/`: the raw client, in small files. The lessons say which to read.
- `clients/sdk/`: the SDK client (TypeScript, run as source by Node), lesson 05.
- `tests/`: unit and end-to-end tests, plus `tests/fixtures/` (the scripted conversations).
- `vendor/`: the pinned reference server and the specification, as git submodules.
- `runs/`: your recordings (created on first use; git ignores it).
- `specs/`, `audits/`: why the project is built the way it is, and its review records. You do not need them to do the lessons.

## Troubleshooting

- `need node v24.22.0`: install it with `nvm install 24.22.0 && nvm use 24.22.0`, then run bootstrap again.
- `... is not checked out` or `... is at <sha>, expected <sha>`: run `git submodule update --init --recursive`.
- `record: .../index.js missing (run scripts/bootstrap.sh)`: you have not run bootstrap, or it failed.
- `record: no such fixture`: the path is relative to the repo root; fixtures are in `tests/fixtures/`.
- A lesson's output differs from its `expect` block: you are probably on a different commit than the
  submodule pins, or edited a tracked file; `git status` shows it. Undo your edit with `git checkout <file>`.
- `scripts/gate.sh` says `uvx: command not found`: install [`uv`](https://docs.astral.sh/uv/). Only the gate needs it.
- To start over, delete `runs/`; it holds nothing else.

## Status

Lessons 01 to 05 are built and checked. Phases 6 and 7 (the 2026 protocol era,
Streamable HTTP) are written up in `specs/` but not built. Your feedback on the lessons is
welcome as a GitHub issue.

## Lessons

Do them in order.

1. [The wire and the handshake](docs/lessons/01-the-wire-and-the-handshake.md): what crosses
   stdio, the 2025 opening exchange, and three ways to break it.
   Walkthrough: [the handshake, frame by frame](docs/walkthrough/01-handshake-2025.md).
2. [A client with no library](docs/lessons/02-raw-client.md): a raw Python client speaks MCP over
   stdio, you check its recording against the spec's JSON Schema, then type messages by hand.
   Walkthrough: [the raw client's tour, frame by frame](docs/walkthrough/02-raw-client-tour.md).
3. [When the server speaks first](docs/lessons/03-server-initiated.md): the raw client answers the
   server's requests (roots, sampling, elicitation), reacts to its notifications, and you read
   which client capability unlocks what.
   Walkthrough: [the server tour, frame by frame](docs/walkthrough/03-server-initiated.md).
4. [The edge lab](docs/lessons/04-edge-lab.md): malformed and out-of-order messages, what the
   server answers against what the spec says, and losing a message at the tap.
   Walkthrough: [the edge experiments](docs/walkthrough/04-edge-lab.md).

5. [What an SDK hides](docs/lessons/05-sdk-client.md): the same tour through the official
   TypeScript SDK, a message-by-message diff of the two traces, and one request followed through
   the SDK's source.
   Walkthrough: [the SDK client](docs/walkthrough/05-sdk-client.md).

More lessons arrive with later phases; [`specs/roadmap.md`](specs/roadmap.md) lists what each
phase adds.

## How it is checked

`scripts/gate.sh` (about two minutes; it is not hung) runs every automated check: the provenance of each recorded decision (G1), lint
and type checks (G2, G3), the unit and end-to-end tests (G4, G5), a check that every
`servers:path:line "fragment"` citation in the docs resolves in the pinned source (G8), a check that
every runnable block in a lesson runs and prints what the lesson says it prints (G9), a check
that no run output is tracked (G11), and a check that every test a validation row names exists (G12). Some things are not checked by any gate: see the Result in
[`specs/phases/01-wire-tap/validation.md`](specs/phases/01-wire-tap/validation.md).

The reasoning behind the project lives in [`specs/`](specs/).

## Licence

This repository's own content is under the MIT licence: see [`LICENSE`](LICENSE). The
submodules under `vendor/` are upstream projects and keep their own licences.
