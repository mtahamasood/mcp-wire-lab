#!/usr/bin/env bash
# One entry point for the automated quality gates (D7); CI runs exactly this.
# Stops at the first failure. Gate numbers are in specs/tech-stack.md.
set -euo pipefail

usage() {
  echo "usage: scripts/gate.sh [--list]"
  echo "  Runs every automated check (needs uv); takes about 5 minutes and stops at the first failure."
  echo "  Each Python test runs once: G4 runs the unit tests, every tests/test_*.py except"
  echo "  tests/test_e2e*.py; G5 runs those end-to-end tests against the built server."
  echo "  --list prints the Python test modules G4 and G5 run, one gate per line, and runs nothing."
}
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# modules <unit|e2e>: the dotted test modules one of the two Python test gates runs.
modules() {
  local file module
  for file in tests/test_*.py; do
    module="${file%.py}"
    module="${module//\//.}"
    case "$file" in
      tests/test_e2e*) if [ "$1" = e2e ]; then echo "$module"; fi ;;
      *) if [ "$1" = unit ]; then echo "$module"; fi ;;
    esac
  done
}

case "${1:-}" in
  "") ;;
  -h|--help) usage; exit 0 ;;
  --list)
    echo "G4" $(modules unit)
    echo "G5" $(modules e2e)
    exit 0
    ;;
  *) echo "gate: unexpected argument: $1" >&2; usage >&2; exit 1 ;;
esac

gate() { local id="$1"; shift; echo "== $id: $*"; "$@"; }

gate G1 python3 tools/check_provenance.py
gate G2 uvx ruff@0.17.1 check .
gate G3 uvx mypy@2.4.0
gate G3 node clients/sdk/node_modules/typescript/bin/tsc -p clients/sdk
# shellcheck disable=SC2046 # one argument per module name
gate G4 python3 -m unittest -v $(modules unit)
gate G4 node --test "clients/sdk/test/*.test.ts"
# shellcheck disable=SC2046
gate G5 python3 -m unittest -v $(modules e2e)
gate G8 python3 tools/check_citations.py
gate G9 python3 tools/check_lessons.py
gate G10 python3 tools/atlas.py --check
gate G11 python3 tools/check_no_run_output.py
# Phases are listed as they are built; a phase that is only specified names tests not yet written.
gate G12 python3 tools/check_claims.py --phases 02,03,04,05,06,07

echo "gate: all green"
