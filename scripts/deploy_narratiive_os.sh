#!/bin/zsh
set -euo pipefail

REPO="$HOME/Documents/narratiive-os"
PYTHON="$REPO/.venv/bin/python"
DEPLOY="$REPO/scripts/deploy_tony_runtime.py"

if [[ ! -d "$REPO/.git" ]]; then
  echo "Narratiive OS repository not found at canonical path: $REPO" >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Narratiive OS virtual-environment Python not found at: $PYTHON" >&2
  echo "Use the repository .venv; do not deploy with /usr/bin/python3." >&2
  exit 1
fi

PYTHON_VERSION="$($PYTHON -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
PYTHON_OK="$($PYTHON -c 'import sys; print("yes" if sys.version_info >= (3, 10) else "no")')"
if [[ "$PYTHON_OK" != "yes" ]]; then
  echo "Narratiive OS requires Python 3.10+; canonical .venv is $PYTHON_VERSION" >&2
  exit 1
fi

echo "Narratiive OS deploy: $REPO"
echo "Python: $PYTHON ($PYTHON_VERSION)"

# Deployment validation must not inherit live Notion credentials from an
# interactive shell. The running Tony LaunchAgents load runtime.env themselves,
# so clearing these variables here isolates tests without removing live access.
unset NARRATIIVE_NOTION_TOKEN
unset NOTION_API_TOKEN
unset NOTION_API_KEY
unset NOTION_TOKEN

cd "$REPO"
exec "$PYTHON" "$DEPLOY" --apply
