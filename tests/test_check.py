"""C9 (unit half): `tap.check` validates trace frames against the pinned spec schema."""

from __future__ import annotations

import contextlib
import io
import json
import re
import tempfile
import unittest
from collections.abc import Callable
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
    records: list[dict[str, Any]], spec_root: Path | None = None, revision: str = REVISION,
    extra: tuple[str, ...] = (),
) -> tuple[int, str, str]:
    """Write the records as a trace file and run `tap.check` on it: (exit, stdout, stderr)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "trace.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        argv = [str(path), "--revision", revision, *extra]
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
        ping = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
        bad_envelope = {"jsonrpc": "1.0", "id": 2, "result": {}}
        records = trace_of(
            ("c2s", bad_params), ("c2s", bad_const), ("c2s", LIST), ("s2c", bad_type),
            ("c2s", ping), ("s2c", bad_envelope))
        code, out, _ = run_check(records)
        self.assertEqual(code, 1)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 4, out)
        self.assertRegex(lines[3], r"^seq 6  \$\.jsonrpc  JSONRPCResultResponse  ")
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

    def test_unknown_revision_exits_2(self) -> None:
        """A revision that is missing, or names its envelopes differently, cannot be checked."""
        records = trace_of(
            ("c2s", {"jsonrpc": "2.0", "id": 2, "method": "ping"}),
            ("s2c", {"jsonrpc": "2.0", "id": 2, "result": {}}),
            ("s2c", {"jsonrpc": "2.0", "id": 3, "error": {"code": -1, "message": "no"}}))
        for revision in ("2025-06-18", "1999-01-01"):
            code, out, err = run_check(records, revision=revision)
            self.assertEqual((code, out), (2, ""), (revision, err))
            self.assertTrue(err.startswith("check: "), err)
            self.assertNotIn("Traceback", err)
            self.assertNotIn("KeyError", err)

    def test_error_frames_are_validated(self) -> None:
        bad = {"jsonrpc": "2.0", "id": 3, "error": {"code": "oops", "message": "no"}}
        code, out, _ = run_check(trace_of(("s2c", bad)))
        self.assertEqual(code, 1)
        self.assertRegex(out, r"^seq 1  \$\.error\.code  JSONRPCErrorResponse  ")

    def test_notification_checked_against_its_method(self) -> None:
        bad = {"jsonrpc": "2.0", "method": "notifications/progress",
               "params": {"progressToken": "t", "progress": "half"}}
        code, out, _ = run_check(trace_of(("s2c", bad)))
        self.assertEqual(code, 1)
        self.assertRegex(
            out, r"^seq 1  \$\.params\.progress  ProgressNotification  ")

    def test_input_required_result_checked_against_its_definition(self) -> None:
        call = modern_request(1, "tools/call", name="get-roots-list", arguments={})
        interim = modern_result(1, "input_required", inputRequests={
            "roots": {"method": "roots/list", "params": {}}}, requestState="opaque")
        code, out, _ = run_check(trace_of(("c2s", call), ("s2c", interim)), revision=MODERN)
        self.assertEqual((code, out), (0, "check: ok (2 frames)\n"))
        bad = modern_result(1, "input_required", inputRequests="not a map")
        code, out, _ = run_check(trace_of(("c2s", call), ("s2c", bad)), revision=MODERN)
        self.assertEqual(code, 1)
        self.assertRegex(out, r"^seq 2  \$\.result\.inputRequests  InputRequiredResult  ")
        # any other result is checked against the method's own definition, as before
        plain = modern_result(1, "complete")  # a CallToolResult needs `content`
        code, out, _ = run_check(trace_of(("c2s", call), ("s2c", plain)), revision=MODERN)
        self.assertEqual(code, 1)
        self.assertRegex(out, r"^seq 2  \$\.result  CallToolResult  .*content")

    def test_2026_request_without_envelope_fails(self) -> None:
        bare = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        no_params = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        code, out, _ = run_check(trace_of(("c2s", bare), ("c2s", no_params)), revision=MODERN)
        self.assertEqual(code, 1)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 2, out)
        self.assertRegex(lines[0], r"^seq 1  \$\.params  ListToolsRequest  .*_meta")
        self.assertRegex(lines[1], r"^seq 2  \$  ListToolsRequest  .*params")
        good = {**bare, "params": {"_meta": META_2026}}
        self.assertEqual(run_check(trace_of(("c2s", good)), revision=MODERN)[0], 0)


MODERN = "2026-07-28"
META_2026 = {
    "io.modelcontextprotocol/protocolVersion": MODERN,
    "io.modelcontextprotocol/clientInfo": {"name": "t", "version": "0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}
TASK = {"taskId": "t-1", "status": "working", "createdAt": "2026-10-22T10:00:00Z",
        "lastUpdatedAt": "2026-10-22T10:00:01Z", "ttlMs": 60000, "pollIntervalMs": 1000}
SEP_PATH = ROOT / "tap/schemas/2026-07-28/sep-2663-tasks.json"
SEP_FILE = ROOT / "vendor/spec/seps/2663-tasks-extension.md"
# D14's table: definition -> the SEP line its description must open with
SEP_LINES = {
    "Task": 137, "WorkingTask": 196, "InputRequiredTask": 204, "CompletedTask": 217,
    "FailedTask": 231, "CancelledTask": 243, "DetailedTask": 252, "CreateTaskResult": 262,
    "GetTaskRequest": 317, "GetTaskResult": 337, "UpdateTaskRequest": 357,
    "UpdateTaskResult": 376, "CancelTaskRequest": 392, "CancelTaskResult": 403,
    "TaskStatusNotification": 421,
}


def modern_request(msg_id: int, method: str, **params: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "method": method,
            "params": {"_meta": META_2026, **params}}


def modern_result(msg_id: int, result_type: str | None = "complete", **result: Any
                  ) -> dict[str, Any]:
    body = dict(result) if result_type is None else {"resultType": result_type, **result}
    return {"jsonrpc": "2.0", "id": msg_id, "result": body}


def pinned_defs() -> dict[str, Any]:
    document = json.loads((ROOT / "vendor/spec/schema" / MODERN / "schema.json").read_text())
    defs: dict[str, Any] = document["$defs"]
    return defs


def sep_document() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(SEP_PATH.read_text(encoding="utf-8"))
    return document


def keywords_of(schema: Any, found: set[str]) -> None:
    """Every keyword used by a schema fragment (property names are not keywords)."""
    if not isinstance(schema, dict):
        return
    for key, value in schema.items():
        found.add(key)
        if key in ("properties", "$defs"):
            for sub in value.values():
                keywords_of(sub, found)
        elif key in ("allOf", "anyOf"):
            for sub in value:
                keywords_of(sub, found)
        elif key in ("items", "additionalProperties"):
            keywords_of(value, found)


def refs_of(node: Any) -> list[str]:
    return check.refs_in(node)


class ExtensionSchemaTest(unittest.TestCase):
    """C16, the file: the SEP-2663 transcription."""

    def test_holds_exactly_the_sep_2663_definitions(self) -> None:
        document = sep_document()
        self.assertEqual(set(document["$defs"]), set(SEP_LINES))
        self.assertIn("SEP-2663", document["description"])
        self.assertIn("not part of", document["description"].replace("NOT part of", "not part of"))
        self.assertIn("$schema", document)

    def test_uses_only_implemented_keywords(self) -> None:
        found: set[str] = set()
        keywords_of(sep_document(), found)
        allowed = check.ASSERTIONS | check.ANNOTATIONS
        self.assertEqual(found - allowed, set())
        # the subset P8 names for this file
        self.assertTrue(found <= {"type", "$ref", "properties", "required", "const", "enum",
                                  "allOf", "anyOf", "$schema", "$defs", "description"}, found)

    def test_every_definition_cites_a_resolving_sep_line(self) -> None:
        sep_lines = SEP_FILE.read_text(encoding="utf-8").split("\n")
        cite = re.compile(r'^`spec:seps/2663-tasks-extension\.md:(\d+)` "([^"]+)"')
        for name, definition in sep_document()["$defs"].items():
            found = cite.match(definition["description"])
            self.assertIsNotNone(found, f"{name}: description must open with a G8 citation")
            assert found is not None
            line, fragment = int(found.group(1)), found.group(2)
            self.assertEqual(line, SEP_LINES[name], name)
            self.assertIn(fragment, sep_lines[line - 1], f"{name}: fragment not on line {line}")
            for more in re.finditer(r'`spec:seps/2663-tasks-extension\.md:(\d+)` "([^"]+)"',
                                    definition["description"]):
                self.assertIn(more.group(2), sep_lines[int(more.group(1)) - 1], name)

    def test_refs_resolve_against_pinned_2026_schema(self) -> None:
        pinned = set(pinned_defs())
        own = set(sep_document()["$defs"])
        self.assertEqual(own & pinned, set(), "the extension never shadows the pinned schema")
        for ref in refs_of(sep_document()):
            self.assertTrue(ref.startswith("#/$defs/"), ref)
            self.assertIn(ref[len("#/$defs/"):], pinned | own, ref)
        for core in ("Result", "RequestId", "InputRequests", "InputResponses",
                     "NotificationParams", "RequestParams"):
            self.assertIn(f"#/$defs/{core}", refs_of(sep_document()), f"{core} is a $ref")


def tasks_trace() -> list[dict[str, Any]]:
    """A valid exchange: a handle, tasks/get, tasks/update, tasks/cancel, a status notification."""
    return trace_of(
        ("c2s", modern_request(1, "tools/call", name="simulate-research-query", arguments={})),
        ("s2c", modern_result(1, "task", content=[], **TASK)),
        ("c2s", modern_request(2, "tasks/get", taskId="t-1")),
        ("s2c", modern_result(2, "complete", **{**TASK, "status": "input_required",
                                                "inputRequests": {"k": {"method": "roots/list"}}})),
        ("c2s", modern_request(3, "tasks/update", taskId="t-1",
                              inputResponses={"k": {"roots": []}})),
        ("s2c", modern_result(3, "complete")),
        ("c2s", modern_request(4, "tasks/get", taskId="t-1")),
        ("s2c", modern_result(4, "complete", **{**TASK, "status": "completed", "result": {}})),
        ("c2s", modern_request(5, "tasks/cancel", taskId="t-1")),
        ("s2c", modern_result(5, "complete")),
        ("s2c", {"jsonrpc": "2.0", "method": "notifications/tasks", "params": dict(TASK)}),
    )


class ExtensionCheckTest(unittest.TestCase):
    """C16, the check: `tap.check --revision 2026-07-28` and the extension."""

    def test_tasks_frames_checked_against_sep_2663(self) -> None:
        code, out, err = run_check(tasks_trace(), revision=MODERN)
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(out.strip().splitlines(), [
            "check: 10 of 11 frames checked against the SEP-2663 extension schema "
            "(tap/schemas/2026-07-28/sep-2663-tasks.json), not the pinned schema.json",
            "check: ok (11 frames)"])
        # each definition rejects a broken frame (seq of the frame is its place in the trace)
        broken: dict[int, tuple[dict[str, Any], str]] = {
            4: (modern_result(2, "complete", **{**TASK, "status": "completed"}), "GetTaskResult"),
            3: (modern_request(2, "tasks/get"), "GetTaskRequest"),
            5: (modern_request(3, "tasks/update", taskId="t-1"), "UpdateTaskRequest"),
            9: (modern_request(5, "tasks/cancel"), "CancelTaskRequest"),
            11: ({"jsonrpc": "2.0", "method": "notifications/tasks",
                  "params": {**TASK, "status": "paused"}}, "TaskStatusNotification"),
            6: (modern_result(3, "bogus"), "UpdateTaskResult"),
            10: (modern_result(5, "bogus"), "CancelTaskResult"),
            2: (modern_result(1, "task", content=[], **{**TASK, "taskId": 7}), "CreateTaskResult"),
        }
        for position, (frame, definition) in broken.items():
            records = tasks_trace()
            records[position]["json"] = frame
            code, out, _ = run_check(records, revision=MODERN)
            self.assertEqual(code, 1, definition)
            self.assertIn(f"SEP-2663:{definition}", out, (definition, out))
            self.assertRegex(out, rf"seq {position}  ", out)
        # a task variant: a completed task needs `result`, a failed one needs `error`, a status
        # outside the five is rejected by the base Task
        bad_variants: list[tuple[str, dict[str, Any]]] = [
            ("completed", {}), ("failed", {}), ("paused", {"result": {}})]
        for status, extra in bad_variants:
            records = tasks_trace()
            records[8]["json"] = modern_result(4, "complete", **{**TASK, "status": status, **extra})
            code, out, _ = run_check(records, revision=MODERN)
            self.assertEqual(code, 1, status)
            self.assertIn("SEP-2663:GetTaskResult", out)
        for status, extra in (("cancelled", {}), ("failed", {"error": {"code": -1}}),
                              ("working", {})):
            records = tasks_trace()
            records[8]["json"] = modern_result(4, "complete", **{**TASK, "status": status, **extra})
            self.assertEqual(run_check(records, revision=MODERN)[0], 0, status)

    def test_task_result_checked_against_create_task_result(self) -> None:
        call = modern_request(1, "tools/call", name="x", arguments={})
        handle = modern_result(1, "task", content=[], **TASK)
        code, out, _ = run_check(trace_of(("c2s", call), ("s2c", handle)), revision=MODERN)
        self.assertEqual(code, 0, out)
        self.assertIn("1 of 2 frames checked against the SEP-2663", out.splitlines()[0])
        no_id = {k: v for k, v in TASK.items() if k != "taskId"}
        bad = modern_result(1, "task", content=[], **no_id)
        code, out, _ = run_check(trace_of(("c2s", call), ("s2c", bad)), revision=MODERN)
        self.assertEqual(code, 1)
        self.assertRegex(out, r"seq 2  \$\.result  SEP-2663:CreateTaskResult  .*taskId")

    def test_task_result_on_other_method_fails(self) -> None:
        records = trace_of(
            ("c2s", modern_request(1, "tools/list")),
            ("s2c", modern_result(1, "task", tools=[], **TASK)))
        code, out, _ = run_check(records, revision=MODERN)
        self.assertEqual(code, 1)
        self.assertIn('resultType "task" on tools/list', out)
        self.assertRegex(out, r"^seq 2  \$\.result\.resultType  SEP-2663:CreateTaskResult  ")

    def test_findings_labelled_sep_2663(self) -> None:
        records = tasks_trace()
        records[4]["json"] = modern_result(2, "complete", **{**TASK, "status": "completed"})
        records[1]["json"]["params"] = {}  # a core frame that fails too
        code, out, _ = run_check(records, revision=MODERN)
        self.assertEqual(code, 1)
        labelled = [ln for ln in out.splitlines() if "SEP-2663:" in ln and ln.startswith("seq")]
        core = [ln for ln in out.splitlines() if ln.startswith("seq") and "SEP-2663:" not in ln]
        self.assertTrue(labelled and core, out)
        self.assertRegex(labelled[0], r"^seq \d+  \$\.result\.status  SEP-2663:GetTaskResult  "
                         r"|^seq \d+  \$\.result  SEP-2663:GetTaskResult  ")

    def test_collision_with_pinned_schema_stops(self) -> None:
        cases: dict[str, Callable[[dict[str, Any]], Any]] = {
            "a definition name": lambda defs: defs.update({"Task": {"type": "object"}}),
            "a method": lambda defs: defs.update({"OtherGet": {"properties": {
                "method": {"const": "tasks/get"}}}}),
            "an unresolved $ref": lambda defs: defs.pop("InputRequests"),
        }
        for label, change in cases.items():
            document = json.loads(
                (ROOT / "vendor/spec/schema" / MODERN / "schema.json").read_text())
            change(document["$defs"])
            with tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "schema" / MODERN
                target.mkdir(parents=True)
                (target / "schema.json").write_text(json.dumps(document), encoding="utf-8")
                code, out, err = run_check(
                    trace_of(("c2s", modern_request(1, "tasks/get", taskId="t"))),
                    spec_root=Path(tmp), revision=MODERN)
                self.assertEqual((code, out), (2, ""), (label, err))
                self.assertTrue(err.startswith("check: "), err)
                self.assertNotIn("Traceback", err)
                no_ext, _, _ = run_check(
                    trace_of(("c2s", modern_request(1, "tasks/get", taskId="t"))),
                    spec_root=Path(tmp), revision=MODERN, extra=("--no-extensions",))
                self.assertNotEqual(no_ext, 2, f"{label}: --no-extensions never loads the file")

    def test_no_extensions_and_2025_ignore_the_file(self) -> None:
        code, out, _ = run_check(tasks_trace(), revision=MODERN, extra=("--no-extensions",))
        self.assertEqual(code, 1)
        failing = [ln for ln in out.splitlines() if ln.startswith("seq")]
        self.assertEqual(len(failing), 9, out)  # 4 requests, their 4 responses, the notification
        self.assertTrue(all("unknown method" in ln for ln in failing), out)
        self.assertNotIn("SEP-2663", out)
        # the handle and the notification: the handle is a CallToolResult again
        # 2025-11-25 has its own core tasks/* definitions and never loads the file
        records = trace_of(
            ("c2s", {"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"taskId": "t"}}),
            ("s2c", {"jsonrpc": "2.0", "id": 1, "result": {
                "taskId": "t", "status": "working", "createdAt": "x", "lastUpdatedAt": "y",
                "ttl": None}}))
        code, out, _ = run_check(records)
        self.assertEqual(code, 0, out)
        self.assertNotIn("SEP-2663", out)

    def test_trace_without_extension_frames_prints_as_before(self) -> None:
        records = trace_of(
            ("c2s", modern_request(1, "tools/list")),
            ("s2c", modern_result(1, "complete", tools=[], ttlMs=0, cacheScope="public")))
        self.assertEqual(run_check(records, revision=MODERN), (0, "check: ok (2 frames)\n", ""))


if __name__ == "__main__":
    unittest.main()
