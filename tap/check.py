"""The schema check (D6): does every frame of a trace conform to the spec's JSON Schema?

Usage:
  python3 -m tap.check <trace> --revision 2025-11-25 [--spec-root <dir>]

Validates each JSON-RPC frame of a trace against `schema/<revision>/schema.json` in the pinned
specification, with a validator that implements exactly the JSON Schema keywords the schemas use
(P8) and stops with exit 2, naming the keyword, on any other keyword it meets. Which definition a
frame is checked against:

- a request or notification: the definition whose `method` is that `const`;
- a response: the envelope against JSONRPCResultResponse, and its `result` against the result
  definition of the request it answers (paired by direction and id, as `tap.show` pairs them):
  `<Name>Result` for a `<Name>Request`, else EmptyResult;
- an error response: JSONRPCErrorResponse.

A frame no definition matches is reported as `unknown method`, never as valid. Output is one
line per failing frame: its seq, the JSON path that failed, the definition, the reason. Exit 0
if none fails, 1 if any does, 2 if the check could not run. Tap events, stderr records and
partial frames are skipped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from tap import show

USAGE = "usage: python3 -m tap.check <trace> --revision <revision> [--spec-root <dir>]"
DEFAULT_SPEC_ROOT = Path(__file__).resolve().parent.parent / "vendor/spec"
# Keywords that assert something; each has a branch in `validate`.
ASSERTIONS = {
    "type", "$ref", "properties", "required", "const", "additionalProperties", "items",
    "anyOf", "allOf", "enum", "minimum", "maximum", "maxItems",
}
# Keywords that assert nothing: `format` is an annotation (P8); the schemas also carry their
# own bookkeeping (`$schema`, `$defs`) and prose (`description`).
ANNOTATIONS = {"format", "$schema", "$defs", "description"}

Error = tuple[str, str]  # (JSON path, reason)


class CheckError(Exception):
    """The check cannot run (exit 2): an unreadable schema, or a keyword it does not implement."""


class UnimplementedKeyword(CheckError):
    def __init__(self, keyword: str, path: str) -> None:
        super().__init__(f"the schema uses the keyword {keyword!r} (at {path}), which this "
                         "validator does not implement")
        self.keyword = keyword


def json_equal(a: Any, b: Any) -> bool:
    """JSON equality: `1` and `true` differ, `1` and `1.0` are the same number."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def type_ok(instance: Any, name: str) -> bool:
    if name == "string":
        return isinstance(instance, str)
    if name == "boolean":
        return isinstance(instance, bool)
    if name == "null":
        return instance is None
    if name == "object":
        return isinstance(instance, dict)
    if name == "array":
        return isinstance(instance, list)
    is_number = isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if name == "number":
        return is_number
    if name == "integer":
        return is_number and float(instance).is_integer()
    raise CheckError(f"the schema uses the type {name!r}, which this validator does not know")


def describe(instance: Any) -> str:
    return "null" if instance is None else type(instance).__name__


def validate(instance: Any, schema: Any, path: str, defs: dict[str, Any]) -> list[Error]:
    """Every way `instance` fails `schema`, as (path, reason); raises UnimplementedKeyword."""
    if schema is True or schema == {}:
        return []
    if not isinstance(schema, dict):
        raise CheckError(f"a schema at {path} is neither an object nor true")
    for keyword in schema:
        if keyword not in ASSERTIONS and keyword not in ANNOTATIONS:
            raise UnimplementedKeyword(keyword, path)
    errors: list[Error] = []
    if "$ref" in schema:
        prefix = "#/$defs/"
        ref = schema["$ref"]
        if not ref.startswith(prefix) or ref[len(prefix):] not in defs:
            raise CheckError(f"cannot resolve $ref {ref!r}: only {prefix}<name> is implemented")
        errors += validate(instance, defs[ref[len(prefix):]], path, defs)
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(type_ok(instance, name) for name in names):
            errors.append((path, f"expected {' or '.join(names)}, got {describe(instance)}"))
    if "const" in schema and not json_equal(instance, schema["const"]):
        errors.append((path, f"expected the constant {json.dumps(schema['const'])}"))
    if "enum" in schema and not any(json_equal(instance, v) for v in schema["enum"]):
        errors.append((path, f"not one of {json.dumps(schema['enum'])}"))
    if isinstance(instance, dict):
        errors += validate_object(instance, schema, path, defs)
    if isinstance(instance, list):
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append((path, f"more than {schema['maxItems']} items"))
        if "items" in schema:
            for i, item in enumerate(instance):
                errors += validate(item, schema["items"], f"{path}[{i}]", defs)
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append((path, f"{instance} is below the minimum {schema['minimum']}"))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append((path, f"{instance} is above the maximum {schema['maximum']}"))
    for sub in schema.get("allOf", []):
        errors += validate(instance, sub, path, defs)
    if "anyOf" in schema:
        errors += any_of(instance, schema["anyOf"], path, defs)
    return errors


def validate_object(
    instance: dict[str, Any], schema: dict[str, Any], path: str, defs: dict[str, Any]
) -> list[Error]:
    errors: list[Error] = []
    for name in schema.get("required", []):
        if name not in instance:
            errors.append((path, f"missing required property {name!r}"))
    declared = schema.get("properties", {})
    for name, value in instance.items():
        if name in declared:
            errors += validate(value, declared[name], f"{path}.{name}", defs)
        elif "additionalProperties" in schema:
            extra = schema["additionalProperties"]
            if extra is False:
                errors.append((path, f"unexpected property {name!r}"))
            elif extra is not True:
                errors += validate(value, extra, f"{path}.{name}", defs)
    return errors


def any_of(
    instance: Any, branches: list[Any], path: str, defs: dict[str, Any]
) -> list[Error]:
    """No error if one branch accepts; else the errors of the branch that came closest."""
    best: list[Error] | None = None
    for branch in branches:
        errors = validate(instance, branch, path, defs)
        if not errors:
            return []
        if best is None or len(errors) < len(best):
            best = errors
    return best or []


class Schema:
    """One revision's definitions, indexed by the `method` each request or notification fixes."""

    def __init__(self, document: dict[str, Any]) -> None:
        self.defs: dict[str, Any] = document.get("$defs", {})
        self.by_method: dict[str, str] = {}
        for name, definition in self.defs.items():
            method = definition.get("properties", {}).get("method", {}).get("const")
            if isinstance(method, str):
                self.by_method[method] = name

    def result_of(self, request_def: str) -> str | None:
        """The result definition for a request definition, by the schema's naming."""
        stem = request_def.removesuffix("Request")
        for name in (f"{stem}Result", "EmptyResult"):
            if name in self.defs:
                return name
        return None


def load_schema(spec_root: Path, revision: str) -> Schema:
    path = spec_root / "schema" / revision / "schema.json"
    try:
        return Schema(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise CheckError(f"cannot read the schema {path}: {exc}") from exc


def check_frame(
    item: dict[str, Any], schema: Schema, methods: dict[int, str]
) -> tuple[str, list[Error]] | None:
    """(definition name, errors) for one annotated frame, or None for an unmatched frame.

    `methods` maps the seq of each request to its method, to find a response's definition.
    """
    message: Any = item.get("json")
    kind = item["kind"]
    defs = schema.defs
    if kind in ("request", "notification"):
        name = schema.by_method.get(message["method"])
        return None if name is None else (name, validate(message, defs[name], "$", defs))
    if kind == "error":
        return "JSONRPCErrorResponse", validate(
            message, defs["JSONRPCErrorResponse"], "$", defs)
    if kind == "response":
        method = methods.get(item.get("answers", -1))
        request_def = schema.by_method.get(method) if method else None
        result_def = schema.result_of(request_def) if request_def else None
        if result_def is None:
            return None
        envelope = validate(message, defs["JSONRPCResultResponse"], "$", defs)
        if envelope:
            return "JSONRPCResultResponse", envelope
        return result_def, validate(message["result"], defs[result_def], "$.result", defs)
    reason = item.get("parse_error") or "not a JSON-RPC object"
    if message is None:
        return "JSONRPCMessage", [("$", reason)]
    return "JSONRPCMessage", validate(message, defs["JSONRPCMessage"], "$", defs)


def check_trace(records: list[dict[str, Any]], schema: Schema) -> tuple[int, list[str]]:
    """(frames checked, one report line per failing frame)."""
    frames = [r for r in records if r["dir"] in show.OTHER and not r.get("partial")]
    items = show.annotate(frames)
    methods = {i["seq"]: i["json"]["method"] for i in items if i["kind"] == "request"}
    lines: list[str] = []
    for item in items:
        outcome = check_frame(item, schema, methods)
        if outcome is None:
            method = item["json"]["method"] if item["kind"] != "response" else None
            what = f"unknown method {method!r}" if method else "unknown method: no known request"
            lines.append(f"seq {item['seq']}  $  -  {what}")
            continue
        definition, errors = outcome
        if errors:
            path, reason = errors[0]
            more = f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""
            lines.append(f"seq {item['seq']}  {path}  {definition}  {reason}{more}")
    return len(items), lines


def run(argv: list[str]) -> int:
    args, spec_root = list(argv), DEFAULT_SPEC_ROOT
    if "--spec-root" in args:
        at = args.index("--spec-root")
        spec_root = Path(args[at + 1]) if at + 1 < len(args) else spec_root
        del args[at : at + 2]
    if len(args) != 3 or args[1] != "--revision" or args[0].startswith("-"):
        print(USAGE, file=sys.stderr)
        return 2
    records = show.load(Path(args[0]))
    count, lines = check_trace(records, load_schema(spec_root, args[2]))
    for line in lines:
        print(line)
    if lines:
        print(f"check: {len(lines)} of {count} frames failed", file=sys.stderr)
        return 1
    print(f"check: ok ({count} frames)")
    return 0


def main(argv: list[str]) -> int:
    try:
        return run(argv)
    except (CheckError, show.ShowError) as exc:
        print(f"check: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
