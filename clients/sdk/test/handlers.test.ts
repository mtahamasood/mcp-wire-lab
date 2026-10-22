import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CANNED_MODEL, CANNED_TEXT, DEFAULT_ROOTS, OTHER_ROOT, Traffic,
  elicitationResult, formValue, rootsResult, samplingResult,
} from "../src/handlers.ts";

test("sampling answers with the canned text that names the SDK client", () => {
  assert.deepEqual(samplingResult(), {
    role: "assistant",
    content: { type: "text", text: "canned reply from wire-lab-sdk" },
    model: "wire-lab-canned",
    stopReason: "endTurn",
  });
  assert.equal(CANNED_TEXT, "canned reply from wire-lab-sdk");
  assert.equal(CANNED_MODEL, "wire-lab-canned");
});

test("form values: default, else first enum value, else a fixed value per type", () => {
  assert.equal(formValue({ type: "string", default: "Ada" }), "Ada");
  assert.equal(formValue({ type: "string", enum: ["a", "b"] }), "a");
  assert.equal(formValue({ type: "string", oneOf: [{ const: "x", title: "X" }] }), "x");
  assert.equal(formValue({ type: "string", anyOf: [{ const: "y" }] }), "y");
  assert.equal(formValue({ type: "string" }), "wire-lab");
  assert.equal(formValue({ type: "number" }), 1);
  assert.equal(formValue({ type: "integer" }), 1);
  assert.equal(formValue({ type: "boolean" }), true);
  assert.equal(formValue({ type: "boolean", default: false }), false);
  assert.equal(formValue({}), "wire-lab");
});

test("a non-integer number goes back as its integer part", () => {
  assert.equal(formValue({ type: "number", default: 3.14 }), 3);
  assert.equal(formValue({ type: "number", default: -3.9 }), -3);
  assert.equal(formValue({ type: "integer", default: 7 }), 7);
});

test("an array property answers with its first option, or an empty list", () => {
  assert.deepEqual(formValue({ type: "array", items: { enum: ["p", "q"] } }), ["p"]);
  assert.deepEqual(formValue({ type: "array", items: { anyOf: [{ const: "r" }] } }), ["r"]);
  assert.deepEqual(formValue({ type: "array", items: { type: "string" } }), []);
});

test("a form elicitation is accepted from the values, a URL one is declined", () => {
  const form = elicitationResult({
    mode: "form",
    requestedSchema: { properties: { name: { type: "string", default: "Ada" }, n: { type: "number" } } },
  });
  assert.deepEqual(form, { action: "accept", content: { name: "Ada", n: 1 } });
  assert.deepEqual(elicitationResult({ requestedSchema: { properties: {} } }), { action: "accept", content: {} });
  assert.deepEqual(elicitationResult({ mode: "url" }), { action: "decline" });
});

test("roots: the project root, then a second root announced after", () => {
  assert.deepEqual(rootsResult(DEFAULT_ROOTS), { roots: [{ uri: "file:///wire-lab/project", name: "wire-lab" }] });
  assert.deepEqual(OTHER_ROOT, { uri: "file:///wire-lab/other", name: "other" });
  const copy = rootsResult(DEFAULT_ROOTS);
  copy.roots[0]!.name = "changed";
  assert.equal(DEFAULT_ROOTS[0]!.name, "wire-lab", "the result is a copy");
});

test("traffic: waits by count, then for quiet", async () => {
  const traffic = new Traffic();
  setTimeout(() => traffic.mark("roots/list"), 30);
  assert.equal(await traffic.waitFor(() => traffic.seen("roots/list") >= 1, 1000), true);
  assert.equal(await traffic.waitFor(() => traffic.seen("never") >= 1, 50), false);
  traffic.mark("notifications/message");
  const started = Date.now();
  assert.equal(await traffic.quiet(80, 1000), true);
  assert.ok(Date.now() - started >= 70, "quiet waits out the window after the last traffic");
  let release = (): void => {};
  const work = traffic.working(() => new Promise<void>((resolve) => { release = resolve; }));
  assert.equal(await traffic.quiet(0, 50), false, "not quiet while work is in flight");
  release();
  await work;
  assert.equal(await traffic.quiet(0, 200), true);
});
