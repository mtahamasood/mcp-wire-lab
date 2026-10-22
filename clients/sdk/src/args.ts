// The SDK client's command line (phase 5 D2, phase 6 D11): a mode, optional --caps and --era, "--", a server command.

export const CAPABILITIES = ["roots", "sampling", "elicitation", "elicitation-url"] as const;
export type Capability = (typeof CAPABILITIES)[number];
export const MODES = ["tour", "server-tour"] as const;
export type Mode = (typeof MODES)[number];
export const ERAS = ["2025-11-25", "2026-07-28"] as const;
export type Era = (typeof ERAS)[number];

export const USAGE = [
  "usage: node clients/sdk/src/main.ts <tour|server-tour> [--caps <list>] [--era <era>] -- <server command...>",
  `  --caps: comma-separated from ${CAPABILITIES.join(", ")}, or none`,
  "  tour: the raw client's scripted conversation, run through @modelcontextprotocol/client",
  "  (exits 0 if every step got the reply it expects). server-tour: the server-initiated traffic",
  "  of lesson 03, answered through the SDK's handlers. The default for --caps is none for tour",
  "  and all four for server-tour (the 2026 tour declares roots, sampling and form elicitation).",
  "  To record a run with the tap in between, use scripts/record.sh --client <sdk-tour|sdk-server-tour|sdk-tour-2026>.",
].join("\n");

export type Parsed =
  | { kind: "help" }
  | { kind: "usage"; message?: string }
  | { kind: "run"; mode: Mode; caps: Capability[] | undefined; era: Era; command: string[] };

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
  let era: Era = ERAS[0];
  const seen = new Set<string>();
  if (options.length % 2 !== 0) return { kind: "usage" };
  for (let i = 0; i < options.length; i += 2) {
    const flag = options[i] as string;
    const value = options[i + 1] as string;
    if (seen.has(flag) || (flag !== "--caps" && flag !== "--era")) return { kind: "usage" };
    seen.add(flag);
    if (flag === "--era") {
      if (!(ERAS as readonly string[]).includes(value)) return { kind: "usage", message: `unknown era '${value}'; use ${ERAS.join(" or ")}` };
      era = value as Era;
      continue;
    }
    try {
      caps = parseCaps(value);
    } catch (error) {
      return { kind: "usage", message: (error as Error).message };
    }
  }
  if (first === "server-tour" && era !== ERAS[0]) return { kind: "usage", message: `server-tour runs only in ${ERAS[0]}` };
  return { kind: "run", mode: first as Mode, caps, era, command };
}
