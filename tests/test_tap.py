"""C1-C6, C17: the tap forwards bytes exactly, records them truly, keeps the child's lifecycle."""

from __future__ import annotations

import base64
import fcntl
import functools
import hashlib
import json
import os
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

import tap.__main__ as tap_main
from tests.fake_children import (
    flood,
    non_utf8_writer,
    partial_writer,
    signal_waiter,
    split_writer,
    stderr_writer,
)

ROOT = Path(__file__).resolve().parent.parent
CHILDREN = ROOT / "tests/fake_children"
TIMEOUT = 30
SIGNAL_TIMEOUT = 5
LINE_BREAKS_JSON_KEEPS = ("\x85", " ", " ")

# Non-canonical JSON: extra spaces, unsorted keys, an escaped and a literal é, and a \r used
# as whitespace inside the object. Re-serializing any of these lines changes its bytes.
NON_CANONICAL = (
    b'{"jsonrpc" : "2.0",   "method":"initialize", "id":0}\n'
    b'{"z": 1, "a": 2, "name": "caf\\u00e9"}\n'
    b'{"name":"caf\xc3\xa9",\r"id":1}\r\n'
    b'{ "params" : { "b" : [ 1 , 2 ] } , "id" : 2 }\n'
)

# A child that copies stdin to stdout unchanged, for runs that need no files from the child.
CAT = "import os\nwhile c := os.read(0, 65536):\n    os.write(1, c)\n"
DEEP = b"[" * 20_000 + b"]" * 20_000 + b"\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw_bytes(record: dict[str, Any]) -> bytes:
    if "raw" in record:
        return str(record["raw"]).encode("utf-8")
    return base64.b64decode(record["raw_b64"])


def _not_json(name: str) -> Any:
    raise ValueError(f"{name} in the trace is not JSON")


def strict_records(trace: bytes) -> list[dict[str, Any]]:
    """Parse a trace as strict JSON Lines: `NaN` and `Infinity` are refused."""
    return [json.loads(line, parse_constant=_not_json) for line in trace.split(b"\n") if line]


def send_signal(proc: subprocess.Popen[bytes], sig: int) -> None:
    proc.send_signal(sig)


def tap_command(trace: Path, *command: str) -> list[str]:
    return [sys.executable, "-m", "tap", "--trace", str(trace), "--", *command]


class TapRun:
    """One run of the tap around a child, with its outputs and trace."""

    def __init__(self, tmp: Path, child: list[str], stdin: bytes) -> None:
        self.trace_path = tmp / "trace.jsonl"
        self.command = [sys.executable, *child]
        start = time.monotonic_ns()
        done = subprocess.run(
            tap_command(self.trace_path, *self.command),
            cwd=ROOT,
            input=stdin,
            capture_output=True,
            timeout=TIMEOUT,
        )
        self.wall_ns = time.monotonic_ns() - start
        self.code = done.returncode
        self.stdout = done.stdout
        self.stderr = done.stderr
        self.trace = self.trace_path.read_bytes()
        self.records = strict_records(self.trace)

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

    def check_trace(self, run: TapRun) -> None:
        """What every trace must satisfy (C2, C4): strict JSON was checked when it was read."""
        self.assertEqual([r["seq"] for r in run.records], list(range(len(run.records))))
        times = [r["t_ns"] for r in run.records]
        self.assertEqual(times, sorted(times))
        self.assertGreater(times[0], 0, "t_ns is not measured from the tap's start")
        self.assertLess(times[-1], run.wall_ns, "t_ns is not measured from the tap's start")
        for record in run.records:
            if record["dir"] != "tap":
                self.assertEqual(record["bytes"], len(raw_bytes(record)), record["seq"])
        self.assertEqual(run.records[-1]["event"], "exit", "exit is not the last record")
        text = run.trace.decode("utf-8")
        for char in LINE_BREAKS_JSON_KEEPS:
            self.assertNotIn(char, text, f"U+{ord(char):04X} written raw into the trace")

    def run_tap(self, child: str, *args: str, stdin: bytes = b"") -> TapRun:
        return self.run_child([str(CHILDREN / child), *args], stdin)

    def run_child(self, child: list[str], stdin: bytes = b"") -> TapRun:
        run = TapRun(self.tmp, child, stdin)
        self.check_trace(run)
        return run

    def run_echo(self, stdin: bytes, *args: str) -> TapRun:
        return self.run_tap("echo.py", str(self.received), str(self.sent), *args, stdin=stdin)

    def popen(self, *command: str, **kwargs: Any) -> subprocess.Popen[bytes]:
        """Start the tap around a command; the test kills it if it is still running at the end."""
        proc = subprocess.Popen(
            tap_command(self.tmp / "trace.jsonl", *command),
            cwd=ROOT,
            stdin=kwargs.pop("stdin", subprocess.PIPE),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs,
        )

        def stop() -> None:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe is not None:
                    pipe.close()

        self.addCleanup(stop)
        return proc


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
            self.assertIsNotNone(record["json"], record)

    def test_s2c_split_and_large_frames(self) -> None:
        run = self.run_tap("split_writer.py")
        self.assertEqual(run.code, 0, run.stderr)
        self.assertEqual(run.stdout, split_writer.OUTPUT)
        self.assertEqual([raw_bytes(r) for r in run.frames("s2c")], split_writer.FRAMES)

    def test_c2s_split_and_large_frames(self) -> None:
        proc = self.popen(
            sys.executable, str(CHILDREN / "echo.py"), str(self.received), str(self.sent),
            "--prefix", "",
        )  # fmt: skip
        assert proc.stdin is not None
        data = split_writer.OUTPUT
        proc.stdin.write(data[:10])
        proc.stdin.flush()
        time.sleep(0.2)
        out, err = proc.communicate(data[10:], timeout=TIMEOUT)
        self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(self.received.read_bytes(), data)
        self.assertEqual(out, data)
        records = strict_records((self.tmp / "trace.jsonl").read_bytes())
        c2s = [raw_bytes(r) for r in records if r["dir"] == "c2s"]
        self.assertEqual(c2s, split_writer.FRAMES)


class DirectionAndOrderTest(TapTestCase):
    """C2."""

    LINES = [b'{"id":1}\n', b'{"id":2}\n', b'{"id":3}\n']

    def test_direction_and_order(self) -> None:
        run = self.run_echo(b"".join(self.LINES))
        self.assertEqual(run.code, 0, run.stderr)
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

    def test_frames_are_recorded_before_they_are_forwarded(self) -> None:
        events: list[tuple[str, bytes]] = []

        class Recorder:
            def frame(self, direction: str, frame: bytes, partial: bool = False) -> None:
                events.append(("record", frame))

        real_write_all = tap_main.write_all

        def write_all(fd: int, data: bytes) -> None:
            events.append(("write", data))
            real_write_all(fd, data)

        src_r, src_w = os.pipe()
        dst_r, dst_w = os.pipe()
        chunks = [b'{"id":1}\n{"id', b'":2}\n{"id":3}\n{"i', b'd":4}\n']
        for chunk in chunks:
            os.write(src_w, chunk)
        os.close(src_w)
        with mock.patch.object(tap_main, "write_all", write_all):
            tap_main.relay(src_r, dst_w, "c2s", Recorder())  # type: ignore[arg-type]
        os.close(src_r)
        os.close(dst_w)
        with os.fdopen(dst_r, "rb") as dst:
            self.assertEqual(dst.read(), b"".join(chunks))
        forwarded = 0
        for kind, data in events:
            if kind == "write":
                forwarded += len(data)
            else:
                end = b"".join(chunks).index(data) + len(data)
                self.assertLess(forwarded, end, f"{data!r} was forwarded before it was recorded")
        self.assertEqual([d for k, d in events if k == "record"], [
            b'{"id":1}\n', b'{"id":2}\n', b'{"id":3}\n', b'{"id":4}\n'
        ])  # fmt: skip

    def test_a_flood_is_recorded_whole_and_exit_is_last(self) -> None:
        run = self.run_tap("flood.py")
        self.assertEqual(run.code, 0, run.stderr)
        self.assertEqual(len(run.frames("s2c")), flood.LINES)
        self.assertEqual(len(run.frames("stderr")), flood.STDERR_LINES)
        self.assertEqual(run.stream("s2c"), run.stdout)
        self.assertEqual(run.stream("stderr"), run.stderr)

    def test_t_ns_follows_real_time(self) -> None:
        child = "import os, time; os.write(1, b'a\\n'); time.sleep(0.5); os.write(1, b'b\\n')"
        run = self.run_child(["-c", child])
        first, second = run.frames("s2c")
        self.assertGreaterEqual(second["t_ns"] - first["t_ns"], 250_000_000)

    def test_nothing_is_recorded_after_exit(self) -> None:
        trace = tap_main.Trace(self.tmp / "t.jsonl")
        trace.finish(code=0)
        trace.frame("c2s", b'{"id":9}\n')
        records = strict_records((self.tmp / "t.jsonl").read_bytes())
        self.assertEqual([r.get("event") for r in records], ["exit"])


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

    def test_cesu8_surrogate_bytes_are_not_utf8(self) -> None:
        stdin = b'{"s":"\xed\xa0\x80"}\n'
        run = self.run_echo(stdin)
        self.assertEqual(self.received.read_bytes(), stdin)
        (record,) = run.frames("c2s")
        self.assertNotIn("raw", record)
        self.assertEqual(base64.b64decode(record["raw_b64"]), stdin)
        self.assertIsNone(record["json"])

    def test_non_standard_constants_are_not_json(self) -> None:
        run = self.run_echo(b'{"x": NaN}\n')
        (record,) = run.frames("c2s")
        self.assertIsNone(record["json"])
        self.assertIn("NaN", record["parse_error"])

    def test_a_number_that_overflows_is_not_held_as_json(self) -> None:
        stdin = b'{"x": 1e999}\n{"id":2}\n'
        run = self.run_echo(stdin, "--prefix", "")
        self.assertEqual(run.code, 0, run.stderr)
        self.assertEqual(run.stdout, stdin)
        big, after = run.frames("c2s")
        self.assertEqual(big["raw"], '{"x": 1e999}\n')
        self.assertIsNone(big["json"])
        self.assertTrue(big["parse_error"])
        self.assertEqual(after["json"], {"id": 2})

    def test_a_deeply_nested_frame_from_the_client(self) -> None:
        stdin = b'{"id":1}\n' + DEEP + b'{"id":3}\n'
        run = self.run_echo(stdin, "--prefix", "")
        self.assertEqual(run.code, 0, run.stderr)
        self.assertEqual(self.received.read_bytes(), stdin)
        self.assertEqual(run.stdout, stdin)
        first, deep, last = run.frames("c2s")
        self.assertEqual(deep["raw"], DEEP.decode("ascii"))
        self.assertIsNone(deep["json"])
        self.assertTrue(deep["parse_error"])
        self.assertEqual((first["json"], last["json"]), ({"id": 1}, {"id": 3}))

    def test_a_deeply_nested_frame_from_the_child(self) -> None:
        out = b'{"id":1}\n' + DEEP + b'{"id":3}\n'
        run = self.run_child(["-c", f"import os; os.write(1, {out!r})"])
        self.assertEqual(run.code, 0, run.stderr)
        self.assertEqual(run.stdout, out)
        first, deep, last = run.frames("s2c")
        self.assertEqual(deep["raw"], DEEP.decode("ascii"))
        self.assertIsNone(deep["json"])
        self.assertTrue(deep["parse_error"])
        self.assertEqual((first["json"], last["json"]), ({"id": 1}, {"id": 3}))

    def test_line_breaks_inside_strings_are_escaped_in_the_trace(self) -> None:
        stdin = '{"t":"a\x85b c d"}\n'.encode()
        run = self.run_echo(stdin, "--prefix", "")
        self.assertEqual(run.stdout, stdin)
        (record,) = run.frames("c2s")
        self.assertEqual(raw_bytes(record), stdin)
        self.assertEqual(record["json"], {"t": "a\x85b c d"})
        self.assertEqual(len(run.trace.decode("utf-8").splitlines()), len(run.records))

    def test_a_parsed_value_too_deep_to_write_is_recorded_as_null(self) -> None:
        deep: list[Any] = []
        for _ in range(100_000):
            deep = [deep]
        line = tap_main.encode_record({"seq": 0, "dir": "c2s", "raw": "[]\n", "json": deep})
        (record,) = strict_records(line)
        self.assertIsNone(record["json"])
        self.assertIn("tap could not write", record["parse_error"])
        self.assertEqual(record["raw"], "[]\n")


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

    def wait_for_signal(self, send: Callable[[subprocess.Popen[bytes]], None], sig: int,
                        **kwargs: Any) -> None:  # fmt: skip
        tap = self.popen(sys.executable, str(CHILDREN / "signal_waiter.py"), **kwargs)
        assert tap.stdout is not None
        self.assertEqual(tap.stdout.readline(), b"ready\n")
        send(tap)
        out, err = tap.communicate(timeout=SIGNAL_TIMEOUT)
        name = signal.Signals(sig).name
        self.assertEqual(out, f"got {name}\n".encode(), "the child did not get it exactly once")
        self.assertEqual(tap.returncode, 10 + sig, err)

    def test_signals_are_forwarded(self) -> None:
        for sig in signal_waiter.SIGNALS:
            with self.subTest(signal=sig.name):
                self.wait_for_signal(functools.partial(send_signal, sig=sig), sig)

    def test_a_signal_to_the_process_group_reaches_the_child_once(self) -> None:
        self.wait_for_signal(
            lambda tap: os.killpg(tap.pid, signal.SIGTERM), signal.SIGTERM, start_new_session=True
        )

    def test_a_signal_before_the_child_starts_is_forwarded(self) -> None:
        # The tap's main() is run with Popen wrapped so that SIGTERM reaches the tap just
        # before the child is spawned; the child sleeps unless it receives it.
        trace = self.tmp / "trace.jsonl"
        script = (
            "import os, signal, subprocess, sys\n"
            "import tap.__main__ as m\n"
            "real = subprocess.Popen\n"
            "def popen(*a, **k):\n"
            "    os.kill(os.getpid(), signal.SIGTERM)\n"
            "    return real(*a, **k)\n"
            "m.subprocess.Popen = popen\n"
            f"sys.exit(m.main(['--trace', {str(trace)!r}, '--', sys.executable, '-c',"
            " 'import time; time.sleep(30)']))\n"
        )
        done = subprocess.run(
            [sys.executable, "-c", script], cwd=ROOT, capture_output=True, timeout=SIGNAL_TIMEOUT
        )
        self.assertEqual(done.returncode, 143, done.stderr)

    def test_child_closing_stdout_gives_the_client_eof_at_once(self) -> None:
        child = "import os, time; os.write(1, b'x\\n'); os.close(1); time.sleep(2)"
        tap = self.popen(sys.executable, "-c", child)
        assert tap.stdout is not None and tap.stdin is not None
        tap.stdin.close()
        start = time.monotonic()
        self.assertEqual(tap.stdout.read(), b"x\n")
        self.assertLess(time.monotonic() - start, 1.5, "stdout EOF waited for the child's exit")
        self.assertEqual(tap.wait(timeout=TIMEOUT), 0)


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

    def test_stderr_written_after_stdout_closes_is_recorded_before_exit(self) -> None:
        child = (
            "import os\nos.write(1, b'x\\n')\nos.close(1)\n"
            "data = b''.join(b'log %d\\n' % n for n in range(20000))\n"
            "while data:\n    data = data[os.write(2, data):]\n"
        )
        run = self.run_child(["-c", child])
        self.assertEqual(run.code, 0)
        self.assertEqual(len(run.frames("stderr")), 20000)
        self.assertEqual(run.stream("stderr"), run.stderr)


class TraceFileTest(TapTestCase):
    """C17."""

    def test_trace_is_created_private(self) -> None:
        old = os.umask(0o022)
        self.addCleanup(os.umask, old)
        run = self.run_echo(b'{"id":1}\n')
        self.assertEqual(stat.S_IMODE(run.trace_path.stat().st_mode), 0o600)

    def test_an_existing_trace_is_replaced_and_made_private(self) -> None:
        trace = self.tmp / "trace.jsonl"
        trace.write_bytes(b"old content that is not a trace\n" * 100)
        trace.chmod(0o644)
        run = self.run_echo(b'{"id":1}\n')
        self.assertEqual(run.records[0]["event"], "spawn")
        self.assertEqual(stat.S_IMODE(trace.stat().st_mode), 0o600)

    def test_a_trace_write_failure_does_not_stop_forwarding(self) -> None:
        stdin = b"".join(b'{"jsonrpc":"2.0","id":%d,"method":"ping"}\n' % n for n in range(200))

        def limit_file_size() -> None:
            resource.setrlimit(resource.RLIMIT_FSIZE, (2048, 2048))

        done = subprocess.run(
            tap_command(self.tmp / "trace.jsonl", sys.executable, "-c", CAT),
            cwd=ROOT,
            input=stdin,
            capture_output=True,
            timeout=TIMEOUT,
            preexec_fn=limit_file_size,
        )
        self.assertEqual(done.stdout, stdin)
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stderr.splitlines()
        self.assertEqual(len(lines), 1, done.stderr)
        self.assertTrue(lines[0].startswith(b"tap: ") and b"trace" in lines[0], done.stderr)

    def test_a_non_blocking_stdin_is_still_relayed(self) -> None:
        read_end, write_end = os.pipe()
        flags = fcntl.fcntl(read_end, fcntl.F_GETFL)
        fcntl.fcntl(read_end, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        tap = self.popen(sys.executable, "-c", CAT, stdin=read_end)
        os.close(read_end)

        def write_late() -> None:
            time.sleep(0.5)
            os.write(write_end, b'{"id":1}\n')
            os.close(write_end)

        writer = threading.Thread(target=write_late)
        writer.start()
        out, err = tap.communicate(timeout=TIMEOUT)
        writer.join()
        self.assertEqual(out, b'{"id":1}\n', err)
        self.assertEqual(tap.returncode, 0, err)
        records = strict_records((self.tmp / "trace.jsonl").read_bytes())
        self.assertEqual([r["raw"] for r in records if r["dir"] == "c2s"], ['{"id":1}\n'])

    def test_closed_standard_descriptors_do_not_reach_the_trace(self) -> None:
        child = "import os; os.write(1, b'x\\n'); os.write(2, b'w\\n')"
        for fd in (0, 1, 2):
            with self.subTest(closed=fd):
                trace = self.tmp / f"trace-{fd}.jsonl"
                done = subprocess.run(
                    tap_command(trace, sys.executable, "-c", child),
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=TIMEOUT,
                    preexec_fn=functools.partial(os.close, fd),
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                records = strict_records(trace.read_bytes())
                self.assertEqual((records[0]["event"], records[-1]["event"]), ("spawn", "exit"))
                self.assertEqual([r["raw"] for r in records if r["dir"] == "stderr"], ["w\n"])
                if fd != 1:
                    self.assertEqual(done.stdout, b"x\n")
                if fd != 2:
                    self.assertEqual(done.stderr, b"w\n")


class FaultModeTest(TapTestCase):
    """Phase 4 C2, C3 (D3): --drop and --delay, opt-in, recorded on the timeline."""

    LINES = (
        b'{"jsonrpc":"2.0","id":1,"method":"a"}\n'
        b'{"jsonrpc":"2.0","id":2,"method":"b"}\n'
        b'{"jsonrpc":"2.0","id":3,"method":"b"}\n'
    )

    def child(self) -> list[str]:
        return [sys.executable, str(CHILDREN / "echo.py"), str(self.received), str(self.sent),
                "--prefix", ""]  # fmt: skip

    def faulty(self, stdin: bytes, *faults: str) -> TapRun:
        """Run the tap with fault options around echo.py (which echoes every line unchanged)."""
        trace_path = self.tmp / "trace.jsonl"
        argv = [sys.executable, "-m", "tap", "--trace", str(trace_path), *faults, "--",
                *self.child()]  # fmt: skip
        done = subprocess.run(argv, cwd=ROOT, input=stdin, capture_output=True, timeout=TIMEOUT)
        run = TapRun.__new__(TapRun)
        run.trace_path, run.command = trace_path, self.child()
        run.wall_ns, run.code = 0, done.returncode
        run.stdout, run.stderr = done.stdout, done.stderr
        run.trace = trace_path.read_bytes()
        run.records = strict_records(run.trace)
        self.assertEqual(run.code, 0, run.stderr)
        return run

    def faults(self, run: TapRun) -> list[dict[str, Any]]:
        return [r for r in run.records if r["dir"] == "tap" and r["event"] == "fault"]

    def test_drop_first_matching_frame_only(self) -> None:
        run = self.faulty(self.LINES, "--drop", "c2s:b")
        lines = self.LINES.splitlines(keepends=True)
        self.assertEqual(self.received.read_bytes(), lines[0] + lines[2], "what the child got")
        self.assertEqual(run.stdout, lines[0] + lines[2], "what came back")
        self.assertEqual(run.stream("c2s"), self.LINES, "a dropped frame is still a frame")
        self.assertEqual(len(self.faults(run)), 1, "only the first match is dropped")

    def test_drop_records_fault_with_seq(self) -> None:
        run = self.faulty(self.LINES, "--drop", "c2s:b")
        (fault,) = self.faults(run)
        self.assertEqual(fault["kind"], "drop")
        frame = next(r for r in run.records if r["seq"] == fault["frame_seq"])
        self.assertEqual(frame["dir"], "c2s")
        self.assertEqual(frame["json"]["id"], 2)
        self.assertGreater(fault["seq"], fault["frame_seq"], "the frame is recorded first")
        self.assertIs(fault["forwarded"], False)

    def test_drop_matches_the_method_member_only(self) -> None:
        # The word appears in params and in a non-JSON line; only a `method` equal to it counts.
        lines = (
            b'{"jsonrpc":"2.0","id":1,"method":"a","params":{"text":"b"}}\n'
            b"not json: b\n"
            b'{"jsonrpc":"2.0","id":2,"method":"b"}\n'
        )
        self.faulty(lines, "--drop", "c2s:b")
        self.assertEqual(self.received.read_bytes(), lines.rsplit(b"{", 1)[0])

    def test_drop_with_no_match_changes_nothing(self) -> None:
        run = self.faulty(self.LINES, "--drop", "c2s:nothing")
        self.assertEqual(self.received.read_bytes(), self.LINES)
        self.assertEqual(self.faults(run), [])

    def test_delay_keeps_order_and_delays(self) -> None:
        trace_path = self.tmp / "trace.jsonl"
        proc = subprocess.Popen(
            [sys.executable, "-m", "tap", "--trace", str(trace_path), "--delay", "s2c:300",
             "--", *self.child()],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )  # fmt: skip
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        assert proc.stdin and proc.stdout
        start = time.monotonic()
        proc.stdin.write(self.LINES)
        proc.stdin.flush()
        got: list[bytes] = []
        arrived: list[float] = []
        for _ in range(3):
            got.append(proc.stdout.readline())
            arrived.append(time.monotonic() - start)
        proc.stdin.close()
        proc.wait(timeout=TIMEOUT)
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None:
                pipe.close()
        self.assertEqual(b"".join(got), self.LINES, "order kept")
        self.assertGreaterEqual(arrived[0], 0.3, "the first frame was not held")
        self.assertGreaterEqual(arrived[2], 0.9, "each frame is held, one after another")
        records = strict_records(trace_path.read_bytes())
        faults = [r for r in records if r["dir"] == "tap" and r.get("event") == "fault"]
        self.assertEqual([f["kind"] for f in faults], ["delay"] * 3)
        s2c = [r["seq"] for r in records if r["dir"] == "s2c"]
        self.assertEqual([f["frame_seq"] for f in faults], s2c)

    def test_without_options_there_is_no_fault_record(self) -> None:
        run = self.faulty(self.LINES)
        self.assertEqual(self.faults(run), [])
        self.assertEqual(run.stdout, self.LINES)

    def test_bad_fault_options_are_usage_errors(self) -> None:
        for bad in (["--delay", "stderr:5"], ["--delay", "s2c:x"], ["--drop", "c2s"],
                    ["--drop", "up:m"], ["--delay", "s2c:-1"], ["--delay"]):
            done = subprocess.run(
                [sys.executable, "-m", "tap", "--trace", str(self.tmp / "t.jsonl"), *bad,
                 "--", "true"],
                cwd=ROOT, capture_output=True, timeout=TIMEOUT,
            )  # fmt: skip
            self.assertEqual(done.returncode, 2, bad)
            self.assertIn(b"usage:", done.stderr, bad)


class UsageTest(unittest.TestCase):
    """C5: usage and start-up errors."""

    def tap(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, "-m", "tap", *args], cwd=ROOT, capture_output=True, timeout=TIMEOUT
        )

    def test_missing_separator_is_a_usage_error(self) -> None:
        done = self.tap("--trace", "x.jsonl", "cat")
        self.assertEqual(done.returncode, 2)
        self.assertIn(b"usage:", done.stderr)

    def test_missing_command_is_a_usage_error(self) -> None:
        done = self.tap("--trace", "x.jsonl", "--")
        self.assertEqual(done.returncode, 2)
        self.assertIn(b"usage:", done.stderr)

    def test_unwritable_trace_path_exits_2_without_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            done = self.tap("--trace", str(Path(tmp) / "no-dir" / "t.jsonl"), "--", "true")
        self.assertEqual(done.returncode, 2)
        self.assertTrue(done.stderr.startswith(b"tap: cannot write trace"), done.stderr)
        self.assertNotIn(b"Traceback", done.stderr)

    def test_unstartable_command_exits_127_and_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "t.jsonl"
            done = self.tap("--trace", str(trace), "--", str(Path(tmp) / "no-such-server"))
            self.assertEqual(done.returncode, 127)
            records = strict_records(trace.read_bytes())
            self.assertEqual([r["event"] for r in records], ["spawn", "exit"])
            self.assertEqual(records[-1]["code"], 127)


if __name__ == "__main__":
    unittest.main()
