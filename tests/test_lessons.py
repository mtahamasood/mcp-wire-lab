"""C12: the lesson gate checks sections, exit codes, and the expected output text."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import check_lessons

SECTIONS = "\n".join(f"## {s}\n\ntext\n" for s in check_lessons.SECTIONS)


def lesson(body: str = "", sections: str = SECTIONS) -> str:
    return f"# Lesson\n\n{sections}\n{body}\n"


def block(cmd: str, expect: str | None = None) -> str:
    out = f"<!-- run -->\n```console\n{cmd}\n```\n"
    if expect is not None:
        out += f"<!-- expect -->\n```text\n{expect}\n```\n"
    return out


class LessonsTest(unittest.TestCase):
    def run_on(self, text: str, min_lessons: int = 1) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs/lessons").mkdir(parents=True)
            (root / "docs/lessons/01-x.md").write_text(text, encoding="utf-8")
            return check_lessons.check(root, min_lessons)

    def test_good_lesson_passes(self) -> None:
        count, errors = self.run_on(lesson(block("$ echo hello", "hello")))
        self.assertEqual((count, errors), (1, []))

    def test_missing_predict_fails(self) -> None:
        sections = SECTIONS.replace("## Predict", "## Guess")
        _, errors = self.run_on(lesson(sections=sections))
        self.assertEqual(len(errors), 1)
        self.assertIn("missing section 'Predict'", errors[0])

    def test_failing_block_fails(self) -> None:
        _, errors = self.run_on(lesson(block("exit 1")))
        self.assertEqual(len(errors), 1)
        self.assertIn("exited 1", errors[0])

    def test_success_with_wrong_text_fails(self) -> None:
        # Exit code 0, so an exit-code-only gate would pass this.
        _, errors = self.run_on(lesson(block("echo hello", "goodbye")))
        self.assertEqual(len(errors), 1)
        self.assertIn("expected output not found", errors[0])

    def test_expected_text_may_be_in_stderr_and_a_fragment(self) -> None:
        _, errors = self.run_on(lesson(block("echo 'a b c' >&2; echo d", "b c")))
        self.assertEqual(errors, [])

    def test_unmarked_block_is_not_run(self) -> None:
        _, errors = self.run_on(lesson("```console\nexit 1\n```\n"))
        self.assertEqual(errors, [])

    def test_no_lessons_fails_when_some_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            count, errors = check_lessons.check(Path(tmp), 1)
        self.assertEqual(count, 0)
        self.assertIn("need 1", errors[0])

    def test_no_lessons_passes_when_none_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(check_lessons.check(Path(tmp), 0), (0, []))


if __name__ == "__main__":
    unittest.main()
