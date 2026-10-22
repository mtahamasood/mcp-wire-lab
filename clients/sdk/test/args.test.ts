import assert from "node:assert/strict";
import { test } from "node:test";
import { capabilityObject, parseArgs, parseCaps } from "../src/args.ts";

test("both modes parse, with the server command after --", () => {
  assert.deepEqual(parseArgs(["tour", "--", "node", "server.js", "stdio"]), {
    kind: "run", mode: "tour", caps: undefined, command: ["node", "server.js", "stdio"],
  });
  assert.deepEqual(parseArgs(["server-tour", "--", "x"]), {
    kind: "run", mode: "server-tour", caps: undefined, command: ["x"],
  });
});

test("--caps takes a list, or none", () => {
  const run = parseArgs(["tour", "--caps", "roots,sampling", "--", "x"]);
  assert.deepEqual(run, { kind: "run", mode: "tour", caps: ["roots", "sampling"], command: ["x"] });
  const none = parseArgs(["server-tour", "--caps", "none", "--", "x"]);
  assert.deepEqual(none, { kind: "run", mode: "server-tour", caps: [], command: ["x"] });
});

test("an unknown capability is a usage error that names it", () => {
  const parsed = parseArgs(["tour", "--caps", "bogus", "--", "x"]);
  assert.equal(parsed.kind, "usage");
  assert.match((parsed as { message?: string }).message ?? "", /bogus/);
  assert.throws(() => parseCaps("roots,nope"), /nope/);
});

test("--help and -h print the usage, after a mode too", () => {
  for (const argv of [["-h"], ["--help"], ["tour", "--help"], ["server-tour", "-h"]]) {
    assert.deepEqual(parseArgs(argv), { kind: "help" });
  }
});

test("bad command lines are usage errors", () => {
  const bad = [
    [], ["nonsense"], ["--nonsense"], ["tour"], ["tour", "--"], ["tour", "x", "--", "y"],
    ["tour", "--caps", "--", "y"], ["tour", "--caps", "roots"], ["tour", "--caps", "roots", "extra", "--", "y"],
  ];
  for (const argv of bad) assert.equal(parseArgs(argv).kind, "usage", argv.join(" "));
});

test("capabilities are the objects the raw client sends", () => {
  assert.deepEqual(capabilityObject([]), {});
  assert.deepEqual(capabilityObject(["roots", "sampling", "elicitation", "elicitation-url"]), {
    roots: { listChanged: true }, sampling: {}, elicitation: { form: {}, url: {} },
  });
  assert.deepEqual(capabilityObject(["elicitation-url"]), { elicitation: { url: {} } });
  assert.deepEqual(capabilityObject(["elicitation"]), { elicitation: { form: {} } });
});
