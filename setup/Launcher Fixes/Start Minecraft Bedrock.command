#!/bin/zsh
set -euo pipefail
cd -- "$(dirname -- "$0")"
PYTHON="$(command -v python3 || true)"
[[ -n "$PYTHON" ]] || PYTHON=/opt/homebrew/bin/python3
"$PYTHON" update_client.py
for APP_PATH in "/Applications/Minecraft Bedrock.app" "$HOME/Applications/Minecraft Bedrock.app"; do
    if [[ -x "$APP_PATH/Contents/MacOS/BedrockLauncher" ]]; then
        exec /usr/bin/open "$APP_PATH"
    fi
done
exec ./launcher_gui "$PWD"
