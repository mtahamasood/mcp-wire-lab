"""Mutation runner: apply one exact text replacement at a time in a temp copy, run a test command.

Usage:
  python3 tools/mutate.py [--root DIR] [--only ID[,ID]] [--timeout SECONDS] <spec.json>

The spec is JSON:
  {"links": ["vendor", "clients/sdk/node_modules"],      optional: paths symlinked, not copied
   "mutants": [{"id": "C9-1", "file": "tap/show.py",      repo-relative target
                "old": "exact text", "new": "replacement",
                "command": "python3 -m unittest tests.test_show",
                "timeout": 120, "note": "why",
                "equivalent": "reason it cannot change behaviour"}]}
                                                          timeout, note, equivalent: optional

The tree (git-tracked and untracked-but-not-ignored files; every file if DIR is not a git
repo) is copied once into a temp dir, and the real tree is never touched. Each distinct command
runs once unmutated first; a red baseline stops the run. For each mutant, `old` must occur
exactly once in `file` (else it is an error, not a kill). The command runs with
PYTHONDONTWRITEBYTECODE=1 and a clean `runs/`, so one mutant's recordings cannot satisfy another.
Afterwards the file is restored and compared byte for byte with the original.

A mutant with a non-empty `equivalent` reason is one the report has signed as unable to change
behaviour. It still runs; if it survives its verdict is `equivalent` (with the reason) and it does
not fail the run; if a test does kill it, it is reported `killed` and the note says so.

Result: killed (command failed; the exit code and failing tests, as `FAIL:`/`ERROR:` lines of the
output, are in the note), killed (timeout) (a timeout is reported this way, not as a plain kill),
survived (command passed), equivalent (marked, and survived), error.
Prints a Markdown table, then
`mutants: N killed: K survived: S errors: E equivalent: Q`.
Exit codes: 0 every mutant killed or equivalent, 1 a survivor not marked equivalent or an error,
2 usage or setup problem (bad spec, leftovers in `runs/` before a command, a file not restored
byte for byte, red baseline). Exit 2 stops the run.
"""

from __future__ import annotations

import filecmp
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 300.0
USAGE = __doc__ or ""


class SetupError(Exception):
    pass


def usage_error(message: str) -> int:
    print(f"mutate: {message}", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2


def load_spec(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise SetupError(f"cannot read spec {path}: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("mutants"), list):
        raise SetupError('spec must be an object with a "mutants" list')
    links = data.get("links", [])
    if not isinstance(links, list) or not all(isinstance(x, str) for x in links):
        raise SetupError('"links" must be a list of repo-relative paths')
    seen: set[str] = set()
    for m in data["mutants"]:
        if not isinstance(m, dict):
            raise SetupError("every mutant must be an object")
        for key in ("id", "file", "old", "new", "command"):
            if not isinstance(m.get(key), str) or (key != "new" and not m[key]):
                raise SetupError(f"mutant {m.get('id', '?')!r}: missing or bad {key!r}")
        if m["id"] in seen:
            raise SetupError(f"duplicate mutant id {m['id']!r}")
        eq = m.get("equivalent")
        if "equivalent" in m and (not isinstance(eq, str) or not eq.strip()):
            raise SetupError(f"mutant {m['id']!r}: 'equivalent' needs a non-empty reason")
        seen.add(m["id"])
    return links, data["mutants"]


def leftovers(runs: Path) -> list[str]:
    return sorted(p.name for p in runs.iterdir()) if runs.is_dir() else []


def tree_files(root: Path) -> list[str]:
    """Repo-relative files to copy: git's view when root is a repo, else a plain walk."""
    done = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
    )
    if done.returncode == 0 and (root / ".git").exists():
        names = [n for n in done.stdout.decode().split("\0") if n]
    else:
        names = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", "runs")]
            rel = Path(dirpath).relative_to(root)
            names += [str(rel / f) for f in filenames]
    return sorted(set(names))


def make_copy(root: Path, dest: Path, links: list[str]) -> None:
    linked = [Path(x).as_posix().strip("/") for x in links]
    for name in tree_files(root):
        if any(name == x or name.startswith(x + "/") for x in linked):
            continue
        src = root / name
        if not src.is_file() or src.is_symlink() and not src.exists():
            continue
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    for x in linked:
        src = root / x
        if not src.exists():
            raise SetupError(f"link path does not exist: {x}")
        (dest / x).parent.mkdir(parents=True, exist_ok=True)
        (dest / x).symlink_to(src.resolve())


def fresh_runs(copy: Path) -> None:
    shutil.rmtree(copy / "runs", ignore_errors=True)
    (copy / "runs").mkdir()
    found = leftovers(copy / "runs")
    if found:
        raise SetupError(f"runs/ in the copy still has entries ({', '.join(found[:3])})")


def failing_tests(output: str) -> list[str]:
    return [ln.strip() for ln in output.splitlines() if ln.startswith(("FAIL:", "ERROR:"))]


def run_command(command: str, cwd: Path, timeout: float) -> tuple[int | None, float, list[str]]:
    """Exit code (None on timeout), seconds, failing tests. The process group dies on timeout."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    start = time.monotonic()
    proc = subprocess.Popen(
        shlex.split(command),
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
        code: int | None = proc.returncode
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        code = None
    return code, time.monotonic() - start, failing_tests(out or "")


def timeout_of(mutant: dict[str, Any], default: float) -> float:
    value = mutant.get("timeout", default)
    return float(value) if isinstance(value, int | float) else default


def run_mutant(
    mutant: dict[str, Any], root: Path, copy: Path, default_timeout: float
) -> tuple[str, float, str]:
    target = copy / mutant["file"]
    original = root / mutant["file"]
    note = str(mutant.get("note", ""))
    if not target.is_file() or target.is_symlink():
        return "error", 0.0, f"target is not a copied file: {mutant['file']}"
    before = target.read_bytes()
    count = before.count(mutant["old"].encode())
    if count != 1:
        return "error", 0.0, f"old text occurs {count} times, need exactly 1"
    target.write_bytes(before.replace(mutant["old"].encode(), mutant["new"].encode()))
    try:
        fresh_runs(copy)
        code, secs, failed = run_command(
            mutant["command"], copy, timeout_of(mutant, default_timeout)
        )
    finally:
        target.write_bytes(before)
    if not filecmp.cmp(target, original, shallow=False):
        raise SetupError(f"NOT restored: {mutant['file']} differs from the original; run stopped")
    print(f"mutate: {mutant['id']}: restored byte-identical", file=sys.stderr)
    reason = str(mutant.get("equivalent", "")).strip()
    if code is None:
        result, detail = "killed (timeout)", "timeout"
    elif code != 0:
        result, detail = "killed", f"exit {code}" + (f"; {'; '.join(failed)}" if failed else "")
    elif reason:
        result, detail = "equivalent", f"equivalent: {reason}"
    else:
        result, detail = "survived", ""
    if reason and result.startswith("killed"):
        detail += "; marked equivalent but killed"
    note = "; ".join(x for x in (note, detail) if x)
    return result, secs, note.replace("|", "/").replace("\n", " ")


def table(rows: list[tuple[str, str, str, float, str]]) -> str:
    lines = ["| id | target | result | seconds | note |", "| --- | --- | --- | --- | --- |"]
    for mid, target, result, secs, note in rows:
        lines.append(f"| {mid} | {target} | {result} | {secs:.1f} | {note} |")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args[:1] in (["-h"], ["--help"]):
        print(USAGE.strip())
        return 0
    root = Path(".")
    only: set[str] | None = None
    timeout = DEFAULT_TIMEOUT
    spec_path: str | None = None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--root", "--only", "--timeout"):
            if i + 1 >= len(args):
                return usage_error(f"{a} needs a value")
            value = args[i + 1]
            i += 2
            if a == "--root":
                root = Path(value)
            elif a == "--only":
                only = {x for x in value.split(",") if x}
            else:
                try:
                    timeout = float(value)
                except ValueError:
                    return usage_error(f"bad --timeout: {value}")
        elif a.startswith("-") or spec_path is not None:
            return usage_error(f"unexpected argument: {a}")
        else:
            spec_path = a
            i += 1
    if spec_path is None:
        return usage_error("missing spec file")
    root = root.resolve()
    try:
        links, mutants = load_spec(Path(spec_path))
        if only is not None:
            unknown = only - {m["id"] for m in mutants}
            if unknown:
                raise SetupError(f"--only names unknown ids: {', '.join(sorted(unknown))}")
            mutants = [m for m in mutants if m["id"] in only]
        if not root.is_dir():
            raise SetupError(f"not a directory: {root}")
        found = leftovers(root / "runs")
        if found:
            raise SetupError(
                f"runs/ in {root} has leftovers ({', '.join(found[:3])}); "
                "they can make a mutant look killed. Remove them and start again."
            )
        with tempfile.TemporaryDirectory(prefix="mutate-") as tmp:
            copy = Path(tmp) / "tree"
            copy.mkdir()
            make_copy(root, copy, links)
            found = leftovers(copy / "runs")
            if found:
                raise SetupError(f"runs/ in the copy has leftovers ({', '.join(found[:3])})")
            for command in dict.fromkeys(m["command"] for m in mutants):
                fresh_runs(copy)
                code, _, _ = run_command(command, copy, timeout)
                if code != 0:
                    why = "timeout" if code is None else f"exit {code}"
                    raise SetupError(f"baseline is red ({why}): {command}")
            rows = []
            for m in mutants:
                result, secs, note = run_mutant(m, root, copy, timeout)
                rows.append((m["id"], m["file"], result, secs, note))
    except SetupError as e:
        print(f"mutate: {e}", file=sys.stderr)
        return 2
    print(table(rows))
    killed = sum(r[2].startswith("killed") for r in rows)
    survived = sum(r[2] == "survived" for r in rows)
    errors = sum(r[2] == "error" for r in rows)
    equivalent = sum(r[2] == "equivalent" for r in rows)
    print(
        f"\nmutants: {len(rows)} killed: {killed} survived: {survived} errors: {errors}"
        f" equivalent: {equivalent}"
    )
    return 0 if survived == 0 and errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
