"""Phase 7 D6, C9: `tap.show` summarises the HTTP layer of a trace and leaves the rest alone."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tap import show

ROOT = Path(__file__).resolve().parent.parent
INIT = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}
REPLY = {"jsonrpc": "2.0", "id": 0, "result": {}}


def record(seq: int, direction: str, **fields: Any) -> dict[str, Any]:
    return {"seq": seq, "t_ns": seq * 1_000_000, "dir": direction, **fields}


def frame(seq: int, direction: str, message: Any, http: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(message)
    return record(seq, direction, bytes=len(raw), raw=raw, json=message, http=http)


TRACE = [
    record(0, "tap", event="spawn", argv=["node", "server.js", "streamableHttp"]),
    record(1, "tap", event="listen", listen="127.0.0.1:1", upstream="unix:/tmp/x/server.sock"),
    record(2, "tap", event="http-request", http={
        "exchange": 0, "method": "POST", "path": "/mcp", "body_bytes": 40,
        "headers": {"accept": "application/json, text/event-stream",
                    "content-type": "application/json"}}),
    frame(3, "c2s", INIT, {"exchange": 0}),
    record(4, "tap", event="http-response", http={
        "exchange": 0, "status": 200,
        "headers": {"content-type": "text/event-stream", "mcp-session-id": "abc\x1b[31m"}}),
    record(5, "tap", event="sse-event", http={"exchange": 0, "id": "p1"}),
    frame(6, "s2c", REPLY, {"exchange": 0, "sse": {"id": "e1", "event": "message"}}),
    record(7, "tap", event="http-end", http={"exchange": 0, "by": "server", "comments": 2}),
    record(8, "tap", event="http-response", http={
        "exchange": 1, "status": 502, "headers": {}, "by": "tap"}),
    record(9, "tap", event="exit", code=0),
]


def write(records: list[dict[str, Any]]) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    handle.write("\n".join(json.dumps(r) for r in records) + "\n")
    handle.close()
    return Path(handle.name)


class ShowHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = write(TRACE)
        self.addCleanup(self.path.unlink)
        self.lines = [show.line_for(i) for i in show.annotate(show.load(self.path))]

    def test_http_records_are_summarised(self) -> None:
        text = "\n".join(self.lines)
        self.assertIn("tap http-request #0 POST /mcp accept=application/json, text/event-stream "
                      "content-type=application/json", text)
        self.assertIn("tap http-response #0 200 content-type=text/event-stream "
                      "mcp-session-id=abc\\x1b[31m", text)  # control characters are escaped
        self.assertNotIn("\x1b", text)
        self.assertIn("tap sse-event #0 id=p1", text)
        self.assertIn("tap http-end #0 by server comments=2", text)
        self.assertIn("tap http-response #1 502 by tap", text)

    def test_frames_show_their_exchange(self) -> None:
        self.assertTrue(self.lines[3].endswith("request initialize id=0 #0"), self.lines[3])
        self.assertTrue(self.lines[6].endswith("#0"), self.lines[6])
        self.assertIn("(answers seq 3", self.lines[6])

    def test_anchors_and_other_views_unchanged(self) -> None:
        anchors = [i["anchor"] for i in show.annotate(show.load(self.path))]
        self.assertEqual(anchors, [
            "tap.spawn.0", "tap.listen.0", "tap.http-request.0", "c2s.initialize.0",
            "tap.http-response.0", "tap.sse-event.0", "s2c.response.0", "tap.http-end.0",
            "tap.http-response.1", "tap.exit.0"])
        for flags in ([], ["--full"], ["--mermaid"]):
            done = subprocess.run([sys.executable, "-m", "tap.show", str(self.path), *flags],
                                  cwd=ROOT, capture_output=True, text=True, timeout=20)
            self.assertEqual(done.returncode, 0, done.stderr)
        mermaid = show.mermaid(show.annotate(show.load(self.path)))
        self.assertIn("Client->>Server: initialize id=0", mermaid)
        self.assertIn("Server-->>Client: response id=0", mermaid)
        notes = {a: "note" for a in anchors}
        lines, ok = show.explain(show.annotate(show.load(self.path)), notes)
        self.assertTrue(ok)
        self.assertEqual(len(lines), 2 * len(anchors))


if __name__ == "__main__":
    unittest.main()
