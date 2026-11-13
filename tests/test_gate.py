"""Phase 8: the gate's shape. Each Python test module runs in exactly one of G4 and G5."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts/gate.sh"


class GateTest(unittest.TestCase):
    def test_e2e_runs_once(self) -> None:
        done = subprocess.run([str(GATE), "--list"], cwd=ROOT, capture_output=True, text=True,
                              timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        listed = dict(line.split(" ", 1) for line in done.stdout.splitlines())
        unit, e2e = set(listed["G4"].split()), set(listed["G5"].split())
        every = {f"tests.{p.stem}" for p in (ROOT / "tests").glob("test_*.py")}
        self.assertEqual(unit & e2e, set(), "a module runs in both G4 and G5")
        self.assertEqual(unit | e2e, every, "a test module runs in neither gate")
        self.assertEqual(e2e, {m for m in every if m.startswith("tests.test_e2e")})
        self.assertIn("tests.test_gate", unit)
        # The gate runs what --list prints, not its own discovery.
        script = GATE.read_text()
        self.assertNotIn("unittest discover", script)
        self.assertRegex(script, r"gate G4 python3 -m unittest -v \$\(modules unit\)")
        self.assertRegex(script, r"gate G5 python3 -m unittest -v \$\(modules e2e\)")

    def test_ci_uploads_runs_on_failure(self) -> None:
        # Phase 8 D3: a failed CI run keeps each run folder's trace.jsonl and stderr.txt, and
        # nothing else from runs/ (bin/ links point at the runner's interpreters; home/ is the
        # server's). The step is read as text: the gate has no YAML parser.
        workflow = (ROOT / ".github/workflows/ci.yml").read_text().splitlines()
        uses = [i for i, line in enumerate(workflow) if "actions/upload-artifact@" in line]
        self.assertEqual(len(uses), 1, "one upload step")
        start = max(i for i in range(uses[0] + 1) if workflow[i].lstrip().startswith("- "))
        indent = len(workflow[start]) - len(workflow[start].lstrip())
        end = next((i for i in range(start + 1, len(workflow))
                    if workflow[i].strip() and len(workflow[i]) - len(workflow[i].lstrip())
                    <= indent), len(workflow))
        step = [line.strip() for line in workflow[start:end]]
        gate = next(i for i, line in enumerate(workflow)
                    if line.strip() == "- run: scripts/gate.sh")
        self.assertGreater(start, gate, "the upload runs after the gate")
        self.assertIn("if: failure()", step)
        self.assertIn("retention-days: 7", step)
        at = step.index("path: |")
        paths = [line for line in step[at + 1:] if line and ":" not in line]
        self.assertEqual(paths, ["runs/*/trace.jsonl", "runs/*/stderr.txt"])

    def test_usage_states_the_split_and_a_duration(self) -> None:
        done = subprocess.run([str(GATE), "--help"], cwd=ROOT, capture_output=True, text=True,
                              timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("tests/test_e2e*.py", done.stdout)
        self.assertRegex(done.stdout, re.compile(r"takes about \d+ minutes"))


if __name__ == "__main__":
    unittest.main()
