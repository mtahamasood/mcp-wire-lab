// Wire-order dispatch for the SDK's transports (phase 8). SDK 2.3.1 hands an inbound notification
// to its handler one microtask after the transport delivers it
// (`sdk:client/dist/src-WCy6ifGf.mjs:5903` "Promise.resolve().then"), but settles a response at
// once, removing the request's progress handler
// (`sdk:client/dist/src-WCy6ifGf.mjs:6055` "this._progressHandlers.delete(messageId);"). When a
// request's last progress notification and its response are read in one chunk, the response is
// settled first and the progress is reported as "for an unknown token": the tour's long-running
// step then saw one progress notification instead of two, mostly on a loaded machine.
//
// Delivering each response one microtask late puts it behind the notifications read before it,
// so every message reaches its handler in the order it crossed the wire. Requests also wait one
// microtask in the SDK (`_onrequest`), so they keep their order too. Nothing is sent or built here;
// the transport's own `onmessage` slot is the only thing wrapped.

import type { Transport } from "@modelcontextprotocol/client";

type OnMessage = NonNullable<Transport["onmessage"]>;
type Message = Parameters<OnMessage>[0];

/**
 * A response is the one kind of message with no `method` and a `result` or an `error`; requests
 * and notifications carry a `method`. (This file names no wire field beyond those three, and no
 * message type of the SDK's by its protocol name, under phase 5's rule that only the SDK speaks.)
 */
function isResponse(message: Message): boolean {
  return !("method" in message) && ("result" in message || "error" in message);
}

/** The same handler, with responses delivered one microtask late. */
export function responsesLast(handler: OnMessage): OnMessage {
  return (message, extra) => {
    if (isResponse(message)) queueMicrotask(() => handler(message, extra));
    else handler(message, extra);
  };
}

/**
 * Make `transport` deliver messages in wire order: every handler the SDK sets on its `onmessage`
 * is wrapped with `responsesLast` as it is set. Each wrapper closes over the one handler it was
 * made for, so a caller that reads the slot and chains the old handler (as `Protocol.connect`
 * does) never calls itself.
 */
export function inWireOrder<T extends Transport>(transport: T): T {
  let current: OnMessage | undefined;
  Object.defineProperty(transport, "onmessage", {
    configurable: true,
    enumerable: true,
    get: () => current,
    set: (handler: OnMessage | undefined) => {
      current = handler === undefined ? undefined : responsesLast(handler);
    },
  });
  return transport;
}
