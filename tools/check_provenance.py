"""G1 and G7: every decision record traces to an ask, a register row, or the constitution.

Usage: python3 tools/check_provenance.py [repo-root]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
ASK = re.compile(r"\bA(\d+)\b")
ROW_DATE = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|", re.MULTILINE)
ASK_ROW = re.compile(r"^\|\s*(A\d+)\s*\|", re.MULTILINE)
SOURCE = re.compile(r"^\*Source:\*", re.MULTILINE)
RECORD = re.compile(r"^#{2,4} (D\d+)\b.*$", re.MULTILINE)
REGISTER_ROW = re.compile(r"\bregister row\b|\bregistered in mission\.md\b", re.IGNORECASE)
STATUS = re.compile(r"^[ \t]*(?:[-*][ \t]+)?Status:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
CONSTITUTION = ("mission.md", "roadmap.md", "tech-stack.md")


def _source_text(block: str) -> str | None:
    """The `*Source:*` paragraph of a record: from its marker to the next blank line."""
    marker = SOURCE.search(block)
    if marker is None:
        return None
    end = block.find("\n\n", marker.start())
    return block[marker.start() : end if end >= 0 else len(block)]


def check_requirements(path: Path, asks: set[str], dates: set[str]) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    heads = list(RECORD.finditer(text))
    for i, head in enumerate(heads):
        block = text[head.start() : heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        name = f"{path}: {head.group(1)}"
        source = _source_text(block)
        if source is None:
            errors.append(f"{name}: no *Source:* line")
            continue
        found_dates = DATE.findall(source)
        if not found_dates:
            errors.append(f"{name}: Source has no YYYY-MM-DD date")
        for d in found_dates:
            if d not in dates:
                errors.append(f"{name}: Source date {d} is not a row date in mission.md")
        cited = [f"A{n}" for n in ASK.findall(source)]
        for a in cited:
            if a not in asks:
                errors.append(f"{name}: Source cites unknown ask {a}")
        resolves = (
            bool(cited)
            or "mission.md" in source
            or REGISTER_ROW.search(source) is not None
            or any(c in source for c in CONSTITUTION)
        )
        if not resolves:
            errors.append(f"{name}: Source names no ask, register row, or constitution file")
    return errors


def check_changelog(root: Path, phase_dir: Path) -> list[str]:
    validation = phase_dir / "validation.md"
    text = validation.read_text(encoding="utf-8")
    head = text.find("## Result")
    if head < 0:
        return [f"{validation}: no ## Result section"]
    nxt = re.search(r"^## ", text[head + 1 :], re.MULTILINE)
    result = text[head : head + 1 + nxt.start()] if nxt else text[head:]
    values = STATUS.findall(result)
    if len(values) != 1 or values[0] not in ("open", "closed"):
        return [f"{validation}: Result needs exactly one line 'Status: open' or 'Status: closed'"]
    if values[0] == "open":
        return []
    changelog = root / "CHANGELOG.md"
    if not changelog.is_file():
        return [f"{phase_dir.name}: Result says closed but CHANGELOG.md is missing"]
    if phase_dir.name not in changelog.read_text(encoding="utf-8"):
        return [f"{phase_dir.name}: Result says closed but CHANGELOG.md has no entry for it"]
    return []


def check(root: Path) -> list[str]:
    specs = root / "specs"
    mission = specs / "mission.md"
    if not specs.is_dir():
        return [f"{specs}: missing"]
    if not mission.is_file():
        return [f"{mission}: missing"]
    mission_text = mission.read_text(encoding="utf-8")
    asks = set(ASK_ROW.findall(mission_text))
    dates = set(ROW_DATE.findall(mission_text))
    if not asks or not dates:
        return [f"{mission}: no ask rows or no dated register rows found"]
    phases = sorted((specs / "phases").glob("*/"))
    if not phases:
        return [f"{specs / 'phases'}: no phase directories"]
    errors: list[str] = []
    for phase in phases:
        req = phase / "requirements.md"
        if not req.is_file():
            errors.append(f"{req}: missing")
            continue
        errors += check_requirements(req, asks, dates)
        if (phase / "validation.md").is_file():
            errors += check_changelog(root, phase)
    return errors


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    errors = check(root)
    for e in errors:
        print(f"provenance: {e}", file=sys.stderr)
    if errors:
        return 1
    print("provenance: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
