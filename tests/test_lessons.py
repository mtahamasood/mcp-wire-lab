"""C12: the lesson gate checks sections, exit codes, and the expected output text."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_failing_command_that_is_not_last_fails_the_block(self) -> None:
        # R7: without -e, only the last command's status counted.
        _, errors = self.run_on(lesson(block("$ false\n$ echo ok", "ok")))
        self.assertEqual(len(errors), 1)
        self.assertIn("exited 1", errors[0])

    def test_failing_pipeline_stage_fails_the_block(self) -> None:
        _, errors = self.run_on(lesson(block("$ cat no-such-file-here | wc -l")))
        self.assertEqual(len(errors), 1)
        self.assertIn("exited", errors[0])

    def test_sections_in_reverse_order_fail(self) -> None:
        reverse = "\n".join(f"## {s}\n\ntext\n" for s in reversed(check_lessons.SECTIONS))
        _, errors = self.run_on(lesson(sections=reverse))
        self.assertTrue(errors)
        self.assertTrue(any("order" in e for e in errors))

    def test_headings_inside_a_fence_do_not_count(self) -> None:
        fenced = "```markdown\n" + SECTIONS + "```\n"
        _, errors = self.run_on(lesson(sections=fenced))
        self.assertEqual(len(errors), len(check_lessons.SECTIONS))
        self.assertTrue(all("missing section" in e for e in errors))

    def run_main(self, root: Path, *args: str) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = check_lessons.main(["check_lessons.py", *args, str(root)])
        return code, err.getvalue()

    def test_main_on_empty_root_fails_by_default(self) -> None:
        # T19: the default is --min-lessons 1; deleting docs/lessons must not turn G9 green.
        with tempfile.TemporaryDirectory() as tmp:
            code, err = self.run_main(Path(tmp))
            self.assertEqual(code, 1)
            self.assertIn("need 1", err)
            self.assertEqual(self.run_main(Path(tmp), "--min-lessons", "0")[0], 0)

    def test_main_reports_a_timed_out_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs/lessons").mkdir(parents=True)
            (root / "docs/lessons/01-x.md").write_text(lesson(block("$ sleep 5")), encoding="utf-8")
            with mock.patch.object(check_lessons, "TIMEOUT_S", 0.2):
                code, err = self.run_main(root)
        self.assertEqual(code, 1)
        self.assertIn("timed out", err)


if __name__ == "__main__":
    unittest.main()
