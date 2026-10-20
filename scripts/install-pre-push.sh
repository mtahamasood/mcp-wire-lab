#!/usr/bin/env bash
# Install the G11 pre-push hook (D15) into a repo's .git/hooks. Refuses to overwrite a
# different existing hook. Usage: scripts/install-pre-push.sh [repo-dir]
set -euo pipefail

repo="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
hook="$(git -C "$repo" rev-parse --absolute-git-dir)/hooks/pre-push"

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
