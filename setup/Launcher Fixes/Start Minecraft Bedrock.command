#!/bin/zsh
set -euo pipefail
cd -- "$(dirname -- "$0")"
PYTHON="$(command -v python3 || true)"
[[ -n "$PYTHON" ]] || PYTHON=/opt/homebrew/bin/python3
"$PYTHON" update_client.py
exec ./launcher_gui "$PWD"
