"""C9 (unit half): `tap.check` validates trace frames against the pinned spec schema."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tap import check

ROOT = Path(__file__).resolve().parent.parent
REVISION = "2025-11-25"

INIT = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
    "protocolVersion": REVISION, "capabilities": {},
    "clientInfo": {"name": "t", "version": "0"}}}
INIT_REPLY = {"jsonrpc": "2.0", "id": 0, "result": {
    "protocolVersion": REVISION, "capabilities": {"tools": {"listChanged": True}},
    "serverInfo": {"name": "s", "version": "1"}, "instructions": "hi"}}
LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
LIST_REPLY = {"jsonrpc": "2.0", "id": 1, "result": {"tools": [
    {"name": "echo", "inputSchema": {"type": "object"}}
]}}


def trace_of(*frames: tuple[str, Any]) -> list[dict[str, Any]]:
    """Trace records for (direction, message) pairs, with a tap event and stderr between."""
    recs: list[dict[str, Any]] = [{"seq": 0, "t_ns": 0, "dir": "tap", "event": "spawn"}]
    for n, (direction, message) in enumerate(frames, 1):
        recs.append({"seq": n, "t_ns": n, "dir": direction, "json": message, "raw": ""})
    return recs


def run_check(
    records: list[dict[str, Any]], spec_root: Path | None = None
) -> tuple[int, str, str]:
    """Write the records as a trace file and run `tap.check` on it: (exit, stdout, stderr)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "trace.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        argv = [str(path), "--revision", REVISION]
        if spec_root is not None:
            argv += ["--spec-root", str(spec_root)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = check.main(argv)
        return code, out.getvalue(), err.getvalue()


class CheckTest(unittest.TestCase):
    def test_valid_frames_pass(self) -> None:
        records = trace_of(
            ("c2s", INIT), ("s2c", INIT_REPLY),
            ("c2s", {"jsonrpc": "2.0", "method": "notifications/initialized"}),
            ("c2s", LIST), ("s2c", LIST_REPLY),
            ("c2s", {"jsonrpc": "2.0", "id": 2, "method": "ping"}),
            ("s2c", {"jsonrpc": "2.0", "id": 2, "result": {}}),
            ("c2s", {"jsonrpc": "2.0", "id": 3, "method": "resources/subscribe",
                     "params": {"uri": "demo://x"}}),
            ("s2c", {"jsonrpc": "2.0", "id": 3, "error": {"code": -32601, "message": "no"}}),
            ("s2c", {"jsonrpc": "2.0", "method": "notifications/progress",
                     "params": {"progressToken": "t", "progress": 1, "total": 2}}),
        )
        records.append({"seq": 11, "t_ns": 11, "dir": "stderr", "raw": "boot\n"})
        records.append({"seq": 12, "t_ns": 12, "dir": "s2c", "partial": True, "raw": "{\"id\":"})
        records.append({"seq": 13, "t_ns": 13, "dir": "tap", "event": "exit", "code": 0})
        code, out, err = run_check(records)
        self.assertEqual(
            (code, out.strip().splitlines()[-1:], err), (0, ["check: ok (10 frames)"], ""))

    def test_invalid_frame_reports_seq_path_definition(self) -> None:
        bad_params = {**INIT, "params": {"capabilities": {}, "clientInfo": {"name": "t"}}}
        bad_const = {**LIST, "jsonrpc": "1.0"}
        bad_type = {**LIST_REPLY, "result": {"tools": "not a list"}}
        records = trace_of(
            ("c2s", bad_params), ("c2s", bad_const), ("c2s", LIST), ("s2c", bad_type))
        code, out, _ = run_check(records)
        self.assertEqual(code, 1)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 3, out)
        self.assertRegex(lines[0], r"^seq 1  \$\.params  InitializeRequest  .*protocolVersion")
        self.assertRegex(lines[1], r"^seq 2  \$\.jsonrpc  ListToolsRequest  ")
        self.assertRegex(lines[2], r"^seq 4  \$\.result\.tools  ListToolsResult  ")

    def test_unimplemented_keyword_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            schema_dir = Path(tmp) / "schema" / REVISION
            schema_dir.mkdir(parents=True)
            (schema_dir / "schema.json").write_text(json.dumps({"$defs": {
                "PingRequest": {"type": "object", "properties": {
                    "method": {"const": "ping"}, "id": {"oneOf": [{"type": "string"}]}}},
                "JSONRPCResultResponse": {}, "JSONRPCErrorResponse": {}, "JSONRPCMessage": {},
            }}), encoding="utf-8")
            code, out, err = run_check(
                trace_of(("c2s", {"jsonrpc": "2.0", "id": 1, "method": "ping"})), Path(tmp))
        self.assertEqual(code, 2, out)
        self.assertIn("oneOf", err)
        self.assertEqual(out, "")

    def test_unknown_method_is_reported(self) -> None:
        records = trace_of(
            ("c2s", {"jsonrpc": "2.0", "id": 0, "method": "tools/frobnicate"}),
            ("s2c", {"jsonrpc": "2.0", "id": 0, "result": {}}),
            ("s2c", {"jsonrpc": "2.0", "id": 9, "result": {}}),
            ("s2c", {"jsonrpc": "2.0", "method": "notifications/nonsense"}),
        )
        code, out, _ = run_check(records)
        self.assertEqual(code, 1)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 4, out)
        self.assertTrue(all("unknown method" in ln for ln in lines), out)
        self.assertIn("tools/frobnicate", lines[0])

    def test_keywords_are_checked(self) -> None:
        """Each implemented keyword rejects what it should (the validator, one keyword each)."""
        cases: list[tuple[dict[str, Any], Any, bool]] = [
            ({"type": "integer"}, 1, True), ({"type": "integer"}, True, False),
            ({"type": "integer"}, 1.5, False), ({"type": "number"}, 1.5, True),
            ({"type": "string"}, 1, False), ({"type": "null"}, None, True),
            ({"type": "boolean"}, 0, False), ({"type": "array"}, {}, False),
            ({"const": 1}, True, False), ({"const": "a"}, "a", True),
            ({"enum": ["a", 1]}, 1, True), ({"enum": ["a", 1]}, True, False),
            ({"required": ["a"]}, {"b": 1}, False), ({"required": ["a"]}, {"a": 1}, True),
            ({"properties": {"a": {"type": "string"}}}, {"a": 1}, False),
            ({"additionalProperties": False, "properties": {"a": {}}}, {"b": 1}, False),
            ({"additionalProperties": {"type": "string"}}, {"b": 1}, False),
            ({"additionalProperties": {}}, {"b": 1}, True),
            ({"items": {"type": "string"}}, ["a", 1], False),
            ({"anyOf": [{"type": "string"}, {"type": "integer"}]}, 1, True),
            ({"anyOf": [{"type": "string"}, {"type": "integer"}]}, None, False),
            ({"allOf": [{"type": "integer"}, {"minimum": 3}]}, 2, False),
            ({"minimum": 3}, 2, False), ({"minimum": 3}, 3, True),
            ({"maximum": 3}, 4, False), ({"maximum": 3}, 3, True),
            ({"maxItems": 1}, [1, 2], False), ({"maxItems": 2}, [1, 2], True),
            ({"format": "uri", "type": "string"}, "not a uri", True),
            ({"$ref": "#/$defs/N"}, "x", False),
        ]
        defs = {"N": {"type": "integer"}}
        for schema, instance, ok in cases:
            errors = check.validate(instance, schema, "$", defs)
            self.assertEqual(errors == [], ok, (schema, instance, errors))


if __name__ == "__main__":
    unittest.main()
