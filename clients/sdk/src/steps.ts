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

/**
 * The last step of a run: `closing` ends the session, then `NN  close  closed` is printed. When it
 * throws (a DELETE answered with an error, a close that is never answered) the step is a failure
 * like any other: a `FAILED` line, an `sdk:` line on stderr, and `true` returned so the run exits 1.
 */
export async function closeStep(steps: Steps, report: (line: string) => void, closing: () => Promise<void>): Promise<boolean> {
  try {
    await closing();
  } catch (error) {
    const failure = `${String(steps.n).padStart(2)}  FAILED  ${(error as Error).name}: ${(error as Error).message}`;
    steps.say(failure);
    report(`sdk: close failed at step ${failure.trim()}`);
    return true;
  }
  steps.step("close", "closed");
  return false;
}
