# Tap review: adversarial pass, C1-C6 mutations re-run, falsifiability audit of C1-C16

Reviewer: an independent model (Sonnet 5.5, fresh session), not the builder of `tap/`.
Branch `phase-01-wire-tap`, tree clean at the start. Status of this file: complete.

## 1. Scope and what I ran

Read in full: `specs/` (mission, roadmap, tech-stack), the phase 1 requirements, validation and
plan, `tap/__main__.py`, `tap/show.py`, `tests/test_tap.py`, `tests/test_show.py`,
`tests/test_e2e.py`, `tests/drive.py`, `tests/fake_children/*`, `scripts/record.sh`,
`scripts/gate.sh`, `.github/workflows/ci.yml`, and the tools and tests behind C8, C11, C12, C15.

Method. All mutation work was done in a scratch copy of `tap tests tools scripts specs
pyproject.toml` (plus `docs/` and `README.md`, and `vendor/` symlinked, not copied, so that the
e2e tests could run there). No tracked file in the repo was edited; the only change I made to the
repo is this file. I did not run `tests/test_e2e.py` or `scripts/gate.sh` in the repo (the other
reviewer owns those); e2e coverage below comes from the scratch copy only.

Baselines in the scratch copy: `tests.test_tap` 17 tests OK; `tests.test_show` 7 OK;
`tests.test_provenance` 12 OK; `tests.test_citations` 8 OK; `tests.test_lessons` 8 OK;
`tests.test_e2e` 3 OK; `tests.test_no_run_output` 9 tests, 1 error that is an artifact of the
scratch copy (it has no `.git`, and `test_real_repo_is_clean` calls `git ls-files`).

Harness note (a flaw in my own first pass, found and fixed). My first mutation harness reused
Python bytecode caches; two mutants of identical file size written within the same second can
run each other's cached code, which contaminated one result (C14c). I deleted the caches before
every run, set `PYTHONDONTWRITEBYTECODE=1`, and re-ran every tap and viewer mutation reported
below. A first batch of record.sh-based e2e mutants also collided in the same-second run folder
(T17) and was re-run with a pause between runs. Every number in this file comes from the clean
re-runs.

Adversarial probes were run directly against the scratch tap with the fake children and small
scripts: a randomized byte-exactness fuzz (40 seeds: random binary, ASCII, UTF-8 with U+2028,
NUL and CR, frames up to 1.5 MB, random write sizes and a slow reader, no trailing newline;
compared sha256 of both streams and the trace `raw` concatenation), a concurrent flood of all
three streams (180000 frames, 16 MB), signals, closed descriptors, large frames, odd JSON.
Content rules: `python3 tools/check_no_run_output.py` in the repo prints ok, but it walks
`git ls-files`, so it does not look at this untracked file until it is committed (the pre-push
hook will, through `check_commit`). I therefore ran `check_file` from a scratch copy of the tool on
this file's bytes: no problems. No home path, login name or run output is quoted here.
Things I did not do: no Windows or macOS run; no test with a real MCP client; Mermaid rendering
was not re-checked (M7 is the owner's); I did not exercise C10 (CI) because that needs pushes.

## 2. Findings

Disposition lines are for the maintainer. CONFIRMED means I reproduced it; PLAUSIBLE means I
could not.

### T1 (major, CONFIRMED) A deeply nested frame kills a relay thread: forwarding stops, the session hangs or output is lost, exit code stays 0

- Location: `tap/__main__.py:46-50` (`frame_fields` catches only `ValueError`) and `:107`
  (`relay` does not catch anything). `RecursionError` is not a `ValueError`.
- Defect: a valid JSON frame nested about 10000 deep (a 20 KB line) raises `RecursionError` in
  `json.loads` or `json.dumps`; the exception ends the relay thread, so that direction stops
  forwarding for the rest of the session. D2 says the tap forwards bytes without interpreting
  them; here the interpretation for the trace breaks the forwarding.
- Reproduction, server to client (run from the repo root):
  `python3 -m tap --trace t.jsonl -- python3 -c 'import os; n=10000; os.write(1, b"{\"id\":1}\n"+b"["*n+b"]"*n+b"\n{\"id\":3}\n")' > out.bin`
  Observed: tap exit 0, `out.bin` is 0 bytes (the child wrote 20019), one `RecursionError`
  traceback on stderr, trace holds `spawn`, the first frame, `exit`. The first, innocent frame
  was lost too, because the whole chunk is forwarded only after its frames are recorded.
- Reproduction, client to server:
  `python3 -c 'import sys; n=10000; sys.stdout.buffer.write(b"["*n+b"]"*n+b"\n")' | python3 -m tap --trace t.jsonl -- cat`
  Observed: the tap never exits (killed by `timeout` after 10 s), 0 bytes delivered, because the
  dead client thread never ran `at_eof`, so `cat` never saw end of file.
- Threshold: first failing depth 9997 under Python 3.12.3 (recursion limit 1000 does not apply to
  the C scanner; the limit is about 10000).
- Why it matters: the edge lab (roadmap phase 4, "oversized frame", malformed traffic) will send
  exactly this kind of frame; a hostile or buggy server can silence the tap.
- Suggested fix: in `frame_fields` catch `RecursionError` as well (record `json: null` and a
  `parse_error`); more generally see T2.
- Disposition: fix in step (a): `RecursionError` while parsing or serializing a frame gives `json: null` plus `parse_error`; forwarding does not depend on recording (D2, D3 amended, register row 2026-10-21; checked by C4).

### T2 (major, CONFIRMED) Any exception in a relay thread silently ends that direction; a trace write failure hangs the session

- Location: `tap/__main__.py:93-116` (`relay`), `:64-76` (`Trace.record`), `:173-184`.
- Defect: `relay` has no exception handling. If recording a frame raises (disk full, quota,
  `OSError`), or `os.read` raises (non-blocking descriptor, `BlockingIOError`), the thread dies
  with a traceback, `at_eof` is never called, the chunk is not forwarded, and nothing tells the
  main thread. Result: either a hang with the child alive, or truncated output with the child's
  exit code (often 0).
- Reproduction (trace write failure; `ulimit -f 2` caps the trace file at 2 KiB):
  `( ulimit -f 2; timeout 10 python3 -m tap --trace t.jsonl -- cat < many.in > out.bin )`
  where `many.in` is 200 JSON-RPC ping lines (8490 bytes). Observed: exit 124 (killed by
  timeout), `out.bin` 0 bytes, `OSError: [Errno 27] File too large` on stderr, trace stuck at
  2048 bytes. Without the timeout this never ends.
- Reproduction (non-blocking stdin, e.g. a shared descriptor a parent set to `O_NONBLOCK`):
  a parent creates a pipe, sets `O_NONBLOCK` on the read end, passes it as the tap's stdin, writes
  one request half a second later. Observed: `BlockingIOError: [Errno 11]` in the c2s thread,
  tap hung, nothing forwarded. Rare with common clients (their child ends are blocking), but real.
- Why it matters: D1's own "cost accepted" says a tap that mishandles buffering, EOF or exit
  codes changes the behavior it observes. The current behavior is neither fail-open nor
  fail-closed: it stalls without saying so, and a hung tap holds the session open.
- Suggested fix: decide a policy and test it. Simplest: wrap the per-frame recording in
  `try/except Exception` and continue forwarding, noting a `tap` error event once; call `at_eof`
  in a `finally`; make `main` exit non-zero (and say why on stderr) if any relay thread died.
- Disposition: fix in step (a): fail open, as the owner chose (register row 2026-10-21): a trace write failure prints one `tap:` line, stops recording, keeps forwarding, and keeps the child's exit code; read and write errors end one direction only and EOF is still passed on (D2 amended; checked by C17).

### T3 (major, CONFIRMED) `tap.show` cannot open a valid trace that contains U+0085, U+2028 or U+2029

- Location: `tap/show.py:44` (`path.read_text(...).splitlines()`); the same call at `:141`
  (`parse_notes`).
- Defect: the tap writes `raw` with `ensure_ascii=False` (`tap/__main__.py:71`), which leaves
  U+0085, U+2028 and U+2029 unescaped inside the JSON string. `str.splitlines()` splits on them,
  so one record becomes two broken lines and `json.loads` fails. The trace file itself is valid
  JSON Lines (the tests read it with `split(b"\n")`).
- Reproduction:
  `printf '{"jsonrpc":"2.0","id":1,"method":"ping","params":{"t":"a\xe2\x80\xa8b"}}\n' | python3 -m tap --trace t.jsonl -- cat > /dev/null; python3 -m tap.show t.jsonl`
  Observed: `json.decoder.JSONDecodeError: Unterminated string starting at: line 1 column 63`,
  exit 1, no output at all. Same for `\xc2\x85` and `\xe2\x80\xa9`; `--mermaid` fails the same
  way. (U+000B, U+000C, U+001C are escaped by `json.dumps`, so they are fine.)
- Why it matters: any tool result carrying such a character (text pasted from the web, for
  instance) makes the learner's whole trace unreadable by the primary viewer.
- Suggested fix: `path.read_bytes().decode("utf-8").split("\n")` (and the same in `parse_notes`),
  plus a test with a frame containing U+2028.
- Disposition: fix in step (a) at the root: the tap writes U+0085, U+2028 and U+2029 as `\u` escapes (D3 amended; checked by C4). The viewer half (split on `\n` only, for traces from elsewhere) stays open as S1 for step (b).

### T4 (minor, CONFIRMED) Quadratic time on large frames

- Location: `tap/__main__.py:104-105` (`pending += chunk` then `pending.split(b"\n")` on every read).
- Defect: both operations copy the whole pending buffer on every 64 KiB read, so a frame of
  size n costs O(n squared / chunk). Forwarding of each chunk waits for this work.
- Reproduction: a child writing one line of N MB (`os.write` loop), run through the tap with
  `/usr/bin/time`: 4 MB took 0.34 s, 16 MB took 3.3 s, 32 MB took 14.5 s (peak RSS 243 MB), all
  delivered intact.
- Why it matters: the tap adds latency that grows quadratically with frame size, which distorts
  the very `t_ns` it reports; the edge lab's "oversized frame" will hit it.
- Suggested fix: search only the new chunk for `\n` (`chunk.find`) and keep the unterminated tail
  in a `bytearray` or a list of chunks.
- Disposition: fix in step (a): frames are cut by searching only the new chunk, so the cost is linear in the frame size (D2; covered by C1's 128 KiB frame).

### T5 (minor, CONFIRMED) `tap.show` crashes on valid JSON frames with unexpected field types, and pairs `true` and `1.0` with `1`

- Location: `tap/show.py:61` (`pending[(direction, msg["id"])]`), `:98` (`msg['error'].get`),
  `:130-134` (`label += ...` on a non-string `method`), `:64` (`pending.pop` keyed by a value
  with Python equality).
- Reproduction (hand-written synthetic traces, `python3 -m tap.show <trace>`):
  request `"id":[1]` gives `TypeError: unhashable type: 'list'`; response `"error":"boom"` gives
  `AttributeError: 'str' object has no attribute 'get'`; `"method":5` crashes the default view
  (`TypeError`) and `--mermaid` (`TypeError` or `AttributeError`, depending on whether `id` is
  present). A request with `"id":1` answered by a response with `"id":true` prints
  `response id=True (answers seq 1, ...)`, and `"id":1.0` likewise pairs.
- Why it matters: roadmap L11 will record malformed traffic on purpose ("string vs number id",
  "notification with an id", batches); the viewer is the tool that must explain those traces.
  Also `--explain` anchors for id `1` and id `"1"` are the same string (`c2s.ping.1`; checked with `annotate` on two synthetic records).
- Suggested fix: treat `id` and `method` defensively (type-check, key on `(type name, value)`),
  and render a frame that does not fit the shape as `raw`.
- Disposition: open, step (b) (viewer).

### T6 (minor, CONFIRMED) Only SIGINT and SIGTERM reach the child; SIGHUP, SIGQUIT and group-directed signals orphan it

- Location: `tap/__main__.py:147-148` (only two signals trapped), `:160` (`process_group=0`).
- Defect: the child is in its own process group, so anything the kernel or a caller sends to the
  tap's group no longer reaches it, and the tap itself dies on SIGHUP and SIGQUIT without telling
  the child. Launched directly, the child would have shared the client's group.
- Reproduction: run the tap around `tests/fake_children/signal_waiter.py` (it ignores stdin), send
  one signal to the tap's pid, look 1 s later. Child still alive: SIGTERM no, SIGINT no, SIGHUP
  yes, SIGQUIT yes, SIGKILL yes (in those last three the tap itself was killed by the signal). A
  well-behaved server (the everything server exits on stdin end of file, M2) is
  rescued by the closed pipe, which is why this is minor. A caller that does `killpg` on the
  tap's group also misses the child.
- Why it matters: D1 promises "any client that launches a stdio server can launch the tap instead,
  unchanged"; terminal hang-up is the standard way a server is told the session ended.
- Suggested fix: trap SIGHUP and SIGQUIT too (forward them, then exit like the child), or keep the
  child in the tap's group and handle the double-SIGINT differently; document the choice in D4.
- Disposition: fix in step (a): forward SIGINT, SIGTERM, SIGHUP and SIGQUIT; the child keeps its own process group, so a group signal reaches it once through the tap; SIGKILL to the tap is an accepted cost (D4 amended, the owner's choice, register row 2026-10-21; checked by C5).

### T7 (minor, CONFIRMED) The trace can contain the token `Infinity`, which is not JSON

- Location: `tap/__main__.py:47` (parses `1e999` to a float infinity) and `:71`
  (`json.dumps` writes `Infinity`).
- Reproduction: `printf '{"x": 1e999}\n' | python3 -m tap --trace t.jsonl -- cat > /dev/null`, then
  parse each trace line with Node's `JSON.parse`: the c2s and s2c lines are rejected
  (`Unexpected token 'I'`), spawn and exit lines are fine. `jq` is not installed here, so I used
  Node as the strict parser.
- Why it matters: D3 sells the trace as `jq`-able; the tap already rejects `NaN` and `Infinity`
  literals on input (`_reject_constant`) but emits them on output.
- Suggested fix: pass `allow_nan=False` and store `json: null` plus a `parse_error` when the
  parsed value contains a non-finite float, or keep floats as `parse_float=decimal.Decimal`.
- Disposition: fix in step (a): a non-finite number gives `json: null` plus `parse_error`, and the writer refuses `NaN` and `Infinity` (D3 amended; checked by C4).

### T8 (nit, CONFIRMED) Start-up failures are Python tracebacks with exit 1, and usage errors exit 1 not 2

- Location: `tap/__main__.py:119-126`, `:136` (`Trace(trace_path)`), `:170-175`.
- Observed: `--trace /nonexistent-dir/t.jsonl` prints a `FileNotFoundError` traceback, exit 1;
  stdin closed (`<&-`) gives `AttributeError: 'NoneType' object has no attribute 'fileno'`, exit 1;
  stderr closed (`2>&-`) exits 1 silently; `--help` is reported as "missing --"; every usage
  error exits 1 (the viewer uses 2). The tests only assert "non-zero".
- Suggested fix: catch `OSError` around the trace open and print `tap: cannot write trace: ...`;
  use exit code 2 for usage errors.
- Disposition: fix in step (a): an unopenable trace path prints `tap: cannot write trace: ...` and exits 2; usage errors exit 2; closed standard descriptors are replaced by /dev/null before anything is opened (D1 amended; checked by C5).

### T9 (nit, CONFIRMED) End of file on the child's stdout is not passed on until the whole child has gone

- Location: `tap/__main__.py:188-190`.
- Observed: a child that closes its stdout and keeps running 3 s: the client sees end of file on
  the tap's stdout after 3.1 s, not at once. A child that exits 3 immediately while a background
  grandchild keeps the pipes open: the tap exits 3 only after the grandchild ends (4.1 s of a 4 s
  sleep). D4 accepts the stdin-EOF case ("a server that never exits on EOF keeps the tap alive
  too") but not these two.
- Suggested fix: document it in D4, or close the tap's stdout when the s2c relay ends.
- Disposition: fix in step (a) for the stdout half: the tap's stdout closes when the child's does (D4 amended; checked by C5). The grandchild half is accepted and written into D4's cost.

### T10 (nit, CONFIRMED) The trace file is overwritten without notice and created with the caller's umask

- Location: `tap/__main__.py:58` (`path.open("wb")`).
- Observed: `--trace` pointing at an existing file truncates it; with umask 022 the new trace is
  mode 644. Traces can contain whatever the server prints (the `get-env` case in A5).
- Suggested fix: open with `os.open(..., O_CREAT|O_EXCL|O_WRONLY, 0o600)` or at least say so in D3.
- Disposition: fix in step (a): the trace is created with mode 0600 and an existing file is replaced, as the owner chose (D3 amended, register row 2026-10-21; checked by C17).

### T11 (major, CONFIRMED) Core relay guarantees have no test that can fail

I applied mutations that violate stated behavior and the C1-C6 tests (`tests.test_tap`) stayed green:

| Mutation (scratch copy) | Claim it breaks | Result |
| --- | --- | --- |
| G1: `pending = chunk` (a frame split across two reads loses its head in the trace) | C1/C3 "concatenated `raw` equals the stream" | survives; the same mutant with `CHUNK = 16` is killed by 5 tests, so only the missing split makes it invisible |
| C1.5: truncate every forwarded chunk to 4096 bytes | C1 byte-exact forwarding | survives: no test sends more than 4 KB |
| G11: record after forward, 12 runs | relay docstring: "frames are recorded before the chunk that completes them is forwarded" | survives 12/12; with a 50 ms-slow c2s recorder the same mutant inverts request and reply in 12/12 runs and the existing test then fails, so the property is observable but the test only notices when recording is slow |
| G8: do not join the stdout and stderr relay threads | `exit` is the last record; every frame is in the trace | survives; on a child writing 20000 lines, the mutant keeps 7547 of 20000 s2c records while stdout is intact |
| G9: remove `process_group=0` | the code comment: Ctrl-C reaches the child once | survives; no test signals the group |
| G10: drop the replay of signals received before spawn | D4 | survives; no test |
| C6.6: join only the stdout thread | stderr frames complete before `exit` | survives 10/10 |

- Why it matters: these are exactly the properties a reviewer would assume the C1-C6 suite
  protects. Recorded mutations C1-C6 were all "easy" ones that change bytes or labels.
- Suggested fix: add (a) a child that writes one frame in two writes with a pause and a frame
  larger than 128 KB, in both directions; (b) an in-process test of `relay()` over a socketpair
  with a recorder that logs the order of "record" and "write" calls; (c) a child that writes
  20000 lines and exits, then assert 20000 s2c records and that `exit` is last; (d) a test that
  signals the tap's process group.
- Disposition: fix in step (a): tests for split and 128 KiB frames in both directions, record-before-forward order in-process, a 20000-line flood with `exit` last, and a process-group signal (C1, C2, C5, C6 amended). Moved from step (b) to (a) by the owner, 2026-10-21. G10 (early-signal replay) is checked too.

### T12 (minor, CONFIRMED) D3 field semantics are unpinned

Mutations that survive `tests.test_tap`: G6 `t_ns` always 0 (the test only checks the list is
sorted, which a constant list is); G5 `t_ns` not relative to tap start; G4 `bytes` off by one for
a complete s2c frame (only the partial frame's `bytes` is asserted); G7 stderr records not
advancing `seq`, giving duplicates (the strict-`seq` assertion runs only on a child with no
stderr); C4.5 decoding with `errors="surrogatepass"` (CESU-8 surrogate bytes would be recorded
as text; the non-UTF-8 tests use only 0xFF and a bad continuation byte).
`t_ns` matters most: the viewer's latency column and every "elapsed ms" a learner reads derive
from it, and the viewer tests use a hand-written fixture, so no test ties real tap output to
plausible timestamps.
- Suggested fix: assert `t_ns` is strictly positive and below the run's wall time, assert `bytes`
  equals `len(raw)` for every record (both directions), run the strict-`seq` check on a child that
  also writes stderr.
- Disposition: fix in step (a): `t_ns` bounds, `bytes` on every record, strict `seq` with stderr present, CESU-8 bytes (C2, C4 amended).

### T13 (nit, CONFIRMED) The signal test fails by a 30 s timeout and leaves processes behind

- Location: `tests/test_tap.py:203-229`.
- Observed: with signal forwarding removed (D4.1 below) `test_signals_are_forwarded` fails, but
  as `subprocess.TimeoutExpired` after 30 s per signal, not as an assertion, and the tap and its
  child are not killed on failure (the child sleeps 30 s).
- Suggested fix: `addCleanup(tap.kill)`, and a short `communicate` timeout (a few seconds).
- Disposition: fix in step (a): the signal test kills the tap and child on failure and uses a short timeout (C5 amended).

### T14 (minor, CONFIRMED) C16's "presence first" check is satisfied by the spawn record, so it cannot fail when the `get-env` reply is missing

- Location: `tests/test_e2e.py:83` (`assertIn("MCP_WIRE_LAB", text)`), `scripts/record.sh:24` (the allowlist that ends up in the argv).
- Defect: the trace's own `spawn` record carries the whole argv, which includes the allowlist
  entry `MCP_WIRE_LAB=1`. The test reads the whole trace file as text, so "MCP_WIRE_LAB appears"
  is true before the server has said anything. The comment says the check exists so that "an
  empty or failed `get-env` result" cannot pass.
- Reproduction (scratch copy): mutant C16.7, the tap records no s2c frames at all, and mutant
  C16.8, every recorded frame is replaced by `{}`: `tests.test_e2e...test_c16_minimal_environment`
  passes on both.
- Also: the test checks one planted variable and the parent's `HOME`. Mutants that add `USER`
  (C16.5) or `PWD` and `SHELL` (C16.6) to the allowlist pass. A mutant that puts the directory of
  the caller's node into `PATH` (C16.3) is caught here only because node lives under `HOME` on this
  machine; on CI node is installed outside the runner's home, so I expect it to pass there
  (argued, not run).
- Suggested fix: parse the trace, find the s2c frame that answers the `get-env` request, and
  assert `MCP_WIRE_LAB` in that frame's `json`; assert the allowlist exactly (the set of variable
  names in the reply equals `{PATH, HOME, LANG, MCP_WIRE_LAB}` plus whatever node adds).
- Disposition: open, step (b).

### T15 (nit, CONFIRMED) G8 accepts an empty or very short fragment on any line

- Location: `tools/check_citations.py:12` (the regex allows `""`), `:51` (`in lines[line_no - 1]`).
- Reproduction: against a three-line file, `` `servers:src/a.ts:1` "" `` and `` `servers:src/a.ts:4` "" ``
  both pass (line 4 does not exist: `split("\n")` yields a phantom empty last element), and
  `"a"` passes on a line that contains an "a". The 31 citations in the repo today all have
  fragments of 8 or more characters, so nothing is wrong now.
- Suggested fix: require a minimum fragment length (for example 6) and compare against
  `splitlines()`.
- Disposition: open, step (b).

### T16 (nit, PLAUSIBLE) `exit` is not guaranteed to be the last record

- Location: `tap/__main__.py:194-197`.
- Defect: the c2s relay is a daemon thread that is not joined, and `Trace.close()` runs a few
  statements after `trace.event("exit", ...)`. A frame the client sends in that window is recorded
  after `exit`; a frame after `close()` is dropped silently. `test_spawn_first_exit_last` runs with
  empty stdin, so it cannot see this. I could not trigger the window without injecting a delay.
- Suggested fix: close the trace inside the same locked section that writes `exit`.
- Disposition: fix in step (a): `exit` is written and the trace closed under one lock (D3 amended).

### T17 (nit, CONFIRMED) `scripts/record.sh` fails with a cryptic message when two recordings share a name within one second

- Location: `scripts/record.sh:15-19` (`runs/<timestamp to the second>-<name>`, `mkdir -p`, `ln -s`).
- Reproduction (scratch copy): start `scripts/record.sh tests/fixtures/handshake-2025.ndjson dup`
  twice at the start of a second. The second exits 1 with
  `ln: failed to create symbolic link '.../bin/node': File exists`. It fails loudly rather than
  mixing two traces, which is the safe direction, but the message does not say why. Two test
  processes using the fixed names `test-c14` and `test-c16` collide the same way (it happened to
  my own first mutation batch).
- Suggested fix: add the shell's `$$` or a counter to the folder name, or `mkdir` without `-p` and
  print "run folder exists".
- Disposition: open, step (b).

### T18 (minor, CONFIRMED) The tests behind C15 do not plant every secret regex, contrary to the row

- Location: `tests/test_no_run_output.py:18-40` and `tools/check_no_run_output.py:26-27,100`,
  against `validation.md` row C15 ("each secret regex's planted sample").
- Reproduction (scratch copy, attributing only to tests other than `test_real_repo_is_clean`, which
  errors in the scratch copy for lack of a `.git`): removing the `github_pat_` pattern (C15.10)
  leaves every test green; so do lowering the environment-dump threshold from 3 to 4 keys (C15.5;
  the samples have 4 and 2 keys, never exactly 3), dropping `PWD` from the key list (C15.6), dropping
  the root-home form (C15.8), checking only added and not modified files in the hook (C15.15), and
  skipping the root commit in the hook (C15.16). The other 11 rule and hook mutants are killed by the
  intended test.
- Suggested fix: add a `github_pat_` sample, a three-key dump, a `PWD` dump and a root-home path to
  `LEAKS`, and two hook tests (a leak introduced by modifying an existing file; a leak in the first
  pushed commit).
- Disposition: open, step (b).

### T19 (minor, CONFIRMED) G9's default `--min-lessons 1` and its timeout report are not pinned

- Location: `tools/check_lessons.py:64-65` (timeout), `:91` (`min_lessons = 1` default),
  `scripts/gate.sh:15` (calls the tool with no flag).
- Reproduction (scratch copy): changing the default to 0 (C12.5) or making a timed-out block pass
  silently (C12.6) leaves `tests.test_lessons` green. The tests call `check()` directly, never
  `main()`.
- Why it matters: with the default at 0, deleting the lessons directory would turn G9 green; the
  `--min-lessons 0` flag was used on purpose earlier in this phase (plan group 2 note).
- Suggested fix: a test that runs `main([...])` on an empty root and on a lesson with a sleeping
  block, with a short patched timeout.
- Disposition: open, step (b).

## 3. C1-C6 mutations re-run

I did not reuse the recorded mutations. For each row I applied my own mutants to the scratch copy
of `tap/__main__.py` (one at a time, bytecode caches cleared), ran `python3 -m unittest
tests.test_tap -v` (or the named test), and recorded which tests fail. "Killed" means at least one
test failed for a reason that matches the broken claim. Baseline before every group: 17 tests OK.
Ids refer to my mutant names; the full list with the exact edit is reproducible from the
description.

| Row | Recorded mutation (validation Result) and my verdict | My mutants: run / killed | Tests that failed | Survivors |
| --- | --- | --- | --- | --- |
| C1 | Re-serialize `json.dumps(json.loads(frame))`. Violates the claim; not too easy for its half. Reproduced as C1.1: 6 tests fail, among them the sha256 and `raw` rebuild tests. | 6 / 5 | C1.1 six tests including byte-exact, both partial-line tests, direction-and-order and the stdin-EOF test; C1.2 (drop CR) only `test_both_directions_are_byte_exact`; C1.3 (drop NUL) only the C4 client test, because C1's fixture has no NUL; C1.4 (CRLF to LF, s2c only) 2 tests; C1.6 (hold the unterminated tail) 3 tests | C1.5: truncate every forwarded chunk to 4096 bytes. No test sends more than 4 KB. Also G1 below |
| C2 | Swap the `dir` labels. Violates the claim but is noisy: my version (C2.1) fails 8 tests, several by `ValueError: not enough values to unpack` in the test helper, so it does not show that the named test discriminates. | 4 / 4 | C2.1 8 tests; C2.2 (only c2s mislabelled) 5; C2.3 (`seq` +100 on s2c records) only `test_direction_and_order`, on the exact list of seqs; C2.4 (spawn recorded after Popen) `test_spawn_first_exit_last` and the 127 test | The "reply recorded after its cause" half: G11 record-after-forward survives 12/12 runs (details in T11). G7 (stderr records do not advance `seq`), G5 and G6 (`t_ns` wrong or constant) also survive |
| C3 | Drop the buffer remainder at EOF. Valid, and the strongest recorded mutation: reproduced as C3.1, 3 tests fail on the missing `partial`. | 7 / 7 | C3.1 3 tests; C3.2 (no flag) 3; C3.3 (empty partial record at every EOF) 6 tests; C3.4 (flag only on s2c) 1; C3.5 (s2c tail not forwarded) 2; C3.6 (newline added in the record) 3; C3.7 (stderr remainder dropped) 1 | none |
| C4 | `decode(errors="replace")` before forwarding. Violates only the forwarding half; it says nothing about the recording half. | 7 / 6 | C4.1 (recorded style) 2 tests; C4.2 (record-only: `raw` with replacement characters) 2; C4.3 (invented `json` for bad UTF-8) 1; C4.4 (NaN accepted) 1; C4.6 (no `parse_error`) 2; C4.7 (c2s only) 1 | C4.5: decode with `surrogatepass`. The tests use only 0xFF and a bad continuation byte, so the boundary of "valid UTF-8" is untested |
| C5 | Always exit 0. Valid but blunt: the signal subtests fail on the exit status (`0 != 25`), so it never exercises D4's signal forwarding. | 7 / 7 plus 4 lifecycle mutants | C5.1 and C5.2 3 tests each; C5.3 (raw negative status), C5.4 (wrong sign), C5.5 (signal death as 0) only `test_child_killed_by_sigterm_gives_143`; C5.6 (127 to 1) only the 127 test; C5.7 (exit record says 0) only the exit-code test. Lifecycle: D4.1 (no signal forwarding) and D4.2 (SIGINT not trapped) fail `test_signals_are_forwarded` by `TimeoutExpired` after 30 s, not by assertion (T13); D4.3 (kill child at stdin EOF) and D4.4 (never close child stdin) fail `test_relaying_continues_after_stdin_eof` | G9 (remove `process_group=0`) and G10 (drop replay of early signals): no test |
| C6 | Child stderr sent to the tap's stdout. Valid; reproduced as C6.1. It is caught by the earlier assertion `run.stderr == STDERR_BYTES` (stderr empty), not by "never on stdout"; C6.4 (stderr to both) is what reaches that assertion. | 6 / 5 | C6.1-C6.5 each fail `test_stderr_is_relayed_and_recorded_not_mixed` (C6.2 and C6.5 on the `stream("stderr")` assertion) | C6.6: do not join the stderr thread (10/10 runs green); G8 shows the same for the stdout thread, and that it loses 62 percent of s2c records on a 20000-line child |

Control: G2 (`CHUNK = 16`, correct code) passes all 17 tests, and the split-frame bug G1 is
killed by 5 tests once `CHUNK = 16` forces splits (G1b). So the code handles splits correctly
today and the suite cannot tell if it stopped doing so.

Recorded versus mine, in short. Every recorded C1-C6 mutation is valid and I reproduced the
result stated in `validation.md` for each (same tests fail). None is "too easy" in the sense of
failing for an unrelated reason, except that C2's swap fails on helper crashes and C5's
exit-0 mutant never tests signal forwarding. What the set shares is that it only changes bytes,
labels and exit statuses; the lifecycle and ordering behaviors (T11) have no recorded mutation.

## 4. Falsifiability table, C1-C16

Verdicts. Falsifiable: a mutant that violates the stated claim makes a test fail, for the right
reason. Weak: some mutant that violates the stated claim, or a clause of it, survives. Vacuous:
a clause that cannot fail. "Run" means I ran the mutant in the scratch copy; "argued" means a
reasoned argument only. All runs below used the cache-safe harness.

| Row | Claim in plain words | Carried by | Verdict | Evidence |
| --- | --- | --- | --- | --- |
| C1 | Bytes out equal bytes in, both directions; `raw` fields rebuild the stream | `ByteExactTest` (2 tests) | falsifiable, narrow | Run: C1.1-C1.4 and C1.6 killed. C1.5 (truncate chunks over 4096 B) and G1 (frame split across reads) survive, so the claim is carried only for small frames that arrive in one read. My fuzz (40 seeds, up to 1.5 MB) found no violation, so the code is right; the test could not tell |
| C2 | `seq` strictly increasing; each frame has its true `dir`; a reply is recorded after its cause | `DirectionAndOrderTest` | weak (the order clause) | Run: C2.1-C2.4 killed. G11 (record after forward) survives 12/12; with a 50 ms-slow c2s recorder the same mutant is caught in 12/12 inversions, so the assertion works only if recording is slower than the child's reply. G7 (stderr no seq advance), G5, G6 (`t_ns`) survive |
| C3 | An unterminated final line is forwarded and recorded with `partial: true` | `PartialLineTest`, `StderrTest` | falsifiable | Run: C3.1-C3.7 killed, plus C1.6 |
| C4 | Non-UTF-8 and non-JSON frames are forwarded unchanged and recorded as `raw_b64` or `json: null` plus `parse_error` | `NonUtf8AndNonJsonTest` (3 tests) | falsifiable, narrow inputs | Run: C4.1-C4.4, C4.6, C4.7 killed; C4.5 (`surrogatepass`) survives |
| C5 | The tap exits with the child's code; 143 for SIGTERM | `ExitCodeTest`, `UsageTest` (127) | falsifiable | Run: C5.1-C5.7 killed; D4.1-D4.4 killed (two by timeout). Process group and early-signal replay unpinned (G9, G10) |
| C6 | Child stderr appears on the tap's stderr and as `stderr` records, never on stdout | `StderrTest` | falsifiable | Run: C6.1-C6.5 killed; C6.6 (no join) survives |
| C7 | Real server through the tap: `initialize`, `tools/list`, `ping` answered by id; every c2s request has exactly one s2c response | `tests/test_e2e.py::test_c7` | falsifiable; one clause vacuous | Run in scratch (vendor symlinked): C7.1 (nothing reaches the driver), C7.2 (s2c twice), C7.3 (c2s not forwarded), C7.5 (result corrupted), C7.6 (stdin EOF not propagated) killed on the intended assertion (e.g. "responses with id 0 reaching the driver"). C7.4 (c2s frames not recorded) passes: the "every request" loop iterates over c2s frames read from the trace and runs zero times; the hard-coded ids 0, 1, 2 carry the real claim |
| C8 | Provenance linter passes the real specs and fails on each broken record | `tests/test_provenance.py` | falsifiable | Run (tool mutants): C8.1-C8.8 and C8.10 killed; C8.9 (Source paragraph not bounded by a blank line) survives. Argued: every register row in `mission.md` is dated 2026-10-20, so "the date exists" cannot identify a row, and the word "register" alone resolves a Source (C8.10 shows a test exists for the no-resolution case, but not for a made-up register reference) |
| C9 | The viewer pairs a response with its request by `id`, not adjacency; errors labelled; notifications unpaired | `tests/test_show.py::test_c9_*` | falsifiable for what is stated; D5's "per direction" unpinned | Run: C9.1 (adjacency), C9.3 (latency base), C9.5 (error label) killed. C9.2 (ignore direction) and C9.4 (pair without consuming) survive: the fixture has no server-initiated request and no repeated id. T5 adds crashes and `true` versus `1` |
| C10 | CI runs the gate and goes red when a test fails | none re-runnable; the green run and the red throwaway branch are recorded in `validation.md` | weak (one-shot measurement) | Argued, not run (needs pushes): `.github/workflows/ci.yml` runs bootstrap and `scripts/gate.sh` on every push and pull request, which is consistent with the recorded runs. Nothing re-runs the check, so a later edit that drops the gate step would not be noticed by any test |
| C11 | Citation gate fails on a missing file, a line past EOF, a fragment one line away, an unknown submodule, an unchecked-out submodule | `tests/test_citations.py` | falsifiable, with a short-fragment hole | Run: C11.1-C11.8 killed (C11.9 was a no-op I discarded). Recorded real-artifact mutation replayed in scratch: shifting `servers:src/everything/transports/stdio.ts:49` to 50 gives exit 1, "fragment is not on line 50"; baseline exit 0, 31 citations. T15: empty fragment passes anywhere |
| C12 | Lesson gate fails on a missing section, a failing block, and an expected block absent from output (even with exit 0) | `tests/test_lessons.py` | falsifiable | Run: C12.1-C12.4 and C12.7 killed. Recorded real-artifact mutation replayed: expected `2024-11-05` changed to `2024-11-06` in lesson 01, gate exit 1, "expected output not found"; baseline exit 0. C12.5 and C12.6 survive (T19) |
| C13 | Mermaid output has the right header, participants, one arrow per message in `seq` order, right arrow styles, stderr as notes | `tests/test_show.py::test_c13_*` | falsifiable for the stated claim; escaping and tap notes unpinned | Run: C13.1 (order), C13.2 (notifications dropped), C13.5 (arrow style), C13.6 (stderr notes) killed. C13.3 (tap spawn and exit notes dropped; D11 requires them, C13 does not state them) and C13.4 (the `;`, `#`, newline and 80-character handling removed) survive |
| C14 | `--explain` exits 0 with a note after every frame on a fresh run; on a missing note prints `(no note)` and exits non-zero; on an extra note prints `(no frame)` and exits non-zero | `tests/test_show.py::test_c14_*`, `tests/test_e2e.py::test_c14` | falsifiable | Run: C14.1-C14.5 killed, each by the intended test (14.2 only the extra-note test, 14.3 only the missing-note test). On the real walkthrough in scratch, with a fresh recording: renaming the heading to `c2s.ping.9` (the recorded mutation), turning the heading of `s2c.response.1` into plain text, and emptying the note of the first frame while adding a heading `tap.spawn.1` that matches no frame: all three fail the e2e test |
| C15 | No run output reaches git: each leak kind is named by file; the installed pre-push hook refuses a push | `tests/test_no_run_output.py` | weak at six points | Run (tool mutants): 11 of 17 killed. Survivors: threshold of three env keys (C15.5), `PWD` (C15.6), the root-home form (C15.8), the `github_pat_` pattern (C15.10; the row says "each secret regex's planted sample", and there is no sample), modified files in the hook (C15.15), the root commit in the hook (C15.16). The local-bare-remote hook test itself is a good test |
| C16 | With a planted variable and the parent's `HOME`, a `record.sh` trace contains neither, and `MCP_WIRE_LAB` appears in the `get-env` result | `tests/test_e2e.py::test_c16` | weak; the presence clause is vacuous | Run in scratch: C16.1 (drop `env -i`), C16.2 (pass `HOME` through), C16.4 (drop `MCP_WIRE_LAB`) killed. C16.7 and C16.8 (the `get-env` reply is missing or empty in the trace) pass, because the `spawn` record already contains `MCP_WIRE_LAB=1` (T14). C16.5 (`USER`) and C16.6 (`PWD`, `SHELL`) pass. C16.3 killed only because node sits under `HOME` here; argued that CI would not catch it |

Rows with a weak or vacuous element: C2, C7 (one clause), C10, C15, C16 (five of sixteen). No row
is vacuous as a whole.

Recorded-mutation check for section E ("a C row without a recorded mutation or a signed
stand-in"). All sixteen rows have an entry in the `validation.md` Result: C1-C6 (grouped), C7,
C8, C9, C10 (the throwaway red branch), C11, C12, C13, C14 (both halves), C15 (both variants), C16.
No row relies on a stand-in. Two things to tidy: the Mutation column in the section C table still
says "to record:" for every row (stale wording now that the Result holds them), and C10's record is
a one-time measurement, not a repeatable mutation.

## 5. Summary

Counts: 0 blockers, 4 major (T1, T2, T3, T11), 8 minor (T4, T5, T6, T7, T12, T14, T18, T19),
7 nit (T8, T9, T10, T13, T15, T16, T17). T16 is PLAUSIBLE; the other 18 are CONFIRMED.

What is sound. Byte-exactness, partial lines, non-UTF-8, CRLF, NUL, line atomicity and
timestamp order held in everything I threw at them: a 40-seed fuzz with random chunking and a
slow reader, and a 180000-frame concurrent flood of stdout, stderr and stdin, produced identical
streams, contiguous `seq` and non-decreasing `t_ns`, with no deadlock. The tap never reads the
environment or the working directory (it records argv verbatim, by design). Signal forwarding,
exit codes (3, 143, 127) and EOF handling behave as D4 says.

What is not. The tap forwards correctly until something goes wrong in the recording path; then
it stalls silently (T1, T2). The viewer cannot open some valid traces (T3, T5). And the C1-C6
suite does not protect the relay's ordering, joining and split-frame handling (T11, T12), while
C16's presence check and C15's secret coverage are weaker than their rows say (T14, T18).

Mutation totals (scratch copy, tap, viewer, scripts and tools together): 128 mutants run, one of
them a correct-code control (G2); 97 killed, 30 survived with a behavior violated. All runs used
cleared bytecode caches.

Not done or not verified: Mermaid rendering (I suspect `mermaid_text` should also strip `\r`,
which stderr progress text can contain, but I had no renderer, so it is not a finding); C10
(needs pushes); a run on the CI image; macOS and Windows; the other reviewer's half (gates, docs,
walkthrough, lesson, CI) beyond the cheap tool mutations above.
