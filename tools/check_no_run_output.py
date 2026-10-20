"""G11 (D15): run output never reaches git.

Usage:
  python3 tools/check_no_run_output.py [repo-root]    check every tracked file
  python3 tools/check_no_run_output.py --pre-push     git pre-push hook: read the pushed refs
                                                      from stdin, check every commit being pushed
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

SECRETS = {
    "GitHub token": re.compile(r"gh[opsu]_[A-Za-z0-9]{30,}"),
    "GitHub fine-grained token": re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    "API key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "Slack token": re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
HOME_PATH = re.compile(r"/(home/[A-Za-z0-9._-]+|Users/[A-Za-z0-9._-]+|root)/[A-Za-z0-9._-]")
ENV_KEY = re.compile(r'\\?"(PATH|HOME|USER|SHELL|PWD)\\?"\s*:')
ENV_WINDOW = 4000
SYNTHETIC = {"dir": "tap", "event": "synthetic"}
FIXTURES = "tests/fixtures/"
ZERO = "0" * 40


def _json_lines(text: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in text.split("\n"):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _has_env_dump(text: str) -> bool:
    hits = [(m.start(), m.group(1)) for m in ENV_KEY.finditer(text)]
    for i, (start, _) in enumerate(hits):
        keys = {k for pos, k in hits[i:] if pos - start <= ENV_WINDOW}
        if len(keys) >= 3:
            return True
    return False


def check_file(path: str, data: bytes) -> list[str]:
    """Problems with one file, given its repo-relative path and content."""
    problems: list[str] = []
    if path.startswith("runs/"):
        problems.append(f"{path}: tracked file under runs/")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return problems
    if path.endswith(".jsonl"):
        records = _json_lines(text)
        if any("seq" in r and "dir" in r for r in records):
            if not path.startswith(FIXTURES):
                problems.append(f"{path}: trace-shaped file outside {FIXTURES}")
            first = records[0] if records else {}
            if {k: first.get(k) for k in SYNTHETIC} != SYNTHETIC:
                problems.append(
                    f"{path}: trace-shaped file does not open with the synthetic marker"
                )
    if _has_env_dump(text):
        problems.append(f"{path}: contains an environment dump")
    if HOME_PATH.search(text):
        problems.append(f"{path}: contains a home-directory path")
    for name, pattern in SECRETS.items():
        if pattern.search(text):
            problems.append(f"{path}: contains a {name}")
    return problems


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout


def check_tracked(root: Path) -> list[str]:
    problems: list[str] = []
    for rel in _git(root, "ls-files", "-z").decode().split("\0"):
        path = root / rel
        if rel and path.is_file() and not path.is_symlink():
            problems += check_file(rel, path.read_bytes())
    return problems


def check_commit(root: Path, commit: str) -> list[str]:
    """Files added or modified by one commit, as they were in that commit."""
    raw = _git(
        root, "diff-tree", "--root", "-r", "--no-commit-id", "--diff-filter=AM", "-z", commit
    )
    fields = raw.decode().split("\0")
    problems: list[str] = []
    for meta, rel in zip(fields[0::2], fields[1::2], strict=False):
        new_mode = meta.split()[1] if meta else ""
        if new_mode in ("160000", "120000"):
            continue
        for p in check_file(rel, _git(root, "show", f"{commit}:{rel}")):
            problems.append(f"{commit[:10]} {p}")
    return problems


def pushed_commits(root: Path, stdin: Iterable[str], remote: str) -> list[str]:
    commits: list[str] = []
    for line in stdin:
        parts = line.split()
        if len(parts) != 4:
            continue
        _, local_sha, _, remote_sha = parts
        if local_sha == ZERO:
            continue
        if remote_sha != ZERO:
            rev = [f"{remote_sha}..{local_sha}"]
        else:
            rev = [local_sha, "--not", f"--remotes={remote}"]
        out = _git(root, "rev-list", *rev).decode().split()
        commits += [c for c in out if c not in commits]
    return commits


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args[:1] == ["--pre-push"]:
        root = Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"], check=True, capture_output=True, text=True
            ).stdout.strip()
        )
        remote = args[1] if len(args) > 1 else "origin"
        problems: list[str] = []
        for commit in pushed_commits(root, sys.stdin, remote):
            problems += check_commit(root, commit)
        scope = "pushed commits"
    else:
        root = Path(args[0]) if args else Path(__file__).resolve().parent.parent
        problems = check_tracked(root)
        scope = "tracked files"
    for p in problems:
        print(f"no-run-output: {p}", file=sys.stderr)
    if problems:
        return 1
    print(f"no-run-output: ok ({scope})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
