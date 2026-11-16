# WIP status: phase-08-mutants-07 (D9, phase 7 part; stopped on STOP-USAGE 2026-11-16)

Branch merged with main 2b6baec (it changes `client/http_wire.py`: C203 wait, C205 join). The
source files `tap/http.py`, `client/http_wire.py`, `client/modern_http.py` are unmodified (git diff
clean). Delete this file in the first real commit.

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
