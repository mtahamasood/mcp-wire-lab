"""A scripted 2026-07-28 server for the client tests (phase 6): made-up methods, no real tools.

Reads newline-delimited JSON from stdin, writes the same to stdout, and records every line it
receives to LOG so a test can check exactly what the client sent. Methods:

  server/discover  replies with --versions (default 2026-07-28), or the error --discover-error
  echo             a `complete` result holding the params it was sent
  legacy           a result with no `resultType`
  weird            a result whose `resultType` is `bogus`
  task             a result whose `resultType` is `task`
  mrtr             `input_required` (inputRequests a, b; a requestState of awkward bytes) until a
                   request carries `inputResponses`, then `complete` echoing the params
  forever          always `input_required`
  unanswerable     `input_required` with an input request no client can answer
  subscriptions/listen
                   acknowledges with `_meta` subscriptionId = the request's id; with the filter
                   {"hold": true} it first sends an acknowledgment under the id as a string (wrong
                   type) and waits for `release` before the real one
  release          sends the held acknowledgments, replies `complete`
  emit             params {"sub": <any>}: sends `notifications/tools/list_changed` tagged with that
                   subscription id, and an untagged `notifications/message`, replies `complete`

On notifications/cancelled, --late replies to the cancelled request (a late listen response).
Any other method gets -32601.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

SUB = "io.modelcontextprotocol/subscriptionId"


def send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def result(msg_id: Any, body: dict[str, Any] | None = None, kind: str | None = "complete") -> None:
    out: dict[str, Any] = {} if kind is None else {"resultType": kind}
    out.update(body or {})
    send({"jsonrpc": "2.0", "id": msg_id, "result": out})


def ack(listen_id: Any, notes: Any) -> None:
    send({"jsonrpc": "2.0", "method": "notifications/subscriptions/acknowledged",
          "params": {"notifications": notes, "_meta": {SUB: listen_id}}})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log")
    parser.add_argument("--versions", default="2026-07-28")
    parser.add_argument("--discover-error", type=int, default=None)
    parser.add_argument("--late", action="store_true")
    args = parser.parse_args()
    held: list[tuple[Any, Any]] = []
    listening: set[Any] = set()
    with open(args.log, "w", encoding="utf-8") as log:
        for line in sys.stdin:
            log.write(line)
            log.flush()
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            method, msg_id = msg.get("method"), msg.get("id")
            params = msg.get("params") or {}
            if method == "server/discover":
                if args.discover_error is not None:
                    send({"jsonrpc": "2.0", "id": msg_id, "error": {
                        "code": args.discover_error, "message": "no",
                        "data": {"supported": ["2025-11-25"]}}})
                else:
                    result(msg_id, {"supportedVersions": args.versions.split(","),
                                    "capabilities": {}})
            elif method == "echo":
                result(msg_id, {"params": params})
            elif method == "legacy":
                result(msg_id, {"x": 1}, None)
            elif method == "weird":
                result(msg_id, {}, "bogus")
            elif method == "task":
                result(msg_id, {"taskId": "t1", "status": "working"}, "task")
            elif method == "mrtr":
                if "inputResponses" in params:
                    result(msg_id, {"params": params})
                else:
                    result(msg_id, {
                        "inputRequests": {
                            "a": {"method": "roots/list"},
                            "b": {"method": "sampling/createMessage", "params": {"messages": []}},
                        },
                        "requestState": "sté \"quoted\"  {not json} \\ end",
                    }, "input_required")
            elif method == "forever":
                result(msg_id, {"inputRequests": {"a": {"method": "roots/list"}}},
                       "input_required")
            elif method == "unanswerable":
                result(msg_id, {"inputRequests": {"a": {"method": "nonsense/x"}}},
                       "input_required")
            elif method == "subscriptions/listen":
                listening.add(msg_id)
                notes = params.get("notifications", {})
                if notes.get("hold"):
                    ack(str(msg_id), notes)  # the wrong type: a client must not take it
                    held.append((msg_id, notes))
                else:
                    ack(msg_id, notes)
            elif method == "release":
                for listen_id, notes in held:
                    ack(listen_id, notes)
                held.clear()
                result(msg_id)
            elif method == "emit":
                send({"jsonrpc": "2.0", "method": "notifications/tools/list_changed",
                      "params": {"_meta": {SUB: params.get("sub")}}})
                send({"jsonrpc": "2.0", "method": "notifications/message",
                      "params": {"level": "info", "data": "untagged"}})
                result(msg_id)
            elif method == "notifications/cancelled":
                if args.late and params.get("requestId") in listening:
                    result(params["requestId"])
            elif msg_id is not None and method is not None:
                send({"jsonrpc": "2.0", "id": msg_id,
                      "error": {"code": -32601, "message": f"Method not found: {method}"}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
