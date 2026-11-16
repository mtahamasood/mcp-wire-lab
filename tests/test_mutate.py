"""tools/mutate.py: one exact replacement per mutant, run in a copy, restored and compared."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MUTATE = ROOT / "tools" / "mutate.py"

CALC = "def add(a, b):\n    return a + b\n"
CHECK = (
    "import unittest\n"
    "from calc import add\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_add(self):\n"
    "        self.assertEqual(add(2, 3), 5)\n"
)
LOOSE = (
    "import unittest\n"
    "from calc import add\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_add(self):\n"
    "        self.assertTrue(add(2, 3) is not None)\n"
)
CMD = f"{sys.executable} -m unittest test_calc"
LOOSE_CMD = f"{sys.executable} -m unittest test_loose"


class MutateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.proj = Path(self._tmp.name) / "proj"
        self.proj.mkdir()
        (self.proj / "calc.py").write_text(CALC)
        (self.proj / "test_calc.py").write_text(CHECK)
        (self.proj / "test_loose.py").write_text(LOOSE)

    def mutant(
        self, id: str, old: str = "a + b", new: str = "a - b", **extra: Any
    ) -> dict[str, Any]:
        return {"id": id, "file": "calc.py", "old": old, "new": new, "command": CMD, **extra}

    def run_tool(
        self,
        mutants: list[dict[str, Any]],
        *args: str,
        links: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        spec = Path(self._tmp.name) / "spec.json"
        spec.write_text(json.dumps({"links": links or [], "mutants": mutants}))
        return subprocess.run(
            [sys.executable, str(MUTATE), "--root", str(self.proj), *args, str(spec)],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

    def python_command(self, code: str, *argv: str) -> str:
        """A test command that runs `code` with Python, one argument per `argv`."""
        return shlex.join([sys.executable, "-c", code, *argv])

    def same_effect(self, id: str, **extra: Any) -> dict[str, Any]:
        """A mutant that changes nothing, signed equivalent, so a run of it exits 0."""
        return self.mutant(
            id, old="return a + b", new="return a + b  # same", equivalent="comment only", **extra
        )

    def test_applies_one_exact_replacement(self) -> None:
        # The replacement reaches the test: the exact-assert test kills it.
        done = self.run_tool([self.mutant("M1")])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("mutants: 1 killed: 1 survived: 0 errors: 0", done.stdout)
        # A replacement that changes nothing observable survives: only the one place is edited.
        same = self.mutant("M2", old="return a + b", new="return a + b  # same")
        done = self.run_tool([same])
        self.assertIn("mutants: 1 killed: 0 survived: 1 errors: 0", done.stdout)

    def test_missing_or_ambiguous_text_is_an_error(self) -> None:
        (self.proj / "calc.py").write_text(CALC + "# a + b\n")
        done = self.run_tool([self.mutant("AMB"), self.mutant("GONE", old="not there", new="x")])
        self.assertEqual(done.returncode, 1)
        self.assertIn("mutants: 2 killed: 0 survived: 0 errors: 2", done.stdout)
        self.assertRegex(done.stdout, r"\| AMB \| calc.py \| error \|")
        self.assertRegex(done.stdout, r"\| GONE \| calc.py \| error \|")

    def test_restores_original_and_checks_with_cmp(self) -> None:
        before = (self.proj / "calc.py").read_bytes()
        done = self.run_tool([self.mutant("M1")])
        self.assertEqual((self.proj / "calc.py").read_bytes(), before)
        self.assertIn("restored byte-identical", done.stderr)
        self.assertNotIn("NOT restored", done.stdout + done.stderr)

    def test_refuses_when_runs_dir_has_leftovers(self) -> None:
        (self.proj / "runs").mkdir()
        (self.proj / "runs" / "old-run").mkdir()
        done = self.run_tool([self.mutant("M1")])
        self.assertEqual(done.returncode, 2)
        self.assertIn("runs/", done.stderr)
        self.assertNotIn("| M1 |", done.stdout)

    def test_reports_killed_and_survived(self) -> None:
        loose = self.mutant("LOOSE", command=LOOSE_CMD, note="weak assertion")
        done = self.run_tool([self.mutant("STRONG"), loose])
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("mutants: 2 killed: 1 survived: 1 errors: 0", done.stdout)
        self.assertIn("weak assertion", done.stdout)
        self.assertRegex(done.stdout, r"\| STRONG \| calc.py \| killed \|")
        self.assertRegex(done.stdout, r"\| LOOSE \| calc.py \| survived \|")

    def test_baseline_red_stops_with_2(self) -> None:
        (self.proj / "calc.py").write_text("def add(a, b):\n    return 0\n")
        done = self.run_tool([self.mutant("M1", old="return 0", new="return 1")])
        self.assertEqual(done.returncode, 2)
        self.assertIn("baseline", done.stderr)

    def test_timeout_is_reported_separately(self) -> None:
        (self.proj / "test_slow.py").write_text(
            "import time, unittest\n"
            "from calc import add\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_slow(self):\n"
            "        if add(1, 1) != 2:\n"
            "            time.sleep(30)\n"
        )
        slow = self.mutant("SLOW", command=f"{sys.executable} -m unittest test_slow", timeout=1)
        done = self.run_tool([slow])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(done.stdout, r"\| SLOW \| calc.py \| killed \(timeout\) \|")
        self.assertIn("mutants: 1 killed: 1 survived: 0 errors: 0", done.stdout)

    def test_marked_equivalent_does_not_fail_the_run(self) -> None:
        same = self.mutant(
            "EQ", old="return a + b", new="return a + b  # same", equivalent="comment only"
        )
        done = self.run_tool([self.mutant("STRONG"), same])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(done.stdout, r"\| EQ \| calc.py \| equivalent \|.*comment only")
        self.assertIn("mutants: 2 killed: 1 survived: 0 errors: 0 equivalent: 1", done.stdout)
        # An equivalent mark needs a reason; an empty one is a bad spec.
        bad = self.mutant("EQ2", equivalent="")
        self.assertEqual(self.run_tool([bad]).returncode, 2)

    def test_killed_row_names_failing_tests(self) -> None:
        done = self.run_tool([self.mutant("M1")])
        self.assertIn("test_add", done.stdout)

    def test_only_selects_mutants(self) -> None:
        done = self.run_tool([self.mutant("A"), self.mutant("B")], "--only", "B")
        self.assertIn("mutants: 1 ", done.stdout)
        self.assertNotIn("| A |", done.stdout)

    def test_help_prints_usage(self) -> None:
        done = subprocess.run(
            [sys.executable, str(MUTATE), "-h"], capture_output=True, text=True, timeout=20
        )
        self.assertEqual(done.returncode, 0)
        self.assertIn("Usage:", done.stdout)

    # -- Stage B of phase 8 (D9): the survivors of the mutation of this file ---------------

    def test_a_restore_that_does_not_match_the_original_stops_the_run(self) -> None:
        # C160: the command changes the real file while it runs, so the restored copy differs
        # from it: the run stops at once (exit 2, no table) and says the file was not restored.
        touch = self.python_command(
            f"open({str(self.proj / 'calc.py')!r}, 'a').write('# changed under the run')"
        )
        mutants = [self.mutant("M1", command=touch), self.mutant("M2", command=touch)]
        done = self.run_tool(mutants)
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("NOT restored: calc.py", done.stderr)
        self.assertEqual(done.stdout, "")
        self.assertNotIn("M2", done.stderr)

    def test_runs_is_empty_and_present_before_every_command(self) -> None:
        # C161: each command finds an empty runs/ in the copy, so a recording left by the
        # previous command (or the baseline) cannot make it pass or fail; two distinct commands
        # and two mutants of one of them all see a clean folder.
        for name in ("test_runs_a.py", "test_runs_b.py"):
            (self.proj / name).write_text(
                "import os, unittest\n\n"
                "class T(unittest.TestCase):\n"
                "    def test_runs(self):\n"
                "        self.assertEqual(os.listdir('runs'), [])\n"
                "        open('runs/recording', 'w').close()\n"
            )
        mutants = [
            self.same_effect("A1", command=f"{sys.executable} -m unittest test_runs_a"),
            self.same_effect("A2", command=f"{sys.executable} -m unittest test_runs_a"),
            self.same_effect("B1", command=f"{sys.executable} -m unittest test_runs_b"),
        ]
        done = self.run_tool(mutants)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("mutants: 3 killed: 0 survived: 0 errors: 0 equivalent: 3", done.stdout)

    def test_baseline_runs_once_per_distinct_command(self) -> None:
        # C162: three mutants of one command make four runs of it: one baseline and one each.
        log = Path(self._tmp.name) / "log.txt"
        command = self.python_command(f"open({str(log)!r}, 'a').write('x')")
        done = self.run_tool([self.same_effect(f"E{i}", command=command) for i in range(3)])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(log.read_text(), "xxxx")

    def test_a_command_killed_by_a_signal_is_a_kill(self) -> None:
        # C162: a negative exit status (the command died of SIGKILL) is a failure, not a pass.
        code = (
            "import os, signal; from calc import add; "
            "os.kill(os.getpid(), signal.SIGKILL) if add(2, 3) != 5 else None"
        )
        done = self.run_tool([self.mutant("SIG", command=self.python_command(code))])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"\| SIG \| calc.py \| killed \|.*exit -9")

    def test_a_signed_mutant_that_is_killed_is_reported_killed_and_says_so(self) -> None:
        # C162: signing a mutant equivalent does not hide a test that kills it.
        signed = self.mutant("SIGNED", equivalent="thought to change nothing")
        done = self.run_tool([signed])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"\| SIGNED \| calc.py \| killed \|")
        self.assertIn("marked equivalent but killed", done.stdout)
        self.assertIn("mutants: 1 killed: 1 survived: 0 errors: 0 equivalent: 0", done.stdout)

    def test_copy_of_a_repository_holds_tracked_and_untracked_files_but_not_ignored_ones(
        self,
    ) -> None:
        # C163: a git repository is copied as git sees it: tracked files, files not yet
        # tracked, and not what .gitignore names. The command is the check.
        git = ["git", "-C", str(self.proj)]
        subprocess.run([*git, "init", "-q"], check=True)
        (self.proj / ".gitignore").write_text("ignored.txt\n")
        for name in ("tracked.txt", "untracked.txt", "ignored.txt"):
            (self.proj / name).write_text(name)
        subprocess.run([*git, "add", ".gitignore", "tracked.txt", "calc.py"], check=True)
        check = self.python_command(
            "import os, sys; sys.exit(0 if os.path.exists('tracked.txt') "
            "and os.path.exists('untracked.txt') and os.path.exists('calc.py') "
            "and not os.path.exists('ignored.txt') and not os.path.exists('.git') else 1)"
        )
        done = self.run_tool([self.same_effect("GIT", command=check)])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_a_folder_inside_a_repository_is_copied_whole_not_by_the_repositorys_list(
        self,
    ) -> None:
        # C163: only a repository's own root is listed by git; a subfolder is walked.
        outer = Path(self._tmp.name) / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        subprocess.run(["git", "-C", str(outer), "init", "-q"], check=True)
        (outer / ".gitignore").write_text("ignored.txt\n")
        (inner / "ignored.txt").write_text("x")
        (inner / "calc.py").write_text(CALC)
        (inner / "test_calc.py").write_text(CHECK)
        check = self.python_command(
            "import os, sys; sys.exit(0 if os.path.exists('ignored.txt') else 1)"
        )
        done = self.run_tool([self.same_effect("SUB", command=check)], "--root", str(inner))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_a_plain_copy_leaves_out_git_and_bytecode_folders(self) -> None:
        # C163: outside a repository the copy is a walk that skips .git and __pycache__.
        (self.proj / ".git").mkdir()
        (self.proj / ".git" / "config").write_text("")
        (self.proj / "__pycache__").mkdir()
        (self.proj / "__pycache__" / "calc.pyc").write_text("")
        check = self.python_command(
            "import os, sys; sys.exit(0 if not os.path.exists('.git') "
            "and not os.path.exists('__pycache__') and os.path.exists('calc.py') else 1)"
        )
        done = self.run_tool([self.same_effect("WALK", command=check)])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_linked_paths_are_linked_not_copied_and_a_missing_one_is_refused(self) -> None:
        # C163: a linked path is a symlink to the real one; a sibling that only shares its
        # first letters is copied as usual; a link to nothing stops the run.
        (self.proj / "lib").mkdir()
        (self.proj / "lib" / "a.txt").write_text("a")
        (self.proj / "lib2").mkdir()
        (self.proj / "lib2" / "b.txt").write_text("b")
        check = self.python_command(
            "import os, sys; sys.exit(0 if os.path.islink('lib') "
            "and os.path.exists('lib/a.txt') and not os.path.islink('lib2') "
            "and os.path.exists('lib2/b.txt') else 1)"
        )
        done = self.run_tool([self.same_effect("LINK", command=check)], links=["lib"])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        done = self.run_tool([self.same_effect("GONE", command=check)], links=["nowhere"])
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("link path does not exist: nowhere", done.stderr)

    def test_command_is_split_like_a_shell_and_runs_with_bytecode_off(self) -> None:
        # C164: quoted arguments stay whole; the command gets PYTHONDONTWRITEBYTECODE=1 even
        # when the caller's environment lacks it (so a mutant's bytecode cannot outlive it).
        code = (
            "import os, sys; sys.exit(0 if os.environ.get('PYTHONDONTWRITEBYTECODE') == '1' "
            "and sys.argv[1:] == ['two words'] else 1)"
        )
        env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
        done = self.run_tool(
            [self.same_effect("ENV", command=self.python_command(code, "two words"))], env=env
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_command_gets_no_stdin_and_odd_output_does_not_stop_the_tool(self) -> None:
        # C164: a command that reads stdin sees end of file at once, even when the tool's own
        # stdin is an open pipe; output that is not UTF-8 is shown replaced, not a crash.
        reads = self.python_command("import sys; sys.stdin.read()")
        odd = self.python_command("import sys; sys.stdout.buffer.write(b'\\xff\\xfe\\n')")
        spec = Path(self._tmp.name) / "spec.json"
        mutants = [self.same_effect("STDIN", command=reads), self.same_effect("ODD", command=odd)]
        spec.write_text(json.dumps({"mutants": mutants}))
        argv = [sys.executable, str(MUTATE), "--root", str(self.proj), "--timeout", "10", str(spec)]
        with subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        ) as tool:
            tool.wait(timeout=60)  # stdin stays open until here: only a closed stdin ends it
            assert tool.stdout is not None and tool.stderr is not None
            out, err = tool.stdout.read(), tool.stderr.read()
        self.assertEqual(tool.returncode, 0, out + err)
        self.assertIn("equivalent: 2", out)

    def test_timeout_flag_applies_when_a_mutant_has_none_and_kills_what_the_command_started(
        self,
    ) -> None:
        # C164: --timeout bounds a command, and the whole process group dies with it (a
        # grandchild holding the output pipe open must not make the tool wait for it).
        (self.proj / "test_grandchild.py").write_text(
            "import subprocess, sys, time, unittest\n"
            "from calc import add\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_grandchild(self):\n"
            "        if add(1, 1) != 2:\n"
            "            subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(25)'])\n"
            "            time.sleep(25)\n"
        )
        grandchild = self.mutant(
            "GRAND", command=f"{sys.executable} -m unittest test_grandchild"
        )
        started = time.monotonic()
        done = self.run_tool([grandchild], "--timeout", "1")
        self.assertLess(time.monotonic() - started, 15)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"\| GRAND \| calc.py \| killed \(timeout\) \|")

    def own_session_child_test(
        self, name: str, hang: bool, holds_pipe: bool
    ) -> tuple[dict[str, Any], Path]:
        """A mutant whose test starts a child in a session of its own (as the tap starts its
        upstream; one that ignores SIGTERM, and holds the output pipe open if `holds_pipe`)
        and writes its pid to a file; when mutated (`add` is wrong) the test then hangs."""
        pidfile = Path(self._tmp.name) / f"{name}.pid"
        # holding the pipe only when mutated: an unmutated run that left it is a red baseline
        quiet_out = "subprocess.DEVNULL"
        held = f"None if add(1, 1) != 2 else {quiet_out}" if holds_pipe else quiet_out
        quiet = f"stdout={held}, stderr={held}"
        (self.proj / f"test_{name}.py").write_text(
            "import os, subprocess, sys, time, unittest\n"
            "from calc import add\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_child(self):\n"
            "        child = subprocess.Popen(\n"
            "            [sys.executable, '-c', 'import signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(300)'],\n"
            f"            start_new_session=True, {quiet})\n"
            f"        open({str(pidfile)!r}, 'a').write(f'{{child.pid}}\\n')\n"
            f"        if add(1, 1) != 2 and {hang!r}:\n"
            "            time.sleep(300)\n"
            "        self.assertEqual(add(1, 1), 2)\n"
        )
        command = f"{sys.executable} -m unittest test_{name}"
        return self.mutant(name.upper(), command=command), pidfile

    def assert_dead_after(self, pidfile: Path) -> None:
        pids = [int(x) for x in pidfile.read_text().split()]
        self.assertEqual(len(pids), 2, "the baseline and the mutant's run each started one")

        def alive(pid: int) -> bool:
            try:
                state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
            except OSError:
                return False
            return state != "Z"

        def reap(pid: int) -> None:
            if alive(pid):
                os.kill(pid, 9)

        for pid in pids:
            self.addCleanup(reap, pid)
        deadline = time.monotonic() + 3
        while any(alive(pid) for pid in pids) and time.monotonic() < deadline:
            time.sleep(0.05)
        for pid in pids:
            self.assertFalse(alive(pid), f"pid {pid}, started by the command, outlived it")

    @unittest.skipUnless(Path("/proc/self/environ").exists(), "needs /proc")
    def test_a_timeout_kills_a_child_in_a_session_of_its_own(self) -> None:
        # P8-MU-1: the process group is not all of what a command starts. The tap starts its
        # upstream in a group of its own; that child must not outlive the mutant's timeout.
        # The child also holds the command's output open, as a tap's upstream does: the tool
        # must not wait for it after the timeout.
        mutant, pidfile = self.own_session_child_test("hang", hang=True, holds_pipe=True)
        started = time.monotonic()
        done = self.run_tool([mutant], "--timeout", "2")
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"\| HANG \| calc.py \| killed \(timeout\) \|")
        self.assert_dead_after(pidfile)

    @unittest.skipUnless(Path("/proc/self/environ").exists(), "needs /proc")
    def test_a_child_left_behind_by_a_command_that_ended_is_killed(self) -> None:
        # P8-MU-1: a command that ends with a child still running leaves it for the next
        # mutant's run to meet; each run ends with nothing of it alive.
        mutant, pidfile = self.own_session_child_test("left", hang=False, holds_pipe=False)
        done = self.run_tool([mutant])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"\| LEFT \| calc.py \| killed \|")
        self.assert_dead_after(pidfile)


if __name__ == "__main__":
    unittest.main()
