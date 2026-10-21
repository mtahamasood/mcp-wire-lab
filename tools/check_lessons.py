"""G9: every lesson has the L1 sections, and its runnable blocks run and print what they say.

A runnable block is a ```console block preceded by `<!-- run -->`; an expected block is a
```text block preceded by `<!-- expect -->` right after it (tech-stack.md, conventions).

Usage: python3 tools/check_lessons.py [--min-lessons N] [repo-root]
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SECTIONS = (
    "Goal",
    "Predict",
    "Run",
    "Read the trace",
    "Read the source",
    "Experiments",
    "Check yourself",
)
BLOCK = re.compile(
    r"<!-- run -->[ \t]*\n```console\n(?P<cmd>.*?)\n```"
    r"(?:[ \t]*\n+<!-- expect -->[ \t]*\n```text\n(?P<expect>.*?)\n```)?",
    re.DOTALL,
)
TIMEOUT_S = 120


def _normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().split("\n"))


def _script(block: str) -> str:
    lines = block.split("\n")
    return "\n".join(line[2:] if line.startswith("$ ") else line for line in lines)


FENCE = re.compile(r"^```.*?^```[ \t]*$", re.DOTALL | re.MULTILINE)


def check_sections(label: str, text: str) -> list[str]:
    """The seven L1 headings must exist, outside code fences, in this order."""
    prose = FENCE.sub("", text)
    headings = [h.strip().lower() for h in re.findall(r"^##\s+(.+)$", prose, re.MULTILINE)]
    errors: list[str] = []
    positions: list[int] = []
    for s in SECTIONS:
        at = next((i for i, h in enumerate(headings) if h.startswith(s.lower())), None)
        if at is None:
            errors.append(f"{label}: missing section '{s}'")
        else:
            positions.append(at)
    if positions != sorted(positions):
        errors.append(f"{label}: sections are out of order (expected {' -> '.join(SECTIONS)})")
    return errors


def check_blocks(root: Path, label: str, text: str) -> list[str]:
    errors: list[str] = []
    for n, m in enumerate(BLOCK.finditer(text), start=1):
        script = _script(m.group("cmd"))
        where = f"{label}: runnable block {n}"
        try:
            done = subprocess.run(
                ["bash", "-eo", "pipefail", "-c", script],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            errors.append(f"{where}: timed out after {TIMEOUT_S}s")
            continue
        if done.returncode != 0:
            errors.append(f"{where}: exited {done.returncode}: {script.splitlines()[0]}")
            continue
        expect = m.group("expect")
        if expect is not None and _normalize(expect) not in _normalize(done.stdout + done.stderr):
            errors.append(f"{where}: expected output not found: {_normalize(expect)[:60]!r}")
    return errors


def check(root: Path, min_lessons: int) -> tuple[int, list[str]]:
    lessons = sorted((root / "docs" / "lessons").glob("*.md"))
    if len(lessons) < min_lessons:
        return len(lessons), [f"found {len(lessons)} lessons in docs/lessons, need {min_lessons}"]
    errors: list[str] = []
    for lesson in lessons:
        text = lesson.read_text(encoding="utf-8")
        label = str(lesson.relative_to(root))
        errors += check_sections(label, text)
        errors += check_blocks(root, label, text)
    return len(lessons), errors


def main(argv: list[str]) -> int:
    args = argv[1:]
    min_lessons = 1
    if args[:1] == ["--min-lessons"]:
        min_lessons = int(args[1])
        args = args[2:]
    root = Path(args[0]) if args else Path(__file__).resolve().parent.parent
    count, errors = check(root, min_lessons)
    for e in errors:
        print(f"lessons: {e}", file=sys.stderr)
    if errors:
        return 1
    print(f"lessons: ok ({count} checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
