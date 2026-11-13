# WIP status: phase-08-fix-r7-tap (Stage B, D10: tap HTTP findings)

Stopped on STOP-USAGE. Branch `phase-08-fix-r7-tap`, cut from `main` at `fe40e63`.
Delete this file in the first commit after resuming.

## Done

Tests written first; all six were red before the fix, for the finding's reason:

| Finding | Test | Red before the fix |
| --- | --- | --- |
| P8-R7-2 | `tests/test_tap_http.py::ClientHangUpTest::test_client_gone_before_response_head_closes_upstream` | "the server never saw the client hang up" (upstream `/slowhead` held its head 3 s, no disconnect) |
| P8-R7-2 | `tests/test_tap_http.py::ClientHangUpTest::test_client_gone_during_a_json_body_closes_upstream` | "the server never saw the client hang up" (`/slowbody`) |
| P8-R7-13 | `tests/test_tap_http.py::ClientHangUpTest::test_hang_up_behind_a_pipelined_request_is_passed_on` | "the server never saw the client hang up" (`/hold`, pipelined POST, then close) |
| P8-R7-12 | `tests/test_tap_http.py::HttpForwardTest::test_many_simultaneous_connections_are_all_answered` | 71 of 200 connections `ConnectionResetError(104)` |
| P8-R7-9 | `tests/test_tap_http.py::SseTest::test_stream_ended_by_a_lone_cr_is_a_whole_event` | frame had `partial: True` |
| P8-R7-9 | `tests/test_tap_sse.py::SseParserFramingTest::test_finish_takes_a_lone_cr_at_the_end_as_a_line_end` | `(b'x', True) != (b'x', False)` |

R7-9 re-checked against the linear `SseParser` first: still present (`finish()` dropped the
trailing CR as half a CRLF). The C28 test `test_cr_at_chunk_end_waits_for_a_possible_lf` pins the
"a CR at a piece end waits for the next byte" rule, so only `finish()` was changed; the D1-order
caveat for a CR split from its LF goes to *Accepted limits* (not yet written).

Fix in `tap/http.py` (uncommitted until this WIP commit):

- `Proxy.request_queue_size = 128` (R7-12).
- `SseParser.finish()`: a last lone CR ends its line, so `data: x` CR CR is a whole event (R7-9).
- New `ClientWatch`: started in `open_upstream` right after the request is sent, before
  `getresponse()`, for every response kind; stopped when the exchange ends. Uses
  `poll(POLLRDHUP)` where available (Linux), so a pipelined request does not end the watch
  (R7-13); elsewhere the old peek-and-stop fallback (an Accepted-limits line is needed for that).
  On hang-up it shuts the upstream socket down.
- `exchange` split into `exchange` + `relay`: a client gone before the head gets no 502; an
  exchange the client left records `http-end` `{by: client, comments: 0}` unless an event
  stream already wrote its own (R7-2). Failure to send the head counts as the client leaving.
- `pump_body`: a body cut off (upstream failure or client gone, including a short
  Content-Length body where `read1` returns `b""`) is recorded with `partial: true`, and the
  connection is closed; the terminating chunk is sent only after a whole body.
- `pump_stream` uses the shared watch instead of its own thread.
- `tests/fake_servers/http_upstream.py`: routes `/slowhead`, `/slowbody`, helper `peer_gone_within`.

Green after the fix: `tests.test_tap_http tests.test_tap_sse tests.test_tap tests.test_show_http`,
101 tests OK, run with `-W always::ResourceWarning` and no warning printed (vendor and
node_modules symlinked for that run, removed since). The new tests plus `HttpForwardTest` and
`SseTest` passed twice more in a row (the third repeat was stopped by STOP-USAGE). No fake
upstream of this worktree left running.

## Remaining

1. Re-run the four modules above 3-5 times (flake check), and check `/tmp/tmp*` count is stable
   (D6). Symlink `vendor/spec`, `vendor/servers` (rmdir the empty dirs first) and
   `clients/sdk/node_modules` from the main checkout for checks; remove them before committing
   (`rm` the links, `mkdir vendor/spec vendor/servers`).
2. `uvx ruff@0.17.1 check .`, `uvx mypy@2.4.0`, `tests.test_e2e_http`, G12
   (`python3 tools/check_claims.py --phases 02,03,04,05,06,07`) and
   `python3 tools/check_claims.py --phases 08` (show errors left belong to later stages).
3. Add C rows to `specs/phases/08-final-pass/validation.md` from C120 (orchestrator renumbers):
   C120 R7-2 (the two `ClientHangUpTest` before-head / json-body tests; mention the `partial`
   body frame and `http-end` by `client` for a non-stream exchange), C121 R7-13 (pipelined
   test), C122 R7-12 (200-connection test), C123 R7-9 (the two lone-CR tests). Mutation column:
   claim code (`tap/http.py` SSE parser and streaming forwarder are phase 7 claim code), e.g.
   "yes (the old watch / backlog 5 / old finish fail it)".
4. Accepted limits lines: (a) a CR that ends a piece is held until the next byte, so an event
   completed by a lone CR at a piece end is recorded after that piece is forwarded (D1 order;
   the pinned server writes LF only); (b) without `POLLRDHUP` (non-Linux) a hang-up behind a
   pipelined request is not passed on.
5. Update `audits/final-pass-review.md` section 2 rows: R7-2, R7-9, R7-12, R7-13 (reproduced,
   fixed, commit, test, C row) and R7-4 ("done by Stage A, `e211e4f`: `communicate()` closes
   the pipe", `tests/test_e2e_http.py:363`).
6. Squash this WIP commit into clean commits (tests+fix, records), messages ending with the
   Co-Authored-By line; delete this file; full `scripts/gate.sh` once; do not push or merge.

Possible review point (not a stop point in my judgement): recording `http-end` by `client` for
an exchange that is not an event stream extends phase 7 D1's record list (D1 lists `http-end`
for streams only; D3 already ties a client hang-up to `http-end` by `client`). The orchestrator
may want a register row naming it.
