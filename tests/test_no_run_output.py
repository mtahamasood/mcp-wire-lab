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
GH_PAT = "github" + "_pat_" + "A1b2C3d4" * 4
PRIVATE_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----"
HOME = "/ho" + "me/someone/project"
ENV_KEYS = ["PA" + "TH", "HO" + "ME", "US" + "ER", "SHE" + "LL"]
ENV_DUMP = json.dumps({k: "x" for k in ENV_KEYS})
TRACE_LINE = json.dumps({"seq": 0, "dir": "c2s", "raw": "{}\n"})
TRACE_NS = json.dumps({"seq": 3, "dir": "s2c", "t_ns": 1, "raw": "{}\n"})
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
    "docs/pat.md": GH_PAT,
    "docs/env3.json": json.dumps({k: "x" for k in ("PW" + "D", "US" + "ER", "SHE" + "LL")}),
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

    def test_undecodable_byte_does_not_hide_a_secret(self) -> None:
        # R10: one Latin-1 byte used to skip every text rule for the whole file.
        problems = g11.check_file(
            "docs/a.log", b"caf\xe9 " + GH_TOKEN.encode() + b" " + HOME.encode()
        )
        self.assertEqual(len(problems), 2, problems)

    def test_trace_shape_ignores_name_and_case(self) -> None:
        # R3: a real trace renamed .ndjson, .JSONL, no extension or .md is still a trace.
        for path in ("plant/e1.ndjson", "plant/e2.JSONL", "plant/trace", "plant/t.md", "x/T.TXT"):
            with self.subTest(path=path):
                problems = g11.check_file(path, (TRACE_NS + "\n").encode())
                self.assertTrue(any("trace-shaped" in p for p in problems), problems)

    def test_trace_shape_in_fixtures_needs_the_marker(self) -> None:
        bad = g11.check_file("tests/fixtures/a.ndjson", (TRACE_NS + "\n").encode())
        self.assertTrue(any("synthetic marker" in p for p in bad), bad)
        ok = g11.check_file("tests/fixtures/a.ndjson", (MARKER + "\n" + TRACE_NS + "\n").encode())
        self.assertEqual(ok, [])

    def test_seq_and_dir_without_t_ns_is_trace_shaped_only_as_jsonl(self) -> None:
        data = (TRACE_LINE + "\n").encode()
        self.assertEqual(g11.check_file("docs/a.ndjson", data), [])
        self.assertTrue(g11.check_file("docs/a.JSONL", data))

    def test_plain_json_lines_fixture_is_not_trace_shaped(self) -> None:
        data = b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
        self.assertEqual(g11.check_file("tests/fixtures/exp.ndjson", data), [])

    def test_bare_home_directory_forms(self) -> None:
        for text in (
            "/ho" + "me/someone",
            "HOME=/ho" + "me/someone\n",
            'x "/ho' + 'me/someone" y',
            "'/ho" + "me/someone'",
            "cd /ho" + "me/someone now",
            "/ro" + "ot",
            "dir: /ro" + "ot\n",
            'is "/ro' + 'ot"',
            "/ro" + "ot/.ssh",
            "/Us" + "ers/someone",
        ):
            with self.subTest(text=text):
                self.assertTrue(g11.check_file("docs/a.md", text.encode()), text)

    def test_home_directory_before_any_delimiter(self) -> None:
        # B3: a doc puts a bare home directory in a code span, before a colon, a comma, a paren.
        h = "/ho" + "me/someone"
        for text in (
            f"your HOME is `{h}`",
            f"PATH=/usr/bin:{h}:/bin",
            f"{h},",
            f"({h})",
            f"see ({h}) now",
            f"someone:x:1000:1000::{h}:/bin/bash",
            f"[{h}]",
            f"{h}\n",
        ):
            with self.subTest(text=text):
                problems = g11.check_file("docs/a.md", text.encode())
                self.assertTrue(any("home-directory" in p for p in problems), (text, problems))

    def test_indented_and_declared_env_dumps(self) -> None:
        keys = ["PA" + "TH", "HO" + "ME", "US" + "ER"]
        forms = {
            "spaces": "\n".join(f"    {k}=x" for k in keys),
            "tab": "\n".join(f"\t{k}=x" for k in keys),
            "declare": "\n".join(f"declare -x {k}=x" for k in keys),
            "indented export": "\n".join(f"  export {k}=x" for k in keys),
        }
        for name, text in forms.items():
            with self.subTest(form=name):
                problems = g11.check_file("docs/a.md", text.encode())
                self.assertTrue(any("environment" in p for p in problems), problems)

    def test_home_lookalikes_pass(self) -> None:
        for text in (
            "/ro" + "oted",
            "/ho" + "mework/x",
            "/ho" + "me/",
            "/ro" + "ot-cause",
            "/ho" + "me/<you>",
        ):
            with self.subTest(text=text):
                self.assertEqual(g11.check_file("docs/a.md", text.encode()), [], text)

    def test_key_value_env_dump(self) -> None:
        keys = ["PA" + "TH", "HO" + "ME", "US" + "ER", "SHE" + "LL", "PW" + "D"]
        three = "\n".join(f"{k}=x" for k in keys[:3]) + "\n"
        self.assertTrue(any("environment" in p for p in g11.check_file("d/a.md", three.encode())))
        exported = "\n".join(f"export {k}=x" for k in keys[2:]) + "\n"
        self.assertTrue(
            any("environment" in p for p in g11.check_file("d/b.md", exported.encode()))
        )
        two = "\n".join(f"{k}=x" for k in keys[:2]) + "\n"
        self.assertEqual(g11.check_file("d/c.md", two.encode()), [])
        self.assertEqual(g11.check_file("d/d.md", (three.replace("=", ":")).encode()), [])

    def test_key_value_env_key_is_the_whole_name(self) -> None:
        # Mutant E5: an unanchored KEY= also matched MANPATH=, OLDPWD= and SUDO_USER=.
        pairs = (("MAN", "PA" + "TH"), ("OLD", "PW" + "D"), ("SUDO_", "US" + "ER"))
        text = "".join(f"{p}{k}=x\n" for p, k in pairs)
        self.assertEqual(g11.check_file("d/a.md", text.encode()), [])

    def test_export_with_any_whitespace_is_an_env_dump(self) -> None:
        # Mutant E6: only `export ` with one space was accepted; the shell takes a tab too.
        text = "\n".join(f"export\t{k}=x" for k in ("US" + "ER", "SHE" + "LL", "PW" + "D"))
        self.assertTrue(any("environment" in p for p in g11.check_file("d/a.sh", text.encode())))

    def test_marker_line_with_an_undecodable_byte_is_not_the_marker(self) -> None:
        # Mutant D1 (errors="ignore"): dropping the byte made the line a valid marker again;
        # replacing it (G11) leaves the line unparseable, so the file does not open with the marker.
        data = MARKER.encode() + b"\xff\n" + TRACE_NS.encode() + b"\n"
        problems = g11.check_file("tests/fixtures/a.ndjson", data)
        self.assertTrue(any("synthetic marker" in p for p in problems), problems)

    def test_one_trace_record_among_other_json_lines_is_trace_shaped(self) -> None:
        # Mutant T5: requiring every JSON line to be a trace record let a pasted trace through.
        data = ('{"jsonrpc":"2.0","id":1,"method":"ping"}\n' + TRACE_NS + "\n").encode()
        problems = g11.check_file("docs/notes.md", data)
        self.assertTrue(any("trace-shaped" in p for p in problems), problems)


def git(
    cwd: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)


def make_env() -> dict[str, str]:
    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }


class TrackedAndMergeTest(unittest.TestCase):
    """R2, R10 (symlinks), R11 against a throwaway repo."""

    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo)
        self.env = make_env()
        self.run_git("init", "-b", "main", ".")
        (self.repo / "README.md").write_text("hello\n", encoding="utf-8")
        self.run_git("add", "-A")
        self.run_git("commit", "-m", "base")

    def run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        done = git(self.repo, *args, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done

    def test_symlink_to_a_home_path_is_checked(self) -> None:
        os.symlink(HOME, self.repo / "link")
        self.run_git("add", "link")
        self.assertTrue(any("link" in p for p in g11.check_tracked(self.repo)))
        self.run_git("commit", "-m", "link")
        head = self.run_git("rev-parse", "HEAD").stdout.strip()
        self.assertTrue(any("link" in p for p in g11.check_commit(self.repo, head)))

    def commit_head(self) -> str:
        return self.run_git("rev-parse", "HEAD").stdout.strip()

    def test_commit_turning_a_file_into_a_symlink_is_checked(self) -> None:
        # B4: a regular file replaced by a symlink is a typechange (T); the filter dropped it.
        (self.repo / "note").write_text("clean\n", encoding="utf-8")
        self.run_git("add", "note")
        self.run_git("commit", "-m", "note")
        (self.repo / "note").unlink()
        os.symlink(HOME, self.repo / "note")
        self.run_git("add", "note")
        self.run_git("commit", "-m", "note becomes a link")
        problems = g11.check_commit(self.repo, self.commit_head())
        self.assertTrue(any("note" in p for p in problems), problems)

    def test_commit_turning_a_symlink_into_a_file_is_checked(self) -> None:
        os.symlink("README.md", self.repo / "note")
        self.run_git("add", "note")
        self.run_git("commit", "-m", "link")
        (self.repo / "note").unlink()
        (self.repo / "note").write_text(GH_TOKEN, encoding="utf-8")
        self.run_git("add", "note")
        self.run_git("commit", "-m", "link becomes a file")
        problems = g11.check_commit(self.repo, self.commit_head())
        self.assertTrue(any("note" in p and "GitHub token" in p for p in problems), problems)

    def test_working_tree_file_replacing_a_tracked_symlink_is_read(self) -> None:
        # B19 (a)
        os.symlink("README.md", self.repo / "note")
        self.run_git("add", "note")
        self.run_git("commit", "-m", "link")
        (self.repo / "note").unlink()
        (self.repo / "note").write_text(GH_TOKEN, encoding="utf-8")
        problems = g11.check_tracked(self.repo)
        self.assertTrue(any("note" in p and "GitHub token" in p for p in problems), problems)

    def test_working_tree_retargeted_symlink_is_read(self) -> None:
        # B19 (b)
        os.symlink("README.md", self.repo / "note")
        self.run_git("add", "note")
        self.run_git("commit", "-m", "link")
        (self.repo / "note").unlink()
        os.symlink(HOME, self.repo / "note")
        problems = g11.check_tracked(self.repo)
        self.assertTrue(any("note" in p and "home-directory" in p for p in problems), problems)

    def test_working_tree_symlink_replacing_a_tracked_file_is_read_as_its_target(self) -> None:
        # B19 (c)
        (self.repo / "README.md").unlink()
        os.symlink(HOME, self.repo / "README.md")
        problems = g11.check_tracked(self.repo)
        self.assertTrue(any("README.md" in p and "home-directory" in p for p in problems), problems)

    def test_staged_leak_hidden_by_the_working_tree_is_found(self) -> None:
        (self.repo / "staged.md").write_text(GH_TOKEN, encoding="utf-8")
        self.run_git("add", "staged.md")
        (self.repo / "staged.md").write_text("clean\n", encoding="utf-8")
        self.assertTrue(any("staged.md" in p for p in g11.check_tracked(self.repo)))

    def test_working_tree_leak_is_still_found(self) -> None:
        (self.repo / "README.md").write_text(GH_TOKEN, encoding="utf-8")
        self.assertTrue(any("README.md" in p for p in g11.check_tracked(self.repo)))

    def test_staged_file_deleted_from_disk_is_found(self) -> None:
        (self.repo / "gone.md").write_text(GH_TOKEN, encoding="utf-8")
        self.run_git("add", "gone.md")
        (self.repo / "gone.md").unlink()
        self.assertTrue(any("gone.md" in p for p in g11.check_tracked(self.repo)))

    def test_clean_repo_has_no_problems(self) -> None:
        self.assertEqual(g11.check_tracked(self.repo), [])

    def test_leak_in_index_and_working_tree_is_named_once(self) -> None:
        # Mutant I4: without the dedupe, a leak present in both copies was reported twice.
        (self.repo / "both.md").write_text(GH_TOKEN, encoding="utf-8")
        self.run_git("add", "both.md")
        (self.repo / "both.md").write_text(GH_TOKEN + "\nmore\n", encoding="utf-8")
        problems = [p for p in g11.check_tracked(self.repo) if "both.md" in p]
        self.assertEqual(len(problems), 1, problems)

    def test_working_tree_symlink_content_is_not_read(self) -> None:
        # Mutant I7: following a working-tree symlink read a file outside the repo, which is not
        # what git would store (it stores the link). The index blob is the clean README.
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside)
        (outside / "secret.txt").write_text(GH_TOKEN, encoding="utf-8")
        (self.repo / "README.md").unlink()
        os.symlink(outside / "secret.txt", self.repo / "README.md")
        problems = g11.check_tracked(self.repo)
        self.assertFalse(any("GitHub token" in p for p in problems), problems)

    def test_non_utf8_file_name_is_checked(self) -> None:
        # Mutants D3, D4, M4: a name that is not UTF-8 crashed the scan, or its blob was not found.
        name = b"leak-\xff.md"
        with open(os.path.join(os.fsencode(self.repo), name), "wb") as f:
            f.write(GH_TOKEN.encode())
        self.run_git("add", "-A")
        self.assertTrue(any("GitHub token" in p for p in g11.check_tracked(self.repo)))
        self.run_git("commit", "-m", "odd name")
        head = self.run_git("rev-parse", "HEAD").stdout.strip()
        self.assertTrue(any("GitHub token" in p for p in g11.check_commit(self.repo, head)))

    def test_commit_adding_a_submodule_gitlink_is_skipped(self) -> None:
        # Mutant M5: a gitlink's id names a commit, not a blob, so reading it crashed the hook.
        base = self.run_git("rev-parse", "HEAD").stdout.strip()
        self.run_git("update-index", "--add", "--cacheinfo", f"160000,{base},sub")
        self.run_git("commit", "-m", "submodule")
        head = self.run_git("rev-parse", "HEAD").stdout.strip()
        self.assertEqual(g11.check_commit(self.repo, head), [])

    def merge_adding(self, rel: str, content: str) -> str:
        self.run_git("checkout", "-q", "-b", "side")
        (self.repo / "side.txt").write_text("s\n", encoding="utf-8")
        self.run_git("add", "-A")
        self.run_git("commit", "-m", "side")
        self.run_git("checkout", "-q", "main")
        (self.repo / "main.txt").write_text("m\n", encoding="utf-8")
        self.run_git("add", "-A")
        self.run_git("commit", "-m", "main")
        self.run_git("merge", "--no-ff", "--no-commit", "side")
        (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / rel).write_text(content, encoding="utf-8")
        self.run_git("add", "-f", rel)
        self.run_git("commit", "-m", "merge")
        return self.run_git("rev-parse", "HEAD").stdout.strip()

    def test_file_added_only_by_a_merge_commit_is_found(self) -> None:
        head = self.merge_adding("runs/trace.jsonl", TRACE_LINE + "\n")
        problems = g11.check_commit(self.repo, head)
        self.assertTrue(any("runs/trace.jsonl" in p for p in problems), problems)

    def test_merge_findings_are_not_duplicated_per_parent(self) -> None:
        head = self.merge_adding("docs/key.md", GH_TOKEN)
        problems = [p for p in g11.check_commit(self.repo, head) if "docs/key.md" in p]
        self.assertEqual(len(problems), 1, problems)

    def test_clean_merge_commit_is_clean(self) -> None:
        head = self.merge_adding("docs/ok.md", "fine\n")
        self.assertEqual(g11.check_commit(self.repo, head), [])


class InstallerTest(unittest.TestCase):
    """R1: the installer follows git's hooks path and says when core.hooksPath is elsewhere."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.env = make_env()
        self.repo = self.tmp / "repo"
        self.run_git(self.tmp, "init", "-b", "main", str(self.repo))

    def run_git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        done = git(cwd, *args, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done

    def install(self, target: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ROOT / "scripts/install-pre-push.sh"), str(target)],
            capture_output=True,
            text=True,
            env=self.env,
        )

    def test_outside_a_repo_the_installer_stops_before_mkdir(self) -> None:
        # B16: `mkdir -p "$(failed)/hooks"` ran with an empty prefix and tried to create /hooks.
        outer = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outer)
        empty = outer / "empty"
        empty.mkdir()
        env = {**self.env, "GIT_CEILING_DIRECTORIES": str(outer)}
        done = subprocess.run(
            [str(ROOT / "scripts/install-pre-push.sh"), str(empty)],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("not a git repository", done.stderr)
        self.assertNotIn("mkdir", done.stderr)
        self.assertEqual(list(empty.iterdir()), [])

    def test_no_warning_when_hooks_path_is_unset(self) -> None:
        done = self.install(self.repo)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("core.hooksPath", done.stderr)
        self.assertTrue((self.repo / ".git/hooks/pre-push").is_file())

    def test_warns_and_still_writes_the_repo_hook_when_hooks_path_is_elsewhere(self) -> None:
        other = self.tmp / "shared-hooks"
        other.mkdir()
        self.run_git(self.repo, "config", "core.hooksPath", str(other))
        done = self.install(self.repo)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("core.hooksPath", done.stderr)
        self.assertTrue((self.repo / ".git/hooks/pre-push").is_file())
        self.assertEqual(list(other.iterdir()), [])

    def test_no_warning_when_hooks_path_is_the_repos_own_directory(self) -> None:
        self.run_git(self.repo, "config", "core.hooksPath", str(self.repo / ".git/hooks"))
        done = self.install(self.repo)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("core.hooksPath", done.stderr)

    def test_no_warning_when_the_repo_is_reached_through_a_symlink(self) -> None:
        # Mutant S5: without `pwd -P` the two spellings of the same directory looked different.
        link = self.tmp / "link"
        os.symlink(self.repo, link)
        hooks = (self.repo / ".git/hooks").resolve()
        self.run_git(self.repo, "config", "core.hooksPath", str(hooks))
        done = self.install(link)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("core.hooksPath", done.stderr)

    def test_missing_hooks_directory_is_created(self) -> None:
        # Mutant S6: `git init` with an empty template leaves no hooks directory.
        shutil.rmtree(self.repo / ".git/hooks")
        done = self.install(self.repo)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.repo / ".git/hooks/pre-push").is_file())

    def test_hooks_path_to_a_missing_directory_warns_and_installs(self) -> None:
        # Mutant S8: a core.hooksPath that does not exist made the installer abort.
        self.run_git(self.repo, "config", "core.hooksPath", str(self.tmp / "missing"))
        done = self.install(self.repo)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("core.hooksPath", done.stderr)
        self.assertTrue((self.repo / ".git/hooks/pre-push").is_file())

    def test_a_dispatcher_that_chains_to_the_repo_hook_blocks_a_push(self) -> None:
        bare = self.tmp / "remote.git"
        self.run_git(self.tmp, "init", "--bare", "-b", "main", str(bare))
        self.run_git(self.repo, "remote", "add", "origin", str(bare))
        shutil.copytree(
            ROOT / "tools", self.repo / "tools", ignore=shutil.ignore_patterns("__pycache__")
        )
        dispatch = self.tmp / "dispatch"
        dispatch.mkdir()
        chain = dispatch / "pre-push"
        chain.write_text(
            '#!/usr/bin/env bash\nexec "$(git rev-parse --git-dir)/hooks/pre-push" "$@"\n',
            encoding="utf-8",
        )
        chain.chmod(0o755)
        self.run_git(self.repo, "config", "core.hooksPath", str(dispatch))
        self.assertEqual(self.install(self.repo).returncode, 0)
        (self.repo / "docs").mkdir()
        (self.repo / "docs/key.md").write_text(GH_TOKEN, encoding="utf-8")
        self.run_git(self.repo, "add", "-A")
        self.run_git(self.repo, "commit", "-m", "leak")
        done = git(self.repo, "push", "origin", "main", env=self.env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("docs/key.md", done.stderr)

    def test_linked_worktree_installs_into_the_shared_hooks_directory(self) -> None:
        self.run_git(
            self.repo,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@e.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "base",
        )
        wt = self.tmp / "wt"
        self.run_git(self.repo, "worktree", "add", "-q", str(wt))
        done = self.install(wt)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.repo / ".git/hooks/pre-push").is_file())


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
            env=self.env,
        )
        self.assertEqual(install.returncode, 0, install.stderr)
        self.assertEqual(install.stderr, "")

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

    def test_leak_edited_into_a_tracked_file_is_refused(self) -> None:
        # B1 (c): the hook must read modified files, not only added ones.
        self.run_git(self.clone, "push", "origin", "main")
        (self.clone / "README.md").write_text("hello\n" + GH_TOKEN + "\n", encoding="utf-8")
        self.run_git(self.clone, "commit", "-am", "edit")
        done = git(self.clone, "push", "origin", "main", env=self.env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("README.md", done.stderr)

    def test_leak_in_the_root_commit_of_a_new_branch_is_refused(self) -> None:
        # B1 (d): without --root the first commit of a branch has no parent to compare with.
        self.run_git(self.clone, "checkout", "-q", "--orphan", "fresh")
        self.run_git(self.clone, "rm", "-rfq", "--cached", ".")  # keep tools/ on disk for the hook
        (self.clone / "leak.md").write_text(GH_TOKEN, encoding="utf-8")
        self.run_git(self.clone, "add", "leak.md")
        self.run_git(self.clone, "commit", "-m", "root")
        done = git(self.clone, "push", "origin", "fresh", env=self.env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("leak.md", done.stderr)
        self.assertNotEqual(
            git(self.bare, "rev-parse", "--verify", "fresh", env=self.env).returncode, 0
        )

    def test_file_that_becomes_a_symlink_to_a_home_path_is_refused(self) -> None:
        # B4: typechange in a pushed commit.
        (self.clone / "note").write_text("clean\n", encoding="utf-8")
        self.run_git(self.clone, "add", "note")
        self.run_git(self.clone, "commit", "-m", "note")
        self.run_git(self.clone, "push", "origin", "main")
        (self.clone / "note").unlink()
        os.symlink(HOME, self.clone / "note")
        self.run_git(self.clone, "add", "note")
        self.run_git(self.clone, "commit", "-m", "note becomes a link")
        done = git(self.clone, "push", "origin", "main", env=self.env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("note", done.stderr)

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

    def test_file_added_only_by_a_merge_is_refused(self) -> None:
        self.run_git(self.clone, "push", "origin", "main")
        self.run_git(self.clone, "checkout", "-q", "-b", "side")
        (self.clone / "side.txt").write_text("s\n", encoding="utf-8")
        self.run_git(self.clone, "add", "-A")
        self.run_git(self.clone, "commit", "-m", "side")
        self.run_git(self.clone, "checkout", "-q", "main")
        (self.clone / "main.txt").write_text("m\n", encoding="utf-8")
        self.run_git(self.clone, "add", "-A")
        self.run_git(self.clone, "commit", "-m", "main")
        self.run_git(self.clone, "push", "origin", "main")
        self.run_git(self.clone, "merge", "--no-ff", "--no-commit", "side")
        (self.clone / "runs").mkdir()
        (self.clone / "runs/trace.jsonl").write_text(TRACE_LINE + "\n", encoding="utf-8")
        self.run_git(self.clone, "add", "-f", "runs/trace.jsonl")
        self.run_git(self.clone, "commit", "-m", "merge")
        done = git(self.clone, "push", "origin", "main", env=self.env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("runs/trace.jsonl", done.stderr)

    def test_install_refuses_to_overwrite_a_different_hook(self) -> None:
        hook = self.clone / ".git/hooks/pre-push"
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        done = subprocess.run(
            [str(ROOT / "scripts/install-pre-push.sh"), str(self.clone)],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(hook.read_text(encoding="utf-8"), "#!/bin/sh\nexit 0\n")


if __name__ == "__main__":
    unittest.main()
