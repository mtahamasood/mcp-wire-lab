# Phase 2 review (LP4): the raw client, `tap.check`, G12, `record.sh`, docs

Reviewer: an independent agent (Opus 5.5) that did not build this work; the builder was Sonnet.
Date: 2026-10-21. Scope: `git diff 883f1bb 1a6263f` restricted to `client/`, `tap/check.py`,
`tools/check_claims.py`, `scripts/record.sh`, `tests/test_client_*.py`, `tests/test_check*.py`,
`tests/test_e2e.py`, `docs/walkthrough/02-*`, `docs/lessons/02-*` and `README.md`. Contract:
`specs/phases/02-raw-client/requirements.md` and `validation.md`. A28 and the "Phase 2 build
amendments" register row are taken as accepted and not re-litigated.

## What I ran

- The phase 2 unit tests (`tests.test_client_wire`, `tests.test_client_session`,
  `tests.test_client_manual`, `tests.test_check`, `tests.test_check_claims`): 31 tests, OK.
  `tools/check_claims.py --phases 02 04`: ok. The full gate was not run (a phase 3 build shares
  the machine).
- The tour against the pinned, built server through the tap: exit 0, 18 steps; its trace passes
  `tap.check` (41 frames) and `tap.show --explain` with the walkthrough (exit 0). Manual mode with
  lesson 02's experiments 1 and 2: the server ignores `{"id":50,"method":"ping"}` (logs a
  `Transport error` on stderr and carries on), answers `:req ping`, and answers
  `nonsense/method` with `-32601`, as the lesson says.
- Probe scripts with small fake servers for each wire and session finding below, a throwaway repo
  for G12, and 7 single-edit mutants of `tap/check.py` run against the C9-named tests and against
  all of `tests/test_check.py`.
- Walkthrough and lesson claims checked against the spec text, the pinned server source and the
  fresh trace: ids 0 to 16, 16 replies, no reply to id 16, the subscribe and unsubscribe log
  notifications, no `list_changed` with empty client capabilities, the 2025 era chosen by the
  first message, the shutdown by closing stdin with exit 0. I found no false statement in either.

Counts: 0 blockers, 2 majors, 7 minors.

## Majors

### P2-R1: one malformed line kills the reader thread, and every request then hangs

- Severity: major
- File: `client/wire.py:254-257` (`_read_loop`), `client/wire.py:296-298` (`_complete`),
  `client/wire.py:272-276` (`handle_line`)
- Claim: D1 and C1 say anything that is not a request, response or notification "is reported on
  the client's stderr and otherwise ignored". It is not: `classify` accepts as a response any
  object with `id` and `result`, whatever the type of `id`, and `_complete` then uses that `id`
  in a dict key. An array or object id raises `TypeError: unhashable type`. A deeply nested line
  makes `json.loads` raise `RecursionError`, which is not a `ValueError` and so not caught.
  Either exception escapes `_read_loop`, so the reader thread dies. `_fail_all` never runs, so
  every pending request waits for its full timeout. Every later line goes unread, including the
  real reply and any server request, which no longer gets its `-32601`. Nothing in the client
  says the reader has gone.
- Reproduction: a fake server that answers the first request with
  `{"jsonrpc":"2.0","id":[0],"result":{}}` and then with the real
  `{"jsonrpc":"2.0","id":0,"result":{"ok":true}}`:

  ```python
  # r1_server.py
  import sys
  sys.stdin.readline()
  sys.stdout.write('{"jsonrpc":"2.0","id":[0],"result":{}}\n')
  sys.stdout.write('{"jsonrpc":"2.0","id":0,"result":{"ok":true}}\n')
  sys.stdout.flush(); sys.stdin.read()
  # r1.py, run from the repo root
  import sys, time
  from client.session import Session
  s = Session.open([sys.executable, "r1_server.py"], timeout=3)
  t = time.monotonic()
  try: print(s.wire.request("x", None, 3))
  except Exception as e: print(f"raised {type(e).__name__} after {time.monotonic() - t:.1f}s")
  print("reader alive:", s.wire._reader.is_alive()); s.close()
  ```

  Observed: `TypeError: unhashable type: 'list'` (traceback from `_complete`, line 298), then
  `raised TimeoutError after 3.0s`, `reader alive: False`. The same happens when the first line
  is `"[" * 100000` (`RecursionError: maximum recursion depth exceeded while decoding a JSON
  array`).
- Proposed fix: in `classify`, take a message as a response only when `valid_id(message["id"])`
  holds or the id is `null` (the error reply to an unparsable request); anything else is junk.
  In `handle_line`, catch `RecursionError` with `ValueError`. In `_read_loop`, wrap each
  `handle_line` call so that an unexpected exception is reported and the loop goes on. Put
  `_fail_all` in a `finally`, so that pending requests fail at once whenever the loop ends. Add
  a C1 test for an array id and one for a deeply nested line, each followed by a good reply that
  must still be delivered.
- Disposition: fix (A30): a response is one only if its id is a valid id or null; `RecursionError` caught with `ValueError`; each line handled under a guard; `_fail_all` in a `finally`. Passes when `ClassifyTest::test_bad_id_or_deep_line_does_not_stop_reader` (C1) passes.

### P2-R2: the write lock also guards the pending table, so a blocked write deadlocks the client

- Severity: major (reachable only with large messages in both directions at once; phase 3 adds
  writes from the reader side, and the fix is small)
- File: `client/wire.py:135` (one lock for both jobs), `client/wire.py:189-201` (write under the
  lock), `client/wire.py:297` (reader takes the lock), `client/wire.py:326-327` (reader writes
  the refusal)
- Claim: D1 says "Writes are serialised by one lock". The same lock also guards `_pending` and
  `_abandoned`. `start_request` holds it for the whole blocking `write`. The reader thread needs it
  for every response (`_complete`) and every server request (`_refuse`). Suppose the client
  writes a line bigger than the free space in the stdin pipe while the server is writing its own
  output. The writer then blocks holding the lock. The reader blocks on the lock at the next
  response, so it stops draining stdout. The server blocks on its stdout, which a Node server
  does, since its pipe writes are synchronous, and so stops reading stdin. Nothing makes
  progress. The per-call timeout does not help, because the caller is stuck inside
  `start_request`, before `wait` begins, so the client hangs forever.
- Reproduction: a fake server reads one line, sleeps 1 s, writes about 2 MB of response lines,
  and only then reads stdin. The client sends one small request, then a request with 1 MB of
  params from a thread:

  ```python
  # r3_server.py
  import sys, time
  sys.stdin.buffer.readline(); time.sleep(1.0)
  line = b'{"jsonrpc":"2.0","id":0,"result":{"pad":"' + b"y" * 1000 + b'"}}\n'
  for _ in range(2000): sys.stdout.buffer.write(line); sys.stdout.buffer.flush()
  sys.stdin.buffer.read()
  # r3.py, run from the repo root
  import sys, threading
  from client.session import Session
  s = Session.open([sys.executable, "r3_server.py"], report=lambda t: None)
  s.wire.start_request("a")
  big = threading.Thread(target=s.wire.start_request,
                         args=("big", {"blob": "x" * 1_000_000}), daemon=True)
  big.start(); big.join(10)
  f = sys._current_frames()[s.wire._reader.ident]
  print("large write still blocked after 10 s:", big.is_alive())
  print("server still running:", s.process.poll() is None)
  print("reader thread stuck in:", f.f_code.co_name, "line", f.f_lineno)
  s.process.kill()
  ```

  Observed: `large write still blocked after 10 s: True`, `server still running: True`,
  `reader thread stuck in: _complete line 297` (the `with self._lock:`).
- Proposed fix: use two locks: a write lock held only around `_write`, and a table lock held only
  for dict operations, never across I/O. `start_request` registers the `Pending` under the table
  lock and then writes under the write lock. If ids must reach the wire in allocation order,
  allocate the id under the write lock, as now, and take the table lock briefly inside it. The
  reader must never wait on the write lock while the main thread blocks in a write: let `_refuse`
  write from a small sender thread or queue. Add a C2 test that runs this deadlock scenario with
  a timeout.
- Disposition: fix (A30): separate write lock and table lock, no table lock held during I/O, refusals and handler replies written off the reader thread. Passes when `FramingTest::test_large_write_does_not_block_reader` (C2) passes.

## Minors

- **P2-R3** (minor) `client/wire.py:180-203,257`, `client/session.py:157-186`: the wire has no
  closed state. After EOF, a request whose write still succeeds is never failed: with
  `r2_server.py` (reply once, `os.close(1)`, sleep) the second `request` raised `TimeoutError`
  after the full 3.0 s, `reader alive after EOF: False`. After `Session.close()`, `request`
  raises `ValueError: I/O operation on closed file` (not `OSError`, so the `except` at line 199
  misses it), and 1 `Pending` is left in the table. Fix: set a `closed` failure in `_fail_all`
  and `close_input`, have `start_request` raise it at once, and catch `ValueError` with
  `OSError`. Disposition: fix (A30): the wire gets a closed state; pending and new requests fail at once with `OSError` after EOF or `close()`, and leave no pending entry. Passes when `LifecycleTest::test_request_after_eof_or_close_fails_fast` (C3) passes.
- **P2-R4** (minor) `client/wire.py:107-117`, `client/session.py:115-124`: a timeout neither
  sends `notifications/cancelled` nor forgets the request. `request` cites lifecycle.mdx:248
  ("SHOULD establish timeouts"), but the same paragraph says the sender SHOULD then cancel and
  stop waiting. A fake server that replies after 1 s to a 0.3 s request gave: `still pending
  after timeout: 1`, `sent after timeout: []`, and the late reply was taken in silently
  (`reports: []`), not reported as a late reply. Fix: on `TimeoutError` in `Session.request`,
  call `cancel(pending, "timeout")`, so the late reply is abandoned, dropped and reported.
  Disposition: fix (A30), D2 amended: on timeout the client sends `notifications/cancelled` (reason `timeout`) and forgets the request, so a late reply is reported. Passes when `CancelTest::test_timeout_sends_cancel_and_forgets` (C5) passes.
- **P2-R5** (minor) `client/session.py:148-155`, `client/wire.py:226-236`: `cancel` checks
  `pending.done` outside the lock. If the reply lands between that check and `abandon`, `cancel`
  returns `True` and sends `notifications/cancelled` for a request that has completed, and
  `wait()` returns the result. That breaks its docstring ("Returns False, sending nothing, if the
  request already has its reply"). Forced interleaving (the reply delivered through
  `handle_line` just before `abandon`) printed `cancel returned: True`,
  `wait() returns: {'content': []}` and one `notifications/cancelled` line. Fix: have
  `abandon` return whether it removed the entry under the lock, and send the notification only
  then. Disposition: fix (A30): `done` check and abandon under one lock; cancel of a completed request returns False and sends nothing. Passes when `CancelTest::test_cancel_after_completion_returns_false` (C5) passes.
- **P2-R6** (minor) `tap/check.py:213-214,221`: on any revision other than 2025-11-25, an error
  or response frame crashes with `KeyError` and exit 1, which reads as "frames failed". The
  usage advertises `--revision <revision>`, and the docstring says a check that cannot run exits
  2. `python3 -m tap.check t.jsonl --revision 2025-06-18`, where `t.jsonl` holds a ping, its
  result and an error frame, gave `KeyError: 'JSONRPCErrorResponse'`, exit 1. That revision
  names the envelopes `JSONRPCResponse` and `JSONRPCError`. Fix: look the envelope names up in
  `load_schema` and raise `CheckError` (exit 2) when they are missing, or reject revisions other
  than 2025-11-25 in the usage check. Disposition: fix (A30): an unknown or unavailable revision exits 2. Passes when `CheckTest::test_unknown_revision_exits_2` (C9) passes.
- **P2-R7** (minor) `specs/phases/02-raw-client/validation.md:28`, `tests/test_check.py`: C9's
  named tests do not hold the validator's keyword checks or the definition choice for
  notifications and error frames. Mutants on `tap/check.py` (my runs): `enum`, `items`, `allOf`
  and `maximum` each ignored all survive the C9-named tests. Only
  `CheckTest.test_keywords_are_checked` kills them, and C9 does not name it, so G12 would not
  notice its removal. Two more mutants survive all of `tests/test_check.py`. In the first, error
  frames are not validated at all (`return "JSONRPCErrorResponse", []`). In the second,
  notifications are checked against the generic `JSONRPCNotification` instead of their method's
  definition. Fix: add `test_keywords_are_checked` to C9. Add an invalid error frame (for
  example a string `error.code`) and an invalid notification (for example a string
  `params.progress` in `notifications/progress`) to `test_invalid_frame_reports_seq_path_definition`.
  Disposition: fix (A30): C9 names `test_keywords_are_checked`; error frames are validated against `JSONRPCErrorResponse` and notifications against their method's definition. Passes when `CheckTest::test_error_frames_are_validated` and `CheckTest::test_notification_checked_against_its_method` (C9) pass.
- **P2-R8** (minor) `tools/check_claims.py:32-35`: G12 picks the Checks cell by position after
  splitting on `|`. A `|` in a claim cell shifts the columns, and a false pass follows. In a
  throwaway repo, the row ``| C1 | Ids 1 | "1" differ, in `tests` | `tests/test_gone.py::GoneTest::test_gone` | yes |``
  gave `claims: ok`, exit 0, although the named test does not exist. Fix: fail a row whose cell
  count differs from the header's, and find the Checks column by its header name.
  Disposition: fix (A30): G12 finds the Checks column from the table header and splits cells on unescaped `|` outside code spans. Passes when `ClaimsTest::test_pipe_in_claim_cell_does_not_shift_columns` (C10) passes.
- **P2-R9** (minor) `README.md:57-68`: under "Do them in order.", the merge put lesson 04 (the
  edge lab) before lesson 02. A CommonMark render (`markdown_it`) of the section is one `<ol>`
  linking `01-the-wire-and-the-handshake.md`, `04-edge-lab.md`, `02-raw-client.md`, numbered
  1, 2, 3. A reader who follows "in order" does the edge lab second. Fix: put lesson 02 second
  and lesson 04 third, with no blank line between items. Disposition: fix (A30): README lesson list in order 01-04. No test (docs).

## Not reported

- An observer race (`->` observed after the lock is released, so a fast `<-` could print first
  and keep manual mode's settle loop waiting) did not reproduce: 0 of 800 requests across 40
  manual runs. Dropped.
- The rest of what I probed held up. The id type is kept apart, `1`, `"1"` and `true` included.
  A server request whose id overlaps a pending client id is refused under its own id. A late
  reply after `cancel` is dropped and reported. Shutdown escalates to SIGTERM, then SIGKILL.
  `record.sh` passes on the client's status. `tap.check` pairs responses by direction and id, and
  reports an unknown method and an unpaired response as `unknown method`.
