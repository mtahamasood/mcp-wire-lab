// The scripted tour (phase 5 D2): phase 2 D3's steps, in the same order with the same arguments
// and expectations, through the SDK's methods. Each step prints one line in the raw client's
// format and checks what came back; the run exits 0 only if every step got what it expects.

import type { Client } from "@modelcontextprotocol/client";
import type { Capability } from "./args.ts";
import { STATIC_DOC, buildLab } from "./client.ts";
import type { Lab } from "./client.ts";
import { Steps, compact, text0 } from "./steps.ts";

const COMPLETABLE_PROMPT = "completable-prompt";
const NOTE_WAIT = 5000; // ms to wait for a notification the tour needs to see
const CANCEL_REASON = "the tour cancels after the first progress";

type Progress = { progress: number; total?: number; message?: string };

class Tour {
  readonly steps: Steps;
  readonly lab: Lab;
  readonly client: Client;

  constructor(steps: Steps, lab: Lab) {
    this.steps = steps;
    this.lab = lab;
    this.client = lab.client;
  }

  async run(command: readonly string[]): Promise<void> {
    await this.lifecycle(command);
    await this.tools();
    await this.resources();
    await this.prompts();
    await this.utilities();
    await this.longRunning();
    await this.cancelled();
  }

  /** `connect` is `initialize` then `notifications/initialized`; `ping` is a Client method. */
  async lifecycle(command: readonly string[]): Promise<void> {
    await this.client.connect(this.lab.transport(command));
    const info = this.client.getServerVersion();
    this.steps.step("initialize", `version ${this.client.getNegotiatedProtocolVersion()}, server ${info?.name}`);
    this.steps.step("notifications/initialized", "sent");
    const pong = await this.client.ping();
    this.steps.expect(Object.keys(pong).length === 0, "ping must be answered with {}");
    this.steps.step("ping", "{}");
  }

  async tools(): Promise<void> {
    const { tools } = await this.client.listTools();
    const names = new Set(tools.map((t) => t.name));
    const missing = ["echo", "get-sum", "trigger-long-running-operation"].filter((n) => !names.has(n));
    this.steps.expect(missing.length === 0, `tools/list lacks ${compact(missing)}`);
    this.steps.step("tools/list", `${tools.length} tools`);
    const echo = await this.client.callTool({ name: "echo", arguments: { message: "hello" } });
    const text = text0(echo as { content: unknown[] });
    this.steps.expect(text === "Echo: hello", "echo must say Echo: hello");
    this.steps.step("tools/call echo", text);
    const total = await this.client.callTool({ name: "get-sum", arguments: { a: 2, b: 3 } });
    const sum = text0(total as { content: unknown[] });
    this.steps.expect(sum.includes("5"), "get-sum of 2 and 3 must say 5");
    this.steps.step("tools/call get-sum", sum);
  }

  async resources(): Promise<void> {
    const { resources } = await this.client.listResources();
    this.steps.expect(resources.some((r) => r.uri === STATIC_DOC), `no resource ${STATIC_DOC}`);
    this.steps.step("resources/list", `${resources.length} resources`);
    const { resourceTemplates } = await this.client.listResourceTemplates();
    this.steps.expect(resourceTemplates.length > 0, "no resource templates");
    this.steps.step("resources/templates/list", `${resourceTemplates.length} templates`);
    const { contents } = await this.client.readResource({ uri: STATIC_DOC });
    const first = contents[0] as { uri: string; text?: string } | undefined;
    this.steps.expect(first?.uri === STATIC_DOC && Boolean(first.text), "resources/read must return the document's text");
    this.steps.step("resources/read", `${first?.text?.length} characters of text`);
    const subscribed = await this.client.subscribeResource({ uri: STATIC_DOC });
    this.steps.expect(Object.keys(subscribed).length === 0, "subscribe -> {}");
    this.steps.step("resources/subscribe", "{}");
    const unsubscribed = await this.client.unsubscribeResource({ uri: STATIC_DOC });
    this.steps.expect(Object.keys(unsubscribed).length === 0, "unsubscribe -> {}");
    this.steps.step("resources/unsubscribe", "{}");
  }

  async prompts(): Promise<void> {
    const { prompts } = await this.client.listPrompts();
    const names = new Set(prompts.map((p) => p.name));
    const missing = ["simple-prompt", "args-prompt", COMPLETABLE_PROMPT].filter((n) => !names.has(n));
    this.steps.expect(missing.length === 0, `prompts/list lacks ${compact(missing)}`);
    this.steps.step("prompts/list", `${prompts.length} prompts`);
    const simple = await this.client.getPrompt({ name: "simple-prompt" });
    this.steps.expect(simple.messages.length > 0, "simple-prompt returned no messages");
    this.steps.step("prompts/get simple-prompt", `${simple.messages.length} message`);
    const city = await this.client.getPrompt({ name: "args-prompt", arguments: { city: "Oslo" } });
    const content = city.messages[0]?.content as { text?: string } | undefined;
    this.steps.expect(Boolean(content?.text?.includes("Oslo")), "args-prompt must use the city");
    this.steps.step("prompts/get args-prompt", content?.text ?? "");
  }

  async utilities(): Promise<void> {
    const { completion } = await this.client.complete({
      ref: { type: "ref/prompt", name: COMPLETABLE_PROMPT },
      argument: { name: "department", value: "E" },
    });
    this.steps.expect(completion.values.includes("Engineering"), "department E must complete Engineering");
    this.steps.step("completion/complete department=E", completion.values.join(", "));
    const level = await this.client.setLoggingLevel("debug");
    this.steps.expect(Object.keys(level).length === 0, "setLevel -> {}");
    this.steps.step("logging/setLevel debug", "{}");
  }

  /** The same `tools/call` the raw tour makes, asking for progress the SDK's way (`onprogress`). */
  async longRunning(): Promise<void> {
    const seen: Progress[] = [];
    const done = await this.client.callTool(
      { name: "trigger-long-running-operation", arguments: { duration: 1, steps: 2 } },
      { onprogress: (p) => { seen.push(p); this.lab.traffic.mark("notifications/progress"); this.steps.say(`      <- notifications/progress ${compact(p)}`); } },
    );
    this.steps.expect(text0(done as { content: unknown[] }).includes("completed"), "the operation must complete");
    this.steps.expect(seen.length === 2, "expected two progress notifications");
    this.steps.step("tools/call long-running (done)", "completed, 2 progress notifications");
  }

  /** The same call, cancelled after its first progress notification (an aborted `AbortSignal`). */
  async cancelled(): Promise<void> {
    const { traffic } = this.lab;
    const controller = new AbortController();
    const before = this.lab.errors.length;
    const progressSeen = traffic.seen("notifications/progress");
    const pending = this.client
      .callTool(
        { name: "trigger-long-running-operation", arguments: { duration: 1, steps: 2 } },
        {
          signal: controller.signal,
          onprogress: (p) => { traffic.mark("notifications/progress"); this.steps.say(`      <- notifications/progress ${compact(p)}`); },
        },
      )
      .then(() => undefined, (error: unknown) => error);
    const first = await traffic.waitFor(() => traffic.seen("notifications/progress") > progressSeen, NOTE_WAIT);
    this.steps.expect(first, `no progress within ${NOTE_WAIT / 1000} s`);
    controller.abort(CANCEL_REASON);
    const outcome = await pending;
    this.steps.expect(outcome instanceof Error, "a cancelled request must stop waiting");
    // The server's tool ignores the cancellation and finishes its second step (measured); the SDK
    // has forgotten the token by then and reports the late progress through onerror.
    const late = await traffic.waitFor(
      () => this.lab.errors.slice(before).some((e) => e.includes("progress notification")), NOTE_WAIT);
    this.steps.expect(late, "the late progress notification never arrived");
    await new Promise((resolve) => setTimeout(resolve, 300)); // room for a late reply, which the SDK drops and reports
    this.steps.step("tools/call long-running (cancelled)", "cancelled after progress 1");
  }
}

export async function runTour(
  command: readonly string[],
  out: (line: string) => void,
  report: (line: string) => void,
  caps: readonly Capability[],
): Promise<number> {
  const steps = new Steps(out);
  const lab = buildLab(caps, (line) => steps.say(`      ${line}`), report);
  const tour = new Tour(steps, lab);
  let status = 0;
  try {
    await tour.run(command);
  } catch (error) {
    const failure = `${String(steps.n).padStart(2)}  FAILED  ${(error as Error).name}: ${(error as Error).message}`;
    steps.say(failure);
    report(`sdk: tour failed at step ${failure.trim()}`);
    status = 1;
  }
  await lab.client.close();
  steps.step("close", "closed");
  return status;
}
