"""The raw client's command line (D3, D4; phase 3 D3, D4; phase 6 D1).

Usage:
  python3 -m client tour [--caps <list>] [--era <era>] -- <server command...>
  python3 -m client manual [--caps <list>] [--era <era>] -- <server command...>
  python3 -m client tasks --era 2026-07-28 -- <server command...>
  python3 -m client server-tour [--caps <list>] -- <server command...>
  python3 -m client matrix -- <server command...>
  python3 -m client <tour|manual|server-tour> [--caps <list>] [--era <era>] --url <url>

`--caps` is a comma-separated list from roots, sampling, elicitation, elicitation-url (or
`none`): exactly those client capabilities are declared (in `initialize`, or in every request's
envelope in 2026-07-28). The default is `none` for `tour` and `manual`, and all four for
`server-tour`; the 2026 tour declares roots, sampling and form elicitation. `--era` is 2025-11-25
(the default) or 2026-07-28: `tour` and `manual` run in either, `tasks` only in 2026-07-28, and
`server-tour` and `matrix` only in 2025-11-25. `--url <url>` (phase 7 D10, D11) replaces
`-- <server command...>` for `tour`, `manual` and `server-tour` (exactly one of the two): the same
mode over Streamable HTTP to a running server; `tasks` and `matrix` stay on stdio.
"""

from __future__ import annotations

import sys

from client.handlers import CAPABILITIES, capability_object
from client.manual import run_manual
from client.matrix import run_matrix
from client.modern import run_modern_tour, run_tasks
from client.server_tour import run_server_tour
from client.tour import run_tour

MODES = ("tour", "manual", "server-tour", "matrix", "tasks")
ERAS = ("2025-11-25", "2026-07-28")
MODERN_ERA = "2026-07-28"
MODERN_TOUR_CAPS = ("roots", "sampling", "elicitation")
USAGE = (
    "usage: python3 -m client <tour|manual|server-tour> [--caps <list>] [--era <era>]"
    " -- <server command...>\n"
    "       python3 -m client tasks --era 2026-07-28 -- <server command...>\n"
    "       python3 -m client matrix -- <server command...>\n"
    "       python3 -m client <tour|manual|server-tour> [--caps <list>] [--era <era>] --url <url>\n"
    "  --url: Streamable HTTP to a running server instead of `-- <server command...>` (not both);\n"
    "  not for tasks or matrix.\n"
    f"  --caps: comma-separated from {', '.join(CAPABILITIES)}, or none\n"
    "  --era: 2025-11-25 (default) or 2026-07-28. tasks needs 2026-07-28; server-tour and matrix\n"
    "  need 2025-11-25.\n"
    "  tour: a scripted conversation (exits 0 if every reply was as expected). manual: type your\n"
    "  own lines (`{...}` raw JSON, `:req <method> [<params>]`, `:note <method> [<params>]`,\n"
    "  `:sample <text>`, `:quit`). server-tour: the server-initiated traffic of lesson 03.\n"
    "  matrix: one session per capability set, printed as a table. tasks: the tasks extension,\n"
    "  one task completed and one cancelled.\n"
    "  To record a run with the tap in between, use scripts/record.sh --client <mode>."
)


def parse_caps(text: str) -> tuple[str, ...]:
    """A `--caps` value as a tuple of capability names; raises ValueError on an unknown one."""
    names = tuple(n for n in text.split(",") if n and n != "none")
    capability_object(names)  # validates
    return names


def parse_options(options: list[str]) -> tuple[str | None, str] | None:
    """`--caps <list>` and `--era <era>` in any order, each at most once; None if malformed."""
    caps: str | None = None
    era = ERAS[0]
    seen: set[str] = set()
    if len(options) % 2:
        return None
    for flag, value in zip(options[::2], options[1::2], strict=True):
        if flag in seen or flag not in ("--caps", "--era"):
            return None
        seen.add(flag)
        if flag == "--caps":
            caps = value
        elif value in ERAS:
            era = value
        else:
            return None
    return caps, era


def main(argv: list[str]) -> int:
    helps = (["-h"], ["--help"])
    if argv[:1] in helps or (argv[:1] and argv[0] in MODES and argv[1:2] in helps):
        print(USAGE)
        return 0
    if not argv or argv[0] not in MODES:
        print(USAGE, file=sys.stderr)
        return 2
    mode, rest = argv[0], argv[1:]
    url: str | None = None
    if "--url" in rest:
        at = rest.index("--url")
        # `--url <url>` replaces `-- <command...>`: nothing may follow the URL, and no command.
        if "--" in rest or at + 2 != len(rest) or rest[at + 1].startswith("-"):
            print(USAGE, file=sys.stderr)
            return 2
        url, options, command = rest[at + 1], rest[:at], []
    elif "--" in rest:
        split = rest.index("--")
        options, command = rest[:split], rest[split + 1:]
        if not command:
            print(USAGE, file=sys.stderr)
            return 2
    else:
        print(USAGE, file=sys.stderr)
        return 2
    parsed = parse_options(options)
    if parsed is None:
        print(USAGE, file=sys.stderr)
        return 2
    caps_text, era = parsed
    modern = era == MODERN_ERA
    if ((mode == "matrix" and (caps_text is not None or modern))
            or (mode == "server-tour" and modern)
            or (mode == "tasks" and (not modern or caps_text is not None))
            or (url is not None and mode in ("matrix", "tasks"))):
        print(USAGE, file=sys.stderr)
        return 2
    caps: tuple[str, ...] | None = None
    if caps_text is not None:
        try:
            caps = parse_caps(caps_text)
        except ValueError as exc:
            print(f"client: {exc}", file=sys.stderr)
            return 2
    if mode == "matrix":
        return run_matrix(command, sys.stdout)
    if mode == "server-tour":
        return run_server_tour(command, sys.stdout, CAPABILITIES if caps is None else caps,
                               url=url)
    if mode == "tasks":
        return run_tasks(command, sys.stdout)
    if mode == "tour":
        if modern:
            return run_modern_tour(command, sys.stdout,
                                   caps=MODERN_TOUR_CAPS if caps is None else caps, url=url)
        return run_tour(command, sys.stdout, caps=caps or (), url=url)
    return run_manual(command, sys.stdin, sys.stdout, caps=caps or (), era=era, url=url)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
