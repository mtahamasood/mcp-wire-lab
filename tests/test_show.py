"""C9, C13, C14: the viewer correlates by id, draws the flow, and checks explanation coverage."""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests/fixtures"
TRACE = FIXTURES / "out-of-order.jsonl"


def show(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tap.show", *map(str, args)],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )


class CorrelationTest(unittest.TestCase):
    def test_c9_responses_pair_by_id_not_adjacency(self) -> None:
        done = show(TRACE)
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        by_seq = {int(ln.split()[0]): ln for ln in lines if ln.split()[0].isdigit()}
        # ping (id 2, seq 2, t=2 ms) is answered first at seq 6 (t=5 ms): 3.0 ms.
        self.assertIn("response id=2 (answers seq 2, 3.0 ms)", by_seq[6])
        # tools/list (id 1, seq 1, t=1 ms) is answered last at seq 7 (t=9 ms): 8.0 ms.
        self.assertIn("id=1", by_seq[7])
        self.assertIn("(answers seq 1, 8.0 ms)", by_seq[7])
        self.assertIn("error", by_seq[7])
        self.assertNotIn("response", by_seq[7])
        self.assertNotIn("answers", by_seq[3])  # the notification pairs with nothing
        self.assertNotIn("answers", by_seq[1])

    def test_c9_full_prints_bodies(self) -> None:
        self.assertIn('"code": -32603', show(TRACE, "--full").stdout)


class MermaidTest(unittest.TestCase):
    def test_c13_diagram_shape_and_seq_order(self) -> None:
        done = show(TRACE, "--mermaid")
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(lines[0], "sequenceDiagram")
        self.assertIn("    participant Client", lines)
        self.assertIn("    participant Server", lines)
        arrows = [ln.strip() for ln in lines if re.search(r"-{1,2}>>", ln)]
        self.assertEqual(
            [re.sub(r":.*", "", a) for a in arrows],
            [
                "Client->>Server",  # tools/list, seq 1
                "Client->>Server",  # ping, seq 2
                "Server->>Client",  # notification, seq 3
                "Client->>Server",  # cancelled, seq 4: after a server record, so order matters
                "Server-->>Client",  # response id 2, seq 6
                "Server-->>Client",  # error id 1, seq 7
            ],
        )
        labels = [a.split(": ", 1)[1] for a in arrows]
        self.assertEqual(labels[0], "tools/list id=1")
        self.assertEqual(labels[1], "ping id=2")
        self.assertEqual(labels[2], "notifications/message")
        self.assertEqual(labels[3], "notifications/cancelled")
        self.assertEqual(labels[4], "response id=2")
        self.assertEqual(labels[5], "error id=1")
        self.assertTrue(any(ln.strip() == "Note over Server: stderr: boot" for ln in lines))


class ExplainTest(unittest.TestCase):
    def test_c14_complete_walkthrough_exits_zero(self) -> None:
        done = show(TRACE, "--explain", FIXTURES / "walkthrough-complete.md")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertNotIn("(no note)", done.stdout)
        self.assertNotIn("(no frame)", done.stdout)
        # a note follows its frame
        lines = done.stdout.splitlines()
        i = next(n for n, ln in enumerate(lines) if "request ping id=2" in ln)
        self.assertEqual(lines[i + 1].strip(), "Client pings.")

    def test_c14_missing_note_is_reported(self) -> None:
        done = show(TRACE, "--explain", FIXTURES / "walkthrough-missing-note.md")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(done.stdout.count("(no note)"), 1)
        self.assertIn("[s2c.response.1]", done.stdout)
        self.assertNotIn("(no frame)", done.stdout)

    def test_c14_extra_note_is_reported(self) -> None:
        done = show(TRACE, "--explain", FIXTURES / "walkthrough-extra-note.md")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("(no frame)  [c2s.initialize.9]", done.stdout)
        self.assertNotIn("(no note)", done.stdout)

    def test_usage_errors(self) -> None:
        self.assertEqual(show().returncode, 2)
        self.assertEqual(show(TRACE, "--explain").returncode, 2)


if __name__ == "__main__":
    unittest.main()
