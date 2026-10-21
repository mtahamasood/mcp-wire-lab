# Phase 7 — Streamable HTTP: requirements (stub)

**Status: specified, not built** (lean profile, LP1; register row 2026-10-21, lean profile).
This stub fixes the phase's objective, scope and exit criteria so a later run can expand
it into full `requirements.md` and `validation.md` before any code.

## Learning objective

Learn what the HTTP transport adds on top of the same messages: one POST per client
message, responses as JSON or as an SSE stream, the `Mcp-Session-Id` header (2025 era),
and the server-to-client stream opened by GET.

## Scope

- The tap gains an HTTP mode: a stdlib reverse proxy that records each request, response
  and SSE event with the headers that matter, on the same JSON Lines timeline as stdio.
- Both clients run both eras over HTTP against the pinned server's Streamable HTTP
  transport.
- A lesson on what HTTP adds; final atlas coverage measured.
- Out of scope, as before: the legacy HTTP+SSE transport, OAuth, resumability
  (`Last-Event-ID`, backlog).

## Exit criteria

The roadmap's phase 7 row, unchanged.

### D1 — Same trace format for both transports

HTTP traffic is recorded into the phase 1 trace format, with transport details as extra
fields, so `tap.show`, `tap.check` and `tap.diff` work unchanged on HTTP traces.

*Source:* register row 2026-10-20 (transports); roadmap.md phase 7 row.
