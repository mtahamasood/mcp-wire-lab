"""Lessons 03 and 04 and walkthroughs 03 and 04 say nothing false that the final-pass review
found (phase 8 D10: P8-R3-2, P8-R3-3, P8-R4-1, P8-R4-2). Text checks against the source and the
pinned schema; the citations are checked by `tools/check_citations.py` (G8)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SCHEMA_TS = ROOT / "vendor/spec/schema/2025-11-25/schema.ts"


def flat(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


class Doc03Test(unittest.TestCase):
    def test_lesson_03_predict_3_is_not_a_deadlock(self) -> None:
        text = flat(DOCS / "lessons/03-server-initiated.md")
        self.assertNotIn("A deadlock: the reader would wait", text)
        self.assertNotIn("the reader is itself busy answering", text)
        # what the worker thread buys, per the C2 test: a slow handler must not stall the reader
        answer = text[text.index("3. No deadlock"):]
        self.assertIn("slow handler", answer[:900])
        self.assertIn("reader", answer[:900])

    def test_walkthrough_03_elicit_number_matches_schema_ts(self) -> None:
        if not SCHEMA_TS.exists():
            self.skipTest("vendor/ is not checked out")
        ts = SCHEMA_TS.read_text(encoding="utf-8")
        self.assertIn("content?: { [key: string]: string | number | boolean | string[] };", ts)
        text = flat(DOCS / "walkthrough/03-server-initiated.md")
        self.assertNotIn("the schema's `ElicitResult` allows only strings, integers", text)
        self.assertIn("`schema.ts` says `number`", text)
        self.assertIn("generated JSON schema", text)


class Doc04Test(unittest.TestCase):
    def test_lesson_04_array_has_a_reply_form(self) -> None:
        text = flat(DOCS / "lessons/04-edge-lab.md")
        self.assertNotIn("there is nothing to reply to", text)
        self.assertIn("an error that has no id", text)

    def test_walkthrough_04_missing_jsonrpc_has_an_id(self) -> None:
        fixture = (ROOT / "tests/fixtures/edge-missing-jsonrpc.ndjson").read_text()
        self.assertIn('"id":1', fixture.splitlines()[2].replace(" ", ""))
        text = flat(DOCS / "walkthrough/04-edge-lab.md")
        self.assertNotIn("so there is no `id` to put on an error reply", text)
        self.assertIn("could have answered `-32600` with `id` 1", text)


if __name__ == "__main__":
    unittest.main()
