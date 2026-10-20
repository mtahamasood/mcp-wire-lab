"""C8: the provenance linter passes the real specs and fails on each broken record."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import check_provenance

ROOT = Path(__file__).resolve().parent.parent

MISSION = """# Mission

| ID | Date | Ask |
| --- | --- | --- |
| A1 | 2026-10-20 | first |

| Date | Decision | Why |
| --- | --- | --- |
| 2026-10-20 | something | A1 |
"""

GOOD = """### D1 — A thing

Text.

*Source:* stakeholder ask A1, 2026-10-20.
"""


def make_tree(root: Path, requirements: str, validation: str | None = None) -> None:
    phase = root / "specs" / "phases" / "01-test"
    phase.mkdir(parents=True)
    (root / "specs" / "mission.md").write_text(MISSION, encoding="utf-8")
    (phase / "requirements.md").write_text(requirements, encoding="utf-8")
    if validation is not None:
        (phase / "validation.md").write_text(validation, encoding="utf-8")


class ProvenanceTest(unittest.TestCase):
    def run_on(self, requirements: str, validation: str | None = None) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            make_tree(Path(tmp), requirements, validation)
            return check_provenance.check(Path(tmp))

    def test_real_specs_pass(self) -> None:
        self.assertEqual(check_provenance.check(ROOT), [])

    def test_good_record_passes(self) -> None:
        self.assertEqual(self.run_on(GOOD), [])

    def test_missing_source_fails_naming_record(self) -> None:
        errors = self.run_on("### D1 — A thing\n\nText only.\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("D1", errors[0])
        self.assertIn("no *Source:*", errors[0])

    def test_inline_mention_is_not_a_source_line(self) -> None:
        errors = self.run_on("### D1 — A thing\n\nA `*Source:*` line is needed. A1 2026-10-20\n")
        self.assertIn("no *Source:*", errors[0])

    def test_undated_source_fails(self) -> None:
        errors = self.run_on(GOOD.replace(", 2026-10-20", ""))
        self.assertTrue(any("no YYYY-MM-DD" in e for e in errors))

    def test_unknown_ask_fails(self) -> None:
        errors = self.run_on(GOOD.replace("A1", "A9"))
        self.assertTrue(any("unknown ask A9" in e for e in errors))

    def test_unknown_register_date_fails(self) -> None:
        errors = self.run_on(GOOD.replace("2026-10-20", "2026-01-01"))
        self.assertTrue(any("2026-01-01" in e for e in errors))

    def test_source_that_resolves_to_nothing_fails(self) -> None:
        errors = self.run_on("### D1 — A thing\n\n*Source:* the agent, 2026-10-20.\n")
        self.assertTrue(any("names no ask" in e for e in errors))

    def test_second_record_is_checked_too(self) -> None:
        errors = self.run_on(GOOD + "\n### D2 — Another\n\nNo source.\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("D2", errors[0])

    def test_missing_specs_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            errors = check_provenance.check(Path(tmp))
        self.assertEqual(len(errors), 1)
        self.assertIn("missing", errors[0])

    def test_closed_phase_needs_changelog(self) -> None:
        closed = "## Result\n\n- Where it stands: closed\n"
        errors = self.run_on(GOOD, closed)
        self.assertTrue(any("CHANGELOG.md is missing" in e for e in errors))
        with tempfile.TemporaryDirectory() as tmp:
            make_tree(Path(tmp), GOOD, closed)
            (Path(tmp) / "CHANGELOG.md").write_text("## 01-test\n", encoding="utf-8")
            self.assertEqual(check_provenance.check(Path(tmp)), [])

    def test_open_phase_needs_no_changelog(self) -> None:
        open_phase = "## Result\n\n- Where it stands: in progress\n"
        self.assertEqual(self.run_on(GOOD, open_phase), [])


if __name__ == "__main__":
    unittest.main()
