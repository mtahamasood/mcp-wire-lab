"""C18 (lesson half): lesson 01 never picks a run folder by name order (D12)."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

LESSON = Path(__file__).resolve().parent.parent / "docs/lessons/01-the-wire-and-the-handshake.md"
BLOCK = re.compile(r"<!-- run -->\n```console\n(.*?)\n```", re.S)
OLD, NEW = "19990101T000000Z-{}", "19990101T000000Z-{}-2"


def blocks() -> list[str]:
    return BLOCK.findall(LESSON.read_text(encoding="utf-8"))


def run_lines(block: str) -> list[str]:
    return [ln.strip().removeprefix("$ ") for ln in block.splitlines() if "run=" in ln]


class Lesson01RunFolderTest(unittest.TestCase):
    def test_no_name_order_pick(self) -> None:
        for n, line in enumerate(LESSON.read_text(encoding="utf-8").splitlines(), 1):
            if "ls -d runs/" in line:
                self.assertNotIn("| tail -1", line, f"line {n} picks a folder by name order")

    def test_recording_blocks_read_the_recorded_line(self) -> None:
        seen = 0
        for block in blocks():
            if "scripts/record.sh" not in block:
                continue
            for line in run_lines(block):
                seen += 1
                self.assertIn("recorded:", line, "a block that records must read recorded:")
        self.assertGreater(seen, 0, "no recording block sets run=")

    def test_reading_blocks_pick_the_newest_by_mtime(self) -> None:
        checked = 0
        for block in blocks():
            if "scripts/record.sh" in block:
                continue
            for line in run_lines(block):
                m = re.search(r"runs/\*-([A-Za-z0-9_-]+)\*", line)
                self.assertIsNotNone(m, f"cannot read the run name from: {line}")
                assert m is not None
                name = m.group(1)
                with tempfile.TemporaryDirectory() as tmp:
                    old = Path(tmp, "runs", OLD.format(name))
                    new = Path(tmp, "runs", NEW.format(name))
                    old.mkdir(parents=True)
                    new.mkdir()
                    os.utime(old, (1_000_000_000, 1_000_000_000))
                    os.utime(new, (1_000_000_100, 1_000_000_100))
                    done = subprocess.run(
                        ["bash", "-eo", "pipefail", "-c", f'{line}\necho "$run"'],
                        cwd=tmp, capture_output=True, text=True, timeout=10,
                    )
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stdout.strip(), f"runs/{NEW.format(name)}", line)
                checked += 1
        self.assertGreater(checked, 0, "no reading block sets run=")


if __name__ == "__main__":
    unittest.main()
