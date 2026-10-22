# Phase 7 — Streamable HTTP: validation

Lean profile (LP1–LP6 in `mission.md`). Every C row names its checks in the G12 form (LP2).
None of them exists yet: phase 07 is added to the G12 list in `scripts/gate.sh` at close,
when its named tests exist (phase 2 D7 as amended). Inherited gates: G1–G5, G7–G12, green via
`scripts/gate.sh` locally and in CI; G5 gains `tests.test_e2e_http` in build step 2. G6
deferred (LP5). Rows are grouped by part (`requirements.md`, *Parts*); a part dropped by a
register row has its rows moved to *Accepted limits* in the same commit, so G12 never checks a
row whose tests were never meant to exist.

## Claim code (RP3)

`tap/http.py`: the SSE-to-frame parser (D4), the streaming forwarder (D3), the record order
and exchange numbering (D1), the header rule (D5). `client/http_wire.py`: the POST headers
(session id, protocol version; 2026-07-28 request headers), response dispatch to the phase 2
line handler and the error-status rule, the GET stream's place before `initialized`, the
reply-while-streaming path, cancellation closing the stream, and close by DELETE (D8, D11).
Mutation testing (LP4) runs where a row's check is the sole guard of a protocol rule: the rows
marked `yes`. Phase 2 and 3 claim code (`client/wire.py`, `client/session.py`,
`client/handlers.py`) is reused unchanged, so it is not mutated again here.

## C. Phase-specific correctness

| Row | Claim | Checks | Mutation |
| --- | --- | --- | --- |
| C1 | Part A. A request with a body is an `http-request` record then one `c2s` frame whose `raw` is the body byte for byte; a response head is an `http-response` record; a JSON body is one `s2c` frame; a GET, a DELETE and a `202` add no frame; exchanges are numbered from 0 in arrival order | `tests/test_tap_http.py::HttpRecordTest::test_post_body_is_one_c2s_frame_after_its_request_head`, `tests/test_tap_http.py::HttpRecordTest::test_json_response_is_one_s2c_frame_after_its_response_head`, `tests/test_tap_http.py::HttpRecordTest::test_bodiless_request_and_202_have_no_frames`, `tests/test_tap_http.py::HttpRecordTest::test_exchange_numbers_follow_arrival_order` | no (trace shape, not a protocol rule) |
| C2 | Part A. An SSE event with data is one `s2c` frame (data lines joined with `\n`; CRLF, LF and CR all end a line; one space after the colon removed; `id` and `event` kept); an empty-data event is an `sse-event` record; comments are forwarded, counted in `http-end` and not recorded; an event cut off by the stream's end is `partial`; non-UTF-8 data is `raw_b64` | `tests/test_tap_http.py::SseTest::test_event_data_becomes_one_frame`, `tests/test_tap_http.py::SseTest::test_line_endings_and_multiline_data`, `tests/test_tap_http.py::SseTest::test_empty_data_is_a_tap_record`, `tests/test_tap_http.py::SseTest::test_comments_are_counted_not_recorded`, `tests/test_tap_http.py::SseTest::test_unterminated_event_is_partial`, `tests/test_tap_http.py::SseTest::test_non_utf8_data_is_base64` | yes |
| C3 | Part A. Method, path, query, status, body bytes and every non-hop-by-hop header reach the other side unchanged; hop-by-hop headers do not; a request's records precede its upstream send, and an event's record precedes its forwarding | `tests/test_tap_http.py::HttpForwardTest::test_bodies_status_and_headers_forwarded_unchanged`, `tests/test_tap_http.py::HttpForwardTest::test_hop_by_hop_headers_not_forwarded`, `tests/test_tap_http.py::HttpForwardTest::test_records_precede_forwarding` | no (instrument behaviour, checked by its tests) |
| C4 | Part A. A response is forwarded piece by piece as it arrives: an event reaches the client before the stream ends, and a stream that waits for a second POST (the M9 round trip) completes through the tap | `tests/test_tap_http.py::HttpForwardTest::test_events_reach_client_before_stream_ends`, `tests/test_tap_http.py::HttpForwardTest::test_server_request_round_trip_does_not_deadlock` | yes |
| C5 | Part A. A client that disconnects mid-stream closes the upstream connection (`http-end` by `client`); an unreachable upstream gets `502` recorded `by tap`; a trace write failure stops recording and proxying goes on | `tests/test_tap_http.py::HttpForwardTest::test_client_disconnect_closes_upstream`, `tests/test_tap_http.py::HttpForwardTest::test_upstream_down_gives_502`, `tests/test_tap_http.py::HttpForwardTest::test_trace_write_failure_keeps_proxying` | no (fail-open paths, checked by their tests) |
| C6 | Part A. Only `accept`, `content-type`, `last-event-id` and `mcp-*` headers are recorded, names lowercased, a repeated header joined with `, ` | `tests/test_tap_http.py::HttpRecordTest::test_only_the_headers_that_matter_are_recorded` | no (trace content) |
| C7 | Part A. The tap listens only after the upstream accepts, on `127.0.0.1` only; a child that exits before that gives its code (1 if 0); SIGINT reaches the child, `exit` is the last record and the code is the child's; the child's stdout and stderr are `stderr` records, stdout ones with `stream`; `--http` with a bad value or with `--delay`/`--drop` exits 2 and starts nothing | `tests/test_tap_http.py::HttpLifecycleTest::test_listens_on_loopback_only_after_upstream_accepts`, `tests/test_tap_http.py::HttpLifecycleTest::test_child_exit_before_ready_gives_its_code`, `tests/test_tap_http.py::HttpLifecycleTest::test_sigint_forwarded_and_exit_is_last`, `tests/test_tap_http.py::HttpLifecycleTest::test_child_output_is_recorded_as_stderr`, `tests/test_tap_http.py::HttpLifecycleTest::test_usage_errors_start_nothing` | no (process timing) |
| C8 | Part A. An HTTP trace loads in `tap.show` and `tap.check` with no change to their reading, and its anchors are phase 1 D11's | `tests/test_tap_http.py::HttpRecordTest::test_trace_loads_in_show_and_check_unchanged` | no (format compatibility) |
| C9 | Part A (D6). `tap.show` summarises `http-*` and `sse-event` records and puts the exchange after a frame; anchors, `--full`, `--mermaid` and `--explain` are unchanged | `tests/test_show_http.py::ShowHttpTest::test_http_records_are_summarised`, `tests/test_show_http.py::ShowHttpTest::test_frames_show_their_exchange`, `tests/test_show_http.py::ShowHttpTest::test_anchors_and_other_views_unchanged` | not claim code (RP3) |
| C10 | Part A (D7). `record.sh --http --client http-tour` writes a run folder and the `recorded:` and `read it:` lines, starts the server under the D14 allowlist plus `PORT` with `streamableHttp`, and exits with the client's status; `--http` with a fixture is a usage error | `tests/test_e2e_http.py::RecordHttpTest::test_record_http_tour_writes_a_run_folder`, `tests/test_e2e_http.py::RecordHttpTest::test_spawn_uses_the_allowlist_plus_port`, `tests/test_e2e_http.py::RecordHttpTest::test_http_with_a_fixture_is_a_usage_error`, `scripts/record.sh` | not claim code (RP3) |
| C11 | Part B1. Each message is one POST with `Content-Type: application/json` and `Accept` listing both types; after `initialize` every request, GET and DELETE carries `Mcp-Session-Id` and `MCP-Protocol-Version`, and `initialize` carries neither | `tests/test_client_http.py::HttpWireTest::test_each_message_is_one_post_with_accept_and_content_type`, `tests/test_client_http.py::HttpWireTest::test_session_and_version_headers_after_initialize_only` | yes |
| C12 | Part B1. A JSON body or each SSE event's data reaches the phase 2 line handler (a response completes its request by id, a server request reaches the handlers, a notification is queued); `202` and empty-data events are skipped; another status fails the posted request at once unless its body carries a non-null id; a `404` ends the session | `tests/test_client_http.py::HttpWireTest::test_json_and_sse_bodies_reach_the_line_handler`, `tests/test_client_http.py::HttpWireTest::test_202_and_empty_events_are_skipped`, `tests/test_client_http.py::HttpWireTest::test_error_status_fails_the_request_at_once`, `tests/test_client_http.py::HttpWireTest::test_404_ends_the_session` | yes |
| C13 | Part B1. POSTs leave in write order, and a reply to a server request is posted while the request's own stream is still open | `tests/test_client_http.py::HttpWireTest::test_posts_leave_in_write_order`, `tests/test_client_http.py::HttpWireTest::test_reply_to_server_request_while_its_stream_is_open` | yes |
| C14 | Part B1. With capabilities declared the GET stream opens after the `initialize` result and before `notifications/initialized`; its server requests are answered by POST and its notifications queued; a refused GET is reported and the session goes on | `tests/test_client_http.py::HttpStreamTest::test_stream_opens_before_initialized`, `tests/test_client_http.py::HttpStreamTest::test_get_stream_delivers_requests_and_notifications`, `tests/test_client_http.py::HttpStreamTest::test_refused_stream_is_reported` | yes |
| C15 | Part B1. Cancelling a request closes the connection carrying its stream (2025: `notifications/cancelled` still sent); close sends DELETE with the session headers, ends every stream, fails what is pending and returns the DELETE status | `tests/test_client_http.py::HttpStreamTest::test_cancel_closes_the_response_stream`, `tests/test_client_http.py::HttpStreamTest::test_close_sends_delete_and_ends_streams` | yes |
| C16 | Part B1 (D9). The HTTP tour against the real server through the tap exits 0, its fresh trace holds every D9 method and passes `tap.check --revision 2025-11-25` | `tests/test_e2e_http.py::HttpTourTest::test_http_tour_runs_and_its_trace_checks` | not claim code (RP3) |
| C17 | Part B1 (D9). The fresh trace shows M3–M11: the `initialize` response is `text/event-stream` with `mcp-session-id` and a priming `sse-event`; `initialized` and the client's replies get `202` and no frame; `roots/list` is a frame of the GET exchange; `sampling/createMessage` is a frame of its `tools/call` exchange before that call's response; the cancelled exchange has no response and ends `by client`; DELETE gets `200` and the GET exchange then ends `by server` | `tests/test_e2e_http.py::HttpTourTest::test_fresh_trace_shows_what_http_adds` | not claim code (RP3) |
| C18 | Part B1 (D9). With `--no-stream` the tour's trace has no `roots/list` | `tests/test_e2e_http.py::HttpTourTest::test_without_the_stream_roots_list_never_arrives` | not claim code (RP3) |
| C19 | Part B1. `python3 -m client.http_tour --help` prints its usage on stdout and exits 0; the tap's usage names `--http` | `tests/test_help.py::HelpTest::test_help_prints_usage_on_stdout_and_exits_0` | not claim code (RP3) |
| C20 | Part E (D13). The walkthrough explains every record of the HTTP tour's fresh trace (no missing, no extra note) and its citations resolve | `tests/test_e2e_http.py::HttpTourTest::test_walkthrough_explains_fresh_trace`, `tools/check_citations.py` | not claim code (RP3) |
| C21 | Part E (D13). Lesson 07 has the L1 sections and its runnable blocks pass | `tests/test_lessons.py`, `tools/check_lessons.py` | not claim code (RP3) |
| C22 | Part B2 (D10). `tour` and `server-tour` with `--url` exit 0 against the real server through the tap, and their fresh traces hold every method of phase 2 D3 and phase 3 D4 and pass `tap.check` | `tests/test_e2e_http.py::HttpModesTest::test_tour_over_http`, `tests/test_e2e_http.py::HttpModesTest::test_server_tour_over_http` | not claim code (RP3) |
| C23 | Part B2 (D10). `manual --url` posts a typed line exactly as typed and prints a refusal's status and body; `--url` and `-- <command>` are mutually exclusive | `tests/test_client_http.py::HttpModesTest::test_manual_posts_typed_line_verbatim`, `tests/test_client_http.py::HttpModesTest::test_url_and_command_are_exclusive` | not claim code (RP3) |
| C24 | Part D (D11). In 2026-07-28 every POST carries `MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name` for `tools/call`, `resources/read` and `prompts/get`; no session header, GET or DELETE is sent; a name that is not plain ASCII is refused before sending | `tests/test_client_http.py::Era2026Test::test_every_post_carries_the_request_headers`, `tests/test_client_http.py::Era2026Test::test_no_session_stream_or_delete`, `tests/test_client_http.py::Era2026Test::test_non_ascii_name_is_refused` | yes |
| C25 | Part D (D11). Cancelling a 2026-07-28 request closes its stream and posts no `notifications/cancelled` | `tests/test_client_http.py::Era2026Test::test_cancel_closes_stream_without_notification` | yes |
| C26 | Part D (D11). Phase 6's 2026-07-28 tour over HTTP exits 0 and its fresh trace passes `tap.check --revision 2026-07-28` | `tests/test_e2e_http.py::Era2026HttpTest::test_2026_tour_over_http_checks` | not claim code (RP3) |
| C27 | Part C (D12). The SDK client's tour over HTTP exits 0, its fresh trace passes `tap.check` and ends with a DELETE | `tests/test_e2e_http.py::SdkHttpTest::test_sdk_tour_over_http_checks_and_deletes` | not claim code (RP3) |

## E. Not-done conditions

Not done if the tap or the raw client imports anything outside the Python standard library
(P4), if `client/wire.py`, `client/session.py` or the tap's stdio path is changed without a
register row, if an HTTP trace needs any change to how `tap.show` or `tap.check` read records,
if the HTTP tour's fresh trace fails `tap.check` or `--explain`, if any C row of a part not
dropped names a check that does not exist, or if run output is tracked.

## Result

- Status: open

Not built. Final atlas coverage (L8) is measured at close with `tools/atlas.py` after phases
5–7 merge, and its counts (methods exercised of 31 in 2025-11-25 and of 21 in 2026-07-28) are
written here.

### Accepted limits

- J rows, the learner walk (L15), the G6 clean-clone walk and lesson polish beyond the L1
  sections: deferred (LP5).
- No review round (LP4): phase 2 and 3 claim code is reused, not changed.
- The pinned server binds every interface while a recording runs (M1), against the spec's
  SHOULD; the tap itself listens on loopback only, and the server's environment is the D14
  allowlist plus `PORT`.
- Not recorded: chunk framing, TCP connections, SSE `data:` prefixes and fields other than
  `id`, `event`, `retry`, and headers outside D5 (D1, D3, D4, D5).
- The two ports `record.sh` picks are released before the tap binds them and can be taken by
  another process; the run then fails and says so (D7).
- The pinned server answers a GET on the 2026-07-28 path `400`, not the spec's `405` (M13):
  recorded as measured and explained in the walkthrough.
- Resumability, re-initialising after `404`, keep-alive reuse, the `Mcp-Name` Base64 form,
  fixtures and `matrix` over HTTP: out of scope (D14).
- Parts C and D: if phases 5 or 6 are not built in this run, the part is dropped by a register
  row and its rows (C24–C27) move here.

### Owner learning check (LP6)

Optional (register row 2026-10-21, learning check). Answers by the owner only; the agent adds
a one-line verdict under each after checking it against a fresh trace.

1. *Explain.* Record `scripts/record.sh --http --client http-tour lc7` and, from `tap.show`
   alone, explain: why the `initialize` reply arrives as an event stream that opens with an
   event carrying no data; how the client learns the session id and where it sends it from
   then on; and why the server's `roots/list` arrives on a different exchange from every reply
   the client asked for.
2. *Change.* On a branch of your own, make the raw client open its GET stream after
   `notifications/initialized` instead of before (what the SDK client does, M15). **Before
   running it**, write down what you expect to change in the HTTP tour's trace (hint: the
   `roots/list` sync comes about 350 ms after `initialized`). Then run the tests and the tour,
   compare, and explain every difference from your prediction. Commit the change yourself on
   that branch; do not merge it.
3. *Debug.* The local branch `learning-check-07-fault` has one planted fault in
   `client/http_wire.py`. From the test output and a fresh trace only (no `git diff`, no
   `git log -p`), say what is wrong on the wire, which function causes it, and the fix. The
   agent reveals the fault after you answer.

Answers:
