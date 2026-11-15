// A request's last progress notification and its response, read from the pipe in one chunk, must
// reach `onprogress` before the call settles (phase 8: the sdk-tour flake). The fake server below
// writes both in one `write`, which is what a loaded machine makes of two quick writes.

import assert from "node:assert/strict";
import { test } from "node:test";
import type { Transport } from "@modelcontextprotocol/client";
import { buildLab } from "../src/client.ts";
import { inWireOrder, responsesLast } from "../src/order.ts";

// A stdio server just big enough for `connect` and one `tools/call` that reports progress twice.
const FAKE_SERVER = String.raw`
const lines = require("node:readline").createInterface({ input: process.stdin });
const out = (m) => JSON.stringify({ jsonrpc: "2.0", ...m }) + "\n";
lines.on("line", (line) => {
  const m = JSON.parse(line);
  if (m.method === "initialize") {
    process.stdout.write(out({ id: m.id, result: { protocolVersion: m.params.protocolVersion,
      capabilities: { tools: {} }, serverInfo: { name: "fake", version: "0" } } }));
  } else if (m.method === "tools/call") {
    const token = m.params._meta.progressToken;
    const progress = (n) => out({ method: "notifications/progress", params: { progress: n, total: 2, progressToken: token } });
    process.stdout.write(progress(1) + progress(2) + out({ id: m.id, result: { content: [{ type: "text", text: "completed" }] } }));
  }
});
`;

test("a progress notification read in one chunk with its response reaches onprogress first", async () => {
  const reported: string[] = [];
  const lab = buildLab([], () => {}, (line) => reported.push(line));
  await lab.client.connect(lab.transport([process.execPath, "-e", FAKE_SERVER]));
  try {
    const seen: number[] = [];
    await lab.client.callTool(
      { name: "trigger-long-running-operation", arguments: {} },
      { onprogress: (p) => seen.push(p.progress) },
    );
    assert.deepEqual(seen, [1, 2], `onprogress saw ${JSON.stringify(seen)}; sdk said ${JSON.stringify(reported)}`);
    assert.deepEqual(lab.errors, []);
  } finally {
    await lab.close();
  }
});

// The rest pins `order.ts` itself, without a server: what is handed over when, to which handler.

type Handler = NonNullable<Transport["onmessage"]>;
const asMessage = (m: object) => ({ jsonrpc: "2.0", ...m }) as unknown as Parameters<Handler>[0];
const notification = asMessage({ method: "notifications/progress", params: { progress: 1 } });
const request = asMessage({ id: 7, method: "ping" });
const result = asMessage({ id: 1, result: {} });
const failure = asMessage({ id: 2, error: { code: -32603, message: "x" } });

test("a response, result or error, is handed over one microtask late and everything else at once", async () => {
  const seen: string[] = [];
  const handler = responsesLast((m) => {
    seen.push("method" in m ? m.method : "error" in m ? "error" : "result");
  });
  for (const m of [result, notification, failure, request]) handler(m);
  assert.deepEqual(seen, ["notifications/progress", "ping"], "requests and notifications at once, responses not yet");
  await Promise.resolve(); // one microtask: the responses are in by now, ahead of any timer
  assert.deepEqual(seen, ["notifications/progress", "ping", "result", "error"]);
});

test("the transport's second argument reaches the handler, late or not", async () => {
  const extras: unknown[] = [];
  const handler = responsesLast(((_m: unknown, extra: unknown) => extras.push(extra)) as Handler);
  const extra = { requestInfo: { headers: {} } } as never;
  handler(notification, extra);
  handler(result, extra);
  await Promise.resolve();
  assert.deepEqual(extras, [extra, extra]);
  assert.equal(extras[0], extra);
});

test("inWireOrder wraps every handler set on onmessage, hands back the same transport, and lets the slot be cleared", async () => {
  const transport = {} as Transport;
  assert.equal(inWireOrder(transport), transport);
  assert.equal(transport.onmessage, undefined);
  const seen: string[] = [];
  transport.onmessage = (m) => seen.push("method" in m ? m.method : "response");
  transport.onmessage?.(result);
  assert.deepEqual(seen, [], "a response set through the slot is late");
  await Promise.resolve();
  assert.deepEqual(seen, ["response"]);
  transport.onmessage = undefined;
  assert.equal(transport.onmessage, undefined, "a cleared slot reads as empty");
});

test("a caller that chains the handler it read from the slot, as the SDK's connect does, reaches both once", () => {
  const transport = inWireOrder({} as Transport);
  const seen: string[] = [];
  transport.onmessage = () => seen.push("first");
  const first = transport.onmessage;
  assert.equal(typeof first, "function", "the slot reads back the handler set");
  transport.onmessage = (m, extra) => {
    first?.(m, extra);
    seen.push("second");
  };
  transport.onmessage?.(notification);
  assert.deepEqual(seen, ["first", "second"]);
});

test("an error reply read in one chunk with a progress notification also reaches onprogress first", async () => {
  const reported: string[] = [];
  const lab = buildLab([], () => {}, (line) => reported.push(line));
  const server = FAKE_SERVER.replace(
    'out({ id: m.id, result: { content: [{ type: "text", text: "completed" }] } })',
    'out({ id: m.id, error: { code: -32603, message: "boom" } })',
  );
  await lab.client.connect(lab.transport([process.execPath, "-e", server]));
  try {
    const seen: number[] = [];
    await assert.rejects(
      lab.client.callTool({ name: "trigger-long-running-operation", arguments: {} }, { onprogress: (p) => seen.push(p.progress) }),
      /boom/,
    );
    assert.deepEqual(seen, [1, 2], `onprogress saw ${JSON.stringify(seen)}; sdk said ${JSON.stringify(reported)}`);
  } finally {
    await lab.close();
  }
});
