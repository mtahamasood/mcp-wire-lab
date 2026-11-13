# WIP status: phase-08-fix-sdk (Stage B, D10: P8-R7-14, P8-R6-4, check_lessons leak)

Delete this file in the first real commit.

## Done (all uncommitted work is in this one WIP commit)
- P8-R7-14: `clients/sdk/src/client.ts` (`CLOSE_WAIT`, bounded `Lab.close(wait)`, always closes
  the client, throws after), `steps.ts` (`closeStep`), `tour.ts`, `server_tour.ts`, `era.ts`
  (close reported as a FAILED step, exit 1). Test: `clients/sdk/test/close.test.ts` (8 tests).
  Red on pre-fix code: 6 of 8 failed (the never-answered ones hang until the test timeout).
  Green after: 8 of 8.
- P8-R6-4: new `clients/sdk/src/listen.ts` (`ListenTag` wraps the transport's `send` slot to read
  the id of the `subscriptions/listen` request; `tagOf`), `era.ts` (`ModernTour` is exported,
  `expectTagged` after each list change and the resource update). Test:
  `clients/sdk/test/listen.test.ts` (6 tests). Red on pre-fix era.ts: 3 of 6 failed (the three
  wrong-tag cases). Green after.
- `node --test "test/*.test.ts"` in clients/sdk: 37 pass; tsc -p clients/sdk clean.
- check_lessons leak: `tools/check_lessons.py` `run_block` (Popen, own session, killpg at block
  end, output to temp files). Tests `tests/test_lessons.py::BackgroundChildTest` (4 tests). Red
  on the old code: 4 of 4 failed; green after. `tests.test_lessons` 27 pass, `tests.test_sdk_client`
  pass, ruff and mypy clean, `check_claims --phases 02..07` ok.
- Records: validation.md rows C140 (R7-14), C141 (R6-4), C142 (check_lessons); audits/final-pass-review.md
  rows and note for P8-R6-4 and P8-R7-14 updated (they name the branch, not commit SHAs).

## Remaining
1. Run `PATH=<nvm 24.22.0 bin>:$PATH python3 -m unittest tests.test_e2e.SdkClientTest tests.test_e2e.ModernTourTest`
   (was running when stopped; no result yet), then `tests.test_e2e_http`, G9
   `python3 tools/check_lessons.py`, G12 `python3 tools/check_claims.py --phases 02,03,04,05,06,07`.
   To run them: symlink ~/gitWork/mcps-practise/vendor over the empty vendor/ dir and
   ~/gitWork/mcps-practise/clients/sdk/node_modules into clients/sdk/, and remove both
   again (recreate empty vendor/servers and vendor/spec) before committing.
2. Split the WIP into three clean commits (R7-14 + C140; R6-4 + C141; check_lessons + C142), each
   with its C row and audit row; then a last commit filling the commit SHAs into the audit rows.
   Messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
3. Optional: lesson 07 still ends its blocks with `kill`/`wait`; nothing to change there.
