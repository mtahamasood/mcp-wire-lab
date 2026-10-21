"""The raw client's command line (D3, D4; phase 3 D3, D4).

Usage:
  python3 -m client tour [--caps <list>] -- <server command...>
  python3 -m client manual [--caps <list>] -- <server command...>
  python3 -m client server-tour [--caps <list>] -- <server command...>
  python3 -m client matrix -- <server command...>

`--caps` is a comma-separated list from roots, sampling, elicitation, elicitation-url (or
`none`): exactly those client capabilities are declared in `initialize`. The default is `none`
for `tour` and `manual`, and all four for `server-tour`.
"""

from __future__ import annotations

import sys

from client.handlers import CAPABILITIES, capability_object
from client.manual import run_manual
from client.matrix import run_matrix
from client.server_tour import run_server_tour
from client.tour import run_tour

MODES = ("tour", "manual", "server-tour", "matrix")
USAGE = (
    "usage: python3 -m client <tour|manual|server-tour> [--caps <list>] -- <server command...>\n"
    "       python3 -m client matrix -- <server command...>\n"
    f"  --caps: comma-separated from {', '.join(CAPABILITIES)}, or none\n"
    "  tour: a scripted conversation (exits 0 if every reply was as expected). manual: type your\n"
    "  own lines (`{...}` raw JSON, `:req <method> [<params>]`, `:note <method> [<params>]`,\n"
    "  `:sample <text>`, `:quit`). server-tour: the server-initiated traffic of lesson 03.\n"
    "  matrix: one session per capability set, printed as a table.\n"
    "  To record a run with the tap in between, use scripts/record.sh --client <mode>."
)


def parse_caps(text: str) -> tuple[str, ...]:
    """A `--caps` value as a tuple of capability names; raises ValueError on an unknown one."""
    names = tuple(n for n in text.split(",") if n and n != "none")
    capability_object(names)  # validates
    return names


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in MODES or "--" not in argv[1:]:
        print(USAGE, file=sys.stderr)
        return 2
    mode, rest = argv[0], argv[1:]
    split = rest.index("--")
    options, command = rest[:split], rest[split + 1:]
    caps: tuple[str, ...] | None = None
    if (options and (len(options) != 2 or options[0] != "--caps" or mode == "matrix")
            or not command):
        print(USAGE, file=sys.stderr)
        return 2
    if options:
        try:
            caps = parse_caps(options[1])
        except ValueError as exc:
            print(f"client: {exc}", file=sys.stderr)
            return 2
    if mode == "matrix":
        return run_matrix(command, sys.stdout)
    if mode == "server-tour":
        return run_server_tour(command, sys.stdout, CAPABILITIES if caps is None else caps)
    if mode == "tour":
        return run_tour(command, sys.stdout, caps=caps or ())
    return run_manual(command, sys.stdin, sys.stdout, caps=caps or ())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
