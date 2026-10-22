// What the SDK client answers when the server speaks first (phase 5 D2; the values are phase 3 D1's).
// Pure functions and a traffic counter: no SDK import, so `node --test` can check them alone.

export type Root = { uri: string; name: string };
export type Schema = Record<string, unknown>;
export type FormValue = string | number | boolean | string[];

export const CANNED_TEXT = "canned reply from wire-lab-sdk";
export const CANNED_MODEL = "wire-lab-canned";
export const DEFAULT_ROOTS: readonly Root[] = [{ uri: "file:///wire-lab/project", name: "wire-lab" }];
export const OTHER_ROOT: Root = { uri: "file:///wire-lab/other", name: "other" };
const FIXED_VALUES: Record<string, FormValue> = { string: "wire-lab", number: 1, integer: 1, boolean: true };

/** The first value a single-select property allows, or undefined if it lists none. */
function firstOption(schema: Schema): unknown {
  const values = schema.enum;
  if (Array.isArray(values) && values.length > 0) return values[0];
  for (const key of ["oneOf", "anyOf"]) {
    const options = schema[key];
    if (Array.isArray(options) && options.length > 0) return (options[0] as Schema).const;
  }
  return undefined;
}

/** One property of an elicitation form: its default, else its first option, else a fixed value. */
export function formValue(schema: Schema): FormValue {
  if ("default" in schema) {
    const given = schema.default;
    // ElicitResult.content allows no fraction, so a default of 3.14 goes back as 3.
    return (typeof given === "number" ? Math.trunc(given) : given) as FormValue;
  }
  const first = firstOption(schema);
  if (first !== undefined && first !== null) return first as FormValue;
  if (schema.type === "array") {
    const option = firstOption((schema.items ?? {}) as Schema);
    return option === undefined || option === null ? [] : [option as string];
  }
  const kind = typeof schema.type === "string" ? schema.type : "string";
  return FIXED_VALUES[kind] ?? (FIXED_VALUES.string as FormValue);
}

export type ElicitParams = { mode?: string; requestedSchema?: { properties?: Record<string, Schema> } };

/** The answer to `elicitation/create`: a form is accepted from its values, a URL is declined. */
export function elicitationResult(params: ElicitParams): { action: "accept" | "decline"; content?: Record<string, FormValue> } {
  if ((params.mode ?? "form") === "url") return { action: "decline" };
  const content: Record<string, FormValue> = {};
  for (const [name, spec] of Object.entries(params.requestedSchema?.properties ?? {})) {
    content[name] = formValue(spec);
  }
  return { action: "accept", content };
}

/** The answer to `sampling/createMessage`: the canned reply. */
export function samplingResult() {
  return {
    role: "assistant" as const,
    content: { type: "text" as const, text: CANNED_TEXT },
    model: CANNED_MODEL,
    stopReason: "endTurn",
  };
}

/** The answer to `roots/list`. */
export function rootsResult(roots: readonly Root[]): { roots: Root[] } {
  return { roots: roots.map((r) => ({ ...r })) };
}

/**
 * Counts the server traffic the client has seen, so a step can wait for what it needs by
 * count (`waitFor`) and then for quiet (`quiet`), never by a fixed sleep alone.
 */
export class Traffic {
  readonly counts = new Map<string, number>();
  readonly relists: string[] = []; // lists re-requested by the SDK, in order ("tools", ...)
  readonly rereads: string[] = []; // resource URIs re-read, in order
  readonly lists = new Map<string, string[]>(); // names or URIs of the last re-list, by list
  private busy = 0;
  private last = Date.now();

  seen(method: string): number {
    return this.counts.get(method) ?? 0;
  }

  mark(method: string): void {
    this.counts.set(method, this.seen(method) + 1);
    this.last = Date.now();
  }

  relisted(kind: string): number {
    return this.relists.filter((k) => k === kind).length;
  }

  /** Run work the client does in answer to the server; `quiet` waits for it. */
  async working<T>(work: () => Promise<T>): Promise<T> {
    this.busy += 1;
    try {
      return await work();
    } finally {
      this.busy -= 1;
      this.last = Date.now();
    }
  }

  touch(): void {
    this.last = Date.now();
  }

  /** True once `predicate` holds, polling until `timeoutMs`. */
  async waitFor(predicate: () => boolean, timeoutMs: number): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (!predicate()) {
      if (Date.now() >= deadline) return false;
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
    return true;
  }

  /** True once nothing is in flight and no server traffic arrived for `quietMs`. */
  quiet(quietMs: number, timeoutMs: number): Promise<boolean> {
    return this.waitFor(() => this.busy === 0 && Date.now() - this.last >= quietMs, timeoutMs);
  }
}
