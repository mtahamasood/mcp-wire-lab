"""C11: the citation gate catches each way a citation can be wrong."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import check_citations

ROOT = Path(__file__).resolve().parent.parent

SERVER_FILE = "alpha\nserveStdio(\nbeta\n"
SPEC_FILE = 'one\n  "method": "initialize"\nthree\n'


def make_tree(root: Path, doc: str) -> None:
    (root / "vendor/servers/src").mkdir(parents=True)
    (root / "vendor/servers/src/a.ts").write_text(SERVER_FILE, encoding="utf-8")
    (root / "vendor/spec/docs").mkdir(parents=True)
    (root / "vendor/spec/docs/b.mdx").write_text(SPEC_FILE, encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs/x.md").write_text(doc, encoding="utf-8")


class CitationsTest(unittest.TestCase):
    def run_on(self, doc: str) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            make_tree(Path(tmp), doc)
            return check_citations.check(Path(tmp))

    def test_real_repo_passes(self) -> None:
        _, errors = check_citations.check(ROOT)
        self.assertEqual(errors, [])

    def test_good_citations_pass_and_are_counted(self) -> None:
        doc = (
            '`servers:src/a.ts:2` "serveStdio("\n'
            '`spec:docs/b.mdx:2` "\\"method\\": \\"initialize\\""\n'
        )
        self.assertEqual(self.run_on(doc), (2, []))

    def test_missing_file_fails_naming_citation(self) -> None:
        _, errors = self.run_on('`servers:src/nope.ts:1` "serveStdio("')
        self.assertEqual(len(errors), 1)
        self.assertIn("src/nope.ts:1", errors[0])
        self.assertIn("does not exist", errors[0])

    def test_line_past_eof_fails(self) -> None:
        _, errors = self.run_on('`servers:src/a.ts:99` "serveStdio("')
        self.assertTrue(any("past the end" in e for e in errors))

    def test_off_by_one_fails(self) -> None:
        # The fragment exists in the file, one line away from the cited line.
        for line in (1, 3):
            _, errors = self.run_on(f'`servers:src/a.ts:{line}` "serveStdio("')
            self.assertEqual(len(errors), 1, line)
            self.assertIn("not on line", errors[0])

    def test_unknown_submodule_fails(self) -> None:
        _, errors = self.run_on('`other:src/a.ts:2` "serveStdio("')
        self.assertTrue(any("unknown submodule" in e for e in errors))

    def test_submodule_not_checked_out_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            make_tree(Path(tmp), '`servers:src/a.ts:2` "serveStdio("')
            for f in (Path(tmp) / "vendor/spec").rglob("*b.mdx"):
                f.unlink()
            (Path(tmp) / "vendor/spec/docs").rmdir()
            _, errors = check_citations.check(Path(tmp))
        self.assertEqual(len(errors), 1)
        self.assertIn("not checked out", errors[0])

    def test_citation_in_tap_and_readme_is_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_tree(root, "no citations here")
            (root / "README.md").write_text('`servers:src/a.ts:1` "wrong"', encoding="utf-8")
            (root / "tap").mkdir()
            (root / "tap/m.py").write_text('# `servers:src/a.ts:3` "wrong"', encoding="utf-8")
            total, errors = check_citations.check(root)
        self.assertEqual(total, 2)
        self.assertEqual(len(errors), 2)

    def test_path_escaping_the_submodule_fails(self) -> None:
        # R12: `../../docs/x.md` resolves to a real file in the repo, outside the submodule.
        _, errors = self.run_on('`servers:../../docs/x.md:1` "servers"')
        self.assertEqual(len(errors), 1)
        self.assertIn("outside", errors[0])

    def test_short_fragment_fails(self) -> None:
        # R12/T15: "" and "a" match almost any line.
        for frag in ("", "a", "alpha"):
            _, errors = self.run_on(f'`servers:src/a.ts:1` "{frag}"')
            self.assertEqual(len(errors), 1, frag)
            self.assertIn("at least 6", errors[0])

    def test_six_character_fragment_is_enough(self) -> None:
        self.assertEqual(self.run_on('`servers:src/a.ts:2` "serveS"')[1], [])

    def test_phantom_last_line_is_past_the_end(self) -> None:
        # SERVER_FILE ends in a newline: it has 3 lines, not 4.
        _, errors = self.run_on('`servers:src/a.ts:4` "serveStdio("')
        self.assertTrue(any("past the end" in e for e in errors))

    def test_undecodable_doc_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_tree(root, "ok")
            (root / "docs/bad.md").write_bytes(b"caf\xe9 `servers:src/a.ts:2` \"serveStdio(\"")
            _, errors = check_citations.check(root)
        self.assertEqual(len(errors), 1)
        self.assertIn("bad.md", errors[0])
        self.assertIn("UTF-8", errors[0])


if __name__ == "__main__":
    unittest.main()
