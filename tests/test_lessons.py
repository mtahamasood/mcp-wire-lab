"""C12: the lesson gate checks sections, exit codes, and the expected output text."""

from __future__ import annotations

import contextlib
import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import check_citations, check_lessons

ROOT = Path(__file__).resolve().parent.parent

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

    def test_headings_between_fenced_blocks_count(self) -> None:
        # Each fence is stripped on its own, not everything from the first fence to the last.
        fence = "```console\n$ echo hi\n```\n"
        between = "\n".join(f"{fence}\n## {s}\n\ntext\n" for s in check_lessons.SECTIONS)
        self.assertEqual(self.run_on(lesson(sections=between + fence)), (1, []))

    def test_headings_inside_a_tilde_fence_do_not_count(self) -> None:
        fenced = "~~~markdown\n" + SECTIONS + "~~~\n"
        _, errors = self.run_on(lesson(sections=fenced))
        self.assertEqual(len(errors), len(check_lessons.SECTIONS))

    def test_headings_inside_a_four_backtick_fence_do_not_count(self) -> None:
        fenced = "````markdown\n```\n" + SECTIONS + "````\n"
        _, errors = self.run_on(lesson(sections=fenced))
        self.assertEqual(len(errors), len(check_lessons.SECTIONS))

    def test_tilde_fence_is_not_closed_by_backticks(self) -> None:
        fenced = "~~~markdown\n```\n" + SECTIONS + "~~~\n"
        _, errors = self.run_on(lesson(sections=fenced))
        self.assertEqual(len(errors), len(check_lessons.SECTIONS))

    def test_headings_after_an_unclosed_fence_are_missing(self) -> None:
        _, errors = self.run_on(lesson(sections="```markdown\n" + SECTIONS))
        self.assertEqual(len(errors), len(check_lessons.SECTIONS))

    def test_fence_closes_only_on_a_bare_fence_line(self) -> None:
        # A "```text" line inside a fence has an info string, so it does not close it.
        fenced = "```markdown\n```text\n" + SECTIONS + "```\n"
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


def _section(prose: str, name: str) -> str:
    """The text of the `## <name>` section: up to the next `## ` heading."""
    m = re.search(rf"^##\s+{name}\b.*?$(.*?)(?=^##\s|\Z)", prose, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else ""


SPEC_ID = re.compile(r"\b(?:phase \d+ )?(?:LP|RP|[DCGJLAM])\d+\b")


class LearnerTextTest(unittest.TestCase):
    """D11/D12: what a learner reads on the real lessons, walkthroughs and README."""

    def lessons(self) -> list[Path]:
        found = sorted((ROOT / "docs/lessons").glob("*.md"))
        self.assertGreaterEqual(len(found), 7)
        return found

    def test_every_lesson_has_predict_answers(self) -> None:
        for path in self.lessons():
            text = path.read_text(encoding="utf-8")
            prose = check_lessons._strip_fences(text)
            predict = _section(prose, "Predict")
            questions = re.findall(r"^\d+\.\s", predict, re.MULTILINE)
            self.assertTrue(questions, f"{path.name}: Predict has no numbered questions")
            self.assertRegex(
                predict, r"\*Predict answers\*", f"{path.name}: Predict has no pointer to answers"
            )
            _, sep, answers = text.partition("<summary>Answers</summary>")
            self.assertTrue(sep, f"{path.name}: no Answers block")
            _, sep, predict_answers = answers.partition("The *Predict* answers:")
            self.assertTrue(sep, f"{path.name}: no 'The *Predict* answers:' in the answers")
            given = re.findall(r"^\d+\.\s", predict_answers, re.MULTILINE)
            self.assertEqual(
                len(given), len(questions), f"{path.name}: Predict answers miss a question"
            )

    def test_no_spec_ids_in_learner_text(self) -> None:
        files = self.lessons() + sorted((ROOT / "docs/walkthrough").glob("*.md"))
        for path in files:
            prose = check_lessons._strip_fences(path.read_text(encoding="utf-8"))
            prose = check_citations.CITATION.sub("", prose)
            hits = [m.group(0) for m in SPEC_ID.finditer(prose)]
            self.assertEqual(hits, [], f"{path.name} names spec record ids")

    def test_readme_links_every_lesson_walkthrough_and_atlas(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        targets = [*self.lessons(), *sorted((ROOT / "docs/walkthrough").glob("*.md")),
                   ROOT / "docs/atlas.md"]
        for path in targets:
            rel = path.relative_to(ROOT).as_posix()
            self.assertIn(f"]({rel})", readme, f"README does not link {rel}")
        self.assertIn("G10", readme)
        self.assertIn(".github/ISSUE_TEMPLATE/feedback", readme)
        self.assertTrue((ROOT / ".github/ISSUE_TEMPLATE/feedback.md").is_file())


if __name__ == "__main__":
    unittest.main()
