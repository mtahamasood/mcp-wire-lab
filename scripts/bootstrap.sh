#!/usr/bin/env bash
# Build the pinned everything server from its own lockfile (D6) and check both
# submodules are at their pins (D10). Never modifies the submodules' tracked files.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

want_node="v24.22.0"
pin_servers="51b6382a3e827aceb6bce430b1208d69b93d95ea"
pin_spec="1155ca460e5097019f32769b38dcba194432e2fb"

fail() { echo "bootstrap: $*" >&2; exit 1; }

[ "$(node --version)" = "$want_node" ] || fail "need node $want_node, found $(node --version)"

check_pin() {
  local path="$1" pin="$2" got
  got="$(git -C "$path" rev-parse HEAD 2>/dev/null)" || fail "$path is not checked out (run: git submodule update --init)"
  [ "$got" = "$pin" ] || fail "$path is at $got, expected $pin"
}
check_pin vendor/servers "$pin_servers"
check_pin vendor/spec "$pin_spec"

# Narrowest install that builds the everything server (M5): one workspace, no scripts.
(cd vendor/servers && npm ci --workspace=@modelcontextprotocol/server-everything --ignore-scripts)
(cd vendor/servers/src/everything && npm run build)

[ -f vendor/servers/src/everything/dist/index.js ] || fail "build did not produce dist/index.js"
[ -z "$(git -C vendor/servers status --porcelain)" ] || fail "vendor/servers working tree was modified"
[ -z "$(git -C vendor/spec status --porcelain)" ] || fail "vendor/spec working tree was modified"

scripts/install-pre-push.sh "$root"

echo "bootstrap: ok ($(node --version))"
