// A request's last progress notification and its response, read from the pipe in one chunk, must
// reach `onprogress` before the call settles (phase 8: the sdk-tour flake). The fake server below
// writes both in one `write`, which is what a loaded machine makes of two quick writes.

import assert from "node:assert/strict";
import { test } from "node:test";
import { buildLab } from "../src/client.ts";

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
