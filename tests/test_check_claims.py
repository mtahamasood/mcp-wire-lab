"""C10: G12 fails on a C row that names nothing, a missing file, class or method; passes phase 2."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import check_claims

ROOT = Path(__file__).resolve().parent.parent

HEADER = "| Row | Claim | Checks | Mutation |\n| --- | --- | --- | --- |\n"
TEST_FILE = (
    "import unittest\n\n\nclass FooTest(unittest.TestCase):\n"
    "    def test_bar(self) -> None:\n        pass\n"
)
OK = "`tests/test_foo.py::FooTest::test_bar`"


def validation(*rows: str) -> str:
    body = "".join(f"| C{n} | a claim | {checks} | yes |\n" for n, checks in enumerate(rows, 1))
    return f"# Phase\n\n## C. Phase-specific correctness\n\n{HEADER}{body}\n## E. Other\n\n| x |\n"


def make_repo(root: Path, text: str, phase: str = "02-demo", tests: str = TEST_FILE) -> None:
    (root / "specs/phases" / phase).mkdir(parents=True)
    (root / "specs/phases" / phase / "validation.md").write_text(text, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests/test_foo.py").write_text(tests, encoding="utf-8")
    (root / "tools").mkdir()
    (root / "tools/thing.py").write_text("", encoding="utf-8")


class ClaimsTest(unittest.TestCase):
    def run_on(self, text: str, phase: str = "02-demo", tests: str = TEST_FILE) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(Path(tmp), text, phase, tests)
            return check_claims.check(Path(tmp))

    def test_row_naming_nothing_fails(self) -> None:
        errors = self.run_on(validation("see the walkthrough", OK))
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("02-demo C1", errors[0])
        self.assertIn("names no check", errors[0])

    def test_missing_targets_fail(self) -> None:
        errors = self.run_on(validation(
            f"{OK}, `tools/thing.py`",
            "`tests/test_nope.py::FooTest::test_bar`",
            "`tests/test_foo.py::NoSuchTest::test_bar`",
            "`tests/test_foo.py::FooTest::test_nope`",
            "`tools/missing.py`",
        ))
        self.assertEqual(len(errors), 4, errors)
        for row, word in (("C2", "file"), ("C3", "class"), ("C4", "method"), ("C5", "file")):
            hits = [e for e in errors if f"02-demo {row}:" in e]
            self.assertEqual(len(hits), 1, (row, errors))
            self.assertIn(word, hits[0])
        self.assertFalse([e for e in errors if "C1:" in e])

    def test_method_must_be_in_the_named_class(self) -> None:
        other = (
            TEST_FILE + "\n\nclass OtherTest(unittest.TestCase):\n"
            "    def test_baz(self) -> None:\n        pass\n"
        )
        errors = self.run_on(validation("`tests/test_foo.py::FooTest::test_baz`"), tests=other)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("method", errors[0])

    def test_phase_one_is_skipped_and_a_table_is_required(self) -> None:
        self.assertEqual(self.run_on(validation("nothing"), phase="01-old"), [])
        self.assertEqual(len(self.run_on("# Phase\n\nno table\n")), 1)

    def test_pipe_in_claim_cell_does_not_shift_columns(self) -> None:
        gone = "`tests/test_gone.py::GoneTest::test_gone`"
        for claim in ('"1" differ, in `a | b`', r"a \| b"):
            text = (
                f"# Phase\n\n## C. Phase-specific correctness\n\n{HEADER}"
                f"| C1 | {claim} | {gone} | yes |\n"
            )
            errors = self.run_on(text)
            self.assertEqual(len(errors), 1, (claim, errors))
            self.assertIn("file does not exist", errors[0])
        head = f"# Phase\n\n## C. Phase-specific correctness\n\n{HEADER}"
        self.assertEqual(self.run_on(f"{head}| C1 | `a | b` | {OK} | yes |\n"), [])

    def test_bad_root_argument_exits_2(self) -> None:
        # A31: a root that is not a directory holding specs/ is a usage error, not "claims: ok".
        with tempfile.TemporaryDirectory() as tmp:
            for bad in (str(Path(tmp) / "no-such-dir"), tmp):  # missing; an empty directory
                proc = subprocess.run(
                    [sys.executable, str(ROOT / "tools/check_claims.py"), bad],
                    capture_output=True, text=True, check=False)
                self.assertEqual(proc.returncode, 2, (bad, proc.stdout, proc.stderr))
                self.assertIn("specs/", proc.stderr)
                self.assertNotIn("claims: ok", proc.stdout)

    def test_repository_passes(self) -> None:
        self.assertEqual(check_claims.check(ROOT, phases=["02"]), [])


if __name__ == "__main__":
    unittest.main()
