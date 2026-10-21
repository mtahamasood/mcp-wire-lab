"""The trace viewer (D5, D11).

Usage:
  python3 -m tap.show <trace> [--full | --mermaid | --explain <walkthrough.md>]

Prints one line per record: seq, elapsed milliseconds, a direction arrow, and for JSON-RPC
messages the kind, method and id. A response is paired with its request by id and direction,
not by adjacency. --mermaid prints a sequenceDiagram; --explain prints each frame followed by
its note from a walkthrough and exits non-zero on a frame with no note or a note with no frame.

A walkthrough note is a heading `#### `<anchor>`` followed by the note's text. A walkthrough
that explains several traces (phase 4) groups notes under `## <name>` headings: `--explain
<file>#<name>` reads the notes under that heading plus those under `## shared`, and a shared
note a trace does not use is not reported as extra. An anchor is
`<dir>.<method-or-response>.<id-or-occurrence>`: requests and responses are keyed by id,
notifications by occurrence (counted from 0 per direction and method); stderr is
`stderr.<occurrence>` and tap events are `tap.<event>.<occurrence>`.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

USAGE = "usage: python3 -m tap.show <trace> [--full | --mermaid | --explain <walkthrough.md>]"
ARROWS = {"c2s": "->", "s2c": "<-", "stderr": "!!", "tap": ".."}
OTHER = {"c2s": "s2c", "s2c": "c2s"}
ANCHOR_HEADING = re.compile(r"^#### `([^`]+)`\s*$")


class ShowError(Exception):
    """A file the viewer cannot read; main prints it as one `show:` line and exits 2."""


def esc(text: str) -> str:
    """Escape control characters and line separators, so server text cannot rewrite the view."""
    return "".join(
        ch.encode("unicode_escape").decode("ascii")
        if unicodedata.category(ch) in ("Cc", "Zl", "Zp") else ch
        for ch in text
    )


def esc_block(text: str) -> str:
    """esc() for several lines: the newlines between them stay."""
    return "\n".join(esc(line) for line in text.split("\n"))


def id_text(value: Any) -> str:
    """An id as JSON text, so `1`, `"1"`, `1.0` and `true` stay different."""
    return esc(json.dumps(value, ensure_ascii=False))


def kind_of(message: Any) -> str:
    """request, response, error, notification, batch, or raw (not a JSON-RPC object)."""
    if isinstance(message, list):
        return "batch"
    if not isinstance(message, dict):
        return "raw"
    has_id = "id" in message
    if has_id and not isinstance(message["id"], (str, int, float)):
        return "raw"
    if "method" in message:
        if not isinstance(message["method"], str):
            return "raw"
        return "request" if has_id else "notification"
    if has_id:
        if "error" in message:
            return "error" if isinstance(message["error"], dict) else "raw"
        return "response" if "result" in message else "raw"
    return "raw"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ShowError(f"cannot read {path}: {exc}") from exc


def load(path: Path) -> list[dict[str, Any]]:
    records = []
    for number, line in enumerate(read_text(path).split("\n"), 1):
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError as exc:
            raise ShowError(f"{path}:{number}: not a trace record: {exc}") from exc
        synthetic = isinstance(rec, dict) and rec.get("event") == "synthetic"
        if (not isinstance(rec, dict) or not isinstance(rec.get("dir"), str)
                or rec["dir"] not in ARROWS
                or not isinstance(rec.get("t_ns", 0 if synthetic else None), (int, float))):
            raise ShowError(f"{path}:{number}: not a trace record")
        if not synthetic:
            records.append(rec)
    return records


def annotate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add kind, anchor, and for responses the paired request's seq and the latency."""
    pending: dict[tuple[str, str, str], dict[str, Any]] = {}
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
                flight = (direction, type(msg["id"]).__name__, id_text(msg["id"]))
                item["in_flight"] = flight in pending
                pending[flight] = rec
                item["anchor"] = f"{direction}.{msg['method']}.{id_text(msg['id'])}"
            elif kind in ("response", "error"):
                asked = pending.pop(
                    (OTHER[direction], type(msg["id"]).__name__, id_text(msg["id"])), None)
                if asked is not None:
                    item["answers"] = asked.get("seq")
                    item["latency_ms"] = (rec["t_ns"] - asked["t_ns"]) / 1e6
                item["anchor"] = f"{direction}.response.{id_text(msg['id'])}"
            else:
                name = msg["method"] if kind == "notification" else kind
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
        return esc(f"tap {item.get('event')} {extra}".rstrip())
    if item["dir"] == "stderr":
        return "stderr " + esc(str(item.get("raw", "<binary>")).rstrip("\n"))
    if kind == "batch":
        return "batch"
    if kind == "raw":
        if "raw_b64" in item:
            return f"raw (binary, {len(item['raw_b64'])} base64 chars)"
        return esc(f"{kind} ({item.get('parse_error') or 'not a JSON-RPC message'})")
    parts = [kind]
    if "method" in msg:
        parts.append(esc(msg["method"]))
    if "id" in msg:
        parts.append(f"id={id_text(msg['id'])}")
    if kind == "error":
        parts.append(f"code={esc(json.dumps(msg['error'].get('code')))}")
    if "answers" in item:
        parts.append(f"(answers seq {item['answers']}, {item['latency_ms']:.1f} ms)")
    if item.get("in_flight"):
        parts.append("(id already in flight)")
    return " ".join(parts)


def line_for(item: dict[str, Any]) -> str:
    seq = item.get("seq", "-")
    return f"{seq:>4}  {item['t_ns'] / 1e6:9.1f} ms  {ARROWS[item['dir']]}  {describe(item)}"


def mermaid_text(text: str) -> str:
    """Make text safe inside a Mermaid message or note: no ; # or newlines, bounded length."""
    text = esc(text).replace(";", ",").replace("#", "").strip()
    return text[:80]


def mermaid(items: list[dict[str, Any]]) -> str:
    lines = ["sequenceDiagram", "    participant Client", "    participant Server"]
    for item in items:
        direction, kind = item["dir"], item["kind"]
        if direction == "tap":
            note = mermaid_text(f"tap {item.get('event')} {item.get('code', '')}")
            lines.append(f"    Note over Client,Server: {note}")
        elif direction == "stderr":
            note = mermaid_text("stderr: " + item.get("raw", "").rstrip("\n"))
            lines.append(f"    Note over Server: {note}")
        elif kind == "batch":
            lines.append(f"    Note over Client,Server: {direction} batch")
        elif kind == "raw":
            note = mermaid_text(f"{direction} not JSON-RPC: {item.get('raw', '<binary>')}")
            lines.append(f"    Note over Client,Server: {note}")
        else:
            msg: Any = item["json"]
            src, dst = ("Client", "Server") if direction == "c2s" else ("Server", "Client")
            arrow = "-->>" if kind in ("response", "error") else "->>"
            label = msg.get("method", kind) if "method" in msg else kind
            if "id" in msg:
                label += f" id={json.dumps(msg['id'], ensure_ascii=False)}"
            lines.append(f"    {src}{arrow}{dst}: {mermaid_text(label)}")
    return "\n".join(lines)


def parse_notes(path: Path, section: str | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """The notes, and the shared notes. With a section only its notes (and the shared ones)."""
    text = read_text(path)
    if section is not None and not re.search(rf"^## {re.escape(section)}\s*$", text, re.M):
        raise ShowError(f"{path} has no section `## {section}`")
    notes: dict[str, str] = {}
    shared: dict[str, str] = {}
    anchor: str | None = None
    heading = ""
    for line in text.split("\n"):
        found = ANCHOR_HEADING.match(line)
        if found:
            anchor = found.group(1)
            target = shared if section is not None and heading == "shared" else notes
            if section is not None and heading not in (section, "shared"):
                anchor = None
                continue
            target[anchor] = ""
            current = target
        elif line.startswith("#"):
            anchor = None
            if line.startswith("## "):
                heading = line[3:].strip()
        elif anchor is not None:
            current[anchor] = (current[anchor] + " " + line.strip()).strip()
    return notes, shared


def explain(
    items: list[dict[str, Any]], notes: dict[str, str], shared: dict[str, str] | None = None
) -> tuple[list[str], bool]:
    out, ok, used = [], True, set()
    for item in items:
        out.append(line_for(item))
        note = notes.get(item["anchor"]) or (shared or {}).get(item["anchor"])
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


def run(argv: list[str]) -> int:
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
        target, _, section = flags[1].partition("#")
        notes, shared = parse_notes(Path(target), section or None)
        lines, ok = explain(annotate(records), notes, shared)
        print("\n".join(lines))
        return 0 if ok else 1
    for item in annotate(records):
        print(line_for(item))
        if flags == ["--full"]:
            if item.get("json") is not None:
                print(esc_block(json.dumps(item["json"], indent=2, ensure_ascii=False)))
            elif item["dir"] in OTHER and "raw" in item:
                print(esc(item["raw"].rstrip("\n")))
    return 0


def main(argv: list[str]) -> int:
    try:
        code = run(argv)
        sys.stdout.flush()
        return code
    except ShowError as exc:
        print(f"show: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        # the reader went away: point stdout at /dev/null so the exit-time flush stays quiet
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
