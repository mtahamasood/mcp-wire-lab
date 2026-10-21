# Phase 5 — SDK client, 2025 era (TypeScript, stdio): requirements (stub)

**Status: specified, not built** (lean profile, LP1; register row 2026-10-21, lean profile).
This stub fixes the phase's objective, scope and exit criteria so a later run can expand
it into full `requirements.md` and `validation.md` before any code.

## Learning objective

See what an SDK hides: run the same tour as the raw client (phases 2–3) through
`@modelcontextprotocol/client` 2.3.1 and explain every difference in the wire traffic.

## Scope

- `clients/sdk/` TypeScript client on the pinned SDK (tech-stack row *SDK client*), run
  through the tap by `scripts/record.sh`.
- `tap.diff a b` (L12): normalises ids and timings, prints message-level differences.
- A walkthrough of the raw-vs-SDK diff, difference by difference; one SDK-side source tour
  (L13): `client.callTool` from the API call down to the bytes written to stdio.
- G3 gains `tsc --strict`.

## Exit criteria

The roadmap's phase 5 row, unchanged.

### D1 — The SDK client mirrors the raw client's tour

The SDK client runs the scripted tour of phases 2 and 3 with the same inputs, so that the
two fresh traces differ only where the clients differ, not where the inputs do.

*Source:* stakeholder ask A3, 2026-10-20 (both clients); roadmap.md phase 5 row.
