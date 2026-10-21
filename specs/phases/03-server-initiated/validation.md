# Phase 3 — Raw client, 2025 era, server-initiated: validation

Lean profile (LP1–LP6 in `mission.md`). Every C row names its checks in the G12 form
(LP2). Inherited gates: G1–G5, G7–G9, G11, G12. G6 deferred (LP5).

## Claim code (RP3)

`client/handlers.py` (dispatch by method and declared capability, id echo, non-blocking
handling) and the notification reactions in `client/` (re-list coalescing, progress
matching). Mutation testing runs on the id echo, the capability check and the
non-blocking dispatch (LP4).

## C. Phase-specific correctness

| Row | Claim | Checks | Mutation |
| --- | --- | --- | --- |
| C1 | Each server request is answered with its own id, type included, by the handler for its method; an undeclared capability or unknown method gets `-32601` | `tests/test_client_handlers.py::HandlersTest::test_reply_echoes_id_and_type`, `tests/test_client_handlers.py::HandlersTest::test_undeclared_capability_is_refused`, `tests/test_client_handlers.py::HandlersTest::test_unknown_method_is_refused` | yes |
| C2 | A pending server request does not block a client request's reply | `tests/test_client_handlers.py::HandlersTest::test_server_request_does_not_block_reader` | yes |
| C3 | Sampling, elicitation (form and URL) and roots replies have the D1 shapes | `tests/test_client_handlers.py::RepliesTest::test_sampling_reply_shape`, `tests/test_client_handlers.py::RepliesTest::test_elicitation_form_values`, `tests/test_client_handlers.py::RepliesTest::test_elicitation_url_declines`, `tests/test_client_handlers.py::RepliesTest::test_roots_reply` | not claim code (RP3) |
| C4 | A burst of `list_changed` notifications causes one re-list; `resources/updated` causes a re-read; progress is matched by token | `tests/test_client_handlers.py::NotificationsTest::test_list_changed_burst_coalesces`, `tests/test_client_handlers.py::NotificationsTest::test_resource_updated_rereads`, `tests/test_client_handlers.py::NotificationsTest::test_progress_matched_by_token` | yes |
| C5 | The server tour against the real server exits 0 and its fresh trace holds every D4 server-initiated method | `tests/test_e2e.py::ServerTourTest::test_server_tour_sees_every_server_initiated_method` | not claim code (RP3) |
| C6 | The matrix shows each gated tool only with its capability | `tests/test_e2e.py::ServerTourTest::test_capability_matrix` | not claim code (RP3) |
| C7 | The server tour's fresh trace passes `tap.check` and the walkthrough explains it | `tests/test_e2e.py::ServerTourTest::test_server_tour_trace_checks_and_is_explained` | not claim code (RP3) |
| C8 | Lesson 03 has the L1 sections and its runnable blocks pass | `tests/test_lessons.py`, `tools/check_lessons.py` | not claim code (RP3) |
| C9 | The atlas regenerates byte-identical from the pinned schemas, lists every method of both revisions with kind and direction, and fails on a lesson declaring an unknown method; each lesson's declared methods appear in its fresh trace | `tests/test_atlas.py::AtlasTest::test_regenerated_atlas_matches_committed`, `tests/test_atlas.py::AtlasTest::test_every_schema_method_listed_with_direction`, `tests/test_atlas.py::AtlasTest::test_unknown_declared_method_fails`, `tests/test_e2e.py::AtlasClaimsTest::test_lesson_declarations_appear_in_fresh_traces`, `tools/atlas.py` | not claim code (RP3) |

## E. Not-done conditions

Not done if any server request goes unanswered in the server tour, if a recorded tour
uses a timer tool, or if the matrix output is committed.

## Result

- Status: open

### Accepted limits

- Learner walk L15, J rows, G6 walk: deferred (LP5).
- No review round for this phase (LP4).
- The atlas has no capability column: the schemas do not encode which capability gates a method (D6).

### Owner learning check (LP6)

Prompts written at close; answers by the owner only.
