"""G8: every `<submodule>:<path>:<line>` "fragment" citation resolves in the pinned submodule.

Usage: python3 tools/check_citations.py [repo-root]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CITATION = re.compile(r'`([A-Za-z0-9_-]+):([^`\s:]+):(\d+)`\s+"((?:[^"\\]|\\.)*)"')
SUBMODULES = {"servers": "vendor/servers", "spec": "vendor/spec"}
SCANNED = ("README.md", "docs", "tap")
MIN_FRAGMENT = 6


def _unescape(fragment: str) -> str:
    return re.sub(r"\\(.)", r"\1", fragment)


def _scanned_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for name in SCANNED:
        target = root / name
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files += sorted(
                p for p in target.rglob("*") if p.is_file() and "__pycache__" not in p.parts
            )
    return files


def check_text(root: Path, label: str, text: str) -> tuple[int, list[str]]:
    errors: list[str] = []
    count = 0
    for m in CITATION.finditer(text):
        count += 1
        sub, rel, line_no, raw = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        cite = f'{label}: `{sub}:{rel}:{line_no}` "{raw}"'
        if sub not in SUBMODULES:
            errors.append(f"{cite}: unknown submodule {sub!r}")
            continue
        base = (root / SUBMODULES[sub]).resolve()
        target = (base / rel).resolve()
        if not target.is_relative_to(base):
            errors.append(f"{cite}: path is outside {SUBMODULES[sub]}")
            continue
        fragment = _unescape(raw)
        if len(fragment) < MIN_FRAGMENT:
            errors.append(f"{cite}: fragment must be at least {MIN_FRAGMENT} characters")
            continue
        if not target.is_file():
            errors.append(f"{cite}: file does not exist in {SUBMODULES[sub]}")
            continue
        lines = target.read_text(encoding="utf-8", errors="replace").split("\n")
        if lines and lines[-1] == "":
            lines.pop()  # a final newline ends the last line; it does not start another
        if line_no < 1 or line_no > len(lines):
            errors.append(f"{cite}: line {line_no} is past the end ({len(lines)} lines)")
        elif fragment not in lines[line_no - 1]:
            errors.append(f"{cite}: fragment is not on line {line_no}")
    return count, errors


def check(root: Path) -> tuple[int, list[str]]:
    for name, path in SUBMODULES.items():
        d = root / path
        if not d.is_dir() or not any(d.iterdir()):
            return 0, [f"submodule {name} is not checked out at {path}"]
    total = 0
    errors: list[str] = []
    for f in _scanned_files(root):
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            total_label = str(f.relative_to(root))
            errors.append(f"{total_label}: not valid UTF-8, citations cannot be checked")
            continue
        n, errs = check_text(root, str(f.relative_to(root)), text)
        total += n
        errors += errs
    return total, errors


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    total, errors = check(root)
    for e in errors:
        print(f"citations: {e}", file=sys.stderr)
    if errors:
        return 1
    print(f"citations: ok ({total} checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
