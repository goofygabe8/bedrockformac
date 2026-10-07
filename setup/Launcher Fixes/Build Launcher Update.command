#!/bin/zsh
set -euo pipefail
cd -- "$(dirname -- "$0")"
python3 build_update.py
read -r 'reply?Press Return to close. ' || true
