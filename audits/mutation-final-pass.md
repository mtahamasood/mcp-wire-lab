# Mutation of the claim code, final pass (phase 8, D9)

The mutation run that phases 5, 6 and 7 deferred (register row 2026-10-22, lean build of phases
5-7; `specs/phases/05-sdk-client/validation.md` and `06-era-2026/validation.md`, *Claim code*), run
with `tools/mutate.py` (D8). Each mutant is one exact text replacement in a temporary copy of the
tree; the real tree is never written. A mutant is **killed** when its test command fails,
**equivalent** when it cannot change behaviour and its row says why (RP3), and a **survivor** is
neither: it is killed by a new test that pins behaviour the spec specifies, or signed equivalent
with its reason. A survivor that showed a spec gap would get a register row first; none did.

The mutants files are `audits/mutants/phase-05.json`, `phase-06.json`, `phase-07.json` and
`phase-08.json`. Rerun one with `python3 tools/mutate.py audits/mutants/phase-05.json` (with
`vendor/` and `clients/sdk/node_modules` present; the files list them under `links`). The tool's
output is run output and is not committed (A5); this file is the authored report.

## Summary

Sections for phases 7 and 8 are filled by a later run, between their markers; the rows below are
updated with them.

| Phase | Mutants file | Mutants | Killed | Equivalent | Survivors left | Run |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | `audits/mutants/phase-05.json` | 31 | 31 | 0 | 0 | 2026-11-14 |
| 6 | `audits/mutants/phase-06.json` | 68 | 65 | 3 | 0 | 2026-11-14 |
| 7 | `audits/mutants/phase-07.json` | (not yet run) | | | | |
| 8 | `audits/mutants/phase-08.json` | (not yet run) | | | | |

The first run of phase 5 gave 27 killed and 4 survivors; of phase 6, 53 killed and 15 survivors.
The survivors were disposed as the sections below list, and each file was run again, in full, with
the result in the table above. Every `yes` row of the two phases has mutants (how many, by row):
phase 5 C1 17 and C2 14; phase 6 C2 12, C3 8, C4 13, C5 14, C9 4 and C16 17. Rows marked `no` or
`not claim code` in those phases' `validation.md` (phase 5 C4; phase 6 C1, whose envelope
`tap.check` also guards) were not mutated.

The mutants began as the reviewers' 30 hand mutants (`audits/final-pass-review.md`, *Mutation
candidates*), kept with their ids, and were widened to the rest of each row's claim code. Two
differences from that list: `p5-diff-explain-exit` is not carried (it is `--explain`'s exit code,
phase 5 C4, which the phase marks `no`), and `p6-check-task-other-method`, which the review wrote as
`method == "tasks/get"`, is kept as `p6-check-task-other-method-narrow`; the id
`p6-check-task-other-method` is the whole rule switched off.

## Phase 5: `tap/diff.py` (message keys and comparison)

Command for every mutant: `python3 -m unittest tests.test_diff` (about 0.3 s). A test marked
(new) was written in this run to kill a survivor; its row is in `specs/phases/08-final-pass/
validation.md` (C100 onward).

| id | row | target | change | verdict | killed by |
| --- | --- | --- | --- | --- | --- |
| `p5-diff-pop-to-get` | C1 | `tap/diff.py` | a second response with the same id pairs with the request again (P8-R5-2) | killed | `tests/test_diff.py::KeysTest::test_response_keyed_by_the_request_it_answers` |
| `p5-diff-response-direction` | C1 | `tap/diff.py` | a response pairs with a request of its own direction | killed | `tests/test_diff.py::KeysTest::test_renumbered_ids_are_not_a_difference`, `tests/test_diff.py::KeysTest::test_response_keyed_by_the_request_it_answers` (+2 more) |
| `p5-diff-response-id-type` | C1 | `tap/diff.py` | a response pairs by id text only: 1 and "1" are one id | killed | `tests/test_diff.py::KeysTest::test_renumbered_ids_are_not_a_difference`, `tests/test_diff.py::KeysTest::test_response_keyed_by_the_request_it_answers` (+2 more) |
| `p5-diff-request-id-type` | C1 | `tap/diff.py` | a request is filed by id text only (pending side) | killed | `tests/test_diff.py::KeysTest::test_cancelled_request_id_is_mapped`, `tests/test_diff.py::KeysTest::test_only_a_cancellation_has_its_request_id_mapped` (new) (+4 more) |
| `p5-diff-error-not-a-response` | C1 | `tap/diff.py` | an error reply is a non-message frame, not paired with its request | killed | `tests/test_diff.py::KeysTest::test_response_keyed_by_the_request_it_answers` |
| `p5-diff-response-key-prefix` | C1 | `tap/diff.py` | a response key keeps the request's direction prefix | killed | `tests/test_diff.py::KeysTest::test_response_keyed_by_the_request_it_answers`, `tests/test_diff.py::KeysTest::test_response_pairing_keeps_the_id_type` (+1 more) |
| `p5-diff-occurrence-not-counted` | C1 | `tap/diff.py` | a request or notification is keyed without counting its occurrence | killed | `tests/test_diff.py::ExplainTest::test_every_entry_needs_a_note`, `tests/test_diff.py::ExplainTest::test_section_shared_and_ranges` (+2 more) |
| `p5-diff-nonmessage-occurrence` | C1 | `tap/diff.py` | non-message frames of one direction share a key | killed | `tests/test_diff.py::KeysTest::test_non_message_frames_keyed_apart`, `tests/test_diff.py::KeysTest::test_response_keyed_by_the_request_it_answers` |
| `p5-diff-nonmessage-slot` | C1 | `tap/diff.py` | non-message frames are keyed without their direction | killed | `tests/test_diff.py::KeysTest::test_non_message_frames_keyed_apart`, `tests/test_diff.py::KeysTest::test_response_keyed_by_the_request_it_answers` (+1 more) |
| `p5-diff-request-slot-direction` | C1 | `tap/diff.py` | requests and notifications are keyed without their direction | killed | `tests/test_diff.py::KeysTest::test_renumbered_ids_are_not_a_difference`, `tests/test_diff.py::KeysTest::test_response_keyed_by_the_request_it_answers` (+7 more) |
| `p5-diff-cancel-direction` | C1 | `tap/diff.py` | a cancelled requestId is looked up in the other direction | killed | `tests/test_diff.py::KeysTest::test_cancelled_request_id_is_mapped`, `tests/test_diff.py::KeysTest::test_only_a_cancellation_has_its_request_id_mapped` (new) |
| `p5-diff-cancel-id-type` | C1 | `tap/diff.py` | a cancelled requestId is looked up by id text only | killed | `tests/test_diff.py::KeysTest::test_cancelled_request_id_is_mapped`, `tests/test_diff.py::KeysTest::test_only_a_cancellation_has_its_request_id_mapped` (new) |
| `p5-diff-asked-dropped` | C1 | `tap/diff.py` | a request is never recorded for requestId mapping | killed | `tests/test_diff.py::KeysTest::test_cancelled_request_id_is_mapped`, `tests/test_diff.py::KeysTest::test_only_a_cancellation_has_its_request_id_mapped` (new) |
| `p5-diff-id-not-normalised` | C1 | `tap/diff.py` | ids are compared as written | killed | `tests/test_diff.py::KeysTest::test_cancelled_request_id_is_mapped`, `tests/test_diff.py::KeysTest::test_only_a_cancellation_has_its_request_id_mapped` (new) (+1 more) |
| `p5-diff-cancel-not-normalised` | C1 | `tap/diff.py` | the requestId of a cancellation is compared as written | killed | `tests/test_diff.py::KeysTest::test_cancelled_request_id_is_mapped`, `tests/test_diff.py::KeysTest::test_only_a_cancellation_has_its_request_id_mapped` (new) |
| `p5-diff-cancel-method-gate` | C1 | `tap/diff.py` | the requestId of any notification is mapped to a request key (the review's near-equivalent survivor) | killed | `tests/test_diff.py::KeysTest::test_only_a_cancellation_has_its_request_id_mapped` (new) |
| `p5-diff-nonmessage-text` | C1 | `tap/diff.py` | non-message frames always compare equal | killed | `tests/test_diff.py::EqualityTest::test_timings_and_non_messages_ignored` |
| `p5-diff-same-type` | C2 | `tap/diff.py` | 1, 1.0 and true compare equal | killed | `tests/test_diff.py::EqualityTest::test_number_and_boolean_types_differ` |
| `p5-diff-same-keys` | C2 | `tap/diff.py` | a member only in b is not a difference | killed | `tests/test_diff.py::EqualityTest::test_an_extra_member_or_array_item_is_a_difference` (new) |
| `p5-diff-same-list-length` | C2 | `tap/diff.py` | a longer array equals its prefix | killed | `tests/test_diff.py::EqualityTest::test_an_extra_member_or_array_item_is_a_difference` (new) |
| `p5-diff-same-list-order` | C2 | `tap/diff.py` | array order is ignored | killed | `tests/test_diff.py::EqualityTest::test_array_order_matters` |
| `p5-diff-order-ignored` | C2 | `tap/diff.py` | member order is no longer a bytes-only difference | killed | `tests/test_diff.py::EqualityTest::test_member_order_is_a_bytes_only_difference`, `tests/test_diff.py::OutputTest::test_summary_and_exit_codes` |
| `p5-diff-plain-ignored` | C2 | `tap/diff.py` | spacing and escapes are no longer a bytes-only difference | killed | `tests/test_diff.py::EqualityTest::test_member_order_is_a_bytes_only_difference` |
| `p5-diff-plain-always` | C2 | `tap/diff.py` | the compact-form flag is always true | killed | `tests/test_diff.py::EqualityTest::test_member_order_is_a_bytes_only_difference` |
| `p5-diff-bytes-only-counted-as-equal` | C2 | `tap/diff.py` | a bytes-only pair is counted as equal | killed | `tests/test_diff.py::EqualityTest::test_member_order_is_a_bytes_only_difference`, `tests/test_diff.py::OutputTest::test_summary_and_exit_codes` |
| `p5-diff-absent-member` | C2 | `tap/diff.py` | a missing member is shown as null, not (absent) | killed | `tests/test_diff.py::EqualityTest::test_an_extra_member_or_array_item_is_a_difference` (new), `tests/test_diff.py::OutputTest::test_paths_and_values_listed` |
| `p5-diff-member-only-in-b` | C2 | `tap/diff.py` | a member only in b is not listed | killed | `tests/test_diff.py::OutputTest::test_paths_and_values_listed`, `tests/test_diff.py::EqualityTest::test_an_extra_member_or_array_item_is_a_difference` (new) |
| `p5-diff-list-extra-item` | C2 | `tap/diff.py` | an extra array item is not listed | killed | `tests/test_diff.py::EqualityTest::test_an_extra_member_or_array_item_is_a_difference` (new) |
| `p5-diff-only-a-dropped` | C2 | `tap/diff.py` | keys only in a are not reported | killed | `tests/test_diff.py::OutputTest::test_only_in_one_trace_listed`, `tests/test_diff.py::OutputTest::test_summary_and_exit_codes` |
| `p5-diff-only-b-dropped` | C2 | `tap/diff.py` | keys only in b are not reported | killed | `tests/test_diff.py::OutputTest::test_only_in_one_trace_listed`, `tests/test_diff.py::OutputTest::test_summary_and_exit_codes` |
| `p5-diff-seq-compared` | C2 | `tap/diff.py` | the frame's seq is compared (timings and seq must not be) | killed | `tests/test_diff.py::EqualityTest::test_timings_and_non_messages_ignored` |

### Survivors of the first run, and what became of them

| Mutant | Why it survived | Disposition |
| --- | --- | --- |
| `p5-diff-pop-to-get` | (the review's P8-R5-2; already killed on the merged tree, so not a survivor of this run) | killed by `KeysTest::test_response_keyed_by_the_request_it_answers` (C22) |
| `p5-diff-cancel-method-gate` | the near-equivalent one: in real traffic only `notifications/cancelled` carries `params.requestId`. The spec text (phase 5 D4) names only that notification, so another notification's `requestId` is compared as written | killed by new `KeysTest::test_only_a_cancellation_has_its_request_id_mapped` (C101); not signed equivalent, since a test can pin what D4 says |
| `p5-diff-same-keys` | no test had a member that only the second trace holds | killed by new `EqualityTest::test_an_extra_member_or_array_item_is_a_difference` (C100) |
| `p5-diff-same-list-length` | no test had an array that is a prefix of the other | killed by the same test (C100) |
| `p5-diff-list-extra-item` | the differing path of an extra array item was never listed in a test | killed by the same test (C100) |

## Phase 6: `client/modern.py` and `tap/check.py`

Commands: `python3 -m unittest tests.test_client_modern` for `client/modern.py` (about 4 s) and
`python3 -m unittest tests.test_check` for `tap/check.py` (about 0.3 s).

| id | row | target | change | verdict | killed by |
| --- | --- | --- | --- | --- | --- |
| `p6-modern-gate-off` | C2 | `client/modern.py` | requests are allowed before discover | killed | `tests/test_client_modern.py::DiscoverTest::test_a_malformed_discover_reply_stops_the_session` (new), `tests/test_client_modern.py::DiscoverTest::test_no_request_before_discover_reply` (+1 more) |
| `p6-modern-gate-not-called` | C2 | `client/modern.py` | start_request no longer checks that discover has been answered | killed | `tests/test_client_modern.py::DiscoverTest::test_a_malformed_discover_reply_stops_the_session` (new), `tests/test_client_modern.py::DiscoverTest::test_no_request_before_discover_reply` (+1 more) |
| `p6-modern-ready-early` | C2 | `client/modern.py` | the session is ready before the discover reply | killed | `tests/test_client_modern.py::DiscoverTest::test_a_malformed_discover_reply_stops_the_session` (new), `tests/test_client_modern.py::DiscoverTest::test_other_error_suggests_2025_era` (+3 more) |
| `p6-modern-ready-never` | C2 | `client/modern.py` | the session is never ready after a good discover | killed | `tests/test_client_modern.py::DiscoverTest::test_no_request_before_discover_reply`, `tests/test_client_modern.py::EnvelopeTest::test_every_request_carries_the_envelope` (+20 more) |
| `p6-modern-version-check` | C2 | `client/modern.py` | any list of supported versions is accepted | killed | `tests/test_client_modern.py::DiscoverTest::test_unsupported_version_stops` |
| `p6-modern-version-not-list` | C2 | `client/modern.py` | a supportedVersions that is a string holding the era is accepted | killed | `tests/test_client_modern.py::DiscoverTest::test_a_malformed_discover_reply_stops_the_session` (new) |
| `p6-modern-32022` | C2 | `client/modern.py` | another error is reported as an unsupported version | killed | `tests/test_client_modern.py::DiscoverTest::test_other_error_suggests_2025_era` |
| `p6-modern-32022-ignored` | C2 | `client/modern.py` | -32022 is reported like any other error (no offered versions, 2025 hint) | killed | `tests/test_client_modern.py::DiscoverTest::test_unsupported_version_error_stops`, `tests/test_client_modern.py::DiscoverTest::test_unsupported_version_error_with_malformed_data_still_says_what_was_sent` |
| `p6-modern-other-error-hint` | C2 | `client/modern.py` | another error no longer names --era 2025-11-25 | killed | `tests/test_client_modern.py::DiscoverTest::test_other_error_suggests_2025_era` |
| `p6-modern-offered-shown` | C2 | `client/modern.py` | the -32022 stop does not name the offered versions | killed | `tests/test_client_modern.py::DiscoverTest::test_unsupported_version_error_stops`, `tests/test_client_modern.py::DiscoverTest::test_unsupported_version_error_with_malformed_data_still_says_what_was_sent` |
| `p6-modern-offered-shown-list` | C2 | `client/modern.py` | the version-list stop does not name the offered versions | killed | `tests/test_client_modern.py::DiscoverTest::test_unsupported_version_stops` |
| `p6-modern-discover-input-required` | C2 | `client/modern.py` | an input_required reply to discover is not refused | killed | `tests/test_client_modern.py::DiscoverTest::test_a_malformed_discover_reply_stops_the_session` (new) |
| `p6-modern-task-gate` | C3 | `client/modern.py` | a task result is accepted without the extension | killed | `tests/test_client_modern.py::ResultTypeTest::test_task_needs_the_tasks_extension_not_just_any_extension` (new), `tests/test_client_modern.py::ResultTypeTest::test_task_only_with_tasks_extension` |
| `p6-modern-task-gate-open` | C3 | `client/modern.py` | task accepted only without the extension | killed | `tests/test_client_modern.py::ResultTypeTest::test_task_needs_the_tasks_extension_not_just_any_extension` (new), `tests/test_client_modern.py::ResultTypeTest::test_task_only_with_tasks_extension` |
| `p6-modern-task-caps-from-request` | C3 | `client/modern.py` | request() always treats the tasks extension as declared | killed | `tests/test_client_modern.py::ResultTypeTest::test_task_needs_the_tasks_extension_not_just_any_extension` (new), `tests/test_client_modern.py::ResultTypeTest::test_task_only_with_tasks_extension` |
| `p6-modern-declares-tasks` | C3 | `client/modern.py` | any extension counts as declaring tasks | killed | `tests/test_client_modern.py::ResultTypeTest::test_task_needs_the_tasks_extension_not_just_any_extension` (new) |
| `p6-modern-absent-is-complete` | C3 | `client/modern.py` | an absent resultType is not a result | killed | `tests/test_client_modern.py::ResultTypeTest::test_complete_and_absent_are_results` |
| `p6-modern-unrecognized-accepted` | C3 | `client/modern.py` | an unrecognized resultType is returned as a result | killed | `tests/test_client_modern.py::ResultTypeTest::test_unrecognized_result_type_is_invalid` |
| `p6-modern-input-required-branch` | C3 | `client/modern.py` | an input_required result is invalid (falls to the unrecognized rule) | killed | `tests/test_client_modern.py::EnvelopeTest::test_every_request_carries_the_envelope`, `tests/test_client_modern.py::InputRequiredTest::test_input_requests_without_an_answer_function_cannot_be_answered` (new) (+6 more) |
| `p6-modern-non-object-result` | C3 | `client/modern.py` | a result that is not an object is not refused | killed | `tests/test_client_modern.py::ResultTypeTest::test_unrecognized_result_type_is_invalid` |
| `p6-modern-state-dropped` | C4 | `client/modern.py` | requestState is not echoed | killed | `tests/test_client_modern.py::InputRequiredTest::test_request_state_is_echoed_byte_for_byte_whatever_it_holds` (new), `tests/test_client_modern.py::InputRequiredTest::test_retry_carries_responses_and_state_verbatim` (+1 more) |
| `p6-modern-state-truthy` | C4 | `client/modern.py` | an empty requestState is not echoed | killed | `tests/test_client_modern.py::InputRequiredTest::test_request_state_is_echoed_byte_for_byte_whatever_it_holds` (new) |
| `p6-modern-state-reencoded` | C4 | `client/modern.py` | requestState is trimmed (not byte for byte) | killed | `tests/test_client_modern.py::InputRequiredTest::test_request_state_is_echoed_byte_for_byte_whatever_it_holds` (new) |
| `p6-modern-stale-retry` | C4 | `client/modern.py` | a retry inherits the previous round's fields (P8-R6-3a) | killed | `tests/test_client_modern.py::InputRequiredTest::test_retry_does_not_inherit_a_previous_rounds_state` |
| `p6-modern-responses-dropped` | C4 | `client/modern.py` | the retry carries no inputResponses | killed | `tests/test_client_modern.py::EnvelopeTest::test_every_request_carries_the_envelope`, `tests/test_client_modern.py::InputRequiredTest::test_retry_carries_responses_and_state_verbatim` (+2 more) |
| `p6-modern-response-per-key` | C4 | `client/modern.py` | an inputResponses entry is the request, not the answer | killed | `tests/test_client_modern.py::InputRequiredTest::test_unanswerable_request_raises`, `tests/test_client_modern.py::InputRequiredTest::test_no_answer_is_computed_for_a_round_that_is_not_sent` (new) (+1 more) |
| `p6-modern-responses-all-keys` | C4 | `client/modern.py` | only the first input request is answered | killed | `tests/test_client_modern.py::InputRequiredTest::test_retry_carries_responses_and_state_verbatim` |
| `p6-modern-rounds` | C4 | `client/modern.py` | one request fewer than max_rounds | killed | `tests/test_client_modern.py::InputRequiredTest::test_no_answer_is_computed_for_a_round_that_is_not_sent` (new), `tests/test_client_modern.py::InputRequiredTest::test_round_limit` |
| `p6-modern-round-limit-break` | C4 | `client/modern.py` | an input request is answered after the last allowed request | killed | `tests/test_client_modern.py::InputRequiredTest::test_no_answer_is_computed_for_a_round_that_is_not_sent` (new) |
| `p6-modern-round-limit-error` | C4 | `client/modern.py` | the round limit returns an empty result | killed | `tests/test_client_modern.py::InputRequiredTest::test_no_answer_is_computed_for_a_round_that_is_not_sent` (new), `tests/test_client_modern.py::InputRequiredTest::test_round_limit` |
| `p6-modern-unanswerable` | C4 | `client/modern.py` | no answer function is not refused | killed | `tests/test_client_modern.py::InputRequiredTest::test_input_requests_without_an_answer_function_cannot_be_answered` (new) |
| `p6-modern-params-not-copied` | C4 | `client/modern.py` | the caller's params are the retry's base (aliased) | equivalent | equivalent: `base` is only read: each round copies it with dict(base) and `request` deep-copies the params into the envelope, so nothing the function does writes through the alias. It differs only for a caller that mutates its own params from inside `answer`, which no caller does and no row specifies. |
| `p6-modern-first-request-bare` | C4 | `client/modern.py` | every round sends the bare params (no responses, no state) | killed | `tests/test_client_modern.py::EnvelopeTest::test_every_request_carries_the_envelope`, `tests/test_client_modern.py::InputRequiredTest::test_request_state_is_echoed_byte_for_byte_whatever_it_holds` (new) (+3 more) |
| `p6-modern-sub-key-type` | C5 | `client/modern.py` | a notification is filed under the stringified subscription id | killed | `tests/test_client_modern.py::EnvelopeTest::test_every_request_carries_the_envelope`, `tests/test_client_modern.py::EnvelopeTest::test_notifications_carry_no_envelope` (+6 more) |
| `p6-modern-sub-wait-key-type` | C5 | `client/modern.py` | a wait looks up the stringified id (3 and "3" are one stream) | killed | `tests/test_client_modern.py::EnvelopeTest::test_every_request_carries_the_envelope`, `tests/test_client_modern.py::EnvelopeTest::test_notifications_carry_no_envelope` (+7 more) |
| `p6-modern-sub-messages-key-type` | C5 | `client/modern.py` | seen() looks up the stringified id | killed | `tests/test_client_modern.py::ListenTest::test_notifications_routed_by_subscription_id`, `tests/test_client_modern.py::ListenTest::test_wait_for_takes_only_the_method_asked_for` (+1 more) |
| `p6-modern-sub-ack-id` | C5 | `client/modern.py` | the acknowledgment is matched on the stringified listen id | killed | `tests/test_client_modern.py::EnvelopeTest::test_every_request_carries_the_envelope`, `tests/test_client_modern.py::EnvelopeTest::test_notifications_carry_no_envelope` (+5 more) |
| `p6-modern-sub-ack-any` | C5 | `client/modern.py` | the acknowledgment of any subscription satisfies listen | killed | `tests/test_client_modern.py::ListenTest::test_notifications_routed_by_subscription_id`, `tests/test_client_modern.py::ListenTest::test_ack_matched_by_subscription_id_type_included` |
| `p6-modern-wait-method` | C5 | `client/modern.py` | wait_for takes a notification of any method (P8-R6-3b) | killed | `tests/test_client_modern.py::ListenTest::test_wait_for_takes_only_the_method_asked_for` |
| `p6-modern-wait-match` | C5 | `client/modern.py` | wait_for ignores its match predicate | killed | `tests/test_client_modern.py::ListenTest::test_wait_for_takes_the_notification_its_match_accepts` (new) |
| `p6-modern-wait-consume` | C5 | `client/modern.py` | a matched notification is not consumed (read twice) | killed | `tests/test_client_modern.py::ListenTest::test_notifications_routed_by_subscription_id`, `tests/test_client_modern.py::ListenTest::test_wait_for_takes_only_the_method_asked_for` (+1 more) |
| `p6-modern-feed-no-notify` | C5 | `client/modern.py` | a filed notification does not wake a waiter | killed | `tests/test_client_modern.py::ListenTest::test_a_waiter_is_woken_when_its_notification_arrives` (new) |
| `p6-modern-close-no-cancel` | C5 | `client/modern.py` | close() sends no notifications/cancelled | killed | `tests/test_client_modern.py::EnvelopeTest::test_notifications_carry_no_envelope`, `tests/test_client_modern.py::ListenTest::test_close_sends_cancelled_with_listen_id` |
| `p6-modern-close-twice` | C5 | `client/modern.py` | close() cancels again when called twice | equivalent | equivalent: Session.cancel is itself idempotent: wire.abandon returns False for a request already abandoned, and cancel then sends nothing and returns False, so a second close() sends no second notifications/cancelled and returns False with or without the `closed` flag (test_close_sends_cancelled_with_listen_id already asserts both). |
| `p6-modern-sub-id` | C5 | `client/modern.py` | the subscription's id is the stringified listen id | killed | `tests/test_client_modern.py::ListenTest::test_ack_matched_by_subscription_id_type_included`, `tests/test_client_modern.py::ListenTest::test_close_sends_cancelled_with_listen_id` (+1 more) |
| `p6-modern-listen-error-ignored` | C5 | `client/modern.py` | an error answering listen is reported as a plain RuntimeError | killed | `tests/test_client_modern.py::ListenTest::test_listen_error_is_raised_not_timed_out` |
| `p6-modern-listen-timeout-cancel` | C5 | `client/modern.py` | a listen that times out is not cancelled | killed | `tests/test_client_modern.py::ListenTest::test_a_listen_with_no_acknowledgment_times_out_and_is_cancelled` (new) |
| `p6-check-input-required` | C9 | `tap/check.py` | an input_required result is checked against the method's own result | killed | `tests/test_check.py::CheckTest::test_input_required_result_checked_against_its_definition` |
| `p6-check-input-required-def` | C9 | `tap/check.py` | the input_required rule picks no definition | killed | `tests/test_check.py::CheckTest::test_input_required_result_checked_against_its_definition` |
| `p6-check-input-required-any-type` | C9 | `tap/check.py` | any resultType is checked as InputRequiredResult | killed | `tests/test_check.py::CheckTest::test_input_required_result_checked_against_its_definition`, `tests/test_check.py::ExtensionCheckTest::test_findings_labelled_sep_2663` (+3 more) |
| `p6-check-input-required-2025` | C9 | `tap/check.py` | the rule fires on a revision whose schema has no InputRequiredResult (KeyError) | killed | `tests/test_check.py::CheckTest::test_input_required_rule_does_not_apply_where_the_schema_has_no_such_definition` (new) |
| `p6-check-name-collision` | C16 | `tap/check.py` | an extension definition may shadow a pinned one | killed | `tests/test_check.py::ExtensionCheckTest::test_collision_with_pinned_schema_stops` |
| `p6-check-method-collision` | C16 | `tap/check.py` | an extension may redefine a pinned method | killed | `tests/test_check.py::ExtensionCheckTest::test_collision_with_pinned_schema_stops` |
| `p6-check-pinned-methods-alias` | C16 | `tap/check.py` | the pinned method index is aliased, not copied | equivalent | equivalent: `pinned_methods` is only read, by the collision loop, before `schema.by_method` is reassigned; the loop never writes to it, so the copy is defensive and an alias behaves the same. |
| `p6-check-ref-resolve` | C16 | `tap/check.py` | an unresolved extension $ref is not caught at load | killed | `tests/test_check.py::ExtensionCheckTest::test_an_unresolved_ref_in_the_extension_stops_at_load_whatever_the_trace` (new), `tests/test_check.py::ExtensionCheckTest::test_collision_with_pinned_schema_stops` |
| `p6-check-ref-prefix` | C16 | `tap/check.py` | a $ref with another prefix is accepted at load | killed | `tests/test_check.py::ExtensionCheckTest::test_an_unresolved_ref_in_the_extension_stops_at_load_whatever_the_trace` (new) |
| `p6-check-label` | C16 | `tap/check.py` | extension frames are not labelled SEP-2663 or counted | killed | `tests/test_check.py::ExtensionCheckTest::test_findings_labelled_sep_2663`, `tests/test_check.py::ExtensionCheckTest::test_task_result_checked_against_create_task_result` (+2 more) |
| `p6-check-by-method` | C16 | `tap/check.py` | the merged method index is not rebuilt | killed | `tests/test_check.py::ExtensionCheckTest::test_findings_labelled_sep_2663`, `tests/test_check.py::ExtensionCheckTest::test_tasks_frames_checked_against_sep_2663` |
| `p6-check-defs-merge` | C16 | `tap/check.py` | the merged definitions are not installed | killed | `tests/test_check.py::ExtensionCheckTest::test_findings_labelled_sep_2663`, `tests/test_check.py::ExtensionCheckTest::test_task_result_checked_against_create_task_result` (+1 more) |
| `p6-check-extension-defs` | C16 | `tap/check.py` | the extension's definition names are not recorded | killed | `tests/test_check.py::ExtensionCheckTest::test_findings_labelled_sep_2663`, `tests/test_check.py::ExtensionCheckTest::test_task_result_checked_against_create_task_result` (+2 more) |
| `p6-check-no-extensions` | C16 | `tap/check.py` | --no-extensions still loads the extension | killed | `tests/test_check.py::ExtensionCheckTest::test_collision_with_pinned_schema_stops`, `tests/test_check.py::ExtensionCheckTest::test_no_extensions_and_2025_ignore_the_file` |
| `p6-check-extension-2025` | C16 | `tap/check.py` | 2025-11-25 loads the 2026 extension file | killed | `tests/test_check.py::CheckTest::test_error_frames_are_validated`, `tests/test_check.py::CheckTest::test_input_required_rule_does_not_apply_where_the_schema_has_no_such_definition` (new) (+6 more) |
| `p6-check-task-other-method` | C16 | `tap/check.py` | a task result on another method than tools/call is accepted | killed | `tests/test_check.py::ExtensionCheckTest::test_task_result_on_other_method_fails` |
| `p6-check-task-other-method-narrow` | C16 | `tap/check.py` | a task result is refused only on tasks/get | killed | `tests/test_check.py::ExtensionCheckTest::test_task_result_on_other_method_fails` |
| `p6-check-task-rule-off` | C16 | `tap/check.py` | a resultType "task" is not checked as CreateTaskResult | killed | `tests/test_check.py::ExtensionCheckTest::test_task_result_checked_against_create_task_result`, `tests/test_check.py::ExtensionCheckTest::test_task_result_on_other_method_fails` (+1 more) |
| `p6-check-task-without-extension` | C16 | `tap/check.py` | the task rule fires without the extension loaded (KeyError) | killed | `tests/test_check.py::ExtensionCheckTest::test_no_extensions_and_2025_ignore_the_file` |
| `p6-check-task-def` | C16 | `tap/check.py` | a task result is checked against the method's result, not CreateTaskResult | killed | `tests/test_check.py::ExtensionCheckTest::test_task_result_checked_against_create_task_result`, `tests/test_check.py::ExtensionCheckTest::test_tasks_frames_checked_against_sep_2663` |
| `p6-check-extension-count` | C16 | `tap/check.py` | extension frames are not counted for the SEP-2663 line | killed | `tests/test_check.py::ExtensionCheckTest::test_task_result_checked_against_create_task_result`, `tests/test_check.py::ExtensionCheckTest::test_tasks_frames_checked_against_sep_2663` |

### Survivors of the first run, and what became of them

| Mutant | Why it survived | Disposition |
| --- | --- | --- |
| `p6-modern-version-not-list` | no test had a `supportedVersions` that is a string holding the era | killed by new `DiscoverTest::test_a_malformed_discover_reply_stops_the_session` (C102) |
| `p6-modern-discover-input-required` | no test had an `input_required` reply to `server/discover` | killed by the same test (C102) |
| `p6-modern-declares-tasks` | no test declared another extension | killed by new `ResultTypeTest::test_task_needs_the_tasks_extension_not_just_any_extension` (C103) |
| `p6-modern-state-truthy` | no test had an empty `requestState` | killed by new `InputRequiredTest::test_request_state_is_echoed_byte_for_byte_whatever_it_holds` (C104) |
| `p6-modern-state-reencoded` | the fake server's state had no padding to lose | killed by the same test (C104) |
| `p6-modern-round-limit-break` | the extra answer at the last round is discarded and the loop ends in `TooManyRounds` either way | killed by new `InputRequiredTest::test_no_answer_is_computed_for_a_round_that_is_not_sent` (C104) |
| `p6-modern-unanswerable` | the test used an answer function that fails, never `answer=None` | killed by new `InputRequiredTest::test_input_requests_without_an_answer_function_cannot_be_answered` (C104) |
| `p6-modern-wait-match` | no caller and no test passes `match` | killed by new `ListenTest::test_wait_for_takes_the_notification_its_match_accepts` (C105) |
| `p6-modern-feed-no-notify` | `listen` polls every 0.05 s, which hides a lost wake-up, and `wait_for` still returns at its timeout | killed by new `ListenTest::test_a_waiter_is_woken_when_its_notification_arrives` (C105) |
| `p6-modern-listen-timeout-cancel` | no test let a `listen` run out of time | killed by new `ListenTest::test_a_listen_with_no_acknowledgment_times_out_and_is_cancelled` (C105) |
| `p6-check-input-required-2025` | no test put `resultType: "input_required"` in a 2025-11-25 result | killed by new `CheckTest::test_input_required_rule_does_not_apply_where_the_schema_has_no_such_definition` (C106) |
| `p6-check-ref-prefix` | the loader's `$ref` test used only a missing definition, never another prefix | killed by new `ExtensionCheckTest::test_an_unresolved_ref_in_the_extension_stops_at_load_whatever_the_trace` (C107) |
| `p6-modern-params-not-copied` | `base` is only read | signed equivalent (reason in the table above) |
| `p6-modern-close-twice` | `Session.cancel` is already idempotent through `wire.abandon` | signed equivalent (reason in the table above) |
| `p6-check-pinned-methods-alias` | `pinned_methods` is only read | signed equivalent (reason in the table above) |

### Findings

- No spec gap: every survivor was a missing test of behaviour the spec states, or equivalent.
- No change to `tap/diff.py`, `client/modern.py` or `tap/check.py` was needed.
- `Subscription.wait_for(..., match=)` and `Registry.wait(..., match=)` have no caller in the
  repository (the tours wait by method alone). The parameter is now tested; it could also be
  removed. Not changed (claim code, outside this task).

## Phase 7: `tap/http.py` and `client/http_wire.py`

<!-- BEGIN phase 7 -->
Not yet run. Another run fills this section from `audits/mutants/phase-07.json`: the table of
every mutant with its verdict and the test that killed it, and the survivors' dispositions, in the
form of the sections above.
<!-- END phase 7 -->

## Phase 8: `tools/mutate.py` and `clients/sdk/src/order.ts`

<!-- BEGIN phase 8 -->
Not yet run. Another run fills this section from `audits/mutants/phase-08.json`, in the same form.
<!-- END phase 8 -->
