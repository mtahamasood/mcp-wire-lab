import assert from "node:assert/strict";
import { test } from "node:test";
import { opensStream, watchStream } from "../src/stream.ts";
import type { Fetch } from "../src/stream.ts";

const URL_ = "http://127.0.0.1:1/mcp";

function answer(status: number, type: string | null): Response {
  const headers = type === null ? undefined : { "content-type": type };
  return new Response(status === 202 || status === 405 ? null : "", { status, headers });
}

test("only a GET answered 2xx with an event stream opens the stream", () => {
  assert.equal(opensStream({ method: "GET" }, answer(200, "text/event-stream")), true);
  assert.equal(opensStream({ method: "get" }, answer(200, "Text/Event-Stream; charset=utf-8")), true);
  assert.equal(opensStream(undefined, answer(200, "text/event-stream")), true, "fetch defaults to GET");
  assert.equal(opensStream({ method: "POST" }, answer(200, "text/event-stream")), false, "a POST's stream answers one request");
  assert.equal(opensStream({ method: "GET" }, answer(405, null)), false, "the server offers no GET stream");
  assert.equal(opensStream({ method: "GET" }, answer(409, "application/json")), false);
  assert.equal(opensStream({ method: "GET" }, answer(200, "application/json")), false);
});

test("watchStream calls onOpen once per opening GET, after the answer, and passes every answer on", async () => {
  const answers = [answer(202, null), answer(200, "text/event-stream"), answer(200, "text/event-stream")];
  const seen: string[] = [];
  const base: Fetch = async (_url, init) => {
    seen.push(`fetch ${init?.method}`);
    return answers.shift() as Response;
  };
  const fetch = watchStream(base, () => seen.push("open"));
  const first = await fetch(URL_, { method: "POST" });
  assert.equal(first.status, 202);
  await fetch(URL_, { method: "GET" });
  await fetch(URL_, { method: "POST" });
  assert.deepEqual(seen, ["fetch POST", "fetch GET", "open", "fetch POST"]);
});

test("watchStream lets a failed fetch reject without calling onOpen", async () => {
  let opened = 0;
  const fetch = watchStream(async () => {
    throw new Error("refused");
  }, () => {
    opened += 1;
  });
  await assert.rejects(fetch(URL_, { method: "GET" }), /refused/);
  assert.equal(opened, 0);
});
