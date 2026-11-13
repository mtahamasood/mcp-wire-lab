"""tools/mutate.py: one exact replacement per mutant, run in a copy, restored and compared."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MUTATE = ROOT / "tools" / "mutate.py"

CALC = "def add(a, b):\n    return a + b\n"
CHECK = (
    "import unittest\n"
    "from calc import add\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_add(self):\n"
    "        self.assertEqual(add(2, 3), 5)\n"
)
LOOSE = (
    "import unittest\n"
    "from calc import add\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_add(self):\n"
    "        self.assertTrue(add(2, 3) is not None)\n"
)
CMD = f"{sys.executable} -m unittest test_calc"
LOOSE_CMD = f"{sys.executable} -m unittest test_loose"


class MutateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.proj = Path(self._tmp.name) / "proj"
        self.proj.mkdir()
        (self.proj / "calc.py").write_text(CALC)
        (self.proj / "test_calc.py").write_text(CHECK)
        (self.proj / "test_loose.py").write_text(LOOSE)

    def mutant(
        self, id: str, old: str = "a + b", new: str = "a - b", **extra: Any
    ) -> dict[str, Any]:
        return {"id": id, "file": "calc.py", "old": old, "new": new, "command": CMD, **extra}

    def run_tool(
        self, mutants: list[dict[str, Any]], *args: str
    ) -> subprocess.CompletedProcess[str]:
        spec = Path(self._tmp.name) / "spec.json"
        spec.write_text(json.dumps({"mutants": mutants}))
        return subprocess.run(
            [sys.executable, str(MUTATE), "--root", str(self.proj), *args, str(spec)],
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_applies_one_exact_replacement(self) -> None:
        # The replacement reaches the test: the exact-assert test kills it.
        done = self.run_tool([self.mutant("M1")])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("mutants: 1 killed: 1 survived: 0 errors: 0", done.stdout)
        # A replacement that changes nothing observable survives: only the one place is edited.
        same = self.mutant("M2", old="return a + b", new="return a + b  # same")
        done = self.run_tool([same])
        self.assertIn("mutants: 1 killed: 0 survived: 1 errors: 0", done.stdout)

    def test_missing_or_ambiguous_text_is_an_error(self) -> None:
        (self.proj / "calc.py").write_text(CALC + "# a + b\n")
        done = self.run_tool([self.mutant("AMB"), self.mutant("GONE", old="not there", new="x")])
        self.assertEqual(done.returncode, 1)
        self.assertIn("mutants: 2 killed: 0 survived: 0 errors: 2", done.stdout)
        self.assertRegex(done.stdout, r"\| AMB \| calc.py \| error \|")
        self.assertRegex(done.stdout, r"\| GONE \| calc.py \| error \|")

    def test_restores_original_and_checks_with_cmp(self) -> None:
        before = (self.proj / "calc.py").read_bytes()
        done = self.run_tool([self.mutant("M1")])
        self.assertEqual((self.proj / "calc.py").read_bytes(), before)
        self.assertIn("restored byte-identical", done.stderr)
        self.assertNotIn("NOT restored", done.stdout + done.stderr)

    def test_refuses_when_runs_dir_has_leftovers(self) -> None:
        (self.proj / "runs").mkdir()
        (self.proj / "runs" / "old-run").mkdir()
        done = self.run_tool([self.mutant("M1")])
        self.assertEqual(done.returncode, 2)
        self.assertIn("runs/", done.stderr)
        self.assertNotIn("| M1 |", done.stdout)

    def test_reports_killed_and_survived(self) -> None:
        loose = self.mutant("LOOSE", command=LOOSE_CMD, note="weak assertion")
        done = self.run_tool([self.mutant("STRONG"), loose])
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("mutants: 2 killed: 1 survived: 1 errors: 0", done.stdout)
        self.assertIn("weak assertion", done.stdout)
        self.assertRegex(done.stdout, r"\| STRONG \| calc.py \| killed \|")
        self.assertRegex(done.stdout, r"\| LOOSE \| calc.py \| survived \|")

    def test_baseline_red_stops_with_2(self) -> None:
        (self.proj / "calc.py").write_text("def add(a, b):\n    return 0\n")
        done = self.run_tool([self.mutant("M1", old="return 0", new="return 1")])
        self.assertEqual(done.returncode, 2)
        self.assertIn("baseline", done.stderr)

    def test_timeout_is_reported_separately(self) -> None:
        (self.proj / "test_slow.py").write_text(
            "import time, unittest\n"
            "from calc import add\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_slow(self):\n"
            "        if add(1, 1) != 2:\n"
            "            time.sleep(30)\n"
        )
        slow = self.mutant("SLOW", command=f"{sys.executable} -m unittest test_slow", timeout=1)
        done = self.run_tool([slow])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(done.stdout, r"\| SLOW \| calc.py \| killed \(timeout\) \|")
        self.assertIn("mutants: 1 killed: 1 survived: 0 errors: 0", done.stdout)

    def test_marked_equivalent_does_not_fail_the_run(self) -> None:
        same = self.mutant(
            "EQ", old="return a + b", new="return a + b  # same", equivalent="comment only"
        )
        done = self.run_tool([self.mutant("STRONG"), same])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(done.stdout, r"\| EQ \| calc.py \| equivalent \|.*comment only")
        self.assertIn("mutants: 2 killed: 1 survived: 0 errors: 0 equivalent: 1", done.stdout)
        # An equivalent mark needs a reason; an empty one is a bad spec.
        bad = self.mutant("EQ2", equivalent="")
        self.assertEqual(self.run_tool([bad]).returncode, 2)

    def test_killed_row_names_failing_tests(self) -> None:
        done = self.run_tool([self.mutant("M1")])
        self.assertIn("test_add", done.stdout)

    def test_only_selects_mutants(self) -> None:
        done = self.run_tool([self.mutant("A"), self.mutant("B")], "--only", "B")
        self.assertIn("mutants: 1 ", done.stdout)
        self.assertNotIn("| A |", done.stdout)

    def test_help_prints_usage(self) -> None:
        done = subprocess.run(
            [sys.executable, str(MUTATE), "-h"], capture_output=True, text=True, timeout=20
        )
        self.assertEqual(done.returncode, 0)
        self.assertIn("Usage:", done.stdout)


if __name__ == "__main__":
    unittest.main()
