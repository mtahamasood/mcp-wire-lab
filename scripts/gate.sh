#!/usr/bin/env bash
# One entry point for the automated quality gates (D7); CI runs exactly this.
# Stops at the first failure. Gate numbers are in specs/tech-stack.md.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

gate() { local id="$1"; shift; echo "== $id: $*"; "$@"; }

gate G1 python3 tools/check_provenance.py
gate G2 uvx ruff@0.17.1 check .
gate G3 uvx mypy@2.4.0
gate G4 python3 -m unittest discover -s tests -t . -v
# G5 (end to end against the built server) is a no-op until plan group 4.
gate G8 python3 tools/check_citations.py
# --min-lessons 0 until lesson 01 exists (plan group 6); then drop it so the default of 1 applies.
gate G9 python3 tools/check_lessons.py --min-lessons 0
gate G11 python3 tools/check_no_run_output.py

echo "gate: all green"
