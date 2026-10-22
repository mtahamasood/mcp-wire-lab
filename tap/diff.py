"""The trace diff (phase 5 D4, L12): which JSON-RPC messages two traces do not share.

Usage:
  python3 -m tap.diff <a> <b> [--explain <walkthrough.md>[#section]]

Each frame gets a key, ids normalised away: a request or notification is
`<dir>.<method>#<n>` (n counts that method in that direction from 0), a response is
`<dir>.response:<method>#<n>` (the key of the request it answers), anything else is
`<dir>.non-message#<n>`. Frames with the same key in both traces are compared as JSON, with
every `id` (and the `requestId` of `notifications/cancelled`) replaced by the request's key. A
pair equal as JSON but written differently (member order, spacing, escapes) is counted, not
listed. Timings, `seq`, stderr and tap records are not compared. Exit 0 if nothing differs and
nothing is in one trace only, 1 otherwise, 2 on a usage error or an unreadable trace.

With --explain each reported entry is followed by the walkthrough note whose anchor heading
(`#### `<key>``) is its key; `<prefix>#<a>-<b>` is one note for keys `<prefix>#a` to
`<prefix>#b`; `#section` reads only that `##` section plus `## shared`. The run fails (exit 1)
on an entry with no note and on a note with no entry.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tap.show import OTHER, ShowError, esc, id_text, kind_of, load, parse_notes

USAGE = (
    "usage: python3 -m tap.diff <a> <b> [--explain <walkthrough.md>[#section]]\n"
    "  <a> and <b> are trace.jsonl files from scripts/record.sh. Prints the JSON-RPC messages\n"
    "  that differ between them (ids normalised), then those in only one trace, then a summary.\n"
    "  Exit 0 if nothing differs, 1 if something does. --explain: a note after every entry, from\n"
    "  a walkthrough in docs/walkthrough/ (e.g. docs/walkthrough/05-sdk-client.md#tour); exits 1\n"
    "  on an entry with no note or a note with no entry."
)
CUT = 60
ABSENT = "(absent)"
RANGE_KEY = re.compile(r"^(.+#)(\d+)-(\d+)$")


@dataclass
class Frame:
    key: str
    seq: Any
    message: Any  # the message with ids replaced by keys; the frame's text for a non-message
    ordered: str  # that message dumped with its members in the order written
    plain: bool  # the frame is the compact form of its own parse (no extra spacing or escapes)


@dataclass
class Entry:
    kind: str  # "differs", "only in a" or "only in b"
    key: str
    detail: list[str] = field(default_factory=list)  # header text, then one line per path


@dataclass
class Result:
    entries: list[Entry]
    pairs: int
    equal: int
    bytes_only: int
    differ: int
    only_a: int
    only_b: int

    @property
    def clean(self) -> bool:
        return self.differ == 0 and self.only_a == 0 and self.only_b == 0


def dump(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def frame_text(rec: dict[str, Any]) -> str:
    """The text of a frame that is not a JSON-RPC message."""
    if "raw" in rec:
        return str(rec["raw"]).rstrip("\n")
    if "raw_b64" in rec:
        return "raw_b64:" + str(rec["raw_b64"])
    return dump(rec.get("json"))


def make_frames(records: list[dict[str, Any]]) -> list[Frame]:
    """Key every c2s and s2c frame; see the module docstring for the key forms."""
    occurrences: Counter[str] = Counter()
    pending: dict[tuple[str, str, str], str] = {}  # (dir, id type, id text) -> request key
    asked: dict[tuple[str, str, str], str] = {}  # every request seen, for requestId mapping
    out: list[Frame] = []
    for rec in records:
        direction = rec["dir"]
        if direction not in OTHER:
            continue
        msg: Any = rec.get("json")
        kind = kind_of(msg)
        seq = rec.get("seq", "-")
        key: str | None = None
        request_key = ""
        if kind in ("request", "notification"):
            slot = f"{direction}.{msg['method']}"
            key = f"{slot}#{occurrences[slot]}"
            occurrences[slot] += 1
            if kind == "request":
                flight = (direction, type(msg["id"]).__name__, id_text(msg["id"]))
                pending[flight] = key
                asked[flight] = key
            request_key = key
        elif kind in ("response", "error"):
            flight = (OTHER[direction], type(msg["id"]).__name__, id_text(msg["id"]))
            request_key = pending.pop(flight, "")
            if request_key:
                key = f"{direction}.response:{request_key.split('.', 1)[1]}"
        if key is None:
            slot = f"{direction}.non-message"
            key = f"{slot}#{occurrences[slot]}"
            occurrences[slot] += 1
            text = frame_text(rec)
            out.append(Frame(key, seq, text, text, True))
            continue
        norm = dict(msg)
        if "id" in norm:
            norm["id"] = request_key
        params = norm.get("params")
        if norm.get("method") == "notifications/cancelled" and isinstance(params, dict):
            if "requestId" in params:
                target = asked.get((direction, type(params["requestId"]).__name__,
                                    id_text(params["requestId"])))
                if target is not None:
                    norm["params"] = {**params, "requestId": target}
        raw = str(rec["raw"]).rstrip("\n") if "raw" in rec else dump(msg)
        out.append(Frame(key, seq, norm, dump(norm), raw == dump(msg)))
    return out


def same(a: Any, b: Any) -> bool:
    """Typed JSON equality: member order ignored, array order kept, 1, 1.0 and true distinct."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    return bool(a == b)


def show_value(value: Any) -> str:
    text = esc(ABSENT if value is _MISSING else dump(value))
    return text if len(text) <= CUT else text[: CUT - 3] + "..."


class _Missing:
    pass


_MISSING = _Missing()


def differences(a: Any, b: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    """The JSON paths where a and b differ, with both values (_MISSING for an absent member)."""
    if isinstance(a, dict) and isinstance(b, dict):
        found: list[tuple[str, Any, Any]] = []
        for k in [*a, *(k for k in b if k not in a)]:
            sub = f"{path}.{k}" if path else str(k)
            if k not in a or k not in b:
                found.append((sub, a.get(k, _MISSING), b.get(k, _MISSING)))
            else:
                found += differences(a[k], b[k], sub)
        return found
    if isinstance(a, list) and isinstance(b, list):
        found = []
        for i in range(max(len(a), len(b))):
            sub = f"{path}[{i}]"
            if i >= len(a) or i >= len(b):
                found.append((sub, a[i] if i < len(a) else _MISSING,
                              b[i] if i < len(b) else _MISSING))
            else:
                found += differences(a[i], b[i], sub)
        return found
    return [] if same(a, b) else [(path or "(message)", a, b)]


def compare(a_records: list[dict[str, Any]], b_records: list[dict[str, Any]]) -> Result:
    a, b = make_frames(a_records), make_frames(b_records)
    b_by_key = {f.key: f for f in b}
    a_keys = {f.key for f in a}
    entries: list[Entry] = []
    pairs = equal = bytes_only = differ = 0
    for fa in a:
        fb = b_by_key.get(fa.key)
        if fb is None:
            continue
        pairs += 1
        if same(fa.message, fb.message):
            if fa.ordered == fb.ordered and fa.plain == fb.plain:
                equal += 1
            else:
                bytes_only += 1
            continue
        differ += 1
        lines = [f"~ {fa.key}  (a seq {fa.seq}, b seq {fb.seq})"]
        for path, va, vb in differences(fa.message, fb.message):
            lines.append(f"    {path}: {show_value(va)} | {show_value(vb)}")
        entries.append(Entry("differs", fa.key, lines))
    only_a = [f for f in a if f.key not in b_by_key]
    only_b = [f for f in b if f.key not in a_keys]
    entries += [Entry("only in a", f.key, [f"- {f.key}  only in a (seq {f.seq})"]) for f in only_a]
    entries += [Entry("only in b", f.key, [f"+ {f.key}  only in b (seq {f.seq})"]) for f in only_b]
    return Result(entries, pairs, equal, bytes_only, differ, len(only_a), len(only_b))


def summary(r: Result) -> str:
    return (f"summary: {r.pairs} pairs, {r.equal} equal, {r.bytes_only} equal as JSON but not as "
            f"bytes, {r.differ} differ; {r.only_a} only in a, {r.only_b} only in b")


def expand_ranges(notes: dict[str, str]) -> dict[str, str]:
    """Turn each `<prefix>#<a>-<b>` note into one note per key; the first has the text."""
    out: dict[str, str] = {}
    for anchor, text in notes.items():
        found = RANGE_KEY.match(anchor)
        if not found:
            out[anchor] = text
            continue
        prefix, first, last = found.group(1), int(found.group(2)), int(found.group(3))
        for n in range(first, last + 1):
            out[f"{prefix}{n}"] = text if n == first else f"(continues the note on {prefix}{first})"
    return out


def render(
    result: Result, notes: tuple[dict[str, str], dict[str, str]] | None
) -> tuple[list[str], bool]:
    """The report lines, and whether the explanation (if any) is complete."""
    lines: list[str] = []
    ok = True
    own = expand_ranges(notes[0]) if notes else {}
    shared = expand_ranges(notes[1]) if notes else {}
    for entry in result.entries:
        lines += entry.detail
        if notes is not None:
            note = own.get(entry.key) or shared.get(entry.key)
            if note:
                lines.append(f"        {note}")
            else:
                lines.append(f"        (no note)  [{entry.key}]")
                ok = False
    if notes is not None:
        used = {e.key for e in result.entries}
        for anchor in own:
            if anchor not in used:
                lines.append(f"(no difference)  [{anchor}]")
                ok = False
    lines.append(summary(result))
    return lines, ok


def run(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        print(USAGE)
        return 0
    flags = argv[2:]
    if len(argv) < 2 or argv[0].startswith("-") or argv[1].startswith("-") or not (
        flags == [] or (len(flags) == 2 and flags[0] == "--explain")
    ):
        print(USAGE, file=sys.stderr)
        return 2
    result = compare(load(Path(argv[0])), load(Path(argv[1])))
    notes = None
    if flags:
        target, _, section = flags[1].partition("#")
        notes = parse_notes(Path(target), section or None)
    lines, ok = render(result, notes)
    print("\n".join(lines))
    if flags:
        return 0 if ok else 1
    return 0 if result.clean else 1


def main(argv: list[str]) -> int:
    try:
        code = run(argv)
        sys.stdout.flush()
        return code
    except ShowError as exc:
        print(f"diff: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
