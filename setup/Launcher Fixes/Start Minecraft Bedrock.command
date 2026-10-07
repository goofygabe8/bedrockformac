#!/bin/zsh
set -euo pipefail
cd -- "$(dirname -- "$0")"

if ! command -v python3 >/dev/null; then
    print -u2 "Python 3 is required. Install it, then open this launcher again."
    read -r "?Press Return to close this window. " || true
    exit 1
fi

python3 update_client.py

if [[ ! -x .venv/bin/python ]] || ! .venv/bin/python -c 'import pick, requests' >/dev/null 2>&1; then
    print "Preparing the launcher's small Python environment..."
    rm -rf .venv
    python3 -m venv .venv
    .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
fi

exec .venv/bin/python cli.py
