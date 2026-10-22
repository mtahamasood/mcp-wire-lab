// The SDK client (phase 5): the raw client's two tours, run through @modelcontextprotocol/client.
// Usage: node clients/sdk/src/main.ts <tour|server-tour> [--caps <list>] (-- <server command...> | --url <url>)

import { parseArgs, USAGE } from "./args.ts";
import { runServerTour } from "./server_tour.ts";
import { runTour } from "./tour.ts";

async function main(argv: string[]): Promise<number> {
  const parsed = parseArgs(argv);
  if (parsed.kind === "help") {
    console.log(USAGE);
    return 0;
  }
  if (parsed.kind === "usage") {
    if (parsed.message) console.error(`sdk: ${parsed.message}`);
    console.error(USAGE);
    return 2;
  }
  const out = (line: string) => console.log(line);
  const report = (line: string) => console.error(line);
  if (parsed.mode === "server-tour") {
    return runServerTour(parsed.command, out, report, parsed.caps ?? ["roots", "sampling", "elicitation", "elicitation-url"], parsed.url);
  }
  return runTour(parsed.command, out, report, parsed.caps ?? [], parsed.url);
}

process.exitCode = await main(process.argv.slice(2));
