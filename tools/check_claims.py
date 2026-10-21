"""G12: every C row of a phase's validation.md names checks, and each one named exists (D7).

A check is a backtick span in the row's Checks cell: `tests/<file>.py::<Class>::<method>` (the
method defined in that class of that file, found with `ast`), or any other path, which must be a
file or a directory. Phases numbered 02 or later are checked; phase 1 names none.

Usage: python3 tools/check_claims.py [--phases NN[,NN...]] [repo-root]
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

PHASE_DIR = re.compile(r"^(\d\d)-")
SPAN = re.compile(r"`([^`]+)`")
FIRST_PHASE = 2


def _split_cells(line: str) -> list[str]:
    """Cells of a table row: split on `|` outside backtick spans and not escaped as `\\|`."""
    cells: list[str] = []
    cur: list[str] = []
    in_code = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and not in_code and line[i + 1 : i + 2] == "|":
            cur.append("|")
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    cells.append("".join(cur).strip())
    return cells[1:-1] if line.rstrip().endswith("|") else cells[1:]


def _c_rows(text: str) -> list[tuple[str, str]] | None:
    """(row id, Checks cell) for each table row under `## C.`, or None if there is no table.

    The Checks column is the one headed `Checks`. A row whose cell count differs from the
    header's gets an empty Checks cell, so it fails as naming no check.
    """
    rows: list[tuple[str, str]] = []
    in_section = False
    checks_at: int | None = None
    width = 0
    for line in text.split("\n"):
        if line.startswith("## "):
            in_section = line.startswith("## C.")
            checks_at = None
            continue
        if not in_section or not line.startswith("|"):
            continue
        cells = _split_cells(line)
        if cells and cells[0] == "Row":
            width = len(cells)
            checks_at = cells.index("Checks") if "Checks" in cells else None
            continue
        if not cells or set(cells[0]) <= {"-", " ", ":"} or checks_at is None:
            continue
        rows.append((cells[0], cells[checks_at] if len(cells) == width else ""))
    return rows or None


def _classes(path: Path) -> dict[str, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: {
            f.name for f in node.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }


def _problem(root: Path, item: str) -> str | None:
    """Why a named check does not exist, or None."""
    path, _, member = item.partition("::")
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()) or not target.exists():
        return f"{item}: file does not exist"
    if not member:
        return None
    if not target.is_file() or target.suffix != ".py":
        return f"{item}: not a Python file"
    cls, _, method = member.partition("::")
    try:
        classes = _classes(target)
    except SyntaxError:
        return f"{item}: file does not parse"
    if cls not in classes:
        return f"{item}: class {cls} does not exist"
    if method not in classes[cls]:
        return f"{item}: method {method or '(none named)'} does not exist in {cls}"
    return None


def check(root: Path, phases: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    base = root / "specs/phases"
    for phase in sorted(base.iterdir()) if base.is_dir() else []:
        found = PHASE_DIR.match(phase.name)
        if not found or int(found.group(1)) < FIRST_PHASE:
            continue
        if phases is not None and found.group(1) not in phases:
            continue
        validation = phase / "validation.md"
        if not validation.is_file():
            continue
        rows = _c_rows(validation.read_text(encoding="utf-8"))
        if rows is None:
            errors.append(f"claims: {phase.name}: no C table in validation.md")
            continue
        for row, cell in rows:
            items = SPAN.findall(cell)
            if not items:
                errors.append(f"claims: {phase.name} {row}: names no check")
            for item in items:
                problem = _problem(root, item)
                if problem:
                    errors.append(f"claims: {phase.name} {row}: {problem}")
    return errors


def main(argv: list[str]) -> int:
    args = argv[1:]
    phases: list[str] | None = None
    if args[:1] == ["--phases"] and len(args) >= 2:
        phases = args[1].split(",")
        args = args[2:]
    root = Path(args[0]) if args else Path(__file__).resolve().parent.parent
    errors = check(root, phases)
    for e in errors:
        print(e, file=sys.stderr)
    if errors:
        return 1
    print("claims: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
