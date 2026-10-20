"""C1-C6: the tap forwards bytes exactly, records them truly, and keeps the child's lifecycle."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.fake_children import non_utf8_writer, partial_writer, stderr_writer

ROOT = Path(__file__).resolve().parent.parent
CHILDREN = ROOT / "tests/fake_children"
TIMEOUT = 30

# Non-canonical JSON: extra spaces, unsorted keys, an escaped and a literal é, and a \r used
# as whitespace inside the object. Re-serializing any of these lines changes its bytes.
NON_CANONICAL = (
    b'{"jsonrpc" : "2.0",   "method":"initialize", "id":0}\n'
    b'{"z": 1, "a": 2, "name": "caf\\u00e9"}\n'
    b'{"name":"caf\xc3\xa9",\r"id":1}\r\n'
    b'{ "params" : { "b" : [ 1 , 2 ] } , "id" : 2 }\n'
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw_bytes(record: dict[str, Any]) -> bytes:
    if "raw" in record:
        return str(record["raw"]).encode("utf-8")
    return base64.b64decode(record["raw_b64"])


class TapRun:
    """One run of the tap around a child, with its outputs and trace."""

    def __init__(self, tmp: Path, child: list[str], stdin: bytes) -> None:
        self.trace_path = tmp / "trace.jsonl"
        self.command = [sys.executable, *child]
        done = subprocess.run(
            [sys.executable, "-m", "tap", "--trace", str(self.trace_path), "--", *self.command],
            cwd=ROOT,
            input=stdin,
            capture_output=True,
            timeout=TIMEOUT,
        )
        self.code = done.returncode
        self.stdout = done.stdout
        self.stderr = done.stderr
        lines = self.trace_path.read_bytes().split(b"\n")
        self.records: list[dict[str, Any]] = [json.loads(line) for line in lines if line]

    def frames(self, direction: str) -> list[dict[str, Any]]:
        return [r for r in self.records if r["dir"] == direction]

    def stream(self, direction: str) -> bytes:
        return b"".join(raw_bytes(r) for r in self.frames(direction))


class TapTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.received = self.tmp / "received.bin"
        self.sent = self.tmp / "sent.bin"

    def run_tap(self, child: str, *args: str, stdin: bytes = b"") -> TapRun:
        return TapRun(self.tmp, [str(CHILDREN / child), *args], stdin)

    def run_echo(self, stdin: bytes, *args: str) -> TapRun:
        return self.run_tap("echo.py", str(self.received), str(self.sent), *args, stdin=stdin)


class ByteExactTest(TapTestCase):
    """C1."""

    def test_both_directions_are_byte_exact(self) -> None:
        run = self.run_echo(NON_CANONICAL, "--prefix", "")
        self.assertEqual(run.code, 0, run.stderr)
        self.assertEqual(sha(self.received.read_bytes()), sha(NON_CANONICAL), "c2s changed")
        self.assertEqual(sha(run.stdout), sha(self.sent.read_bytes()), "s2c changed")
        self.assertEqual(run.stdout, NON_CANONICAL)

    def test_raw_fields_rebuild_each_stream(self) -> None:
        run = self.run_echo(NON_CANONICAL, "--prefix", "")
        self.assertEqual(run.stream("c2s"), NON_CANONICAL)
        self.assertEqual(run.stream("s2c"), run.stdout)
        for record in run.frames("c2s"):
            self.assertEqual(record["bytes"], len(raw_bytes(record)))
            self.assertIsNotNone(record["json"], record)


class DirectionAndOrderTest(TapTestCase):
    """C2."""

    LINES = [b'{"id":1}\n', b'{"id":2}\n', b'{"id":3}\n']

    def test_direction_and_order(self) -> None:
        run = self.run_echo(b"".join(self.LINES))
        self.assertEqual(run.code, 0, run.stderr)
        seqs = [r["seq"] for r in run.records]
        self.assertEqual(seqs, list(range(len(run.records))))
        times = [r["t_ns"] for r in run.records]
        self.assertEqual(times, sorted(times))
        c2s, s2c = run.frames("c2s"), run.frames("s2c")
        self.assertEqual([raw_bytes(r) for r in c2s], self.LINES)
        self.assertEqual([raw_bytes(r) for r in s2c], [b"echo:" + line for line in self.LINES])
        for sent, echoed in zip(c2s, s2c, strict=True):
            self.assertLess(sent["seq"], echoed["seq"], "a reply is recorded before its cause")

    def test_spawn_first_exit_last(self) -> None:
        run = self.run_echo(b"")
        first, last = run.records[0], run.records[-1]
        self.assertEqual((first["dir"], first["event"]), ("tap", "spawn"))
        self.assertEqual(first["argv"], run.command)
        self.assertEqual((last["dir"], last["event"], last["code"]), ("tap", "exit", 0))


class PartialLineTest(TapTestCase):
    """C3."""

    def test_child_partial_final_line(self) -> None:
        run = self.run_tap("partial_writer.py")
        self.assertEqual(run.stdout, partial_writer.OUTPUT)
        last = run.frames("s2c")[-1]
        self.assertTrue(last.get("partial"), last)
        self.assertEqual(last["raw"], '{"id":2,"res')
        self.assertEqual(last["bytes"], len(b'{"id":2,"res'))
        self.assertIsNone(last["json"])
        self.assertEqual(run.stream("s2c"), partial_writer.OUTPUT)
        self.assertNotIn("partial", run.frames("s2c")[0])

    def test_client_partial_final_line(self) -> None:
        stdin = b'{"id":1}\n{"id":2'
        run = self.run_echo(stdin)
        self.assertEqual(self.received.read_bytes(), stdin)
        last = run.frames("c2s")[-1]
        self.assertTrue(last.get("partial"), last)
        self.assertEqual(last["raw"], '{"id":2')
        self.assertEqual(run.stdout, b'echo:{"id":1}\necho:{"id":2')


class NonUtf8AndNonJsonTest(TapTestCase):
    """C4."""

    def test_child_frames(self) -> None:
        run = self.run_tap("non_utf8_writer.py")
        self.assertEqual(run.stdout, b"".join(non_utf8_writer.FRAMES))
        bad, text, good = run.frames("s2c")
        self.assertNotIn("raw", bad)
        self.assertEqual(base64.b64decode(bad["raw_b64"]), non_utf8_writer.FRAMES[0])
        self.assertIsNone(bad["json"])
        self.assertIn("UTF-8", bad["parse_error"])
        self.assertEqual(text["raw"], "this is not json\n")
        self.assertIsNone(text["json"])
        self.assertTrue(text["parse_error"])
        self.assertEqual(good["json"], {"ok": True})
        self.assertNotIn("parse_error", good)

    def test_client_non_utf8_is_forwarded_unchanged(self) -> None:
        stdin = b"\xff\x00\xc3\x28 binary\n"
        run = self.run_echo(stdin)
        self.assertEqual(self.received.read_bytes(), stdin)
        self.assertEqual(run.stdout, b"echo:" + stdin)
        (record,) = run.frames("c2s")
        self.assertEqual(base64.b64decode(record["raw_b64"]), stdin)

    def test_non_standard_constants_are_not_json(self) -> None:
        run = self.run_echo(b'{"x": NaN}\n')
        (record,) = run.frames("c2s")
        self.assertIsNone(record["json"])
        self.assertIn("NaN", record["parse_error"])


class ExitCodeTest(TapTestCase):
    """C5, and the rest of D4's lifecycle."""

    def test_exit_code_is_propagated(self) -> None:
        run = self.run_tap("exit_with.py", "3")
        self.assertEqual(run.code, 3)
        self.assertEqual(run.records[-1]["code"], 3)

    def test_child_killed_by_sigterm_gives_143(self) -> None:
        run = self.run_tap("exit_with.py", f"-{int(signal.SIGTERM)}")
        self.assertEqual(run.code, 143)
        self.assertEqual(run.records[-1], {**run.records[-1], "code": 143, "signal": 15})

    def test_relaying_continues_after_stdin_eof(self) -> None:
        run = self.run_echo(b'{"id":1}\n', "--say-eof")
        self.assertEqual(run.code, 0, run.stderr)
        self.assertEqual(run.stdout, b'echo:{"id":1}\neof\n')
        self.assertEqual(raw_bytes(run.frames("s2c")[-1]), b"eof\n")

    def test_signals_are_forwarded(self) -> None:
        for sig in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=sig.name):
                trace = self.tmp / f"{sig.name}.jsonl"
                child = str(CHILDREN / "signal_waiter.py")
                tap = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "tap",
                        "--trace",
                        str(trace),
                        "--",
                        sys.executable,
                        child,
                    ],
                    cwd=ROOT,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                assert tap.stdout is not None
                self.assertEqual(tap.stdout.readline(), b"ready\n")
                tap.send_signal(sig)
                out, err = tap.communicate(timeout=TIMEOUT)
                self.assertEqual(out, f"got {sig.name}\n".encode(), err)
                self.assertEqual(tap.returncode, 10 + sig, err)


class StderrTest(TapTestCase):
    """C6."""

    def test_stderr_is_relayed_and_recorded_not_mixed(self) -> None:
        run = self.run_tap("stderr_writer.py")
        self.assertEqual(run.code, 0, run.stderr)
        self.assertEqual(run.stderr, stderr_writer.STDERR_BYTES)
        self.assertEqual(run.stdout, stderr_writer.STDOUT_BYTES)
        self.assertNotIn(b"warn", run.stdout)
        self.assertEqual(run.stream("stderr"), stderr_writer.STDERR_BYTES)
        self.assertEqual(run.stream("s2c"), stderr_writer.STDOUT_BYTES)
        self.assertTrue(run.frames("stderr")[-1].get("partial"))


class UsageTest(unittest.TestCase):
    def tap(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, "-m", "tap", *args], cwd=ROOT, capture_output=True, timeout=TIMEOUT
        )

    def test_missing_separator_is_a_usage_error(self) -> None:
        done = self.tap("--trace", "x.jsonl", "cat")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn(b"usage:", done.stderr)

    def test_missing_command_is_a_usage_error(self) -> None:
        done = self.tap("--trace", "x.jsonl", "--")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn(b"usage:", done.stderr)

    def test_unstartable_command_exits_127_and_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "t.jsonl"
            done = self.tap("--trace", str(trace), "--", str(Path(tmp) / "no-such-server"))
            self.assertEqual(done.returncode, 127)
            records = [json.loads(line) for line in trace.read_text().splitlines()]
            self.assertEqual([r["event"] for r in records], ["spawn", "exit"])
            self.assertEqual(records[-1]["code"], 127)


if __name__ == "__main__":
    unittest.main()
