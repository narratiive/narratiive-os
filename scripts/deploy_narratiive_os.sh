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

cd "$REPO"
exec "$PYTHON" "$DEPLOY" --apply
