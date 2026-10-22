// Knowing when the Streamable HTTP GET stream is open (phase 7 fix). The server drops what it sends
// unprompted while no GET stream exists, so a client cannot trust that it heard every list change
// sent before then; once the stream is open it re-lists. The SDK transport exposes no "stream
// opened" event, but it takes a `fetch` (a public option), and the server registers the stream
// before it answers the GET, so a GET answered `2xx` with `text/event-stream` means the stream is
// open. No SDK import, so `node --test` can check it alone.

export type Fetch = (url: string | URL, init?: RequestInit) => Promise<Response>;

/** True for the answer that opens a standalone stream: a GET answered 2xx with an event stream. */
export function opensStream(init: RequestInit | undefined, response: Response): boolean {
  const type = (response.headers.get("content-type") ?? "").split(";")[0]?.trim().toLowerCase();
  return (init?.method ?? "GET").toUpperCase() === "GET" && response.ok && type === "text/event-stream";
}

/** `base`, calling `onOpen` each time it answers a GET that opens the stream (a reconnect too). */
export function watchStream(base: Fetch, onOpen: () => void): Fetch {
  return async (url, init) => {
    const response = await base(url, init);
    if (opensStream(init, response)) onOpen();
    return response;
  };
}
