// Output shared by both modes: one line per step in the raw client's format, `NN  <label>  <summary>`.

export class TourFailure extends Error {}

export class Steps {
  n = 0;
  private readonly out: (line: string) => void;

  constructor(out: (line: string) => void) {
    this.out = out;
  }

  say(text: string): void {
    this.out(text);
  }

  step(label: string, summary: string): void {
    this.out(`${String(this.n).padStart(2)}  ${label.padEnd(42)} ${summary}`);
    this.n += 1;
  }

  expect(condition: boolean, what: string): void {
    if (!condition) throw new TourFailure(what);
  }
}

export function compact(value: unknown): string {
  return JSON.stringify(value) ?? "undefined";
}

export function text0(result: { content?: unknown[] }): string {
  const first = (result.content ?? [])[0] as { text?: string } | undefined;
  return first?.text ?? "";
}
