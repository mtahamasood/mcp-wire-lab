# Closing review: trace viewer `tap/show.py` and checks C9, C13, C14 (branch phase-01-wire-tap)

Reviewer: Opus, fresh session, independent of the builder (Sonnet, plan group 5). The two other
review files in `audits/` were not read.

## 1. Scope and what I ran

Read: `specs/tech-stack.md` (gates and standing laws), `specs/phases/01-wire-tap/requirements.md`
in full (D5, D11, D14, D15, D16 matter most here), `validation.md` in full (C9, C13, C14 and their
recorded mutations), `plan.md` groups 5 and 8, `tap/show.py`, `tests/test_show.py`, `tests/test_e2e.py`,
`tests/fixtures/out-of-order.jsonl` and the three `walkthrough-*.md` fixtures, the intro, headings and
viewer-related notes of `docs/walkthrough/01-handshake-2025.md`, the "Read the trace" part of lesson
01, `scripts/record.sh`, the trace writer in `tap/__main__.py`, `tools/check_no_run_output.py`, and
`audits/learner-walk-lesson-01.md` for format. I skimmed but did not read in full `specs/mission.md` and
`specs/roadmap.md`. I did not read `audits/rest-review.md` or `audits/tap-review.md`.

Ran, all in a scratch copy of `tap tests tools scripts specs docs README.md pyproject.toml` with
`vendor/` symlinked (there is no top-level `node_modules/`), one test process at a time:
- `python3 -m unittest tests.test_show -v`: 7 tests, OK (baseline, and again after every restore).
- About 30 hand-made traces and walkthroughs fed to `python3 -m tap.show` in plain, `--full`,
  `--mermaid` and `--explain` modes, plus 5 traces recorded through the real tap (`python3 -m tap
  --trace ... -- <child>`) with `cat` or a short Python child, to get the tap's own encoding.
- markdown-it-py 3.0.0 (already installed) to render one `--mermaid` output inside a Markdown fence (S5).
- 21 mutations of `tap/show.py` through a small harness, each followed by `tests.test_show` (section 3).
- `tests.test_e2e.E2ETest.test_c14_explain_covers_a_fresh_run` 9 times in the scratch copy: 4 runs of
  which 3 failed for an unrelated reason (S17), then 5 valid runs (baseline and 4 mutants).
- In the real repo, once: `python3 -m unittest tests.test_e2e -v`, 3 tests OK (writes only to the
  git-ignored `runs/`).

Not done: `scripts/gate.sh` was not run (G11 was run on its own, see section 5); Mermaid itself was not
rendered (no network), so the effect of directives or HTML inside a diagram is unverified; the terminal
effect of the escape sequences in S4 was inferred from `cat -v`, not seen on a live terminal; no trace
larger than 20000 records was tried, so memory use on very large traces is untested.

## 2. Findings

Each finding was reproduced in the scratch copy (paths below are relative to it; `w/` is a scratch
work folder). Line numbers are `tap/show.py` at commit 6659123.

### S1 (major, CONFIRMED): a U+2028, U+2029 or U+0085 anywhere in a frame makes the whole trace unreadable

- Location: `tap/show.py:44` (`load`, `.splitlines()`).
- Defect: the tap writes records with `json.dumps(..., ensure_ascii=False)` (`tap/__main__.py:71`),
  which leaves U+2028, U+2029 and U+0085 unescaped inside strings, and `str.splitlines()` splits on
  them, so one valid record becomes two invalid halves.
- Reproduction: `printf '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"note":"a\xe2\x80\xa8b"}}\n' | python3 -m tap --trace w/u2028.jsonl -- cat`
  (tap exit 0; `wc -l` counts 4 records), then `python3 -m tap.show w/u2028.jsonl`: traceback ending
  `json.decoder.JSONDecodeError: Unterminated string starting at: line 1 column 63`, exit 1. Same with
  `\xc2\x85` (U+0085). `--mermaid` and `--explain` share `load` and fail the same way.
- Why it matters: these are legal characters in any JSON string (a tool description, a log message);
  a trace recorded by this repo's own tap of valid traffic cannot be viewed at all, and G5's `--explain`
  would go red on a server change that is not a protocol change.
- Fix: split on `"\n"` only (`read_text(...).split("\n")`, or `read_bytes().split(b"\n")` and decode
  each line). Add a test with a U+2028 frame recorded through the tap.
- Disposition: open

### S2 (major, CONFIRMED): one JSON-valid but malformed JSON-RPC message crashes the whole view

- Location: `tap/show.py:61` (object/array id is unhashable), `:94` and `:131-134` (non-string
  `method`), `:98` (`error` that is not an object).
- Defect: `kind_of` checks only for the keys `method`/`id`, and later code assumes their JSON-RPC
  types, so a message with the right keys and wrong types raises instead of being shown.
- Reproduction (one-line traces in `w/`, each run as `python3 -m tap.show w/<name>.jsonl`):
  `"id":{"a":1}` on a request: `TypeError: unhashable type: 'dict'`; `"method":5` on a notification:
  `TypeError: sequence item 1: expected str instance, int found`; a response `"error":"boom"`:
  `AttributeError: 'str' object has no attribute 'get'`. Each exits 1 with a traceback in plain and `--explain`
  mode (plain mode stops at the bad record; `--explain` prints nothing); the first two also crash
  `--mermaid`, while the bad `error` field happens to survive it.
- Why it matters: the tap records anything (C4), and the lab exists to show what really crosses the
  wire, including wrong traffic (phase 2's raw client, phase 4's fault mode). The frame most worth
  seeing is the one that makes the viewer fail, and the learner then sees a Python traceback instead
  of the trace.
- Fix: validate types in `kind_of` (string `method`; `id` string, number or null; `error` object) and
  give anything else a kind such as `invalid` that `describe` and `mermaid` print with its raw text.
- Disposition: open

### S3 (minor, CONFIRMED): file-level problems give a traceback and exit 1, the same code as "a note is missing"

- Location: `tap/show.py:44` (`load`), `:53` (`rec["dir"]`), `:67`/`:106` (`t_ns`), `:106`
  (`ARROWS[...]`), `:141` (`parse_notes`), `:181`-`:186` (no error handling in `main`).
- Defect: a missing path, a directory, a non-UTF-8 trace, a truncated or whitespace-only line, a
  record that is not an object, a record without `dir` or `t_ns`, an unknown `dir`, and a missing
  walkthrough file all end in an uncaught exception.
- Reproduction: `python3 -m tap.show w/nope.jsonl` gives `FileNotFoundError`, exit 1; `python3 -m tap.show w`
  gives `IsADirectoryError`; a trace whose last line is cut mid-record gives `JSONDecodeError`; a line
  of three spaces, `JSONDecodeError`; a line `[1,2]`, `AttributeError: 'list' object has no attribute 'get'`;
  `{"seq":0,"t_ns":1}`, `KeyError: 'dir'`; `"dir":"weird"`, `KeyError: 'weird'`;
  `python3 -m tap.show tests/fixtures/out-of-order.jsonl --explain w/nope.md`, `FileNotFoundError`, exit 1.
- Why it matters: `--explain` uses exit 1 for "coverage failed", so G5 and the lesson's
  `--explain ... && echo` cannot tell a crash from a missing note; and every traceback prints the
  absolute path of `tap/show.py`, which on a learner's machine is a home-directory path, in text a
  learner is likely to paste into an issue.
- Fix: catch `OSError`, `UnicodeDecodeError` and `ValueError` in `main`, print one line naming the file
  and line number, and exit with a code distinct from 1 (2 is already "usage"; 3 would do). Skip or
  flag a record with an unknown `dir` instead of raising.
- Disposition: open

### S4 (minor, CONFIRMED): plain output passes server bytes to the terminal, and a newline in a method name forges extra lines

- Location: `tap/show.py:89` (stderr text), `:94` (method), `:106`.
- Defect: `describe` prints `raw` stderr text and JSON `method` strings as they are, so ESC, BEL and CR
  reach the terminal, and a `\n` inside a method string splits one record over several output lines.
- Reproduction: a child (`w/evil_child.py`) run under the tap writes the stderr line
  `ESC]0;PWNED-TITLE BEL ESC[2K hidden CR boot ok` and a notification whose method is
  `"notifications/\u001b[31mred\u001b[0m"` and another whose method contains `\r\nClient->>Server: forged`.
  `python3 -m tap.show w/evil.jsonl | cat -v` shows `^[]0;PWNED-TITLE^G^[[2Khidden^Mboot ok` and
  `notifications/^[[31mred^[[0m` verbatim, and record 3 printed as three lines, the last being
  `Client->>Server: forged`. On a terminal the OSC sets the window title and the CR hides `hidden`.
- Why it matters: D14 expects learners to share traces; viewing someone else's trace should not let its
  content drive the terminal or print lines that look like records. (`--full`'s JSON bodies are safe:
  `json.dumps` escapes control characters.)
- Fix: escape C0/C1 control characters (and U+2028/2029) in every string `describe` prints, for example
  through `json.dumps(text)[1:-1]`.
- Disposition: open

### S5 (minor, CONFIRMED for CommonMark, PLAUSIBLE for GitHub): `--mermaid` labels can break out of the fenced block

- Location: `tap/show.py:109-112` (`mermaid_text`).
- Defect: it removes `;`, `#` and `\n` but not a lone `\r`, which CommonMark treats as a line ending,
  and not backticks, so a method name `tools/x\r```\r**injected** [click](http://example.invalid)` closes
  the ` ```mermaid ` fence the lesson (and M7) tells the learner to paste the output into.
- Reproduction: a child run under the tap sends that notification (trace `w/cr.jsonl`); `python3 -m tap.show
  w/cr.jsonl --mermaid`, wrapped in a ` ```mermaid ` fence, rendered with markdown-it-py 3.0.0 in
  CommonMark mode: the code block ends after `Server->>Client: tools/x`, then a `<p>` with
  `<strong>injected</strong>` and a link to `http://example.invalid`, then an empty code block. The same
  sanitizer also lets `%%{init: ...}%%` directives, HTML tags and ESC through; I could not render
  Mermaid itself (no network), so their effect inside the diagram is PLAUSIBLE only.
- Why it matters: the docstring says the text is made "safe"; the 80-character cut limits but does not
  prevent a server choosing what a learner's issue or README shows.
- Fix: replace every control character (category `Cc`, plus U+2028/2029/0085) with a space, and drop or
  replace backticks, `%`, `<` and `>`; or keep only a known-safe character set for labels.
- Disposition: open

### S6 (minor, CONFIRMED): ids are shown with Python spellings and lose their JSON type; `true` pairs with `1`

- Location: `tap/show.py:61-68` (pairing key and anchors), `:96`, `:133`.
- Defect: ids are formatted with Python `str()`, and the pending map uses Python equality, where
  `True == 1 == 1.0`.
- Reproduction: `w/ids.jsonl` holds c2s `ping` id `1`, c2s `ping` id `"1"`, s2c result id `true`, s2c
  error id `null`, s2c result id `"1"`. `python3 -m tap.show w/ids.jsonl` prints `request ping id=1`
  twice, `response id=True (answers seq 0, 2.0 ms)`, `error id=None code=-32700`, and
  `response id=1 (answers seq 1, ...)`. Both requests get the anchor `c2s.ping.1`, and one walkthrough
  note covers both under `--explain`.
- Why it matters: "the response must carry the same id, of the same type" is part of what the lab
  teaches; the viewer shows `None` and `True`, which never crossed the wire, hides the 1 versus "1"
  difference, and invents a pairing for `true`. A server's parse-error reply (id `null`) is a normal
  sight in later experiments.
- Fix: render ids with `json.dumps(id)` everywhere (plain, Mermaid, anchors) and key the pending map
  on `(direction, json.dumps(id))`.
- Disposition: open

### S7 (minor, CONFIRMED): a reused in-flight id silently mis-pairs

- Location: `tap/show.py:61`.
- Defect: a second request with an id still in flight overwrites the first in `pending`, so the first
  response is attributed to the later request and the second response shows no pairing, with no warning.
- Reproduction: `w/dup.jsonl` (c2s `a` id 5 at 1 ms, c2s `b` id 5 at 2 ms, two s2c results id 5):
  `response id=5 (answers seq 1, 1.0 ms)`, then `response id=5` unpaired.
- Why it matters: a reused id is a protocol violation the viewer is the natural tool to expose; instead
  it reports a confident, wrong latency. Both responses also share the anchor `s2c.response.5`.
- Fix: keep a queue per key, pair first-in-first-out, and print `duplicate id` on the second request.
- Disposition: open

### S8 (minor, CONFIRMED): `--explain` note parsing accepts things that should fail and hides others

- Location: `tap/show.py:138-150` (`parse_notes`).
- Defect: a repeated heading silently replaces the earlier note; a ``#### `<anchor>` `` line inside a
  fenced code block counts as a note; a line starting with `#` inside a note's code block (a shell
  comment) ends the note.
- Reproduction: `walkthrough-complete.md` plus a second ``#### `c2s.ping.2` `` note: exit 0, only the
  second text is shown. `walkthrough-missing-note.md` plus a ` ```markdown ` block containing
  ``#### `s2c.response.1` ``: exit 0, the frame shows the example text, so the missing note is not
  reported. A note `First part.` + a ` ```console ` block whose first line is `# a shell comment` +
  `Second part, lost.` parses as `'First part. ```console'`.
- Why it matters: C14 is the gate for "every frame has a note"; the fenced-heading case lets a walkthrough
  that lacks a note pass it, and the duplicate case lets an editor lose a note without any signal.
- Fix: track fence state (lines starting with three backticks or tildes) and ignore headings inside
  fences; report a duplicate anchor as an error with a non-zero exit.
- Disposition: open

### S9 (minor, CONFIRMED): D11's "a note that covers any number" cannot be written

- Location: `tap/show.py:70-73`, `:157`; `specs/phases/01-wire-tap/requirements.md` D11, *Cost accepted*.
- Defect: D11 says unprompted traffic in varying number must be keyed by occurrence "with a note that
  covers 'any number', or the check flaps", but `--explain` looks up each occurrence's exact anchor, so
  one note covers exactly one occurrence.
- Reproduction: two s2c `notifications/message` records and a walkthrough with only
  ``#### `s2c.notifications/message.0` `` ("Any number of these may arrive."): the second record prints
  `(no note)  [s2c.notifications/message.1]`, exit 1. Adding `.1` makes a run with one notification
  fail with `(no frame)`.
- Why it matters: latent in phase 1 (the handshake has no notifications), but the first walkthrough over
  the everything server's simulated logging will flap, which is the failure D11 names.
- Fix: support one wildcard form, for example ``#### `s2c.notifications/message.*` ``, that matches zero
  or more occurrences and never reports `(no frame)`; or amend D11.
- Disposition: open

### S10 (minor, CONFIRMED): piping into a pager or `head` that exits early prints a traceback

- Location: `tap/show.py:183`, `:187`, `:189-192` (unguarded `print`).
- Defect: a closed stdout raises `BrokenPipeError`, which is not handled.
- Reproduction: a 20000-record trace, `python3 -m tap.show w/big.jsonl --full | head -1`: exit 1 and a
  9-line traceback on stderr ending `BrokenPipeError: [Errno 32] Broken pipe`.
- Why it matters: lesson 01 tells the learner to pipe `--full` to `less`; quitting `less` early on the
  `tools/list` reply prints a traceback that looks like a bug.
- Fix: catch `BrokenPipeError` in `main` (redirect stdout to `os.devnull` and exit 0 or 141), or restore
  the default `SIGPIPE` handler.
- Disposition: open

### S11 (nit, CONFIRMED): the walkthrough says the viewer truncates the `tools/list` reply; it prints no body at all

- Location: `docs/walkthrough/01-handshake-2025.md:105-106`.
- Defect: "Its size is why the viewer truncates it by default and `--full` prints it whole"; plain mode
  prints only `response id=1 (answers seq ..., ... ms)`, with no body to truncate.
- Reproduction: `python3 -m tap.show tests/fixtures/out-of-order.jsonl` prints one summary line per
  record and no message bodies (`describe`, `tap/show.py:82-101`).
- Fix: "the viewer shows one line per frame and `--full` prints the decoded body".
- Disposition: open

### S12 (nit, CONFIRMED): output follows file order, not `seq` order

- Location: `tap/show.py:52`, `:116-117`, `:189`.
- Defect: D11 says arrows come "in `seq` order"; the code uses the order of lines in the file and never
  looks at `seq`, so a trace whose lines are out of `seq` order (a hand-edited fixture) is drawn and
  paired wrongly.
- Reproduction: `out-of-order.jsonl` with the seq-6 line moved first: plain output starts with an
  unpaired `response id=2`, and the request it answers stays unpaired; `--mermaid` draws the response
  before `tap spawn`.
- Why it matters: true only for traces not written by the tap (the tap writes in `seq` order under a
  lock), so it matters for fixtures. Fix: sort by `seq` when present, or reject a non-increasing `seq`.
- Disposition: open

### S13 (nit, CONFIRMED): a batch is labeled "not a JSON-RPC message"

- Location: `tap/show.py:34-35`, `:91`.
- Defect: a JSON array of requests is a JSON-RPC 2.0 batch, but `describe` prints
  `raw (not a JSON-RPC message)` and `--mermaid` a note `not JSON-RPC`.
- Reproduction: `w/batch.jsonl` (c2s `[{"jsonrpc":"2.0","id":1,"method":"ping"}]` and its batched
  reply): both lines print `raw (not a JSON-RPC message)`.
- Why it matters: the label is false; the true statement is that the 2025-11-25 revision has no batching.
  Fix: label arrays `batch (N messages; not supported in MCP 2025-11-25)`.
- Disposition: open

### S14 (nit, CONFIRMED): `--full` shows nothing for the frames whose bytes matter most

- Location: `tap/show.py:191`.
- Defect: `--full` prints a body only when `json` is not null, so a non-JSON frame's `raw` text and a
  non-UTF-8 frame's `raw_b64` are never shown in any mode.
- Reproduction: `printf 'not json\n\xff\xfe\n' | python3 -m tap --trace w/raw.jsonl -- cat`, then
  `python3 -m tap.show w/raw.jsonl --full`: six summary lines (`raw (Expecting value: ...)`,
  `raw (not valid UTF-8: ...)`) and no bodies.
- Fix: under `--full`, print `raw` (escaped as in S4) or `raw_b64` for frames with no `json`.
- Disposition: open

### S15 (major, CONFIRMED): C9's fixture cannot tell pairing by id from pairing by a stack

- Location: `tests/test_show.py:24-37`, `tests/fixtures/out-of-order.jsonl`.
- Defect: with exactly two requests in flight and their responses reversed, last-in-first-out pairing
  (pop the most recent unanswered request, ignoring `id`) gives the same pairs as pairing by `id`, so a
  viewer that never reads the response's `id` passes C9.
- Reproduction: in the scratch copy, replace `tap/show.py:64` with
  `asked = pending.pop(next(reversed(pending)), None) if pending else None`; `python3 -m tap.show
  tests/fixtures/out-of-order.jsonl` is byte-identical (`cmp`) to the unmutated output, and
  `python3 -m unittest tests.test_show` passes 7 of 7. The recorded mutation ("the most recent
  request", without removing it once answered) is caught only because it pairs both responses with
  seq 2; a stack that removes what it pairs is the natural form of that mistake and survives.
- Why it matters: C9 exists to prove correlation "by `id`, not by adjacency" (D5), and D5 names this
  discriminating fixture as the cost of keeping the viewer correct; it discriminates first-in-first-out
  only. Pairing that ignores direction also survives (section 3).
- Fix: put three requests in flight and answer them in an order that is neither first-in-first-out nor
  last-in-first-out (for example requests 1, 2, 3 answered 2, 3, 1; a stack pairs the response to 2
  with request 3), and add an s2c request whose id equals a c2s request's id to pin "per direction".
- Disposition: open

### S16 (nit, CONFIRMED, outside `show.py`): the walkthrough calls the `initialize` reply the largest frame

- Location: `docs/walkthrough/01-handshake-2025.md:63`.
- Defect: "The reply is the largest frame of the handshake"; in a fresh run the `initialize` reply is
  3533 bytes and the `tools/list` reply 10184 bytes, which M1 already records as the largest.
- Reproduction: the trace `tests.test_e2e` recorded in the real repo's git-ignored `runs/`, `bytes` per
  record: seq 3 (s2c, `initialize` reply) 3533, seq 6 (s2c, `tools/list` reply) 10184.
- Fix: "the largest frame so far" or "larger than the request because it carries `instructions`".
- Disposition: open

### S17 (nit, CONFIRMED, outside `show.py`): two recordings with the same name in one second collide

- Location: `scripts/record.sh:15` and `:19`.
- Defect: the run folder is named to the second, and `ln -s` into an existing `bin/node` fails, so a
  second `record.sh` of the same name within the same second exits non-zero.
- Reproduction: running `tests.test_e2e.E2ETest.test_c14_explain_covers_a_fresh_run` twice in a row in
  the scratch copy: the second fails with `ln: failed to create symbolic link
  'runs/<timestamp>-test-c14/bin/node': File exists`. It made my first three C14 real-half mutants fail
  for this reason rather than the mutation; I re-ran them with `runs/` cleared.
- Why it matters: a mutation can look caught when it is not. Fix: add `-%N` or a counter to the folder
  name, or fail early with a clear message if the folder exists.
- Disposition: open

## 3. C9, C13, C14 mutations re-run

All in the scratch copy. Harness: for each mutation, rewrite `tap/show.py` with one exact text
replacement, run `python3 -m unittest tests.test_show`, record the exit code and failing tests, and
restore the file (checked with `cmp` against the real repo after every batch). Baseline: 7 tests, OK.

### C9 (viewer correlates by `id`)

| Mutation | Violates C9? | Result |
| --- | --- | --- |
| pair with the oldest unanswered request (first-in-first-out) | yes | exit 1, `test_c9_responses_pair_by_id_not_adjacency` |
| pair with the newest unanswered request and remove it (stack) | yes | **exit 0, nothing fails** (S15) |
| pair by `id` but ignore direction | yes (D5 "per direction") | **exit 0, nothing fails** |
| `kind_of` never returns `error` | yes ("the error response is labeled as an error") | exit 1, C9 pairing test and C13 test |
| latency measured from the trace start, not the request | yes | exit 1, C9 pairing test |

Verdict: falsifiable, but only partly. The recorded mutation (most recent request, not removed) is
real and is caught, but it is the easy form; the stack form survives because the fixture's reversed
pair is exactly a stack's order. C9 should not count as falsified until S15 is fixed.

### C13 (Mermaid output)

| Mutation | Violates C13? | Result |
| --- | --- | --- |
| every arrow solid (`->>`), responses included | yes | exit 1, `test_c13_diagram_shape_and_seq_order` |
| `Client` and `Server` swapped on every arrow | yes | exit 1, C13 test |
| stderr note drawn `over Client,Server` instead of `over Server` | not strictly (C13 says "as notes") | exit 1, C13 test (it pins the exact line) |
| `tap` records not drawn at all | not the C13 row; yes for D11 ("stderr and `tap` records as notes") | **exit 0** |
| a non-JSON-RPC c2s/s2c frame drawn as an arrow | yes ("exactly one arrow per JSON-RPC record") | **exit 0**: the fixture has no such frame |
| `mermaid_text` no longer removes `;`, `#`, newlines | not in C13's text | **exit 0** |

Verdict: falsifiable for order, arrow style, participants and stderr notes. I did not re-run the
recorded order mutation itself; the direction-swap and all-solid mutants are independent evidence that
the arrow list is pinned exactly. The "exactly one arrow" half is pinned against duplicate or missing
JSON-RPC arrows, not against extra arrows for frames that are not JSON-RPC, and D11's `tap` notes are
unpinned.

### C14 (`--explain` coverage), synthetic half

| Mutation | Violates C14? | Result |
| --- | --- | --- |
| never report `(no frame)` | yes | exit 1, `test_c14_extra_note_is_reported` |
| report `(no frame)` but exit 0 when it is the only problem | yes | exit 1, `test_c14_extra_note_is_reported` |
| notification occurrences counted globally, not per direction and method | yes (D11 anchors) | exit 1, all three C14 tests |
| the synthetic record is no longer skipped | yes | exit 1, all three C14 tests and both C9 tests |
| a heading with an empty body counts as a note | arguably ("prints a note after every frame") | **exit 0** |
| a non-anchor heading no longer ends a note | no | exit 0 |

The recorded mutation (always exit 0) is the easiest possible one; the two subtler exit-code mutants
above are also caught, so the claim holds for the synthetic half.

### C14, real half (`tests/test_e2e.py:66-76`)

Baseline in the real repo: `python3 -m unittest tests.test_e2e -v`, 3 tests OK, run once. In the
scratch copy, `tests.test_e2e.E2ETest.test_c14_explain_covers_a_fresh_run` with `runs/` cleared before
each run (see S17): baseline OK; walkthrough with the `tap.exit.0` note deleted: fails,
`(no note)  [tap.exit.0]`; with an extra `s2c.notifications/message.0` note: fails,
`(no frame)  [s2c.notifications/message.0]`; with the `stderr.0` heading kept and its body emptied:
fails, `(no note)  [stderr.0]`. A `show.py` that ignores orphan notes, run with a walkthrough that has
one, passes the real half; that is expected, since the real half checks the walkthrough against a
fresh run and leaves `show.py`'s logic to the unit tests, which catch that mutant. Verdict: falsifiable.
The recorded mutation (renaming `c2s.ping.2` to `c2s.ping.9`) is valid but triggers both messages at
once; the three single-defect mutants above show each failure on its own.

## 4. Behaviours no test pins down

Each item below was shown unpinned by a mutation that `tests.test_show` passes (section 3), or by the
fixtures' contents.

- Pairing per direction (D5): pairing by `id` alone passes, because no fixture has an s2c request
  sharing an id with a c2s request.
- Pairing by `id` rather than by position: a stack pairer passes (S15).
- `--mermaid` draws `tap` records as notes (D11): dropping them passes.
- `mermaid_text`'s sanitizing and its 80-character cut: removing them passes; no fixture label contains
  `;`, `#`, a newline or more than 80 characters.
- Frames that are not JSON-RPC (non-JSON, non-UTF-8 `raw_b64`, `partial: true`, batches): no viewer
  fixture has one, so their plain line, their Mermaid note and "exactly one arrow per JSON-RPC record"
  are unpinned; drawing them as arrows passes.
- Plain output for `stderr` and `tap` records, and the elapsed-milliseconds column: omitting both, or
  printing 0.0 for every elapsed time, passes. Only latencies are checked.
- `--full`: one substring (`"code": -32603`) is checked; printing only error bodies passes.
- A note heading with an empty body counts as missing; a non-anchor heading ends a note: changing
  either passes.
- Usage handling: only "no arguments" and "`--explain` without a path" are tested; unknown flags,
  extra arguments and combined flags are not.
- Errors on unreadable or malformed input (S3), wire-shape errors (S2), non-`\n` line separators (S1),
  control characters (S4, S5), id types (S6), duplicate ids (S7), duplicate or fenced note headings
  (S8): none has a test.

## 5. Summary

17 findings: 3 major (S1, S2, S15), 8 minor (S3 to S10), 6 nits (S11 to S14, S16, S17). S16 and
S17 are outside `show.py` and were found while checking how the viewer is used.

`show.py` does what D5 and D11 describe on the well-formed traffic of the pinned handshake: pairing by
id and direction, latencies, Mermaid shape and order, and `--explain` coverage with the right exit code
all hold. Its weakness is input it did not expect: a legal Unicode line separator (S1) or one
wrongly typed field (S2) makes the whole trace unreadable, server text reaches the terminal and the
Markdown it is pasted into unescaped (S4, S5), and `--explain`'s parser has two ways to let a
missing or lost note pass (S8).

On falsifiability: C13 and both halves of C14 are falsifiable, with mutations I wrote myself. C9 is
falsifiable only against first-in-first-out pairing: a stack pairer gives byte-identical output on
`out-of-order.jsonl` and passes (S15), so C9's fixture does not yet discriminate what D5 says it must.
The recorded C9 mutation is real but is the easy form of the mistake; the recorded C14 mutation (always
exit 0) is the easiest possible one, though subtler exit-code mutants are also caught.

The only change I made to the real repo is this file.
