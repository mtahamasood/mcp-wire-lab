// P8-R6-4: the 2026 tour's list changes and resource update must carry the id of the
// `subscriptions/listen` request, which the SDK's `listen()` does not hand back. The id is read from
// the request on the transport; each notification must be tagged with it.

import assert from "node:assert/strict";
import { test } from "node:test";
import { SUBSCRIPTION_ID_META_KEY } from "@modelcontextprotocol/client";
import { ModernTour } from "../src/era.ts";
import { ListenTag, tagOf } from "../src/listen.ts";
import { Steps, TourFailure } from "../src/steps.ts";

test("ListenTag reads the id from the listen request on its way to the transport, and passes it on", async () => {
  const sent: unknown[] = [];
  const transport = {
    marker: "kept",
    async send(this: { marker: string }, message: unknown) {
      assert.equal(this.marker, "kept", "send keeps its transport as `this`");
      sent.push(message);
    },
  };
  const tag = new ListenTag();
  assert.equal(tag.watch(transport as never), transport);
  await transport.send({ method: "tools/list", id: 1 });
  assert.equal(tag.id, undefined, "another request is not the listen request");
  await transport.send({ method: "subscriptions/listen", id: "listen:7", params: {} });
  await transport.send({ method: "subscriptions/listen", id: "listen:8", params: {} });
  assert.equal(tag.id, "listen:7", "the first listen request is the tour's");
  assert.equal(sent.length, 3);
});

test("a notification is tagged with the listen id only if its subscription id is that id", () => {
  const tag = new ListenTag();
  assert.match(tag.mismatch("listen:0") ?? "", /no subscriptions\/listen request/);
  tag.id = "listen:0";
  assert.equal(tag.mismatch("listen:0"), undefined);
  assert.match(tag.mismatch("listen:1") ?? "", /"listen:1".*listen:0/);
  assert.match(tag.mismatch(undefined) ?? "", /no listen id/);
  assert.match(tag.mismatch(0) ?? "", /listen:0/);
  assert.equal(tagOf({ _meta: { [SUBSCRIPTION_ID_META_KEY]: "listen:0" } }), "listen:0");
  assert.equal(tagOf({ _meta: {} }), undefined);
  assert.equal(tagOf(undefined), undefined);
});

// A 2026 stdio server just big enough for the tour's discover and subscription steps. argv:
// the subscription key, then what it tags its notifications with: "right" (the listen id),
// "wrong" (another id) or "none" (no `_meta`), and, for "wrong" and "none", only from the resource
// update on when argv[3] is "late".
const FAKE_SERVER = String.raw`
const [key, mode, from] = process.argv.slice(1);
const out = (m) => process.stdout.write(JSON.stringify({ jsonrpc: "2.0", ...m }) + "\n");
let listenId;
const tagged = (params, update) => {
  if (mode === "right" || (from === "late" && !update)) return { ...params, _meta: { [key]: listenId } };
  return mode === "none" ? params : { ...params, _meta: { [key]: "listen:99" } };
};
require("node:readline").createInterface({ input: process.stdin }).on("line", (line) => {
  const m = JSON.parse(line);
  if (m.method === "server/discover") {
    out({ id: m.id, result: { supportedVersions: ["2026-07-28"], capabilities: { tools: {} }, serverInfo: { name: "fake", version: "0" } } });
  } else if (m.method === "subscriptions/listen") {
    listenId = m.id;
    out({ method: "notifications/subscriptions/acknowledged", params: { _meta: { [key]: listenId }, notifications: m.params.notifications } });
  } else if (m.method === "tools/call") {
    out({ id: m.id, result: { resultType: "complete", content: [{ type: "text", text: "ok" }] } });
    const a = m.params.arguments;
    if (m.params.name === "trigger-list-changed") out({ method: "notifications/" + a.list + "/list_changed", params: tagged({}, false) });
    if (m.params.name === "trigger-resource-update") out({ method: "notifications/resources/updated", params: tagged({ uri: a.uri }, true) });
  }
});
`;

async function runSubscriptions(mode: string, from = "start"): Promise<{ lines: string[]; failure: unknown }> {
  const lines: string[] = [];
  const tour = new ModernTour(new Steps((line) => lines.push(line)), ["roots"], () => {});
  let failure: unknown;
  try {
    await tour.discovery([process.execPath, "-e", FAKE_SERVER, SUBSCRIPTION_ID_META_KEY, mode, from]);
    await tour.subscriptions();
  } catch (error) {
    failure = error;
  } finally {
    await tour.client.close();
  }
  return { lines, failure };
}

test("the 2026 tour's subscription steps pass when every notification carries the listen id", async () => {
  const { lines, failure } = await runSubscriptions("right");
  assert.equal(failure, undefined, String(failure));
  assert.equal(lines.filter((l) => l.includes("on subscription listen:0")).length, 4, lines.join("\n"));
});

test("the 2026 tour fails a list change tagged with another subscription", async () => {
  const { failure } = await runSubscriptions("wrong");
  assert.ok(failure instanceof TourFailure, String(failure));
  assert.match((failure as Error).message, /notifications\/tools\/list_changed .*"listen:99".*listen:0/);
});

test("the 2026 tour fails a list change with no subscription tag at all", async () => {
  const { failure } = await runSubscriptions("none");
  assert.ok(failure instanceof TourFailure, String(failure));
  assert.match((failure as Error).message, /notifications\/tools\/list_changed .*no listen id/);
});

test("the 2026 tour fails a resource update tagged with another subscription (list changes right)", async () => {
  const { lines, failure } = await runSubscriptions("wrong", "late");
  assert.equal(lines.filter((l) => l.includes("list_changed on subscription listen:0")).length, 3, lines.join("\n"));
  assert.ok(failure instanceof TourFailure, String(failure));
  assert.match((failure as Error).message, /notifications\/resources\/updated .*"listen:99"/);
});
