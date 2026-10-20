"""The trace viewer (D5, D11).

Usage:
  python3 -m tap.show <trace> [--full | --mermaid | --explain <walkthrough.md>]

Prints one line per record: seq, elapsed milliseconds, a direction arrow, and for JSON-RPC
messages the kind, method and id. A response is paired with its request by id and direction,
not by adjacency. --mermaid prints a sequenceDiagram; --explain prints each frame followed by
its note from a walkthrough and exits non-zero on a frame with no note or a note with no frame.

A walkthrough note is a heading `#### `<anchor>`` followed by the note's text. An anchor is
`<dir>.<method-or-response>.<id-or-occurrence>`: requests and responses are keyed by id,
notifications by occurrence (counted from 0 per direction and method); stderr is
`stderr.<occurrence>` and tap events are `tap.<event>.<occurrence>`.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

USAGE = "usage: python3 -m tap.show <trace> [--full | --mermaid | --explain <walkthrough.md>]"
ARROWS = {"c2s": "->", "s2c": "<-", "stderr": "!!", "tap": ".."}
OTHER = {"c2s": "s2c", "s2c": "c2s"}
ANCHOR_HEADING = re.compile(r"^#### `([^`]+)`\s*$")


def kind_of(message: Any) -> str:
    """request, response, error, notification, or raw (not a single JSON-RPC object)."""
    if not isinstance(message, dict):
        return "raw"
    if "method" in message:
        return "request" if "id" in message else "notification"
    if "id" in message:
        return "error" if "error" in message else "response"
    return "raw"


def load(path: Path) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [r for r in records if r.get("event") != "synthetic"]


def annotate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add kind, anchor, and for responses the paired request's seq and the latency."""
    pending: dict[tuple[str, Any], dict[str, Any]] = {}
    occurrences: Counter[str] = Counter()
    out = []
    for rec in records:
        direction = rec["dir"]
        item: dict[str, Any] = {**rec, "kind": "tap", "anchor": ""}
        if direction in OTHER:
            msg: Any = rec.get("json")
            kind = kind_of(msg)
            item["kind"] = kind
            if kind == "request":
                pending[(direction, msg["id"])] = rec
                item["anchor"] = f"{direction}.{msg['method']}.{msg['id']}"
            elif kind in ("response", "error"):
                asked = pending.pop((OTHER[direction], msg["id"]), None)
                if asked is not None:
                    item["answers"] = asked.get("seq")
                    item["latency_ms"] = (rec["t_ns"] - asked["t_ns"]) / 1e6
                item["anchor"] = f"{direction}.response.{msg['id']}"
            else:
                name = msg["method"] if kind == "notification" else "raw"
                key = f"{direction}.{name}"
                item["anchor"] = f"{key}.{occurrences[key]}"
                occurrences[key] += 1
        else:
            key = "stderr" if direction == "stderr" else f"tap.{rec.get('event')}"
            item["anchor"] = f"{key}.{occurrences[key]}"
            occurrences[key] += 1
        out.append(item)
    return out


def describe(item: dict[str, Any]) -> str:
    msg: Any = item.get("json")
    kind = item["kind"]
    if item["dir"] == "tap":
        extra = item.get("argv") or item.get("code", "")
        return f"tap {item.get('event')} {extra}".rstrip()
    if item["dir"] == "stderr":
        return "stderr " + str(item.get("raw", "<binary>")).rstrip("\n")
    if kind == "raw":
        return f"{kind} ({item.get('parse_error') or 'not a JSON-RPC message'})"
    parts = [kind]
    if "method" in msg:
        parts.append(msg["method"])
    if "id" in msg:
        parts.append(f"id={msg['id']}")
    if kind == "error":
        parts.append(f"code={msg['error'].get('code')}")
    if "answers" in item:
        parts.append(f"(answers seq {item['answers']}, {item['latency_ms']:.1f} ms)")
    return " ".join(parts)


def line_for(item: dict[str, Any]) -> str:
    seq = item.get("seq", "-")
    return f"{seq:>4}  {item['t_ns'] / 1e6:9.1f} ms  {ARROWS[item['dir']]}  {describe(item)}"


def mermaid_text(text: str) -> str:
    """Make text safe inside a Mermaid message or note: no ; # or newlines, bounded length."""
    text = text.replace(";", ",").replace("#", "").replace("\n", " ").strip()
    return text[:80]


def mermaid(items: list[dict[str, Any]]) -> str:
    lines = ["sequenceDiagram", "    participant Client", "    participant Server"]
    for item in items:
        direction, kind = item["dir"], item["kind"]
        if direction == "tap":
            note = mermaid_text(f"tap {item.get('event')} {item.get('code', '')}")
            lines.append(f"    Note over Client,Server: {note}")
        elif direction == "stderr":
            lines.append(f"    Note over Server: {mermaid_text('stderr: ' + item.get('raw', ''))}")
        elif kind == "raw":
            note = mermaid_text(f"{direction} not JSON-RPC: {item.get('raw', '<binary>')}")
            lines.append(f"    Note over Client,Server: {note}")
        else:
            msg: Any = item["json"]
            src, dst = ("Client", "Server") if direction == "c2s" else ("Server", "Client")
            arrow = "-->>" if kind in ("response", "error") else "->>"
            label = msg.get("method", kind) if "method" in msg else kind
            if "id" in msg:
                label += f" id={msg['id']}"
            lines.append(f"    {src}{arrow}{dst}: {mermaid_text(label)}")
    return "\n".join(lines)


def parse_notes(path: Path) -> dict[str, str]:
    notes: dict[str, str] = {}
    anchor: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        found = ANCHOR_HEADING.match(line)
        if found:
            anchor = found.group(1)
            notes[anchor] = ""
        elif line.startswith("#"):
            anchor = None
        elif anchor is not None:
            notes[anchor] = (notes[anchor] + " " + line.strip()).strip()
    return notes


def explain(items: list[dict[str, Any]], notes: dict[str, str]) -> tuple[list[str], bool]:
    out, ok, used = [], True, set()
    for item in items:
        out.append(line_for(item))
        note = notes.get(item["anchor"])
        used.add(item["anchor"])
        if note:
            out.append(f"        {note}")
        else:
            out.append(f"        (no note)  [{item['anchor']}]")
            ok = False
    for anchor in notes:
        if anchor not in used:
            out.append(f"(no frame)  [{anchor}]")
            ok = False
    return out, ok


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(USAGE, file=sys.stderr)
        return 2
    path, flags = Path(argv[0]), argv[1:]
    if flags not in ([], ["--full"], ["--mermaid"]) and not (
        len(flags) == 2 and flags[0] == "--explain"
    ):
        print(USAGE, file=sys.stderr)
        return 2
    records = load(path)
    if flags[:1] == ["--mermaid"]:
        print(mermaid(annotate(records)))
        return 0
    if flags[:1] == ["--explain"]:
        lines, ok = explain(annotate(records), parse_notes(Path(flags[1])))
        print("\n".join(lines))
        return 0 if ok else 1
    for item in annotate(records):
        print(line_for(item))
        if flags == ["--full"] and item.get("json") is not None:
            print(json.dumps(item["json"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
