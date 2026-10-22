// The SDK client in the 2026-07-28 era (phase 6 D11): the raw client's 2026 tour (phase 6 D6),
// step for step with the same inputs, through @modelcontextprotocol/client pinned to the new era.
// Everything era-specific lives here so that phase 5's files stay as they were.

import { CLIENT_CAPABILITIES_META_KEY, Client, LOG_LEVEL_META_KEY, StreamableHTTPClientTransport, SUBSCRIPTION_ID_META_KEY } from "@modelcontextprotocol/client";
import type { ClientCapabilities, McpSubscription } from "@modelcontextprotocol/client";
import { StdioClientTransport } from "@modelcontextprotocol/client/stdio";
import { capabilityObject } from "./args.ts";
import type { Capability } from "./args.ts";
import { CLIENT_INFO, STATIC_DOC } from "./client.ts";
import { DEFAULT_ROOTS, Traffic, elicitationResult, rootsResult, samplingResult } from "./handlers.ts";
import type { ElicitParams } from "./handlers.ts";
import { Steps, compact, text0 } from "./steps.ts";

export const MODERN_ERA = "2026-07-28";
/** The capabilities the 2026 tour declares unless `--caps` says otherwise (phase 6 D6). */
export const MODERN_TOUR_CAPS: readonly Capability[] = ["roots", "sampling", "elicitation"];
const MISSING_CAPABILITY = -32021;
const NOTE_WAIT = 5000; // ms to wait for a notification the tour needs to see
const CANCEL_REASON = "the tour cancels after the first progress";

/**
 * A member-less subclass of the SDK's stdio transport. With the base class the SDK runs the
 * `server/discover` probe on a second, short-lived process started from the same command
 * (`sdk:client/dist/index.mjs:2880`, `readStdioServerParams`, which only the base class
 * satisfies); under `scripts/record.sh` that second process is a second tap that truncates the
 * trace the first one writes, so the discover would be lost. A subclass probes on the same
 * connection, so the trace opens with `server/discover`.
 */
export class InPlaceStdioTransport extends StdioClientTransport {}

type Progress = { progress: number; total?: number; message?: string };
type Meta = Record<string, unknown>;

class ModernTour {
  readonly steps: Steps;
  readonly client: Client;
  readonly traffic = new Traffic();
  readonly errors: string[] = [];
  private subscription: McpSubscription | undefined;
  private subscriptionId: unknown;
  private http = false;

  constructor(steps: Steps, caps: readonly Capability[], report: (line: string) => void) {
    this.steps = steps;
    // No `listChanged` option: on a 2026 connection it would make the SDK open its own
    // subscription and re-list; this tour opens one itself with `listen()`.
    this.client = new Client(CLIENT_INFO, {
      capabilities: capabilityObject(caps) as ClientCapabilities,
      versionNegotiation: { mode: { pin: MODERN_ERA } },
    });
    this.client.onerror = (error) => {
      this.errors.push(error.message);
      report(`sdk: ${error.message}`);
    };
    // The SDK fulfils input requests (MRTR) through the handlers registered for the
    // server-to-client methods of 2025.
    if (caps.includes("roots")) {
      this.client.setRequestHandler("roots/list", () => {
        this.traffic.mark("roots/list");
        return rootsResult(DEFAULT_ROOTS);
      });
    }
    if (caps.includes("sampling")) {
      this.client.setRequestHandler("sampling/createMessage", () => {
        this.traffic.mark("sampling/createMessage");
        return samplingResult();
      });
    }
    if (caps.includes("elicitation") || caps.includes("elicitation-url")) {
      this.client.setRequestHandler("elicitation/create", (request) => {
        this.traffic.mark("elicitation/create");
        return elicitationResult(request.params as ElicitParams);
      });
    }
    this.client.setNotificationHandler("notifications/message", (note) => {
      this.traffic.mark("notifications/message");
      const p = note.params;
      this.steps.say(`      <- notifications/message level=${p.level} logger=${p.logger ?? "-"} ${compact(p.data)}`);
    });
    for (const kind of ["tools", "prompts", "resources"] as const) {
      const method = `notifications/${kind}/list_changed` as const;
      this.client.setNotificationHandler(method, (note) => {
        this.traffic.mark(method);
        this.subscriptionId = (note.params?._meta as Meta | undefined)?.[SUBSCRIPTION_ID_META_KEY];
      });
    }
    this.client.setNotificationHandler("notifications/resources/updated", (note) => {
      this.traffic.mark("notifications/resources/updated");
      this.subscriptionId = (note.params?._meta as Meta | undefined)?.[SUBSCRIPTION_ID_META_KEY];
    });
  }

  async run(command: readonly string[], url?: string): Promise<void> {
    this.http = url !== undefined;
    await this.discovery(command, url);
    await this.tools();
    await this.resources();
    await this.prompts();
    await this.utilities();
    await this.logLevels();
    await this.longRunning();
    await this.cancelled();
    await this.subscriptions();
    await this.inputRequired();
    await this.closeSubscription();
  }

  /**
   * `connect` probes with `server/discover` (the pin), replacing `initialize`. With a URL the
   * transport is the SDK's Streamable HTTP one (phase 7 D11): no session id, so no GET stream
   * and no DELETE.
   */
  async discovery(command: readonly string[], url?: string): Promise<void> {
    await this.client.connect(url === undefined
      ? new InPlaceStdioTransport({ command: command[0] as string, args: command.slice(1) })
      : new StreamableHTTPClientTransport(new URL(url)));
    const version = this.client.getNegotiatedProtocolVersion();
    this.steps.expect(version === MODERN_ERA, `the connection must run ${MODERN_ERA}, not ${version}`);
    this.steps.step("server/discover", `version ${version}, server ${this.client.getServerVersion()?.name}`);
  }

  async tools(): Promise<void> {
    const { tools } = await this.client.listTools();
    const names = new Set(tools.map((t) => t.name));
    const needed = [
      "echo", "get-sum", "trigger-long-running-operation", "trigger-log-messages", "trigger-list-changed",
      "trigger-resource-update", "get-roots-list", "trigger-sampling-request", "trigger-elicitation-request",
      "trigger-multi-step-elicitation",
    ];
    const missing = needed.filter((n) => !names.has(n));
    this.steps.expect(missing.length === 0, `tools/list lacks ${compact(missing)}`);
    this.steps.step("tools/list", `${tools.length} tools`);
    const echo = text0((await this.client.callTool({ name: "echo", arguments: { message: "hello" } })) as { content: unknown[] });
    this.steps.expect(echo === "Echo: hello", "echo must say Echo: hello");
    this.steps.step("tools/call echo", echo);
    const sum = text0((await this.client.callTool({ name: "get-sum", arguments: { a: 2, b: 3 } })) as { content: unknown[] });
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
    const read = await this.client.readResource({ uri: STATIC_DOC });
    const first = read.contents[0] as { uri: string; text?: string } | undefined;
    this.steps.expect(first?.uri === STATIC_DOC && Boolean(first.text), "resources/read must return the document's text");
    const meta = read as { ttlMs?: number; cacheScope?: string };
    this.steps.step("resources/read", `${first?.text?.length} characters of text, ttlMs ${meta.ttlMs}, cacheScope ${meta.cacheScope}`);
  }

  async prompts(): Promise<void> {
    const { prompts } = await this.client.listPrompts();
    const names = new Set(prompts.map((p) => p.name));
    const missing = ["simple-prompt", "args-prompt"].filter((n) => !names.has(n));
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
      ref: { type: "ref/prompt", name: "completable-prompt" },
      argument: { name: "department", value: "E" },
    });
    this.steps.expect(completion.values.includes("Engineering"), "department E must complete Engineering");
    this.steps.step("completion/complete department=E", completion.values.join(", "));
  }

  /** The log level is per request, in `_meta` (replaces `logging/setLevel`). */
  async logLevels(): Promise<void> {
    const { traffic } = this;
    const before = traffic.seen("notifications/message");
    await this.client.callTool({ name: "trigger-log-messages", arguments: {} });
    await traffic.quiet(300, NOTE_WAIT);
    const none = traffic.seen("notifications/message") - before;
    this.steps.expect(none === 0, `no log level was sent, yet ${none} notifications/message arrived`);
    this.steps.step("tools/call trigger-log-messages", "no logLevel: 0 notifications/message");
    await this.client.callTool({ name: "trigger-log-messages", arguments: {}, _meta: { [LOG_LEVEL_META_KEY]: "warning" } });
    const five = await traffic.waitFor(() => traffic.seen("notifications/message") - before >= 5, NOTE_WAIT);
    await traffic.quiet(300, NOTE_WAIT);
    const got = traffic.seen("notifications/message") - before;
    this.steps.expect(five && got === 5, `logLevel warning must give 5 notifications/message, got ${got}`);
    this.steps.step("tools/call trigger-log-messages", "logLevel warning: 5 notifications/message");
  }

  async longRunning(): Promise<void> {
    const seen: Progress[] = [];
    const done = await this.client.callTool(
      { name: "trigger-long-running-operation", arguments: { duration: 1, steps: 2 } },
      { onprogress: (p) => { seen.push(p); this.traffic.mark("notifications/progress"); this.steps.say(`      <- notifications/progress ${compact(p)}`); } },
    );
    this.steps.expect(text0(done as { content: unknown[] }).includes("completed"), "the operation must complete");
    this.steps.expect(seen.length === 2, "expected two progress notifications");
    this.steps.step("tools/call long-running (done)", "completed, 2 progress notifications");
  }

  async cancelled(): Promise<void> {
    const { traffic } = this;
    const controller = new AbortController();
    const before = this.errors.length;
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
    // The server's tool ignores the cancellation and finishes (measured); the SDK has forgotten
    // the token by then and reports the late progress through onerror.
    // Over HTTP the abort closes the response stream (the cancellation, D11), so nothing arrives.
    if (!this.http) {
      const late = await traffic.waitFor(() => this.errors.slice(before).some((e) => e.includes("progress notification")), NOTE_WAIT);
      this.steps.expect(late, "the late progress notification never arrived");
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
    this.steps.step("tools/call long-running (cancelled)", "cancelled after progress 1");
  }

  /** `subscriptions/listen`, then each change the server announces on that stream. */
  async subscriptions(): Promise<void> {
    const { traffic } = this;
    this.subscription = await this.client.listen({
      toolsListChanged: true, promptsListChanged: true, resourcesListChanged: true, resourceSubscriptions: [STATIC_DOC],
    });
    this.steps.step("subscriptions/listen", `acknowledged, honoured ${compact(this.subscription.honoredFilter)}`);
    for (const kind of ["tools", "prompts", "resources"]) {
      const method = `notifications/${kind}/list_changed`;
      const count = traffic.seen(method);
      await this.client.callTool({ name: "trigger-list-changed", arguments: { list: kind } });
      this.steps.expect(await traffic.waitFor(() => traffic.seen(method) > count, NOTE_WAIT), `no ${method}`);
      this.steps.step(`tools/call trigger-list-changed ${kind}`, `${method} on subscription ${String(this.subscriptionId)}`);
    }
    const count = traffic.seen("notifications/resources/updated");
    await this.client.callTool({ name: "trigger-resource-update", arguments: { uri: STATIC_DOC } });
    this.steps.expect(await traffic.waitFor(() => traffic.seen("notifications/resources/updated") > count, NOTE_WAIT), "no resource update");
    this.steps.step("tools/call trigger-resource-update", `notifications/resources/updated on subscription ${String(this.subscriptionId)}`);
  }

  /** No server-to-client requests: the server answers `input_required` and the SDK retries. */
  async inputRequired(): Promise<void> {
    let failed = false;
    try {
      await this.client.callTool({ name: "get-roots-list", arguments: {}, _meta: { [CLIENT_CAPABILITIES_META_KEY]: {} } });
    } catch (error) {
      failed = true;
      const code = (error as { code?: number }).code;
      this.steps.expect(code === MISSING_CAPABILITY, `expected ${MISSING_CAPABILITY}, got ${String(code)}: ${(error as Error).message}`);
      this.steps.step("tools/call get-roots-list (no caps)", `error ${code}`);
    }
    this.steps.expect(failed, "get-roots-list without the roots capability must fail");
    const calls: [string, Record<string, unknown>, string][] = [
      ["get-roots-list", {}, "roots listed"],
      ["trigger-sampling-request", { prompt: "Say hello" }, "sampling answered"],
      ["trigger-elicitation-request", {}, "form accepted from defaults"],
      ["trigger-multi-step-elicitation", {}, "three rounds answered"],
    ];
    for (const [name, args, summary] of calls) {
      const result = await this.client.callTool({ name, arguments: args });
      this.steps.expect(Boolean((result as { content?: unknown[] }).content?.length), `${name} returned no content`);
      this.steps.step(`tools/call ${name}`, summary);
    }
  }

  async closeSubscription(): Promise<void> {
    this.steps.expect(this.subscription !== undefined, "no subscription to close");
    await this.subscription?.close();
    this.steps.step("notifications/cancelled", "closed the subscription");
  }
}

export async function runModernTour(
  command: readonly string[],
  out: (line: string) => void,
  report: (line: string) => void,
  caps: readonly Capability[],
  url?: string,
): Promise<number> {
  const steps = new Steps(out);
  const tour = new ModernTour(steps, caps, report);
  let status = 0;
  try {
    await tour.run(command, url);
  } catch (error) {
    const failure = `${String(steps.n).padStart(2)}  FAILED  ${(error as Error).name}: ${(error as Error).message}`;
    steps.say(failure);
    report(`sdk: tour failed at step ${failure.trim()}`);
    status = 1;
  }
  await tour.client.close();
  steps.step("close", "closed");
  return status;
}
