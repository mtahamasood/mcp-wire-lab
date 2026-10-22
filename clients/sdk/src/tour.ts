// The scripted tour (phase 5 D2): connect, one echo call, close. (Slice; widened below.)

import type { Capability } from "./args.ts";
import { buildLab } from "./client.ts";
import { Steps, text0 } from "./steps.ts";

export async function runTour(
  command: readonly string[],
  out: (line: string) => void,
  report: (line: string) => void,
  caps: readonly Capability[],
): Promise<number> {
  const steps = new Steps(out);
  const lab = buildLab(caps, (line) => steps.say(`      ${line}`), report);
  const { client } = lab;
  let status = 0;
  try {
    await client.connect(lab.transport(command));
    const info = client.getServerVersion();
    steps.step("initialize", `version ${client.getNegotiatedProtocolVersion()}, server ${info?.name}`);
    steps.step("notifications/initialized", "sent");
    const echo = await client.callTool({ name: "echo", arguments: { message: "hello" } });
    steps.step("tools/call echo", text0(echo as { content: unknown[] }));
  } catch (error) {
    const failure = `${String(steps.n).padStart(2)}  FAILED  ${(error as Error).name}: ${(error as Error).message}`;
    steps.say(failure);
    report(`sdk: tour failed at step ${failure.trim()}`);
    status = 1;
  }
  await client.close();
  steps.step("close", "closed");
  return status;
}
