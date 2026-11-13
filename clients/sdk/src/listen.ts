// The id of the 2026 tour's `subscriptions/listen` request, and the check that what the server
// announces on that subscription carries it (phase 6 D6: each list change and the resource update
// are "tagged with the listen id"; P8-R6-4).
//
// The SDK's `listen()` result does not expose the id: the SDK makes it up (`listen:<n>`, in
// `sdk:client/dist/index.mjs:3987`) and puts it on the request it sends. So the tour reads it from
// that request as the transport is handed it, and nothing here builds or sends a message: the
// transport's own `send` slot is wrapped, as order.ts wraps `onmessage`.

import { SUBSCRIPTION_ID_META_KEY } from "@modelcontextprotocol/client";
import type { Transport } from "@modelcontextprotocol/client";

type Meta = Record<string, unknown>;
type Outgoing = { method?: unknown; id?: unknown };
type Forward = (message: Outgoing, options?: unknown) => Promise<void>;

/** What the server tagged a notification with: `params._meta` under the SDK's subscription key. */
export function tagOf(params: { _meta?: unknown } | undefined): unknown {
  return (params?._meta as Meta | undefined)?.[SUBSCRIPTION_ID_META_KEY];
}

export class ListenTag {
  /** The id of the `subscriptions/listen` request the transport was handed, once it was. */
  id: string | undefined;

  /** `transport`, with each message it is handed looked at on its way (the first listen request is kept). */
  watch<T extends Transport>(transport: T): T {
    const forward = transport.send as Forward;
    Object.defineProperty(transport, "send", {
      configurable: true,
      writable: true,
      value: (message: Outgoing, options?: unknown) => {
        if (this.id === undefined && message.method === "subscriptions/listen" && typeof message.id === "string") this.id = message.id;
        return forward.call(transport, message, options);
      },
    });
    return transport;
  }

  /** Why a notification's `tag` is not the listen id, or undefined when it is. */
  mismatch(tag: unknown): string | undefined {
    if (this.id === undefined) return "no subscriptions/listen request was seen on the transport";
    if (tag === this.id) return undefined;
    return `tagged ${tag === undefined ? "with no listen id" : `with ${JSON.stringify(tag)}`}, not with the listen id ${this.id}`;
  }
}
