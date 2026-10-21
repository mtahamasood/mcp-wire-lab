#!/usr/bin/env bash
# Install the G11 pre-push hook (D15) into a repo's .git/hooks. Refuses to overwrite a
# different existing hook. Usage: scripts/install-pre-push.sh [repo-dir]
set -euo pipefail

repo="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# The repo's own hooks directory: shared by linked worktrees, and what git uses when
# core.hooksPath is unset (`git rev-parse --git-path hooks` then prints the same place).
# Its own assignment, so that `set -e` stops the script outside a repo (B16).
common="$(git -C "$repo" rev-parse --git-common-dir)"
own="$(cd "$repo" && mkdir -p "$common/hooks" && cd "$common/hooks" && pwd -P)"
hook="$own/pre-push"
configured="$(git -C "$repo" config --get core.hooksPath || true)"
if [ -n "$configured" ]; then
  active="$(cd "$repo" && cd "$(git rev-parse --git-path hooks)" 2>/dev/null && pwd -P || true)"
  if [ "$active" != "$own" ]; then
    echo "install-pre-push: warning: core.hooksPath is set to $configured, so git does not run" >&2
    echo "install-pre-push: $hook unless the hooks in that directory chain to it" >&2
  fi
fi

body='#!/usr/bin/env bash
# Installed by scripts/install-pre-push.sh: G11, run output never reaches git.
exec python3 "$(git rev-parse --show-toplevel)/tools/check_no_run_output.py" --pre-push "$@"'

if [ -e "$hook" ] && [ "$(cat "$hook")" != "$body" ]; then
  echo "install-pre-push: $hook exists and is different; not overwriting it" >&2
  exit 1
fi
mkdir -p "$(dirname "$hook")"
printf '%s\n' "$body" > "$hook"
chmod +x "$hook"
