"""Walkthrough 06 (the 2026-07-28 era) says nothing false about the pinned spec (phase 8 D10,
P8-R6-5). Text checks on the claims the final-pass review found wrong; the citations in the
same file are checked by `tools/check_citations.py` (G8)."""

from __future__ import annotations

import unittest
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "docs/walkthrough/06-era-2026.md"


class EraDocTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = DOC.read_text(encoding="utf-8")

    def test_cancelled_listen_is_not_a_departure(self) -> None:
        # a server sends nothing for a cancelled request, so it is not "departing" there
        start = self.text.index("**No `subscriptions/listen` response at shutdown.**")
        bullet = self.text[start:self.text.index("\n\n", start)]
        self.assertIn("stdin closes", bullet)
        self.assertNotIn("client cancels the listen request", bullet)
        self.assertNotIn("(or the client cancels", bullet)

    def test_notification_is_never_given_an_error_code(self) -> None:
        rows = [ln for ln in self.text.splitlines()
                if ln.startswith("|") and "notifications/roots/list_changed" in ln]
        self.assertEqual(len(rows), 1, rows)
        self.assertNotIn("-32601", rows[0], "a notification is never answered")
        requests = [ln for ln in self.text.splitlines()
                    if ln.startswith("|") and "`logging/setLevel`" in ln]
        self.assertEqual(len(requests), 1, requests)
        self.assertIn("-32601", requests[0])
        self.assertNotIn("notifications/roots/list_changed", requests[0])


if __name__ == "__main__":
    unittest.main()
