import type { Capability } from "./args.ts";

export async function runServerTour(
  _command: readonly string[],
  out: (line: string) => void,
  _report: (line: string) => void,
  _caps: readonly Capability[],
): Promise<number> {
  out("server-tour: not built yet");
  return 1;
}
