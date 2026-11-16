// P8-R7-14: over --url the close step sends DELETE. A DELETE answered with an error must be a step
// failure (a FAILED line, exit 1), not an uncaught exception with the SDK's stack; a DELETE that is
// never answered must not hang the client; and the SDK client is closed in both cases.

import assert from "node:assert/strict";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { after, before, test } from "node:test";
import { Client } from "@modelcontextprotocol/client";
import { CLOSE_WAIT, buildLab } from "../src/client.ts";
import type { Lab } from "../src/client.ts";
import { ModernTour, runModernTour } from "../src/era.ts";
import { ServerTour, runServerTour } from "../src/server_tour.ts";
import { Tour, runTour } from "../src/tour.ts";

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

// The rest pins what the close step is wired to, with the tours' own steps stubbed out so that
// only the close step can fail a run: with a real tour against this fake server, the tour fails
// first and the run's status 1 would not show whether a failed close alone sets it.

test("the DELETE is given five seconds by default", () => {
  assert.equal(CLOSE_WAIT, 5000);
});

test("Lab.close reports an error from closing the client, and the DELETE's error ahead of it", async (t) => {
  for (const [how, expected] of [["ok", /close broke/], ["500", /Failed to terminate session/]] as const) {
    mode = how;
    const lab = buildLab([], () => {}, () => {}, url);
    await lab.client.connect(lab.transport([]));
    const real = lab.client.close.bind(lab.client);
    t.mock.method(lab.client, "close", async () => {
      await real();
      throw new Error("close broke");
    });
    await assert.rejects(lab.close(WAIT), expected, how);
  }
});

test("Lab.close leaves no timer of its wait running", async () => {
  mode = "ok";
  const timers = () => process.getActiveResourcesInfo().filter((name) => name === "Timeout").length;
  const before = timers();
  const lab = buildLab([], () => {}, () => {}, url);
  await lab.client.connect(lab.transport([]));
  await lab.close(60_000);
  assert.ok(timers() <= before, `${timers()} timers running after close, ${before} before`);
});

type Stubbed = { run(command: readonly string[]): Promise<void>; lab: Lab };
for (const [name, cls, run] of [["tour", Tour, runTour], ["server-tour", ServerTour, runServerTour]] as const) {
  // A run whose only step is the connection, so the close step has a DELETE to send.
  const connectOnly = async function (this: Stubbed) { await this.lab.client.connect(this.lab.transport([])); };

  test(`${name}: a failed close step alone fails the run, within the wait it was given`, async (t) => {
    mode = "never";
    t.mock.method(cls.prototype as unknown as Stubbed, "run", connectOnly);
    const out: string[] = [];
    const started = Date.now();
    const status = await run(["unused"], (line) => out.push(line), () => {}, [], url, WAIT);
    assert.equal(status, 1);
    assert.ok(Date.now() - started < 3000, "the wait given is the wait used");
    assert.match(out[out.length - 1] as string, /FAILED .*no answer to DELETE within 0\.3 s/);
  });

  test(`${name}: a close that works leaves the run passing, with the close step printed`, async (t) => {
    mode = "ok";
    t.mock.method(cls.prototype as unknown as Stubbed, "run", connectOnly);
    const out: string[] = [];
    const status = await run(["unused"], (line) => out.push(line), () => {}, [], url, WAIT);
    assert.equal(status, 0);
    assert.match(out[out.length - 1] as string, /\bclose\s+closed$/);
  });
}

test("the 2026 tour: a close that throws is a failed close step and fails the run", async (t) => {
  t.mock.method(ModernTour.prototype as unknown as { run(): Promise<void> }, "run", async () => {});
  t.mock.method(Client.prototype, "close", async () => { throw new Error("close broke"); });
  const out: string[] = [];
  const reported: string[] = [];
  const status = await runModernTour(["unused"], (line) => out.push(line), (line) => reported.push(line), []);
  assert.equal(status, 1);
  assert.match(out[out.length - 1] as string, /^\s*\d+\s+FAILED\s+Error: close broke$/);
  assert.ok(!out.some((line) => /\bclose\s+closed\b/.test(line)), "a failed close is not printed as closed");
  assert.ok(reported.some((line) => line.startsWith("sdk: close failed at step")), reported.join("\n"));
});

test("the 2026 tour: a close that works leaves the run passing, with the close step printed", async (t) => {
  t.mock.method(ModernTour.prototype as unknown as { run(): Promise<void> }, "run", async () => {});
  t.mock.method(Client.prototype, "close", async () => {});
  const out: string[] = [];
  const status = await runModernTour(["unused"], (line) => out.push(line), () => {}, []);
  assert.equal(status, 0);
  assert.match(out[out.length - 1] as string, /\bclose\s+closed$/);
});
