"""C15: the run-output gate names each kind of leak, and the pre-push hook stops a push."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import check_no_run_output as g11

ROOT = Path(__file__).resolve().parent.parent

# Samples are assembled from parts so this file does not itself match the patterns.
GH_TOKEN = "gh" + "p_" + "a1B2" * 9
SK_KEY = "sk" + "-" + "abcDEF123_" * 3
AWS_KEY = "AK" + "IA" + "ABCDEFGHIJKLMNOP"
SLACK = "xo" + "xb-" + "1234567890-abc"
PRIVATE_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----"
HOME = "/ho" + "me/someone/project"
ENV_KEYS = ["PA" + "TH", "HO" + "ME", "US" + "ER", "SHE" + "LL"]
ENV_DUMP = json.dumps({k: "x" for k in ENV_KEYS})
TRACE_LINE = json.dumps({"seq": 0, "dir": "c2s", "raw": "{}\n"})
MARKER = json.dumps({"dir": "tap", "event": "synthetic"})

LEAKS = {
    "runs/2026/trace.jsonl": "anything",
    "tests/fixtures/real.jsonl": TRACE_LINE + "\n",
    "docs/trace.jsonl": MARKER + "\n" + TRACE_LINE + "\n",
    "docs/env.md": "output: " + ENV_DUMP.replace('"', '\\"') + "\n",
    "docs/home.md": f"run it in {HOME}\n",
    "docs/gh.md": GH_TOKEN,
    "docs/sk.md": SK_KEY,
    "docs/aws.md": AWS_KEY,
    "docs/slack.md": SLACK,
    "docs/key.md": PRIVATE_KEY,
}


class CheckFileTest(unittest.TestCase):
    def test_real_repo_is_clean(self) -> None:
        self.assertEqual(g11.check_tracked(ROOT), [])

    def test_each_leak_is_named_by_file(self) -> None:
        for path, content in LEAKS.items():
            with self.subTest(path=path):
                problems = g11.check_file(path, content.encode())
                self.assertTrue(problems, path)
                self.assertTrue(all(p.startswith(path) for p in problems))

    def test_synthetic_fixture_is_allowed(self) -> None:
        data = (MARKER + "\n" + TRACE_LINE + "\n").encode()
        self.assertEqual(g11.check_file("tests/fixtures/ok.jsonl", data), [])

    def test_two_env_keys_are_not_a_dump(self) -> None:
        self.assertEqual(
            g11.check_file("docs/a.md", json.dumps({k: "x" for k in ENV_KEYS[:2]}).encode()), []
        )

    def test_binary_files_are_skipped(self) -> None:
        self.assertEqual(g11.check_file("docs/a.bin", b"\xff\xfe" + GH_TOKEN.encode()), [])


def git(
    cwd: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)


class PrePushHookTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        }
        self.bare = self.tmp / "remote.git"
        self.clone = self.tmp / "clone"
        self.run_git(self.tmp, "init", "--bare", "-b", "main", str(self.bare))
        self.run_git(self.tmp, "init", "-b", "main", str(self.clone))
        self.run_git(self.clone, "remote", "add", "origin", str(self.bare))
        shutil.copytree(
            ROOT / "tools", self.clone / "tools", ignore=shutil.ignore_patterns("__pycache__")
        )
        (self.clone / "README.md").write_text("hello\n", encoding="utf-8")
        self.run_git(self.clone, "add", "-A")
        self.run_git(self.clone, "commit", "-m", "base")
        install = subprocess.run(
            [str(ROOT / "scripts/install-pre-push.sh"), str(self.clone)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(install.returncode, 0, install.stderr)

    def run_git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        done = git(cwd, *args, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done

    def test_clean_push_succeeds(self) -> None:
        self.run_git(self.clone, "push", "origin", "main")

    def test_forced_run_output_is_refused(self) -> None:
        (self.clone / "runs").mkdir()
        (self.clone / "runs/trace.jsonl").write_text(TRACE_LINE + "\n", encoding="utf-8")
        self.run_git(self.clone, "add", "-f", "runs/trace.jsonl")
        self.run_git(self.clone, "commit", "-m", "oops")
        done = git(self.clone, "push", "origin", "main", env=self.env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("runs/trace.jsonl", done.stderr)
        self.assertEqual(
            git(self.bare, "rev-parse", "--verify", "main", env=self.env).returncode, 128
        )

    def test_leak_removed_by_a_later_commit_is_still_refused(self) -> None:
        (self.clone / "docs").mkdir()
        (self.clone / "docs/key.md").write_text(GH_TOKEN, encoding="utf-8")
        self.run_git(self.clone, "add", "-A")
        self.run_git(self.clone, "commit", "-m", "add")
        self.run_git(self.clone, "rm", "-q", "docs/key.md")
        self.run_git(self.clone, "commit", "-m", "remove")
        done = git(self.clone, "push", "origin", "main", env=self.env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("docs/key.md", done.stderr)

    def test_install_refuses_to_overwrite_a_different_hook(self) -> None:
        hook = self.clone / ".git/hooks/pre-push"
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        done = subprocess.run(
            [str(ROOT / "scripts/install-pre-push.sh"), str(self.clone)],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(hook.read_text(encoding="utf-8"), "#!/bin/sh\nexit 0\n")


if __name__ == "__main__":
    unittest.main()
