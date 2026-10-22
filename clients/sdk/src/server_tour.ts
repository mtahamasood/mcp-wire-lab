// The server tour (phase 5 D2): phase 3 D4's steps. Declares the capabilities, answers what the
// server asks through the handlers `buildLab` registers, and calls the tools that make the
// server speak first. It waits at the raw server tour's settle points by counting the traffic it
// has seen, then for a quiet window; never by a fixed sleep alone.

import type { Client } from "@modelcontextprotocol/client";
import type { Capability } from "./args.ts";
import { STATIC_DOC, buildLab } from "./client.ts";
import type { Lab } from "./client.ts";
import { OTHER_ROOT } from "./handlers.ts";
import { Steps, text0 } from "./steps.ts";

const SETTLE = 5000; // ms to wait for server traffic a step needs to see
const QUIET = 450; // ms without server traffic that ends a settle: longer than the SDK's 300 ms debounce
const GATED_TOOLS = [
  "get-roots-list", "trigger-sampling-request", "trigger-elicitation-request",
  "trigger-multi-step-elicitation", "trigger-url-elicitation",
];
const NOTE = "notifications/message";
const ELICIT = "elicitation/create";

class ServerTour {
  readonly steps: Steps;
  readonly lab: Lab;
  readonly client: Client;
  readonly caps: readonly Capability[];

  constructor(steps: Steps, lab: Lab, caps: readonly Capability[]) {
    this.steps = steps;
    this.lab = lab;
    this.client = lab.client;
    this.caps = caps;
  }

  seen(method: string): number {
    return this.lab.traffic.seen(method);
  }

  /** Call a tool and return the first text of its result; an error result is a failure. */
  async tool(name: string, args: Record<string, unknown> = {}): Promise<string> {
    const result = await this.client.callTool({ name, arguments: args });
    this.steps.expect(!result.isError, `${name} returned an error: ${JSON.stringify(result)}`);
    return text0(result as { content: unknown[] });
  }

  async settle(what: string): Promise<void> {
    this.steps.expect(await this.lab.traffic.quiet(QUIET, SETTLE), `${what}: the client did not go quiet`);
  }

  async run(command: readonly string[]): Promise<void> {
    await this.opening(command);
    await this.roots();
    await this.sampling();
    await this.elicitation();
    await this.logging();
    await this.listChanges();
    await this.resourceUpdate();
    await this.rootsChange();
  }

  /** `initialize` with every capability, then the server's roots sync and tool burst. */
  async opening(command: readonly string[]): Promise<void> {
    const { traffic } = this.lab;
    await this.client.connect(this.lab.transport(command));
    const info = this.client.getServerVersion();
    this.steps.step("initialize (all capabilities)", `version ${this.client.getNegotiatedProtocolVersion()}, server ${info?.name}`);
    this.steps.step("notifications/initialized", "sent");
    if (this.caps.length > 0) {
      await traffic.waitFor(() => traffic.relisted("tools") >= 1, SETTLE);
    }
    if (this.caps.includes("roots")) {
      await traffic.waitFor(() => this.seen("roots/list") >= 1, SETTLE);
      await traffic.waitFor(() => this.seen(NOTE) >= 1, SETTLE);
    }
    await this.settle("the opening");
    this.steps.expect(this.seen("roots/list") === 1, "the server did not ask roots/list after init");
    this.steps.expect(this.seen(NOTE) === 1, "no log message after the roots sync");
    this.steps.step("roots/list (server asked)", "answered, 1 root");
    const listed = traffic.lists.get("tools") ?? [];
    const missing = GATED_TOOLS.filter((t) => !listed.includes(t));
    this.steps.expect(missing.length === 0, `tools/list after the burst lacks ${JSON.stringify(missing)}`);
    this.steps.expect(traffic.relisted("tools") >= 1, "no re-list after list_changed");
    this.steps.step("tools/list_changed burst", `re-listed, ${listed.length} tools`);
  }

  async roots(): Promise<void> {
    const before = this.seen("roots/list");
    const text = await this.tool("get-roots-list");
    this.steps.expect(this.seen("roots/list") === before + 1, "get-roots-list asked no roots/list");
    this.steps.expect(text.includes("wire-lab"), `the roots were not reported back: ${JSON.stringify(text)}`);
    this.steps.step("tools/call get-roots-list", text.split("\n")[0] ?? "");
  }

  async sampling(): Promise<void> {
    const before = this.seen("sampling/createMessage");
    const text = await this.tool("trigger-sampling-request", { prompt: "hello from the wire lab" });
    this.steps.expect(this.seen("sampling/createMessage") === before + 1, "no sampling request");
    this.steps.expect(text.includes("canned reply from wire-lab-sdk"), `canned reply missing: ${JSON.stringify(text)}`);
    this.steps.step("tools/call trigger-sampling-request", "sampling answered with canned text");
  }

  async elicitation(): Promise<void> {
    const before = this.seen(ELICIT);
    let text = await this.tool("trigger-elicitation-request");
    this.steps.expect(this.seen(ELICIT) === before + 1, "no form elicitation request");
    this.steps.expect(text.includes("provided the requested information"), `form not accepted: ${JSON.stringify(text)}`);
    this.steps.step("tools/call trigger-elicitation-request", "form accepted from defaults");
    text = await this.tool("trigger-multi-step-elicitation");
    this.steps.expect(this.seen(ELICIT) === before + 3, "multi-step asked other than two rounds");
    this.steps.step("tools/call trigger-multi-step-elicitation", "two rounds answered");
    text = await this.tool("trigger-url-elicitation", { url: "https://example.com/wire-lab" });
    this.steps.expect(this.seen(ELICIT) === before + 4, "no URL elicitation request");
    this.steps.expect(text.includes("declined"), `the URL elicitation was not declined: ${JSON.stringify(text)}`);
    this.steps.step("tools/call trigger-url-elicitation", "URL mode declined");
  }

  async logging(): Promise<void> {
    const level = await this.client.setLoggingLevel("debug");
    this.steps.expect(Object.keys(level).length === 0, "setLevel -> {}");
    this.steps.step("logging/setLevel debug", "{}");
    const before = this.seen(NOTE);
    await this.tool("trigger-log-messages");
    await this.lab.traffic.waitFor(() => this.seen(NOTE) >= before + 8, SETTLE);
    this.steps.expect(this.seen(NOTE) === before + 8, "expected a message at each of 8 levels");
    this.steps.step("tools/call trigger-log-messages", "8 notifications/message");
  }

  /** `trigger-list-changed` for each list; the SDK re-requests the one that changed. */
  async listChanges(): Promise<void> {
    const { traffic } = this.lab;
    for (const kind of ["tools", "prompts", "resources"]) {
      const note = `notifications/${kind}/list_changed`;
      const before = this.seen(note);
      const relisted = traffic.relisted(kind);
      await this.tool("trigger-list-changed", { list: kind });
      await traffic.waitFor(() => traffic.relisted(kind) > relisted, SETTLE);
      await this.settle(`${kind} list_changed`);
      this.steps.expect(this.seen(note) === before + 1, `no ${note}`);
      this.steps.expect(traffic.relisted(kind) === relisted + 1, `${kind} not re-listed`);
      this.steps.step(`tools/call trigger-list-changed ${kind}`, `${kind}/list re-requested`);
    }
  }

  /** Subscribe, then `trigger-resource-update`: the client re-reads the resource. */
  async resourceUpdate(): Promise<void> {
    const { traffic } = this.lab;
    const subscribed = await this.client.subscribeResource({ uri: STATIC_DOC });
    this.steps.expect(Object.keys(subscribed).length === 0, "subscribe -> {}");
    this.steps.step("resources/subscribe", "{}");
    const before = this.seen("notifications/resources/updated");
    await this.tool("trigger-resource-update", { uri: STATIC_DOC });
    await traffic.waitFor(() => traffic.rereads.length >= 1, SETTLE);
    await this.settle("resources/updated");
    this.steps.expect(this.seen("notifications/resources/updated") === before + 1, "no update");
    this.steps.expect(traffic.rereads.length === 1 && traffic.rereads[0] === STATIC_DOC, "the resource was not re-read");
    this.steps.step("tools/call trigger-resource-update", "resources/updated, re-read");
  }

  /** Change the roots: `notifications/roots/list_changed`, and the server asks again. */
  async rootsChange(): Promise<void> {
    const asked = this.seen("roots/list");
    const logged = this.seen(NOTE);
    this.lab.roots.push({ ...OTHER_ROOT });
    await this.client.sendRootsListChanged();
    this.steps.step("notifications/roots/list_changed", "sent, 2 roots now");
    const answered = await this.lab.traffic.waitFor(() => this.seen("roots/list") >= asked + 1, SETTLE);
    this.steps.expect(answered, "the server did not ask roots/list after the change");
    this.steps.expect(await this.lab.traffic.waitFor(() => this.seen(NOTE) >= logged + 1, SETTLE), "no log after the change");
    await this.settle("roots change");
    this.steps.step("roots/list (server asked)", "answered, 2 roots");
  }
}

export async function runServerTour(
  command: readonly string[],
  out: (line: string) => void,
  report: (line: string) => void,
  caps: readonly Capability[],
  url?: string,
): Promise<number> {
  const steps = new Steps(out);
  const lab = buildLab(caps, (line) => steps.say(`      ${line}`), report, url);
  const tour = new ServerTour(steps, lab, caps);
  let status = 0;
  try {
    await tour.run(command);
  } catch (error) {
    const failure = `${String(steps.n).padStart(2)}  FAILED  ${(error as Error).name}: ${(error as Error).message}`;
    steps.say(failure);
    report(`sdk: server tour failed at step ${failure.trim()}`);
    status = 1;
  }
  await lab.close();
  steps.step("close", "closed");
  return status;
}
