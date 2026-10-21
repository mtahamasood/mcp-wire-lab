"""C9 (offline half): the atlas regenerates byte-identical, lists every method with direction,
and fails on a lesson declaring an unknown method."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools import atlas

ROOT = Path(__file__).resolve().parent.parent
REVISIONS = ("2025-11-25", "2026-07-28")
UNIONS = {
    "ClientRequest": ("request", "client to server"),
    "ServerRequest": ("request", "server to client"),
    "ClientNotification": ("notification", "client to server"),
    "ServerNotification": ("notification", "server to client"),
    "InputRequest": ("request", "server to client, inside an InputRequiredResult"),
}


def schema_defs(revision: str) -> dict[str, Any]:
    path = ROOT / "vendor/spec/schema" / revision / "schema.json"
    defs: dict[str, Any] = json.loads(path.read_text("utf-8"))["$defs"]
    return defs


def schema_methods(revision: str) -> dict[str, list[tuple[str, str]]]:
    """Read independently of tools/atlas.py: method -> [(kind, direction)] from the unions."""
    defs = schema_defs(revision)
    found: dict[str, list[tuple[str, str]]] = {}
    for union, (kind, direction) in UNIONS.items():
        node = defs.get(union, {})
        refs = [m["$ref"].rsplit("/", 1)[1] for m in node.get("anyOf", [])]
        nodes = [defs[r] for r in refs] or ([node] if node else [])
        for member in nodes:
            found.setdefault(member["properties"]["method"]["const"], []).append((kind, direction))
    return found


def make_root(tmp: str, lesson_text: str) -> Path:
    root = Path(tmp)
    (root / "vendor").mkdir()
    (root / "vendor/spec").symlink_to(ROOT / "vendor/spec", target_is_directory=True)
    (root / "docs/lessons").mkdir(parents=True)
    (root / "docs/lessons/01-x.md").write_text(lesson_text, encoding="utf-8")
    return root


class AtlasTest(unittest.TestCase):
    def test_regenerated_atlas_matches_committed(self) -> None:
        committed = (ROOT / "docs/atlas.md").read_text(encoding="utf-8")
        self.assertEqual(atlas.render(ROOT), committed)
        self.assertEqual(atlas.check(ROOT), [])

    def test_every_schema_method_listed_with_direction(self) -> None:
        lines = atlas.render(ROOT).splitlines()
        for revision in REVISIONS:
            methods = schema_methods(revision)
            self.assertTrue(methods)
            for method, entries in methods.items():
                rows = [ln for ln in lines if ln.startswith(f"| `{method}` |")]
                self.assertEqual(len(rows), 1, method)
                for kind, direction in entries:
                    self.assertIn(f"| {kind} |", rows[0])
                    self.assertIn(direction, rows[0])
                self.assertIn(revision, rows[0])

    def test_2026_server_requests_travel_inside_results(self) -> None:
        self.assertNotIn("ServerRequest", schema_defs("2026-07-28"))
        row = next(ln for ln in atlas.render(ROOT).splitlines()
                   if ln.startswith("| `sampling/createMessage` |"))
        self.assertIn("2025-11-25: server to client; 2026-07-28: server to client, inside", row)

    def test_unknown_declared_method_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, "# L\n\n<!-- exercises: ping, tools/nonexistent -->\n")
            errors = atlas.check(root)
        self.assertEqual(len(errors), 1)
        self.assertIn("tools/nonexistent", errors[0])
        self.assertIn("01-x.md", errors[0])

    def test_declared_method_shows_its_lesson_and_others_are_unexercised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, "# L\n\n<!-- exercises: ping -->\n")
            text = atlas.render(root)
        ping = next(ln for ln in text.splitlines() if ln.startswith("| `ping` |"))
        self.assertIn("01-x.md", ping)
        other = next(ln for ln in text.splitlines() if ln.startswith("| `tools/list` |"))
        self.assertIn("unexercised", other)

    def test_drift_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, "# L\n\n<!-- exercises: ping -->\n")
            (root / "docs/atlas.md").write_text("stale\n", encoding="utf-8")
            errors = atlas.check(root)
        self.assertEqual(len(errors), 1)
        self.assertIn("python3 tools/atlas.py", errors[0])


if __name__ == "__main__":
    unittest.main()
