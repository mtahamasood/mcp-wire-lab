#!/usr/bin/env bash
# Record one fixture against the pinned, built everything server (D14).
# Usage: scripts/record.sh <fixture> [name]
# Writes runs/<UTC timestamp>-<name>/{trace.jsonl,stderr.txt}. runs/ is git-ignored (A5).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

fixture="${1:?usage: scripts/record.sh <fixture> [name]}"
[ -f "$fixture" ] || { echo "record: no such fixture: $fixture" >&2; exit 1; }
name="${2:-$(basename "$fixture" | sed 's/\..*$//')}"
server=vendor/servers/src/everything/dist/index.js
[ -f "$server" ] || { echo "record: $server missing (run scripts/bootstrap.sh)" >&2; exit 1; }
node_bin="$(command -v node)" || { echo "record: node not found" >&2; exit 1; }

# A numeric suffix is added until the folder is new, so two recordings of one name in the same
# second never share a folder (D14). mkdir without -p is the atomic claim.
mkdir -p runs
base="runs/$(date -u +%Y%m%dT%H%M%SZ)-$name"
dir="$base"
n=1
until mkdir "$dir" 2> /dev/null; do
  # Only an existing folder means "name taken"; any other failure (missing parent, read-only
  # runs/, full disk) would otherwise loop forever.
  [ -e "$dir" ] || { echo "record: cannot create $dir" >&2; exit 1; }
  n=$((n + 1))
  dir="$base-$n"
done
mkdir "$dir/home" "$dir/bin"
# node is reached through a link in the run folder so the caller's install path (often under
# their home directory) never appears in the server's PATH or the trace.
ln -s "$node_bin" "$dir/bin/node"

# The server sees only this allowlist (D14); nothing from the caller's environment.
# A server may exit non-zero on purpose (the everything server does after a transport error,
# which the edge experiments provoke). The trace is the product and its last record is the exit
# code, so a non-zero status is reported, not fatal.
status=0
python3 tests/drive.py "$fixture" -- \
  python3 -m tap --trace "$dir/trace.jsonl" -- \
  env -i "PATH=$dir/bin:/usr/bin:/bin" "HOME=$dir/home" LANG=C.UTF-8 MCP_WIRE_LAB=1 \
  node "$server" stdio 2> "$dir/stderr.txt" > /dev/null || status=$?
[ -s "$dir/trace.jsonl" ] || { echo "record: no trace was written (exit $status)" >&2; exit 1; }
[ "$status" -eq 0 ] || echo "record: the run ended with exit code $status (see the exit record)" >&2

echo "recorded: $dir/trace.jsonl"
echo "read it:  python3 -m tap.show $dir/trace.jsonl"
