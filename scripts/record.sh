#!/usr/bin/env bash
# Record one fixture, or one run of the raw client, against the pinned, built everything server
# (D14; phase 2 D5).
# Usage: scripts/record.sh <fixture> [name]
#        scripts/record.sh --client <tour|manual|server-tour|sdk-tour|sdk-server-tour> [name]
#        scripts/record.sh --http --client <http-tour|sdk-tour> [name]
# Writes runs/<UTC timestamp>-<name>/{trace.jsonl,stderr.txt}. runs/ is git-ignored (A5).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

usage() {
  echo "usage: scripts/record.sh <fixture> [name]   or   scripts/record.sh --client <tour|manual|server-tour|sdk-tour|sdk-server-tour> [name]"
  echo "  sdk-tour and sdk-server-tour record the TypeScript SDK client (phase 5; needs scripts/bootstrap.sh)."
  echo "  Records the run between the tap and the pinned server into runs/<time>-<name>/ and prints the path."
  echo "  A fixture is a file in tests/fixtures/. Set up once with scripts/bootstrap.sh."
  echo "  scripts/record.sh --http --client <http-tour|sdk-tour> [name]: the same over"
  echo "  Streamable HTTP (the SDK modes use its HTTP transport and end with a DELETE); the tap runs"
  echo "  the server on a private Unix socket and listens on a free 127.0.0.1 port."
}
case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  --client|--http) ;;
  -*) echo "record: unknown option: $1" >&2; usage >&2; exit 1 ;;
esac
http=0
if [ "${1:-}" = "--http" ]; then
  http=1
  shift
  [ "${1:-}" = "--client" ] || { echo "record: --http needs --client http-tour or sdk-tour (fixtures stay on stdio)" >&2; usage >&2; exit 1; }
fi
client=""
if [ "${1:-}" = "--client" ]; then
  client="${2:?usage: scripts/record.sh --client <tour|manual|server-tour|sdk-tour|sdk-server-tour> [name]}"
  case "$client" in
    tour|manual|server-tour) ;;
    sdk-tour|sdk-server-tour)
      [ -d clients/sdk/node_modules ] \
        || { echo "record: clients/sdk/node_modules missing (run scripts/bootstrap.sh)" >&2; exit 1; }
      ;;
    http-tour) [ "$http" = 1 ] || { echo "record: http-tour needs --http" >&2; exit 1; } ;;
    *) echo "record: unknown client mode: $client (use tour, manual, server-tour, sdk-tour, sdk-server-tour or http-tour)" >&2; exit 1 ;;
  esac
  case "$client:$http" in
    tour:1|manual:1|server-tour:1|sdk-server-tour:1) echo "record: --http runs only the http-tour and sdk-tour modes" >&2; exit 1 ;;
  esac
  name="${3:-client-$client}"
else
  fixture="${1:?usage: scripts/record.sh <fixture> [name]}"
  [ -f "$fixture" ] || { echo "record: no such fixture: $fixture" >&2; exit 1; }
  name="${2:-$(basename "$fixture" | sed 's/\..*$//')}"
fi
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
server_cmd=(
  python3 -m tap --trace "$dir/trace.jsonl" --
  env -i "PATH=$dir/bin:/usr/bin:/bin" "HOME=$dir/home" LANG=C.UTF-8 MCP_WIRE_LAB=1
  node "$server" stdio
)

# A server may exit non-zero on purpose (the everything server does after a transport error,
# which the edge experiments provoke). For a fixture the trace is the product and its last
# record is the exit code, so a non-zero status is reported, not fatal. A client run's status
# is the client's verdict on its own steps, so it is passed on after the lines below.
status=0
run_as="$client"
[ "$http" = 0 ] || [ "$client" = http-tour ] || run_as="http-$client"
case "$run_as" in
  "")
    python3 tests/drive.py "$fixture" -- "${server_cmd[@]}" 2> "$dir/stderr.txt" > /dev/null \
      || status=$?
    ;;
  tour)
    # The tour prints its own progress; here it is only the recording that matters.
    python3 -m client tour -- "${server_cmd[@]}" 2> "$dir/stderr.txt" > /dev/null || status=$?
    ;;
  server-tour)
    # The server tour (phase 3) declares every capability and answers the server's requests.
    python3 -m client server-tour -- "${server_cmd[@]}" 2> "$dir/stderr.txt" > /dev/null \
      || status=$?
    ;;
  sdk-tour|sdk-server-tour)
    # The TypeScript SDK client (phase 5), run as source by Node; its stdio transport starts the
    # tap, which starts the server with the allowlisted environment.
    node clients/sdk/src/main.ts "${client#sdk-}" -- "${server_cmd[@]}" 2> "$dir/stderr.txt" \
      > /dev/null || status=$?
    ;;
  http-tour|http-sdk-tour)
    # Streamable HTTP (phase 7 D7): the tap runs the server on a private Unix socket (it adds PORT
    # to the server's environment) and listens on a free loopback port; the client posts to the tap.
    ln -s "$(command -v python3)" "$dir/bin/python3"
    port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
    env -i "PATH=$dir/bin:/usr/bin:/bin" "HOME=$dir/home" LANG=C.UTF-8 MCP_WIRE_LAB=1 \
      python3 -m tap --trace "$dir/trace.jsonl" --http "$port" -- node "$server" streamableHttp \
      2> "$dir/stderr.txt" > /dev/null &
    tap_pid=$!
    ready=0
    for _ in $(seq 1 400); do
      if (exec 3<> "/dev/tcp/127.0.0.1/$port") 2> /dev/null; then ready=1; break; fi
      kill -0 "$tap_pid" 2> /dev/null || break
      sleep 0.05
    done
    if [ "$ready" -eq 1 ]; then
      # The raw client, or the SDK client (phase 7 D12) over its Streamable HTTP transport.
      if [ "$client" = http-tour ]; then
        python3 -m client.http_tour --url "http://127.0.0.1:$port/mcp" 2>> "$dir/stderr.txt" > /dev/null \
          || status=$?
      else
        node clients/sdk/src/main.ts "${client#sdk-}" --url "http://127.0.0.1:$port/mcp" \
          2>> "$dir/stderr.txt" > /dev/null || status=$?
      fi
    fi
    kill -INT "$tap_pid" 2> /dev/null || true
    wait "$tap_pid" || true
    [ "$ready" -eq 1 ] || { echo "record: server did not start (see $dir/stderr.txt)" >&2; exit 1; }
    ;;
  manual)
    # Interactive: the learner's terminal is the client's stdin and stdout; stderr is shown
    # and kept.
    python3 -m client manual -- "${server_cmd[@]}" 2> >(tee "$dir/stderr.txt" >&2) || status=$?
    ;;
esac
[ -s "$dir/trace.jsonl" ] || { echo "record: no trace was written (exit $status)" >&2; exit 1; }
[ "$status" -eq 0 ] || echo "record: the run ended with exit code $status (see the exit record)" >&2

echo "recorded: $dir/trace.jsonl"
echo "read it:  python3 -m tap.show $dir/trace.jsonl"
# A client run's failure is the client's verdict (see above), so it is the script's status too.
[ -z "$client" ] || exit "$status"
