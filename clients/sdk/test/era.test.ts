// Phase 6 C13 (SDK half): the `--era` option and the transport subclass of D11.
import assert from "node:assert/strict";
import { test } from "node:test";
import { StdioClientTransport } from "@modelcontextprotocol/client/stdio";
import { parseArgs } from "../src/args.ts";
import { InPlaceStdioTransport, MODERN_ERA, MODERN_TOUR_CAPS } from "../src/era.ts";

test("--era defaults to 2025-11-25 and takes 2026-07-28, in any order with --caps", () => {
  assert.deepEqual(parseArgs(["tour", "--", "x"]), {
    kind: "run", mode: "tour", caps: undefined, era: "2025-11-25", command: ["x"],
  });
  assert.deepEqual(parseArgs(["tour", "--era", "2026-07-28", "--", "x"]), {
    kind: "run", mode: "tour", caps: undefined, era: "2026-07-28", command: ["x"],
  });
  assert.deepEqual(parseArgs(["tour", "--era", "2026-07-28", "--caps", "roots", "--", "x"]), {
    kind: "run", mode: "tour", caps: ["roots"], era: "2026-07-28", command: ["x"],
  });
  assert.deepEqual(parseArgs(["tour", "--caps", "roots", "--era", "2025-11-25", "--", "x"]), {
    kind: "run", mode: "tour", caps: ["roots"], era: "2025-11-25", command: ["x"],
  });
  assert.equal(MODERN_ERA, "2026-07-28");
  assert.deepEqual([...MODERN_TOUR_CAPS], ["roots", "sampling", "elicitation"]);
});

test("server-tour in 2026-07-28 and an unknown era are usage errors", () => {
  const server = parseArgs(["server-tour", "--era", "2026-07-28", "--", "x"]);
  assert.equal(server.kind, "usage");
  assert.match((server as { message?: string }).message ?? "", /server-tour/);
  assert.deepEqual(parseArgs(["server-tour", "--era", "2025-11-25", "--", "x"]), {
    kind: "run", mode: "server-tour", caps: undefined, era: "2025-11-25", command: ["x"],
  });
  const unknown = parseArgs(["tour", "--era", "2027-01-01", "--", "x"]);
  assert.equal(unknown.kind, "usage");
  assert.match((unknown as { message?: string }).message ?? "", /2027-01-01/);
  for (const argv of [
    ["tour", "--era", "--", "x"], ["tour", "--era", "2026-07-28"], ["tour", "--era", "2026-07-28", "--era", "2026-07-28", "--", "x"],
    ["tour", "--era", "2026-07-28", "extra", "--", "x"],
  ]) {
    assert.equal(parseArgs(argv).kind, "usage", argv.join(" "));
  }
});

test("the transport is a member-less subclass, so the SDK probes in place (D11)", () => {
  // The SDK clones only a transport whose own prototype carries `_dispose` (the base class); a
  // subclass has no member of its own, so it takes the in-place probe and one process starts.
  assert.deepEqual(Object.getOwnPropertyNames(InPlaceStdioTransport.prototype), ["constructor"]);
  assert.equal(Object.getPrototypeOf(InPlaceStdioTransport), StdioClientTransport);
  assert.equal(Object.hasOwn(InPlaceStdioTransport.prototype, "_dispose"), false);
  assert.equal(Object.hasOwn(StdioClientTransport.prototype, "_dispose"), true);
  assert.ok(new InPlaceStdioTransport({ command: "x" }) instanceof StdioClientTransport);
});
