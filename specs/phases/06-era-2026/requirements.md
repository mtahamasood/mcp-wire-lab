# Phase 6 — 2026-07-28 era, both clients (stdio): requirements (stub)

**Status: specified, not built** (lean profile, LP1; register row 2026-10-21, lean profile).
This stub fixes the phase's objective, scope and exit criteria so a later run can expand
it into full `requirements.md` and `validation.md` before any code.

## Learning objective

Understand what changed between the 2025 era and 2026-07-28 by speaking both: discovery
instead of a handshake, per-request `_meta` instead of a session, and the new task and
subscription machinery.

## Scope

- The raw client gains a `--era 2026-07-28` mode: `server/discover`, the `_meta`
  envelope on every request, `subscriptions/listen`, tasks, multi-round requests.
- The SDK client, if phase 5 is built, does the same.
- `tap.check --revision 2026-07-28` validates the new traffic (L7).
- A walkthrough diffs the two eras message by message (L12 `tap.diff`).
- The atlas (L8, G10), deferred from phase 2 by the lean profile, is built in the final
  pass and measures coverage of both revisions.

## Exit criteria

The roadmap's phase 6 row, unchanged.

### D1 — One client, two eras

The era is a client option, not a second client: the shared parts (framing, id
correlation, the tap) are reused, so the walkthrough's diff isolates what the protocol
changed.

*Source:* register row 2026-10-20 (both eras); roadmap.md phase 6 row.
