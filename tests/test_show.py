"""C9, C13, C14: the viewer correlates by id, draws the flow, and checks explanation coverage."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests/fixtures"
TRACE = FIXTURES / "out-of-order.jsonl"


def show(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tap.show", *map(str, args)],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )


def rec(seq: int, direction: str, message: object = None, **extra: object) -> dict[str, object]:
    out: dict[str, object] = {"seq": seq, "t_ns": seq * 1_000_000, "dir": direction}
    if message is not None:
        out["raw"] = json.dumps(message) + "\n"
        out["json"] = message
    out.update(extra)
    return out


class TraceCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def trace(self, records: list[dict[str, object]], name: str = "t.jsonl") -> Path:
        path = self.dir / name
        body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
        path.write_text(body, encoding="utf-8")
        return path

    def lines(self, records: list[dict[str, object]], *flags: str) -> list[str]:
        done = show(self.trace(records), *flags)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        # split on "\n" only: splitlines() would swallow a raw "\r" or U+2028 the view leaked
        return done.stdout.removesuffix("\n").split("\n")


def req(i: object, method: str = "ping") -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": i, "method": method}


def res(i: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": i, "result": {}}


class RobustnessTest(TraceCase):
    def test_c9_stack_and_id_pairing_differ_in_both_directions(self) -> None:
        lines = self.lines([
            rec(1, "c2s", req(1)), rec(2, "c2s", req(2)),
            rec(3, "s2c", req(10)), rec(4, "s2c", req(11)),
            rec(5, "s2c", res(1)), rec(6, "c2s", res(10)),
            rec(7, "s2c", res(2)), rec(8, "c2s", res(11)),
        ])
        by_seq = {int(ln.split()[0]): ln for ln in lines}
        self.assertIn("(answers seq 1,", by_seq[5])
        self.assertIn("(answers seq 3,", by_seq[6])
        self.assertIn("(answers seq 2,", by_seq[7])
        self.assertIn("(answers seq 4,", by_seq[8])

    def test_c9_ids_keep_their_json_type(self) -> None:
        records = [rec(1, "c2s", req(1)), rec(2, "c2s", req("1")), rec(3, "c2s", req(1.0)),
                   rec(4, "c2s", req(True))]
        records += [rec(5, "s2c", res(True)), rec(6, "s2c", res(1.0)), rec(7, "s2c", res("1")),
                    rec(8, "s2c", res(1))]
        by_seq = {int(ln.split()[0]): ln for ln in self.lines(records)}
        self.assertIn("id=true (answers seq 4,", by_seq[5])
        self.assertIn("id=1.0 (answers seq 3,", by_seq[6])
        self.assertIn('id="1" (answers seq 2,', by_seq[7])
        self.assertIn("id=1 (answers seq 1,", by_seq[8])

    def test_c9_unicode_line_separators_do_not_split_the_trace(self) -> None:
        text = "a\u2028b\u2029c\u0085d\x0be\x1cf"
        lines = self.lines([rec(1, "stderr", raw=text + "\n", json=None), rec(2, "c2s", req(1))])
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].split()[0] == "1" and lines[1].split()[0] == "2")
        for ch in "\u2028\u2029\u0085\x0b\x1c":
            self.assertNotIn(ch, "\n".join(lines))
        self.assertIn("\\u2028", lines[0])

    def test_c9_notes_file_is_split_on_newline_only(self) -> None:
        notes = self.dir / "w.md"
        notes.write_text("#### `c2s.ping.1`\nfirst\u2028second\nthird\n", encoding="utf-8")
        done = show(self.trace([rec(1, "c2s", req(1))]), "--explain", notes)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("first\u2028second third", done.stdout.replace("\n        ", "\n"))

    def test_c9_malformed_json_rpc_is_shown_raw(self) -> None:
        shapes = [[1, 2], "text", 7, {"jsonrpc": "2.0"}, {"id": None, "method": "x"},
                  {"id": [1], "result": {}}, {"method": 5, "id": 1}, {"id": 1, "error": "boom"},
                  {"id": 2, "error": None}]
        records = [rec(n + 1, "s2c", shape) for n, shape in enumerate(shapes)]
        records[0]["raw"] = "[1,2]\n"
        for flags in ((), ("--full",), ("--mermaid",)):
            self.assertEqual(len(self.lines(records, *flags)) >= len(shapes), True)
        lines = self.lines(records)
        self.assertIn("batch", lines[0])
        for line in lines[1:]:
            self.assertIn("raw", line)
            self.assertNotIn("response", line)

    def test_c9_binary_and_unparsed_frames_show_escaped_raw_in_full(self) -> None:
        records = [rec(1, "c2s", raw="bad\x07\u2028json\n", json=None, parse_error="x"),
                   rec(2, "s2c", raw_b64="AAEC", bytes=3, json=None)]
        out = "\n".join(self.lines(records, "--full"))
        self.assertIn("bad\\x07\\u2028json", out)
        self.assertIn("binary", out)

    def test_c9_in_flight_id_reuse_is_flagged_and_latest_pairs(self) -> None:
        lines = self.lines([rec(1, "c2s", req(1)), rec(2, "c2s", req(1)), rec(3, "s2c", res(1)),
                            rec(4, "s2c", req(1)), rec(5, "c2s", res(1))])
        self.assertNotIn("in flight", lines[0])
        self.assertIn("id already in flight", lines[1])
        self.assertIn("answers seq 2,", lines[2])
        self.assertNotIn("in flight", lines[3])  # the other direction has its own ids
        self.assertIn("answers seq 4,", lines[4])

    def test_c9_pairing_and_in_flight_ids_are_per_direction(self) -> None:
        # id 1 is in flight both ways at once: neither request is a reuse, each answer finds its own
        lines = self.lines([rec(1, "c2s", req(1)), rec(2, "s2c", req(1)), rec(3, "s2c", res(1)),
                            rec(4, "c2s", res(1))])
        self.assertNotIn("in flight", lines[1])
        self.assertIn("answers seq 1,", lines[2])
        self.assertIn("answers seq 2,", lines[3])

    def test_c9_batch_and_result_less_response_do_not_crash(self) -> None:
        batch = ["method", "id"]  # an array is a batch whatever it holds
        records = [rec(1, "c2s", batch, raw=json.dumps(batch) + "\n"),
                   rec(2, "s2c", {"jsonrpc": "2.0", "id": 3})]
        lines = self.lines(records)
        self.assertTrue(lines[0].endswith("  batch"), lines[0])
        self.assertIn("raw", lines[1])
        self.assertNotIn("response", lines[1])

    def test_c9_every_printed_field_is_escaped(self) -> None:
        bad = "a\x1b[31mb\rc d"
        records = [rec(1, "tap", event=bad), rec(2, "c2s", raw="x\n", json=None, parse_error=bad),
                   rec(3, "s2c", {"jsonrpc": "2.0", "id": 7, "error": {"code": bad}})]
        for flags in ((), ("--full",), ("--mermaid",)):
            out = "\n".join(self.lines(records, *flags))
            for ch in "\x1b\r ":
                self.assertNotIn(ch, out, flags)

    def test_c9_full_pretty_prints_json_and_adds_nothing_to_stderr(self) -> None:
        lines = self.lines([rec(1, "c2s", req(1)), rec(2, "stderr", raw="boot\n", json=None)],
                           "--full")
        self.assertIn('  "id": 1,', lines)
        self.assertEqual(lines[-1].split("  ")[-1], "stderr boot")
        self.assertEqual(sum("boot" in ln for ln in lines), 1)

    def test_c9_records_of_the_wrong_shape_exit_two_with_one_line(self) -> None:
        bodies = ["[1, 2]", '{"seq": 1, "t_ns": 1, "dir": "weird"}',
                  '{"seq": 1, "t_ns": "x", "dir": "c2s", "json": null}']
        for n, body in enumerate(bodies):
            path = self.dir / f"shape{n}.jsonl"
            path.write_text(body + "\n", encoding="utf-8")
            done = show(path)
            self.assertEqual(done.returncode, 2, (body, done.stderr))
            self.assertEqual(done.stdout, "")
            self.assertEqual(len(done.stderr.splitlines()), 1, done.stderr)
            self.assertTrue(done.stderr.startswith("show: "), done.stderr)

    def test_c9_record_without_t_ns_or_with_listy_dir_exits_two_with_one_line(self) -> None:
        bodies = ['{"seq": 0, "dir": "c2s", "json": null}',
                  '{"seq": 0, "t_ns": 1, "dir": ["c2s"], "json": null}',
                  '{"seq": 0, "t_ns": 1, "dir": {"a": 1}, "json": null}']
        for n, body in enumerate(bodies):
            path = self.dir / f"missing{n}.jsonl"
            path.write_text(body + "\n", encoding="utf-8")
            done = show(path)
            self.assertEqual(done.returncode, 2, (body, done.stderr))
            self.assertEqual(done.stdout, "")
            self.assertNotIn("Traceback", done.stderr)
            self.assertEqual(len(done.stderr.strip().split("\n")), 1, done.stderr)

    def test_c9_synthetic_marker_may_omit_t_ns(self) -> None:
        path = self.dir / "synth.jsonl"
        path.write_text('{"seq": 0, "dir": "tap", "event": "synthetic"}\n', encoding="utf-8")
        self.assertEqual(show(path).returncode, 0)

    def test_c13_mermaid_labels_a_batch_as_a_batch(self) -> None:
        out = "\n".join(self.lines([rec(1, "c2s", [req(1)])], "--mermaid"))
        self.assertIn("batch", out)
        self.assertNotIn("not JSON-RPC", out)

    def test_c9_output_pipe_closed_before_start_ends_quietly(self) -> None:
        # the read end is gone before the viewer writes, so its one buffered flush hits EPIPE
        read_end, write_end = os.pipe()
        os.close(read_end)
        try:
            done = subprocess.run([sys.executable, "-m", "tap.show", str(TRACE)], cwd=ROOT,
                                  stdout=write_end, stderr=subprocess.PIPE, timeout=30)
        finally:
            os.close(write_end)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr, b"")

    def test_c13_frames_that_are_not_messages_are_notes_and_ids_keep_json_type(self) -> None:
        batch = [{"jsonrpc": "2.0", "id": 2, "method": "ping"}]
        records = [rec(0, "tap", event="spawn", argv=["server"]), rec(1, "c2s", req("1")),
                   rec(2, "s2c", res("1")), rec(3, "c2s", batch), rec(4, "s2c", req(True)),
                   rec(5, "c2s", raw="junk\n", json=None, parse_error="x"),
                   rec(6, "tap", event="exit", code=0)]
        lines = [ln.strip() for ln in self.lines(records, "--mermaid")]
        arrows = [ln for ln in lines if re.search(r"-{1,2}>>", ln)]
        self.assertEqual(arrows, ['Client->>Server: ping id="1"',
                                  'Server-->>Client: response id="1"',
                                  "Server->>Client: ping id=true"])
        notes = [ln for ln in lines if ln.startswith("Note over Client,Server: ")]
        self.assertEqual(len(notes), 4, lines)
        self.assertEqual(notes[0], "Note over Client,Server: tap spawn")
        self.assertEqual(notes[-1], "Note over Client,Server: tap exit 0")

    def test_c9_control_characters_in_method_id_and_stderr_are_escaped(self) -> None:
        bad = "a\x1b[31mb\rc\u2028d"
        records = [rec(1, "c2s", req(bad, bad)), rec(2, "stderr", raw=bad + "\n", json=None),
                   rec(3, "s2c", res(bad))]
        for flags in ((), ("--full",), ("--mermaid",)):
            out = "\n".join(self.lines(records, *flags))
            for ch in "\x1b\r\u2028":
                self.assertNotIn(ch, out)
        self.assertIn("\\x1b", "\n".join(self.lines(records)))

    def test_c9_unreadable_trace_exits_two_with_one_line(self) -> None:
        bad_json = self.dir / "bad.jsonl"
        bad_json.write_text('{"dir": "c2s"\nnot json\n', encoding="utf-8")
        bad_utf8 = self.dir / "utf8.jsonl"
        bad_utf8.write_bytes(b"\xff\xfe\n")
        for path in (self.dir / "missing.jsonl", self.dir, bad_json, bad_utf8):
            done = show(path)
            self.assertEqual(done.returncode, 2, (path, done.stderr))
            self.assertEqual(done.stdout, "")
            self.assertEqual(len(done.stderr.splitlines()), 1, done.stderr)
            self.assertTrue(done.stderr.startswith("show: "), done.stderr)

    def test_c13_unreadable_notes_exit_two_missing_note_exits_one(self) -> None:
        done = show(TRACE, "--explain", self.dir / "nope.md")
        self.assertEqual(done.returncode, 2)
        self.assertEqual(len(done.stderr.splitlines()), 1)
        self.assertTrue(done.stderr.startswith("show: "))
        missing = show(TRACE, "--explain", FIXTURES / "walkthrough-missing-note.md")
        self.assertEqual(missing.returncode, 1)

    def test_c9_closed_output_pipe_ends_quietly(self) -> None:
        records = [rec(n, "c2s", req(n)) for n in range(1, 20000)]
        path = self.trace(records)
        proc = subprocess.Popen([sys.executable, "-m", "tap.show", str(path)], cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.stdout is not None and proc.stderr is not None
        proc.stdout.read(10)
        proc.stdout.close()
        err = proc.stderr.read().decode()
        self.assertEqual(proc.wait(timeout=30), 0)
        self.assertEqual(err, "")


class CorrelationTest(unittest.TestCase):
    def test_c9_responses_pair_by_id_not_adjacency(self) -> None:
        done = show(TRACE)
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        by_seq = {int(ln.split()[0]): ln for ln in lines if ln.split()[0].isdigit()}
        # ping (id 2, seq 2, t=2 ms) is answered first at seq 6 (t=5 ms): 3.0 ms.
        self.assertIn("response id=2 (answers seq 2, 3.0 ms)", by_seq[6])
        # tools/list (id 1, seq 1, t=1 ms) is answered last at seq 7 (t=9 ms): 8.0 ms.
        self.assertIn("id=1", by_seq[7])
        self.assertIn("(answers seq 1, 8.0 ms)", by_seq[7])
        self.assertIn("error", by_seq[7])
        self.assertNotIn("response", by_seq[7])
        self.assertNotIn("answers", by_seq[3])  # the notification pairs with nothing
        self.assertNotIn("answers", by_seq[1])

    def test_c9_full_prints_bodies(self) -> None:
        self.assertIn('"code": -32603', show(TRACE, "--full").stdout)


class MermaidTest(unittest.TestCase):
    def test_c13_diagram_shape_and_seq_order(self) -> None:
        done = show(TRACE, "--mermaid")
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(lines[0], "sequenceDiagram")
        self.assertIn("    participant Client", lines)
        self.assertIn("    participant Server", lines)
        arrows = [ln.strip() for ln in lines if re.search(r"-{1,2}>>", ln)]
        self.assertEqual(
            [re.sub(r":.*", "", a) for a in arrows],
            [
                "Client->>Server",  # tools/list, seq 1
                "Client->>Server",  # ping, seq 2
                "Server->>Client",  # notification, seq 3
                "Client->>Server",  # cancelled, seq 4: after a server record, so order matters
                "Server-->>Client",  # response id 2, seq 6
                "Server-->>Client",  # error id 1, seq 7
            ],
        )
        labels = [a.split(": ", 1)[1] for a in arrows]
        self.assertEqual(labels[0], "tools/list id=1")
        self.assertEqual(labels[1], "ping id=2")
        self.assertEqual(labels[2], "notifications/message")
        self.assertEqual(labels[3], "notifications/cancelled")
        self.assertEqual(labels[4], "response id=2")
        self.assertEqual(labels[5], "error id=1")
        self.assertTrue(any(ln.strip() == "Note over Server: stderr: boot" for ln in lines))


class ExplainTest(unittest.TestCase):
    def test_c14_complete_walkthrough_exits_zero(self) -> None:
        done = show(TRACE, "--explain", FIXTURES / "walkthrough-complete.md")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertNotIn("(no note)", done.stdout)
        self.assertNotIn("(no frame)", done.stdout)
        # a note follows its frame
        lines = done.stdout.splitlines()
        i = next(n for n, ln in enumerate(lines) if "request ping id=2" in ln)
        self.assertEqual(lines[i + 1].strip(), "Client pings.")

    def test_c14_missing_note_is_reported(self) -> None:
        done = show(TRACE, "--explain", FIXTURES / "walkthrough-missing-note.md")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(done.stdout.count("(no note)"), 1)
        self.assertIn("[s2c.response.1]", done.stdout)
        self.assertNotIn("(no frame)", done.stdout)

    def test_c14_extra_note_is_reported(self) -> None:
        done = show(TRACE, "--explain", FIXTURES / "walkthrough-extra-note.md")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("(no frame)  [c2s.initialize.9]", done.stdout)
        self.assertNotIn("(no note)", done.stdout)

    def test_c14_anchors_keep_json_id_type_and_name_a_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace, notes = Path(tmp) / "t.jsonl", Path(tmp) / "w.md"
            batch = [req(3)]
            records = [rec(1, "c2s", req("1")), rec(2, "s2c", res("1")), rec(3, "c2s", batch)]
            trace.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            notes.write_text('#### `c2s.ping."1"`\nA string id.\n\n#### `s2c.response."1"`\n'
                             "Its answer.\n\n#### `c2s.batch.0`\nA batch.\n", encoding="utf-8")
            done = show(trace, "--explain", notes)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertNotIn("(no note)", done.stdout)
        self.assertNotIn("(no frame)", done.stdout)

    def test_sections_select_notes_and_shared_notes_may_go_unused(self) -> None:
        # Phase 4: `--explain file.md#name` reads the notes under `## name` plus those under
        # `## shared`; a shared note a trace does not use is not "extra", a section's is.
        with tempfile.TemporaryDirectory() as tmp:
            trace, notes = Path(tmp) / "t.jsonl", Path(tmp) / "w.md"
            records = [rec(1, "c2s", req(1)), rec(2, "s2c", res(1))]
            trace.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            text = (
                "# Title\n\n## shared\n\n#### `s2c.response.1`\nShared answer.\n\n"
                "#### `c2s.initialize.0`\nUnused shared note.\n\n"
                "## one\n\n#### `c2s.ping.1`\nOne asks.\n\n"
                "## two\n\n#### `c2s.ping.1`\nTwo asks.\n\n#### `c2s.ping.5`\nExtra.\n"
            )
            notes.write_text(text, encoding="utf-8")
            one = show(trace, "--explain", f"{notes}#one")
            two = show(trace, "--explain", f"{notes}#two")
            nope = show(trace, "--explain", f"{notes}#three")
        self.assertEqual(one.returncode, 0, one.stdout)
        self.assertIn("One asks.", one.stdout)
        self.assertIn("Shared answer.", one.stdout)
        self.assertNotIn("Two asks.", one.stdout)
        self.assertNotEqual(two.returncode, 0)
        self.assertIn("(no frame)  [c2s.ping.5]", two.stdout)
        self.assertNotIn("(no frame)  [c2s.initialize.0]", two.stdout)
        self.assertEqual(nope.returncode, 2)
        self.assertIn("no section", nope.stderr)
        # The message names the sections the file does have, so a wrong name is easy to fix.
        self.assertIn("one", nope.stderr)
        self.assertIn("two", nope.stderr)
        self.assertNotIn("shared", nope.stderr.split("sections")[-1])

    def test_a_range_anchor_covers_consecutive_occurrences(self) -> None:
        # Phase 4: `stderr.1-3` is one note for stderr.1, stderr.2 and stderr.3 (a stack trace).
        with tempfile.TemporaryDirectory() as tmp:
            trace, notes = Path(tmp) / "t.jsonl", Path(tmp) / "w.md"
            records = [rec(0, "stderr", raw="boot\n")] + [
                rec(n, "stderr", raw=f"line {n}\n") for n in range(1, 4)
            ]
            trace.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            notes.write_text("#### `stderr.0`\nBoot.\n\n#### `stderr.1-3`\nA trace.\n",
                             encoding="utf-8")
            done = show(trace, "--explain", notes)
            notes.write_text("#### `stderr.0`\nBoot.\n\n#### `stderr.1-4`\nToo far.\n",
                             encoding="utf-8")
            over = show(trace, "--explain", notes)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertNotIn("(no note)", done.stdout)
        self.assertEqual(done.stdout.count("A trace."), 1, "the note is printed once")
        self.assertNotEqual(over.returncode, 0)
        self.assertIn("(no frame)  [stderr.4]", over.stdout)

    def test_usage_errors(self) -> None:
        self.assertEqual(show().returncode, 2)
        self.assertEqual(show(TRACE, "--explain").returncode, 2)


if __name__ == "__main__":
    unittest.main()
