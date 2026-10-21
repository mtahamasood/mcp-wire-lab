# Autonomous decisions (owner review at the end)

On 2026-10-21 the owner delegated every remaining Phase 1 decision to the agent ("no input from me"), asking
only to review at the end which decisions to overrule. This file is that list. Each row: what was decided,
why, confidence, what breaks if wrong, and how to overrule. Spec-level decisions also get a register row in
`specs/mission.md`.

| Id | Decision | Reason | Confidence | If wrong | Overrule |
|---|---|---|---|---|---|
| A1 | The remaining work runs locally with subagents, not in a Claude web session. | The owner dropped the web requirement mid-session. | high | none | n/a |
| A2 | R18 licence: MIT (pending, see below). | Common default for a public learning lab; replaceable. | medium | wrong licence published | Replace `LICENSE`, amend the register row. |
| A3 | R17: J2 sign-off is kept as the owner's earlier pass; learner-walk items 3 and 7 stay accepted; recorded as "agent-proposed, owner to confirm". | These were already the agent's recommendation. | medium | a sign-off the owner did not give | Re-sign or reject in `validation.md` and `audits/learner-walk-lesson-01.md`. |
