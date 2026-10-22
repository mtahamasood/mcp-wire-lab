"""Phase 5 C1 to C4: the trace diff keys frames, compares them as JSON, reports and explains."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tap import diff

ROOT = Path(__file__).resolve().parent.parent


def rec(
    seq: int, direction: str, message: Any = None, raw: str | None = None, **extra: Any
) -> dict[str, Any]:
    out: dict[str, Any] = {"seq": seq, "t_ns": seq * 1_000_000, "dir": direction}
    if message is not None:
        out["raw"] = (json.dumps(message, separators=(",", ":")) if raw is None else raw) + "\n"
        out["json"] = message
    elif raw is not None:
        out["raw"] = raw + "\n"
    out.update(extra)
    return out


def request(i: Any, method: str = "ping", **params: Any) -> dict[str, Any]:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": i, "method": method}
    if params:
        msg["params"] = params
    return msg


def reply(i: Any, result: Any = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": i, "result": {} if result is None else result}


def note(method: str, **params: Any) -> dict[str, Any]:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params:
        msg["params"] = params
    return msg


def trace(*frames: tuple[str, Any]) -> list[dict[str, Any]]:
    return [rec(n, d, m) for n, (d, m) in enumerate(frames)]


def keys(records: list[dict[str, Any]]) -> list[str]:
    return [f.key for f in diff.make_frames(records)]


class DiffCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, records: list[dict[str, Any]], name: str) -> Path:
        path = self.dir / name
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return path

    def cli(
        self, a: list[dict[str, Any]], b: list[dict[str, Any]], *flags: str
    ) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = diff.main([str(self.write(a, "a.jsonl")), str(self.write(b, "b.jsonl")), *flags])
        return code, out.getvalue(), err.getvalue()


class KeysTest(DiffCase):
    def test_requests_and_notifications_keyed_by_occurrence(self) -> None:
        records = trace(
            ("c2s", request(0, "tools/call")), ("c2s", note("notifications/initialized")),
            ("c2s", request(1, "tools/call")), ("s2c", note("notifications/progress")),
            ("s2c", note("notifications/progress")), ("s2c", request(0, "roots/list")),
            ("c2s", note("notifications/initialized")),
        )
        self.assertEqual(keys(records), [
            "c2s.tools/call#0", "c2s.notifications/initialized#0", "c2s.tools/call#1",
            "s2c.notifications/progress#0", "s2c.notifications/progress#1", "s2c.roots/list#0",
            "c2s.notifications/initialized#1",
        ])

    def test_response_keyed_by_the_request_it_answers(self) -> None:
        error9 = {"jsonrpc": "2.0", "id": 9, "error": {"code": -1, "message": "x"}}
        records = trace(
            ("c2s", request(0, "initialize")), ("c2s", request(1, "ping")), ("s2c", reply(1)),
            ("s2c", request(0, "roots/list")), ("c2s", reply(0)), ("s2c", reply(0)),
            ("s2c", {"jsonrpc": "2.0", "id": 9, "error": {"code": -1, "message": "x"}}),
            ("c2s", request(9, "tools/call")), ("s2c", error9),
        )
        self.assertEqual(keys(records), [
            "c2s.initialize#0", "c2s.ping#0", "s2c.response:ping#0", "s2c.roots/list#0",
            "c2s.response:roots/list#0", "s2c.response:initialize#0",
            "s2c.non-message#0",  # an error that answers no request
            "c2s.tools/call#0", "s2c.response:tools/call#0",
        ])

    def test_response_pairing_keeps_the_id_type(self) -> None:
        records = trace(
            ("c2s", request(1, "ping")), ("c2s", request("1", "tools/list")),
            ("s2c", reply("1")), ("s2c", reply(1)), ("s2c", reply(True)),
        )
        self.assertEqual(keys(records), [
            "c2s.ping#0", "c2s.tools/list#0", "s2c.response:tools/list#0",
            "s2c.response:ping#0", "s2c.non-message#0",
        ])

    def test_renumbered_ids_are_not_a_difference(self) -> None:
        a = trace(("c2s", request(0, "initialize")), ("s2c", reply(0)), ("c2s", request(1, "ping")),
                  ("s2c", reply(1)))
        b = trace(("c2s", request(7, "initialize")), ("s2c", reply(7)),
                  ("c2s", request("x", "ping")), ("s2c", reply("x")))
        result = diff.compare(a, b)
        self.assertTrue(result.clean)
        self.assertEqual((result.pairs, result.entries), (4, []))
        code, out, _ = self.cli(a, b)
        self.assertEqual(code, 0)
        self.assertNotIn("~", out)

    def test_cancelled_request_id_is_mapped(self) -> None:
        def run(first: int, second: int) -> list[dict[str, Any]]:
            cancel = note("notifications/cancelled", requestId=second, reason="r")
            return trace(("c2s", request(first, "tools/call")),
                         ("c2s", request(second, "tools/call")), ("c2s", cancel))
        self.assertTrue(diff.compare(run(0, 1), run(5, 6)).clean)
        # naming a different request of the trace is a real difference
        other = trace(("c2s", request(0, "tools/call")), ("c2s", request(1, "tools/call")),
                      ("c2s", note("notifications/cancelled", requestId=0, reason="r")))
        result = diff.compare(run(0, 1), other)
        self.assertEqual(result.differ, 1)
        self.assertIn("params.requestId", "\n".join(result.entries[0].detail))
        # a requestId that names no request stays as written
        stray = trace(("c2s", note("notifications/cancelled", requestId=99)))
        self.assertEqual(diff.make_frames(stray)[0].message["params"]["requestId"], 99)

    def test_non_message_frames_keyed_apart(self) -> None:
        records = [
            rec(0, "c2s", request(0, "ping")),
            rec(1, "c2s", None, raw="not json", json=None, parse_error="x"),
            rec(2, "c2s", None, raw="[1]", json=[1]),
            rec(3, "s2c", None, raw_b64="AAE=", json=None),
            rec(4, "stderr", None, raw="noise"),
            rec(5, "tap", None, event="exit", code=0),
            rec(6, "c2s", None, raw="half", json=None, partial=True),
        ]
        self.assertEqual(keys(records), [
            "c2s.ping#0", "c2s.non-message#0", "c2s.non-message#1", "s2c.non-message#0",
            "c2s.non-message#2",
        ])


class EqualityTest(DiffCase):
    def test_member_order_is_a_bytes_only_difference(self) -> None:
        a = [rec(0, "c2s", {"jsonrpc": "2.0", "method": "ping", "id": 0})]
        b = [rec(0, "c2s", {"id": 0, "method": "ping", "jsonrpc": "2.0"})]
        result = diff.compare(a, b)
        counts = (result.pairs, result.equal, result.bytes_only, result.differ)
        self.assertEqual(counts, (1, 0, 1, 0))
        self.assertTrue(result.clean)
        self.assertEqual(result.entries, [])
        # spacing and escapes count the same way
        spaced = [rec(0, "c2s", {"jsonrpc": "2.0", "method": "ping", "id": 0},
                      raw='{"jsonrpc": "2.0", "method": "ping", "id": 0}')]
        self.assertEqual(diff.compare(a, spaced).bytes_only, 1)
        same = diff.compare(a, a)
        self.assertEqual((same.equal, same.bytes_only), (1, 0))

    def test_number_and_boolean_types_differ(self) -> None:
        def one(value: Any, raw: str) -> list[dict[str, Any]]:
            msg = {"jsonrpc": "2.0", "method": "m", "params": {"v": value}}
            return [rec(0, "c2s", msg, raw=raw)]
        as_int = one(1, '{"jsonrpc":"2.0","method":"m","params":{"v":1}}')
        as_float = one(1.0, '{"jsonrpc":"2.0","method":"m","params":{"v":1.0}}')
        as_bool = one(True, '{"jsonrpc":"2.0","method":"m","params":{"v":true}}')
        for left, right in ((as_int, as_float), (as_int, as_bool), (as_float, as_bool)):
            self.assertEqual(diff.compare(left, right).differ, 1)
        self.assertEqual(diff.compare(as_int, as_int).differ, 0)

    def test_array_order_matters(self) -> None:
        a = [rec(0, "c2s", note("m", v=[1, 2]))]
        b = [rec(0, "c2s", note("m", v=[2, 1]))]
        result = diff.compare(a, b)
        self.assertEqual(result.differ, 1)
        self.assertEqual(result.entries[0].detail[1:],
                         ["    params.v[0]: 1 | 2", "    params.v[1]: 2 | 1"])

    def test_progress_token_is_not_normalised(self) -> None:
        a = trace(("c2s", request(15, "tools/call", _meta={"progressToken": "tour-done"})),
                  ("s2c", note("notifications/progress", progressToken="tour-done", progress=1)))
        b = trace(("c2s", request(15, "tools/call", _meta={"progressToken": 15})),
                  ("s2c", note("notifications/progress", progressToken=15, progress=1)))
        result = diff.compare(a, b)
        self.assertEqual(result.differ, 2)
        text = "\n".join(line for e in result.entries for line in e.detail)
        self.assertIn('params._meta.progressToken: "tour-done" | 15', text)
        self.assertIn('params.progressToken: "tour-done" | 15', text)

    def test_timings_and_non_messages_ignored(self) -> None:
        a = [rec(0, "c2s", request(0)), rec(1, "stderr", None, raw="one"),
             rec(2, "tap", None, event="exit", code=0),
             rec(3, "c2s", None, raw="junk", json=None)]
        b = [{**rec(5, "c2s", request(0)), "t_ns": 999_999_999},
             rec(6, "stderr", None, raw="other noise"),
             rec(7, "tap", None, event="exit", code=1), rec(8, "stderr", None, raw="more"),
             rec(9, "c2s", None, raw="junk", json=None)]
        result = diff.compare(a, b)
        self.assertTrue(result.clean)
        self.assertEqual(result.pairs, 2)
        # a non-message frame is compared by its text
        c = [rec(0, "c2s", None, raw="junk!", json=None)]
        d = [rec(0, "c2s", None, raw="junk", json=None)]
        self.assertEqual(diff.compare(c, d).differ, 1)


class OutputTest(DiffCase):
    def test_paths_and_values_listed(self) -> None:
        raw_info = {"name": "wire-lab-raw", "version": "0"}
        sdk_info = {"name": "wire-lab-sdk", "version": "0"}
        long_text = "\u00e9\u2028" + "x" * 80
        a = trace(("c2s", request(0, "initialize", clientInfo=raw_info, extra=1)))
        b = trace(("c2s", request(0, "initialize", clientInfo=sdk_info, more=long_text)))
        code, out, _ = self.cli(a, b)
        self.assertEqual(code, 1)
        lines = out.splitlines()
        self.assertEqual(lines[0], "~ c2s.initialize#0  (a seq 0, b seq 0)")
        self.assertIn('    params.clientInfo.name: "wire-lab-raw" | "wire-lab-sdk"', lines)
        self.assertIn("    params.extra: 1 | (absent)", lines)
        more = next(line for line in lines if line.startswith("    params.more:"))
        self.assertIn("(absent) | ", more)
        self.assertIn("\\u2028", more)  # escaped as tap.show escapes
        self.assertTrue(more.endswith("..."))
        self.assertEqual(len(more.split(" | ", 1)[1]), diff.CUT)

    def test_only_in_one_trace_listed(self) -> None:
        a = trace(("c2s", request(0, "ping")), ("c2s", request(1, "tools/list")), ("s2c", reply(1)))
        b = trace(("c2s", request(0, "ping")), ("c2s", request(1, "prompts/list")))
        code, out, _ = self.cli(a, b)
        self.assertEqual(code, 1)
        lines = out.splitlines()
        self.assertEqual(lines[:3], ["- c2s.tools/list#0  only in a (seq 1)",
                                     "- s2c.response:tools/list#0  only in a (seq 2)",
                                     "+ c2s.prompts/list#0  only in b (seq 1)"])

    def test_summary_and_exit_codes(self) -> None:
        a = trace(("c2s", request(0, "initialize")), ("c2s", note("notifications/initialized")),
                  ("c2s", note("m", v=1)), ("c2s", request(1, "gone")))
        b = [rec(0, "c2s", request(0, "initialize")),
             rec(1, "c2s", {"method": "notifications/initialized", "jsonrpc": "2.0"}),
             rec(2, "c2s", note("m", v=2)), rec(3, "c2s", request(1, "new"))]
        code, out, _ = self.cli(a, b)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[-1],
                         "summary: 3 pairs, 1 equal, 1 equal as JSON but not as bytes, 1 differ; "
                         "1 only in a, 1 only in b")
        code, out, _ = self.cli(a, a)
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[-1],
                         "summary: 4 pairs, 4 equal, 0 equal as JSON but not as bytes, 0 differ; "
                         "0 only in a, 0 only in b")
        # bytes-only differences alone do not fail the run
        self.assertEqual(self.cli(a[:2], b[:2])[0], 0)
        # a usage error
        code, _, err = self.cli(a, a, "--bogus")
        self.assertEqual(code, 2)
        self.assertIn("usage:", err)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(diff.main([]), 2)

    def test_unreadable_trace_exits_2(self) -> None:
        good = self.write(trace(("c2s", request(0))), "good.jsonl")
        bad = self.dir / "bad.jsonl"
        bad.write_text("not a trace record\n")
        for args in ([str(good), str(self.dir / "missing.jsonl")], [str(bad), str(good)]):
            done = subprocess.run([sys.executable, "-m", "tap.diff", *args], cwd=ROOT,
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 2, done.stdout)
            self.assertEqual(len(done.stderr.splitlines()), 1)
            self.assertTrue(done.stderr.startswith("diff: "), done.stderr)
            self.assertEqual(done.stdout, "")


WALKTHROUGH = """# Walkthrough

## one

#### `c2s.initialize#0`
The client's name differs.

#### `c2s.tools/call#1-2`
Both calls carry another token.

## two

#### `c2s.ping#0`
Only the second section's note.

## shared

#### `c2s.shared-only#0`
A shared note that no entry uses is fine.
"""


class ExplainTest(DiffCase):
    def traces(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        def one(name: str, token: Any) -> list[dict[str, Any]]:
            return trace(("c2s", request(0, "initialize", clientInfo={"name": name})),
                         ("c2s", request(1, "tools/call", token=token)),
                         ("c2s", request(2, "tools/call", token=token)))
        return one("raw", "a"), one("sdk", "b")

    def explain(self, text: str, section: str = "one") -> tuple[int, str]:
        (self.dir / "w.md").write_text(text)
        a, b = self.traces()
        code, out, _ = self.cli(a, b, "--explain", f"{self.dir / 'w.md'}#{section}")
        return code, out

    def test_every_entry_needs_a_note(self) -> None:
        dropped = "#### `c2s.tools/call#1-2`\nBoth calls carry another token.\n"
        text = WALKTHROUGH.replace(dropped, "")
        code, out = self.explain(text)
        self.assertEqual(code, 1)
        self.assertIn("(no note)  [c2s.tools/call#0]", out)
        self.assertIn("(no note)  [c2s.tools/call#1]", out)
        self.assertNotIn("(no note)  [c2s.initialize#0]", out)
        self.assertIn("The client's name differs.", out)

    def test_note_without_entry_fails(self) -> None:
        text = WALKTHROUGH.replace("## two", "#### `c2s.ping#7`\nNo such difference.\n\n## two")
        code, out = self.explain(text.replace("c2s.tools/call#1-2", "c2s.tools/call#0-1"))
        self.assertEqual(code, 1)
        self.assertIn("(no difference)  [c2s.ping#7]", out)

    def test_section_shared_and_ranges(self) -> None:
        text = WALKTHROUGH.replace("c2s.tools/call#1-2", "c2s.tools/call#0-1")
        code, out = self.explain(text)
        self.assertEqual(code, 0, out)
        self.assertIn("Both calls carry another token.", out)
        self.assertIn("(continues the note on c2s.tools/call#0)", out)
        self.assertNotIn("Only the second section's note", out)
        self.assertNotIn("(no difference)", out)  # the unused shared note is not reported
        # a section the walkthrough lacks is an error
        (self.dir / "w.md").write_text(WALKTHROUGH)
        a, b = self.traces()
        code, _, err = self.cli(a, b, "--explain", f"{self.dir / 'w.md'}#nope")
        self.assertEqual(code, 2)
        self.assertIn("diff:", err)
        # a clean diff with an explanation exits 0 whatever the differences
        self.assertEqual(self.cli(a, b, "--explain", f"{self.dir / 'w.md'}#two")[0], 1)


if __name__ == "__main__":
    unittest.main()
