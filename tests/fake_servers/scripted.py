"""A scripted MCP-shaped server for the client tests: answers a few made-up methods.

Reads newline-delimited JSON from stdin, writes the same to stdout, and records every line it
receives to LOG (one per line) so a test can check exactly what the client sent. Methods:

  initialize   replies with --version (default 2025-11-25), no capabilities
  ping         replies {}
  echo         replies with the params it was sent
  boom         replies with error -32000 and data {"x": 1}
  hang         never replies (--late: replies after it sees notifications/cancelled for it)
  overlap      sends a request with id 0 first (method roots/list), replies when the client
               has answered it, with the client's answer as the result

--ignore-eof makes it keep running after stdin closes, --ignore-term makes it ignore SIGTERM.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from typing import Any


def send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log")
    parser.add_argument("--version", default="2025-11-25")
    parser.add_argument("--late", action="store_true")
    parser.add_argument("--ignore-eof", action="store_true")
    parser.add_argument("--ignore-term", action="store_true")
    args = parser.parse_args()
    if args.ignore_term:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    hung: dict[Any, bool] = {}
    asked_overlap: Any = None
    with open(args.log, "w", encoding="utf-8") as log:
        for line in sys.stdin:
            log.write(line)
            log.flush()
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            method, msg_id = msg.get("method"), msg.get("id")
            if method is None and msg_id == 0 and asked_overlap is not None:
                send({"jsonrpc": "2.0", "id": asked_overlap, "result": msg})
            elif method == "initialize":
                send({"jsonrpc": "2.0", "id": msg_id, "result": {
                    "protocolVersion": args.version, "capabilities": {},
                    "serverInfo": {"name": "scripted", "version": "0"}}})
            elif method == "ping":
                send({"jsonrpc": "2.0", "id": msg_id, "result": {}})
            elif method == "echo":
                send({"jsonrpc": "2.0", "id": msg_id, "result": msg.get("params", {})})
            elif method == "boom":
                send({"jsonrpc": "2.0", "id": msg_id, "error": {
                    "code": -32000, "message": "boom", "data": {"x": 1}}})
            elif method == "hang":
                hung[msg_id] = True
            elif method == "overlap":
                asked_overlap = msg_id
                send({"jsonrpc": "2.0", "id": 0, "method": "roots/list"})
            elif method == "notifications/cancelled" and args.late:
                late_id = msg["params"]["requestId"]
                if hung.pop(late_id, False):
                    send({"jsonrpc": "2.0", "id": late_id, "result": {"late": True}})
    if args.ignore_eof:
        time.sleep(60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
