# WIP status: phase-08-mutants-07 (D9 phase 7 part; second stop on STOP-USAGE 2026-11-25)

Branch is merged with main 2b6baec (main had not moved). Delete this file in the first real commit.
The earlier notes (mutants, survivor tests, what is equivalent) are kept below the line.

## Done since the last WIP
- Retests: `p7-sse-event-not-reset` (narrow command) killed; `p7-wire-receive-inline` (narrow command)
  killed by `test_reply_to_server_request_while_its_stream_is_open`; `p7-watch-upstream-none` is
  KILLED by the in-process tests (they call `client_left` on a watch never started), so its
  `equivalent` mark was dropped from `audits/mutants/phase-07.json` (committed). Equivalent marks: 17.
- `uvx ruff@0.17.1 check .` and `uvx mypy@2.4.0`: green.
- A single tap run (cap 5400 s) was too slow (the `p7-fwd-*` mutants take 3-4 min each); stopped at
  54 of 102 without a table. The tap part was restarted as 3 detached batches (`setsid nohup`, own
  sessions, `timeout 6000`), started 03:17:58 PKT 2026-11-25. The mutants-08 agent shares the 4 CPUs.

## Runs going when this was written (detached; they survive the agent)
Script: `/tmp/claude-1000/-home-zodiac-gitWork-mcps-practise/8f18d5f3-8804-44ce-9d2f-f5c3823af351/scratchpad/phase-08-mutants-07/run_batch.sh <b1|b2|b3>` runs `python3 tools/mutate.py --only "$(cat <name>.ids)" audits/mutants/phase-07.json`
from this worktree (node 24.22.0 on PATH). Each writes its table to `<name>.md` ONLY at its end,
`restored byte-identical` progress lines (one per mutant done) to `<name>.err`, and a last line
`exit N` to `<name>.err` (0 = every mutant killed or equivalent). Logs, all in `/tmp/claude-1000/-home-zodiac-gitWork-mcps-practise/8f18d5f3-8804-44ce-9d2f-f5c3823af351/scratchpad/phase-08-mutants-07/`:
- b1 (54 mutants): b1.ids, b1.md, b1.err
- b2 (24 mutants): b2.ids, b2.md, b2.err
- b3 (24 mutants): b3.ids, b3.md, b3.err
Check: `ps -eo pid,cmd | grep "mutate.py --only"`; the three `timeout 6000` PIDs at 03:17:58 were
156902 (b1), 156906 (b2), 156903 (b3). Expect them done about 04:45. After the runs, kill any
`tests/fake_servers/http_upstream.py` whose `/tmp/mutate-*/tree` no longer exists.
The runs' tree links `vendor` to THIS worktree's `vendor/`: keep the symlinks `vendor/servers`,
`vendor/spec` (to the main checkout) and `clients/sdk/node_modules` until they end (the tap tests do
not use vendor, but the client part and the gate do). They are not committed (`git status` shows
`T vendor/servers`, `T vendor/spec`, `?? clients/sdk/node_modules`). Before the final commits remove the
three symlinks and restore the empty submodule dirs with `git checkout vendor/servers vendor/spec`.

## ids per batch
b1: p7-sse-lf-only,p7-sse-cr-only,p7-sse-crlf-two-ends,p7-sse-lone-cr-eats-next,p7-sse-cr-at-chunk-end,p7-sse-cr-wait-rescan,p7-sse-scan-restart,p7-sse-no-trim,p7-sse-data-join-empty,p7-sse-strip-no-space,p7-sse-strip-all-spaces,p7-sse-strip-without-colon,p7-sse-comment-uncounted,p7-sse-comment-opens-event,p7-sse-comment-needs-space,p7-sse-field-case,p7-sse-field-prefix,p7-sse-id-dropped,p7-sse-event-dropped,p7-sse-id-event-swapped,p7-sse-retry-dropped,p7-sse-retry-unchecked,p7-sse-retry-ascii-test,p7-sse-bad-retry-opens-event,p7-sse-unknown-field-opens-event,p7-sse-blank-dispatches-untouched,p7-sse-event-not-reset,p7-sse-reset-keeps-id,p7-sse-finish-drops-tail-line,p7-sse-finish-not-partial,p7-sse-finish-untouched,p7-sse-finish-cr-off,p7-sse-finish-cr-dropped,p7-sse-finish-cr-kept,p7-sse-finish-buffer-kept,p7-sse-finish-scanned-kept,p7-rec-empty-data-is-frame,p7-rec-partial-empty-recorded,p7-rec-sse-meta-dropped,p7-rec-sse-event-key,p7-rec-sse-id-key,p7-rec-record-id,p7-rec-record-retry,p7-rec-partial-flag,p7-rec-tail-dropped,p7-rec-comments-count,p7-fwd-stream-read-blocks,p7-fwd-body-read-blocks,p7-fwd-send-before-record,p7-fwd-stream-kind-off,p7-fwd-kind-case,p7-fwd-kind-params,p7-fwd-chunked-off,p7-fwd-chunk-decimal
b2: p7-fwd-chunk-header-off,p7-fwd-stream-terminator,p7-fwd-body-terminator,p7-fwd-stream-clean-never,p7-fwd-stream-close-conn,p7-fwd-stream-by-server,p7-fwd-stream-by-client,p7-fwd-stream-by-ignores-completed,p7-fwd-stream-completed-unset,p7-fwd-body-completed-unset,p7-fwd-nobody-completed-unset,p7-fwd-record-after-last-piece,p7-fwd-body-partial-flag,p7-fwd-body-whole-by-end,p7-fwd-body-empty-frame,p7-fwd-body-close-conn,p7-fwd-head-has-body,p7-fwd-no-body-304,p7-fwd-nodelay,p7-proxy-unthreaded,p7-proxy-backlog,p7-proxy-daemon-threads,p7-proxy-drain-off,p7-watch-no-pollrdhup
b3: p7-watch-pollin,p7-watch-never-leaves,p7-watch-left-after-done,p7-watch-gone-unset,p7-watch-shutdown-wr,p7-watch-shutdown-rd,p7-watch-shutdown-off,p7-watch-upstream-none,p7-watch-poll-error,p7-watch-period,p7-watch-fallback-queued-ends,p7-watch-fallback-eof,p7-exch-end-for-streams,p7-exch-end-never,p7-exch-end-completed,p7-exch-close-conn,p7-relay-502-always,p7-relay-502-never,p7-open-no-watch,p7-open-stop-on-fail,p7-relay-finally-stop,p7-relay-head-oserror,p7-pump-body-oserror,p7-pump-stream-oserror

## Remaining
1. Read the three tables; every tap mutant must be killed or equivalent (check that each kill's failing
   tests are for the mutant's reason). Then the client part: the 109 ids of `client/http_wire.py` and
   `client/modern_http.py` (`/tmp/claude-1000/-home-zodiac-gitWork-mcps-practise/8f18d5f3-8804-44ce-9d2f-f5c3823af351/scratchpad/client.ids`), same script pattern (two batches in parallel is fine,
   about 30 min for one).  A mutant reported "marked equivalent but killed" needs its mark dropped.
2. Report rows: concatenate b1/b2/b3 `.md` into `/tmp/claude-1000/-home-zodiac-gitWork-mcps-practise/8f18d5f3-8804-44ce-9d2f-f5c3823af351/scratchpad/final_tap.md`, the client tables into
   `/tmp/claude-1000/-home-zodiac-gitWork-mcps-practise/8f18d5f3-8804-44ce-9d2f-f5c3823af351/scratchpad/final_client.md`, then `python3 /tmp/claude-1000/-home-zodiac-gitWork-mcps-practise/8f18d5f3-8804-44ce-9d2f-f5c3823af351/scratchpad/gen.py /tmp/claude-1000/-home-zodiac-gitWork-mcps-practise/8f18d5f3-8804-44ce-9d2f-f5c3823af351/scratchpad` writes `/tmp/claude-1000/-home-zodiac-gitWork-mcps-practise/8f18d5f3-8804-44ce-9d2f-f5c3823af351/scratchpad/report_rows.md` (rows in the
   style of `audits/mutation-final-pass.md`, new tests marked `(new)`); it prints the totals and problems.
3. C rows C180 upward in `specs/phases/08-final-pass/validation.md` (after C142, before C200; style of
   C100-C107), one per group of survivor tests (listed below); the mutants a test kills come from the tables.
4. Phase 7 section of `audits/mutation-final-pass.md` (between the markers, the summary row, and the
   sentence "Sections for phases 7 and 8 ..."), and a Result line in
   `specs/phases/07-streamable-http/validation.md` (like phase 5's line 71).
5. `scripts/gate.sh` once (needs the symlinks, node 24.22.0), then remove the symlinks, delete this file,
   squash into clean commits ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`,
   push the branch with `--force-with-lease` (the pre-push hook runs tests and is slow). Do not merge to main.

----- earlier notes (first WIP) -----

## Mutants (audits/mutants/phase-07.json, 211 = 102 tap + 109 client)

The WIP json from the first agent held specs only (no verdicts). This run: fixed 3 `old` texts that
the merge broke (`p7-wire-carrier-kept`, `p7-wire-receive-inline`, `p7-close-connections-kept`), added
9 mutants for C203/C205 (`p7-wire-next-post-*`, `p7-wire-receivers-*`, `p7-wire-join-*`,
`p7-close-no-join`, `p7-close-join-before-hangup`), dropped the `equivalent` mark of
`p7-sse-finish-buffer-kept` (killed by `test_finish_returns_the_cut_off_event_as_partial`), set
commands to include the new test modules, and gave `p7-sse-event-not-reset` and
`p7-wire-receive-inline` narrower commands (the first: the scaling tests turn quadratic and only time
out; the second: only `test_reply_to_server_request_while_its_stream_is_open`; neither re-run yet with
its new command).

First full runs (before the survivor tests): tap (code unchanged by the merge): 65 killed (one is
`p7-sse-event-not-reset`, killed only by timeout), 29 survived, 8 equivalent. Client (on the merged
code): 61 killed (one `p7-wire-receive-inline`, timeout), 37 survived, 11 equivalent.

Equivalent (signed, reasons are in the json): tap `p7-sse-strip-without-colon`, `p7-sse-retry-ascii-test`,
`p7-sse-finish-scanned-kept`, `p7-watch-upstream-none`, `p7-watch-poll-error`, `p7-watch-period`,
`p7-open-stop-on-fail`, `p7-relay-finally-stop`; client `p7-wire-session-any-status`,
`p7-sse-client-comment-test`, `p7-sse-client-empty-yield`, `p7-wire-refused-null-id`,
`p7-wire-by-request-kept`, `p7-wire-carrier-kept`, `p7-abandon-pop-kept`,
`p7-era-edge-whitespace-set`, `p7-era-version-preset`, new `p7-wire-receivers-kept`,
`p7-wire-join-stream-dropped` (reasons written for the two new ones). Note: the new in-process tests
call `client_left` on a watch that was never started, so `p7-watch-upstream-none` may now be KILLED;
if the clean re-run says "marked equivalent but killed", drop the mark.

## Survivor tests (all uncommitted in the working tree), each verified red on its mutant, green on code

- `tests/test_tap_sse.py`: `SseParserFramingTest::test_field_names_are_case_sensitive_whole_words`,
  `::test_an_event_starts_empty_after_one_is_dispatched` (retest killed field-case, field-prefix;
  event-not-reset was killed by timeout only: re-run with its new narrow command).
- `tests/test_tap_http_pump.py` (new module, in-process `ProxyHandler.exchange` with a fake upstream
  and wfile): `RecordBeforeForwardTest`, `ContentTypeTest`, `EndOfAnswerTest`, `LeavingWithTheLastBytesTest`,
  `NoBodyTest`, `WriteFailureTest`, `ClientWatchTest`, `NoDelayTest`, `DrainTest`.
- `tests/test_tap_http.py`: `HttpLifecycleTest::test_exit_does_not_wait_for_an_idle_client_connection`,
  `ClientHangUpTest::test_a_request_queued_behind_an_open_stream_is_not_itself_a_hang_up`.
  Tap retests: 13 + 17 = 30 mutants (the 29 survivors and event-not-reset), all killed.
- `tests/test_client_http.py`: `HttpWireDetailTest` (18), `HttpWireDetailTwoTest`, `SseDataTest`,
  `Era2026DetailTest`. Client retest 3 (39 mutants: the 37 survivors plus `p7-wire-any-4xx-ends` and
  `p7-wire-init-has-session`, whose first kills were by an unrelated test): 35 killed, 4 survived;
  retest 4 (after adding `test_closing_a_stream_before_its_head_arrives_is_no_failure`,
  `test_cancelling_a_request_before_its_head_arrives_is_no_failed_post`,
  `test_a_later_initialize_carries_no_session_headers_either`): those 4 killed (receive-error-always,
  stream-error-end-always-server, stream-error-always-reported, init-has-session). The whole of
  `tests.test_client_http` was green (60 tests) before those last three were added; `HttpWireDetailTest`
  (18) green after.

## Not done

1. Clean full re-run of the whole file (tap then client; the run of `final_tap.json` and `final_client.json`
   was started and killed): `python3 tools/mutate.py audits/mutants/phase-07.json`, with the vendor
   and node_modules symlinks from the main checkout (rm the empty dirs first, recreate after);
   it needs the NVM node 24.22.0. About 60 min for tap, 30 for client. Every mutant must come out
   killed or equivalent; check each kill's failing test is for the mutant's reason (a kill by
   `HttpModesTest.test_manual_posts_typed_line_verbatim` alone is the old flake: re-run alone).
2. C rows C180 upward in `specs/phases/08-final-pass/validation.md` (one per group of survivor tests:
   tap SSE parser; forwarder order/end/type; completed flag and write failures; watch; lifecycle
   (nodelay, drain, daemon threads); client version/initialize; `sse_data`; error status and session
   end; GET stream; close and cancel; era 2026 headers; C203 bound and C205 order). Row style: C100-C107.
3. Phase 7 section of `audits/mutation-final-pass.md` (between the phase 7 markers; also the summary
   table row) and the Result line in `specs/phases/07-streamable-http/validation.md` (like phase 5's).
4. `uvx ruff@0.17.1 check .`, `uvx mypy@2.4.0`, `python3 tools/check_claims.py --phases 08` if it
   accepts it, `scripts/gate.sh` once; squash into clean commits ending with the Co-Authored-By line;
   push with `--force-with-lease`. Do not merge to main.

## mutate.py leak note (for the orchestrator)

`tools/mutate.py` kills the runner's process group on timeout (`start_new_session=True`, `killpg`),
but the tap starts its child server with `process_group=0` (its own group), so a tap mutant that
hangs the tests and is timed out leaves that child (`tests/fake_servers/http_upstream.py`) alive.
Seven such processes from an earlier run were killed by hand. After a run: kill any
`http_upstream.py` whose `/tmp/mutate-*/tree` no longer exists.
