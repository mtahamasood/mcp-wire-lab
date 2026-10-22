// The SDK client's command line (phase 5 D2): a mode, an optional --caps list, "--", a server command.

export const CAPABILITIES = ["roots", "sampling", "elicitation", "elicitation-url"] as const;
export type Capability = (typeof CAPABILITIES)[number];
export const MODES = ["tour", "server-tour"] as const;
export type Mode = (typeof MODES)[number];

export const USAGE = [
  "usage: node clients/sdk/src/main.ts <tour|server-tour> [--caps <list>] -- <server command...>",
  `  --caps: comma-separated from ${CAPABILITIES.join(", ")}, or none`,
  "  tour: the raw client's scripted conversation, run through @modelcontextprotocol/client",
  "  (exits 0 if every step got the reply it expects). server-tour: the server-initiated traffic",
  "  of lesson 03, answered through the SDK's handlers. The default for --caps is none for tour",
  "  and all four for server-tour.",
  "  To record a run with the tap in between, use scripts/record.sh --client <sdk-tour|sdk-server-tour>.",
].join("\n");

export type Parsed =
  | { kind: "help" }
  | { kind: "usage"; message?: string }
  | { kind: "run"; mode: Mode; caps: Capability[] | undefined; command: string[] };

/** A `--caps` value as a list of capability names; throws on an unknown one. */
export function parseCaps(text: string): Capability[] {
  const names = text.split(",").filter((n) => n !== "" && n !== "none");
  const out: Capability[] = [];
  for (const name of names) {
    if (!(CAPABILITIES as readonly string[]).includes(name)) {
      throw new Error(`unknown capability '${name}'; use ${CAPABILITIES.join(", ")}`);
    }
    if (!out.includes(name as Capability)) out.push(name as Capability);
  }
  return out;
}

/** The `capabilities` object for `initialize` that declares exactly `caps` (the raw client's). */
export function capabilityObject(caps: readonly Capability[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (caps.includes("roots")) out.roots = { listChanged: true };
  if (caps.includes("sampling")) out.sampling = {};
  if (caps.includes("elicitation") || caps.includes("elicitation-url")) {
    const elicitation: Record<string, unknown> = {};
    if (caps.includes("elicitation")) elicitation.form = {};
    if (caps.includes("elicitation-url")) elicitation.url = {};
    out.elicitation = elicitation;
  }
  return out;
}

export function parseArgs(argv: readonly string[]): Parsed {
  const isHelp = (a: string | undefined) => a === "-h" || a === "--help";
  const first = argv[0];
  if (isHelp(first) || (first !== undefined && (MODES as readonly string[]).includes(first) && isHelp(argv[1]))) {
    return { kind: "help" };
  }
  if (first === undefined || !(MODES as readonly string[]).includes(first)) return { kind: "usage" };
  const rest = argv.slice(1);
  const split = rest.indexOf("--");
  if (split < 0) return { kind: "usage" };
  const options = rest.slice(0, split);
  const command = rest.slice(split + 1);
  if (command.length === 0) return { kind: "usage" };
  let caps: Capability[] | undefined;
  if (options.length > 0) {
    if (options.length !== 2 || options[0] !== "--caps") return { kind: "usage" };
    try {
      caps = parseCaps(options[1] as string);
    } catch (error) {
      return { kind: "usage", message: (error as Error).message };
    }
  }
  return { kind: "run", mode: first as Mode, caps, command };
}
