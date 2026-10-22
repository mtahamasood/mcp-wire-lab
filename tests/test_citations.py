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

    def test_escaping_path_gets_one_error_and_is_not_read(self) -> None:
        # docs/x.md has one line, so reading it would also report line 2 past the end.
        _, errors = self.run_on('`servers:../../docs/x.md:2` "nowhere-at-all"')
        self.assertEqual(len(errors), 1)
        self.assertIn("outside", errors[0])

    def test_fragment_length_counts_unescaped_characters(self) -> None:
        # `\": \"` is 6 characters as written but the fragment is `": "`, 4 characters,
        # and it is on spec line 2: only the length rule can catch it.
        _, errors = self.run_on('`spec:docs/b.mdx:2` "\\": \\""')
        self.assertEqual(len(errors), 1)
        self.assertIn("at least 6", errors[0])

    def test_root_reached_through_a_symlink_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            real.mkdir()
            make_tree(real, '`servers:src/a.ts:2` "serveStdio("')
            link = Path(tmp) / "link"
            link.symlink_to(real)
            self.assertEqual(check_citations.check(link), (1, []))

    # -- phase 5 D6: the `sdk` root (C12) ----------------------------------------------------

    @staticmethod
    def add_sdk(root: Path, installed: bool = True) -> None:
        (root / "clients/sdk/src").mkdir(parents=True)
        (root / "clients/sdk/test").mkdir()
        if installed:
            dist = root / "clients/sdk/node_modules/@modelcontextprotocol/client/dist"
            dist.mkdir(parents=True)
            body = "one\nasync callTool(params) {\nthree\n"
            (dist / "index.mjs").write_text(body, encoding="utf-8")

    def test_sdk_root_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_tree(root, '`sdk:client/dist/index.mjs:2` "async callTool("')
            self.add_sdk(root)
            self.assertEqual(check_citations.check(root), (1, []))
            # a wrong line, a short fragment and a path leaving the root each fail
            (root / "docs/x.md").write_text(
                '`sdk:client/dist/index.mjs:1` "async callTool("\n'
                '`sdk:client/dist/index.mjs:2` "async"\n'
                '`sdk:../../../../docs/x.md:1` "sdk:../../"\n', encoding="utf-8")
            _, errors = check_citations.check(root)
            self.assertEqual(len(errors), 3, errors)
            self.assertIn("not on line 1", errors[0])
            self.assertIn("at least 6", errors[1])
            self.assertIn("outside", errors[2])
            # the scanned client sources are checked too
            (root / "docs/x.md").write_text("none", encoding="utf-8")
            (root / "clients/sdk/src/a.ts").write_text(
                '// `sdk:client/dist/index.mjs:3` "async callTool("', encoding="utf-8")
            (root / "clients/sdk/test/a.test.ts").write_text(
                '// `sdk:client/dist/index.mjs:2` "async callTool("', encoding="utf-8")
            total, errors = check_citations.check(root)
            self.assertEqual(total, 2)
            self.assertEqual(len(errors), 1)
            self.assertIn("clients/sdk/src/a.ts", errors[0])

    def test_sdk_root_missing_fails_with_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_tree(root, '`sdk:client/dist/index.mjs:2` "async callTool("')
            self.add_sdk(root, installed=False)
            _, errors = check_citations.check(root)
        self.assertEqual(len(errors), 1)
        self.assertIn("scripts/bootstrap.sh", errors[0])

    def test_node_modules_not_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_tree(root, "none")
            self.add_sdk(root)
            # a citation-shaped string inside an installed package is not ours to check
            installed = root / "clients/sdk/node_modules/@modelcontextprotocol/client/dist"
            (installed / "index.mjs").write_text(
                '`sdk:client/dist/index.mjs:1` "does not matter"', encoding="utf-8")
            (root / "clients/sdk/node_modules/pkg.md").write_text(
                '`sdk:client/dist/index.mjs:1` "nope-nope"', encoding="utf-8")
            self.assertEqual(check_citations.check(root), (0, []))

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
