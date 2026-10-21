"""The raw client's command line (D3, D4).

Usage:
  python3 -m client tour -- <server command...>
  python3 -m client manual -- <server command...>
"""

from __future__ import annotations

import sys

from client.manual import run_manual
from client.tour import run_tour

USAGE = "usage: python3 -m client <tour|manual> -- <server command...>"


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[0] not in ("tour", "manual") or argv[1] != "--":
        print(USAGE, file=sys.stderr)
        return 2
    command = argv[2:]
    if argv[0] == "tour":
        return run_tour(command, sys.stdout)
    return run_manual(command, sys.stdin, sys.stdout)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
