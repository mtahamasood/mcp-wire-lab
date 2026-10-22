"""C7: manual mode sends what is typed, builds :req and :note, and shuts down on :quit and EOF."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from client import manual

ROOT = Path(__file__).resolve().parent.parent
FAKE = str(ROOT / "tests/fake_servers/scripted.py")
MODERN_FAKE = str(ROOT / "tests/fake_servers/modern.py")


def run(lines: list[str]) -> tuple[list[str], list[str], bool]:
    """Run manual mode on the scripted server: what it received, what was printed, EOF seen."""
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "received.log"
        manual.run_manual([sys.executable, FAKE, str(log)], lines, out, settle=3.0,
                          report=lambda _text: None)
        # run_manual returns after the server has exited, so the marker is already written
        return (log.read_text().splitlines(), out.getvalue().splitlines(),
                Path(str(log) + ".eof").exists())


class ManualTest(unittest.TestCase):
    def test_typed_line_sent_verbatim(self) -> None:
        typed = '{"id":7,  "method":"echo","params":{"a":1} }'  # no jsonrpc, odd spacing
        broken = '{"jsonrpc":"2.0","id":8,"method":"echo"'  # not valid JSON, still sent
        received, printed, _ = run([typed, broken])
        self.assertEqual(received[2:], [typed, broken])
        self.assertIn(f"-> {typed}", printed)
        self.assertIn('<- {"jsonrpc":"2.0","id":7,"result":{"a":1}}', printed)

    def test_req_and_note_commands(self) -> None:
        received, printed, _ = run([
            ':req echo {"b":2}', ":req ping", ':note notifications/custom {"c":3}', ""])
        sent = [json.loads(ln) for ln in received[2:]]  # after initialize and initialized
        self.assertEqual(sent, [
            {"jsonrpc": "2.0", "id": 1, "method": "echo", "params": {"b": 2}},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            {"jsonrpc": "2.0", "method": "notifications/custom", "params": {"c": 3}},
        ])
        self.assertIn('<- {"jsonrpc":"2.0","id":1,"result":{"b":2}}', printed)
        self.assertIn('<- {"jsonrpc":"2.0","id":2,"result":{}}', printed)

    def test_quit_and_eof_shut_down(self) -> None:
        received, _, eof = run([":req ping", ":quit", ":req echo"])
        self.assertTrue(eof, "stdin was closed")
        self.assertEqual([json.loads(ln).get("method") for ln in received],
                         ["initialize", "notifications/initialized", "ping"])
        received, _, eof = run([":req ping"])  # end of input, no :quit
        self.assertTrue(eof, "stdin was closed at end of input")
        self.assertEqual(len(received), 3)

    def test_bad_lines_are_reported_not_sent(self) -> None:
        received, printed, _ = run(["hello", ":req echo {not json}"])
        self.assertEqual(len(received), 2, "only initialize and initialized were sent")
        self.assertTrue(any(ln.startswith("manual: not a command") for ln in printed))
        self.assertTrue(
            any(ln.startswith("manual: the params are not valid JSON") for ln in printed))


def run_modern(lines: list[str], caps: tuple[str, ...] = ()) -> tuple[list[str], list[str]]:
    """Manual mode in the 2026 era on the modern fake server: what it received, what was printed."""
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "received.log"
        manual.run_manual([sys.executable, MODERN_FAKE, str(log)], lines, out, settle=3.0,
                          report=lambda _text: None, caps=caps, era="2026-07-28")
        return log.read_text().splitlines(), out.getvalue().splitlines()


class ModernManualTest(unittest.TestCase):
    def test_typed_line_in_2026_era_sent_verbatim(self) -> None:
        typed = '{"id":7,  "method":"echo","params":{"a":1} }'  # no jsonrpc, no envelope
        received, printed = run_modern([typed])
        self.assertEqual(json.loads(received[0])["method"], "server/discover", "discovers first")
        self.assertEqual(received[1:], [typed])
        self.assertIn(f"-> {typed}", printed)
        self.assertTrue(any(ln.startswith("<- ") and '"id":7' in ln for ln in printed), printed)

    def test_req_in_2026_era_carries_envelope(self) -> None:
        received, printed = run_modern(
            [':req echo {"b":2}', ":req echo", ':note notifications/custom {"c":3}'],
            caps=("roots",))
        sent = [json.loads(ln) for ln in received]
        self.assertEqual([m.get("method") for m in sent],
                         ["server/discover", "echo", "echo", "notifications/custom"])
        meta = sent[1]["params"]["_meta"]
        self.assertEqual(meta["io.modelcontextprotocol/protocolVersion"], "2026-07-28")
        self.assertEqual(meta["io.modelcontextprotocol/clientCapabilities"],
                         {"roots": {"listChanged": True}})
        self.assertEqual(sent[1]["params"]["b"], 2)
        self.assertIn("_meta", sent[2]["params"], "a bare :req still gets the envelope")
        self.assertEqual(sent[3], {"jsonrpc": "2.0", "method": "notifications/custom",
                                   "params": {"c": 3}}, "a notification is sent as typed")
        self.assertTrue(any(ln.startswith("<- ") and '"resultType":"complete"' in ln
                            for ln in printed))


if __name__ == "__main__":
    unittest.main()
