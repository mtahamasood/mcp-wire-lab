#!/usr/bin/env bash
# One entry point for the automated quality gates (D7); CI runs exactly this.
# Stops at the first failure. Gate numbers are in specs/tech-stack.md.
set -euo pipefail

usage() {
  echo "usage: scripts/gate.sh"
  echo "  Takes no arguments. Runs every automated check (needs uv); takes about two minutes and stops at the first failure."
}
case "${1:-}" in
  "") ;;
  -h|--help) usage; exit 0 ;;
  *) echo "gate: unexpected argument: $1" >&2; usage >&2; exit 1 ;;
esac
cd "$(dirname "${BASH_SOURCE[0]}")/.."

gate() { local id="$1"; shift; echo "== $id: $*"; "$@"; }

gate G1 python3 tools/check_provenance.py
gate G2 uvx ruff@0.17.1 check .
gate G3 uvx mypy@2.4.0
gate G4 python3 -m unittest discover -s tests -t . -v
gate G5 python3 -m unittest tests.test_e2e -v
gate G8 python3 tools/check_citations.py
gate G9 python3 tools/check_lessons.py
gate G10 python3 tools/atlas.py --check
gate G11 python3 tools/check_no_run_output.py
# Phases are listed as they are built; a phase that is only specified names tests not yet written.
gate G12 python3 tools/check_claims.py --phases 02,03,04

echo "gate: all green"
