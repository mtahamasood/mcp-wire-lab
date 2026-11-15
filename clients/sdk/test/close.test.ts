// P8-R7-14: over --url the close step sends DELETE. A DELETE answered with an error must be a step
// failure (a FAILED line, exit 1), not an uncaught exception with the SDK's stack; a DELETE that is
// never answered must not hang the client; and the SDK client is closed in both cases.

import assert from "node:assert/strict";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { after, before, test } from "node:test";
import { buildLab } from "../src/client.ts";
import { runServerTour } from "../src/server_tour.ts";
import { runTour } from "../src/tour.ts";

type Delete = "ok" | "500" | "never";

/** An HTTP server that completes `initialize` (with a session id), accepts notifications, offers no GET stream, and answers any other request 500. */
function fake(del: () => Delete) {
  const open = new Set<import("node:net").Socket>();
  const deletes: string[] = [];
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => { body += chunk; });
    req.on("end", () => {
      if (req.method === "DELETE") {
        deletes.push(req.headers["mcp-session-id"] as string);
        const how = del();
        if (how === "never") return; // the response is never written
        res.writeHead(how === "ok" ? 200 : 500).end();
      } else if (req.method === "GET") {
        res.writeHead(405).end();
      } else {
        const message = JSON.parse(body) as { id?: number; method: string; params: { protocolVersion?: string } };
        if (message.id === undefined) {
          res.writeHead(202).end();
        } else if (message.method === "initialize") {
          res.writeHead(200, { "content-type": "application/json", "mcp-session-id": "s1" }).end(JSON.stringify({
            jsonrpc: "2.0", id: message.id,
            result: { protocolVersion: message.params.protocolVersion, capabilities: {}, serverInfo: { name: "fake", version: "0" } },
          }));
        } else {
          res.writeHead(500).end();
        }
      }
    });
  });
  server.on("connection", (socket) => { open.add(socket); socket.on("close", () => open.delete(socket)); });
  return {
    deletes,
    start: () => new Promise<string>((resolve) => server.listen(0, "127.0.0.1", () => resolve(`http://127.0.0.1:${(server.address() as AddressInfo).port}/mcp`))),
    stop: () => new Promise<void>((resolve) => { for (const socket of open) socket.destroy(); server.close(() => resolve()); }),
  };
}

let mode: Delete = "ok";
const server = fake(() => mode);
let url = "";
before(async () => { url = await server.start(); });
after(async () => { await server.stop(); });

const WAIT = 300; // ms the DELETE may take in these tests

test("Lab.close with a DELETE answered 500 throws after closing the client", async () => {
  mode = "500";
  const lab = buildLab([], () => {}, () => {}, url);
  await lab.client.connect(lab.transport([]));
  await assert.rejects(lab.close(WAIT), /Failed to terminate session/);
  assert.equal(lab.client.transport, undefined, "the client was closed");
});

test("Lab.close with a DELETE never answered gives up after the wait, and closes the client", async () => {
  mode = "never";
  const lab = buildLab([], () => {}, () => {}, url);
  await lab.client.connect(lab.transport([]));
  const started = Date.now();
  await assert.rejects(lab.close(WAIT), /no answer to DELETE within 0\.3 s/);
  assert.ok(Date.now() - started < 3000, "the wait is bounded");
  assert.equal(lab.client.transport, undefined, "the client was closed");
});

test("Lab.close with a DELETE answered 200 closes without an error", async () => {
  mode = "ok";
  const lab = buildLab([], () => {}, () => {}, url);
  await lab.client.connect(lab.transport([]));
  await lab.close(WAIT);
  assert.equal(lab.client.transport, undefined);
});

for (const [name, run] of [["tour", runTour], ["server-tour", runServerTour]] as const) {
  for (const how of ["500", "never"] as const) {
    test(`${name} over --url: a DELETE ${how === "500" ? "answered 500" : "never answered"} is a failed close step, not a crash`, async () => {
      mode = how;
      server.deletes.length = 0;
      const out: string[] = [];
      const reported: string[] = [];
      const status = await run(["unused"], (line) => out.push(line), (line) => reported.push(line), [], url, WAIT);
      assert.equal(status, 1);
      assert.equal(server.deletes.length, 1, "the DELETE was sent");
      const last = out[out.length - 1] as string;
      assert.match(last, /^\s*\d+\s+FAILED\s+\w+: /, `last line: ${last}`);
      assert.match(last, how === "500" ? /Failed to terminate session/ : /no answer to DELETE/);
      assert.ok(!out.some((line) => /\bclose\s+closed\b/.test(line)), "a failed close is not printed as closed");
      assert.ok(reported.some((line) => line.startsWith("sdk: close failed at step")), reported.join("\n"));
    });
  }
}

test("tour over --url with a DELETE answered 200 still ends with the close step", async () => {
  mode = "ok";
  const out: string[] = [];
  await runTour(["unused"], (line) => out.push(line), () => {}, [], url, WAIT);
  assert.match(out[out.length - 1] as string, /\bclose\s+closed$/);
});
