// Builds the SDK `Client` both modes use: capabilities declared, the server's requests answered
// through `setRequestHandler`, its notifications followed with `listChanged` and
// `setNotificationHandler`. Everything here goes through the SDK; nothing builds a message.

import { Client } from "@modelcontextprotocol/client";
import type { ClientCapabilities } from "@modelcontextprotocol/client";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/client";
import { StdioClientTransport } from "@modelcontextprotocol/client/stdio";
import { capabilityObject } from "./args.ts";
import type { Capability } from "./args.ts";
import { DEFAULT_ROOTS, Traffic, elicitationResult, rootsResult, samplingResult } from "./handlers.ts";
import type { ElicitParams, Root } from "./handlers.ts";
import { compact } from "./steps.ts";

export const CLIENT_INFO = { name: "wire-lab-sdk", version: "0.5.0" };
export const STATIC_DOC = "demo://resource/static/document/architecture.md";

export type Lab = {
  client: Client;
  traffic: Traffic;
  roots: Root[];
  /** Every error the SDK reported through onerror, in order. */
  errors: string[];
  /** Make the transport: stdio for a server command (the SDK starts the process), or, when the lab was built with a URL, Streamable HTTP to it. */
  transport(command: readonly string[]): StdioClientTransport | StreamableHTTPClientTransport;
  /** End the session: over HTTP the SDK sends DELETE only on `terminateSession()` (M15), then close. */
  close(): Promise<void>;
};

/**
 * `say` prints one notification line (indented as the raw client's), `report` one `sdk:` line
 * on stderr. The returned `Lab` holds the client and what the handlers record.
 */
export function buildLab(
  caps: readonly Capability[],
  say: (line: string) => void,
  report: (line: string) => void,
  url?: string,
): Lab {
  const traffic = new Traffic();
  const roots: Root[] = DEFAULT_ROOTS.map((r) => ({ ...r }));
  const client = new Client(CLIENT_INFO, {
    capabilities: capabilityObject(caps) as ClientCapabilities,
    listChanged: {
      tools: { onChanged: (error, items) => listed("tools", error, items?.map((t) => t.name)) },
      prompts: { onChanged: (error, items) => listed("prompts", error, items?.map((p) => p.name)) },
      resources: { onChanged: (error, items) => listed("resources", error, items?.map((r) => r.uri)) },
    },
  });
  const errors: string[] = [];
  client.onerror = (error) => {
    errors.push(error.message);
    report(`sdk: ${error.message}`);
  };

  // The SDK re-lists after its 300 ms debounce and hands the new list to onChanged.
  function listed(kind: string, error: Error | null, names: string[] | undefined): void {
    if (error !== null) {
      report(`sdk: could not re-list ${kind}: ${error.message}`);
      return;
    }
    traffic.mark(`notifications/${kind}/list_changed`);
    traffic.relists.push(kind);
    traffic.lists.set(kind, names ?? []);
    say(`<- notifications/${kind}/list_changed (re-listed: ${names?.length ?? 0} ${kind})`);
  }

  if (caps.includes("roots")) {
    client.setRequestHandler("roots/list", () => {
      traffic.mark("roots/list");
      return rootsResult(roots);
    });
  }
  if (caps.includes("sampling")) {
    client.setRequestHandler("sampling/createMessage", () => {
      traffic.mark("sampling/createMessage");
      return samplingResult();
    });
  }
  if (caps.includes("elicitation") || caps.includes("elicitation-url")) {
    client.setRequestHandler("elicitation/create", (request) => {
      traffic.mark("elicitation/create");
      return elicitationResult(request.params as ElicitParams);
    });
  }

  client.setNotificationHandler("notifications/message", (note) => {
    traffic.mark("notifications/message");
    const p = note.params;
    say(`<- notifications/message level=${p.level} logger=${p.logger ?? "-"} ${compact(p.data)}`);
  });
  client.setNotificationHandler("notifications/resources/updated", async (note) => {
    traffic.mark("notifications/resources/updated");
    say(`<- notifications/resources/updated ${compact(note.params)}`);
    await traffic.working(async () => {
      try {
        await client.readResource({ uri: note.params.uri });
        traffic.rereads.push(note.params.uri);
      } catch (error) {
        report(`sdk: could not re-read ${note.params.uri}: ${(error as Error).message}`);
      }
    });
  });

  let http: StreamableHTTPClientTransport | undefined;
  return {
    client,
    traffic,
    roots,
    errors,
    transport: (command) => {
      if (url === undefined) return new StdioClientTransport({ command: command[0] as string, args: command.slice(1) });
      http = new StreamableHTTPClientTransport(new URL(url));
      return http;
    },
    close: async () => {
      if (http?.sessionId !== undefined) await http.terminateSession();
      await client.close();
    },
  };
}
