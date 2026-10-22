"""C19: `-h` / `--help` print the usage on stdout and exit 0; bad options still fail."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 20

TOOLS: dict[str, list[str]] = {
    "tap": [sys.executable, "-m", "tap"],
    "tap.show": [sys.executable, "-m", "tap.show"],
    "tap.check": [sys.executable, "-m", "tap.check"],
    "tap.diff": [sys.executable, "-m", "tap.diff"],
    "sdk client": ["node", "clients/sdk/src/main.ts"],
    "client": [sys.executable, "-m", "client"],
    "record.sh": ["scripts/record.sh"],
    "bootstrap.sh": ["scripts/bootstrap.sh"],
    "gate.sh": ["scripts/gate.sh"],
}


def run(command: list[str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*command, *args], cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT
    )


class HelpTest(unittest.TestCase):
    def test_help_prints_usage_on_stdout_and_exits_0(self) -> None:
        for name, command in TOOLS.items():
            for flag in ("-h", "--help"):
                with self.subTest(tool=name, flag=flag):
                    done = run(command, flag)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertIn("usage:", done.stdout)
                    self.assertEqual(done.stderr, "")

    def test_client_help_after_a_mode(self) -> None:
        done = run(TOOLS["client"], "tour", "--help")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("usage:", done.stdout)

    def test_record_help_writes_no_run_folder(self) -> None:
        before = set((ROOT / "runs").glob("*")) if (ROOT / "runs").exists() else set()
        run(TOOLS["record.sh"], "--help")
        after = set((ROOT / "runs").glob("*")) if (ROOT / "runs").exists() else set()
        self.assertEqual(before, after)

    def test_help_after_the_separator_belongs_to_the_server_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace = str(Path(tmp) / "t.jsonl")
            done = run(TOOLS["tap"], "--trace", trace, "--",
                      sys.executable, "-c", "import sys; print(sys.argv[1])", "--help")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout.strip(), "--help")

    def test_bad_options_still_fail(self) -> None:
        for name in ("tap", "tap.show", "tap.check", "tap.diff", "sdk client", "client"):
            with self.subTest(tool=name):
                done = run(TOOLS[name], "--nonsense")
                self.assertEqual(done.returncode, 2)
                self.assertIn("usage:", done.stderr)
        for script in ("record.sh", "bootstrap.sh", "gate.sh"):
            with self.subTest(tool=script):
                done = run(TOOLS[script], "--nonsense")
                self.assertEqual(done.returncode, 1)
                self.assertIn("usage:", done.stderr)


if __name__ == "__main__":
    unittest.main()
