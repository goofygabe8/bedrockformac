#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
INSTALL_DIR="$SCRIPT_DIR/Minecraft Bedrock GDK Mac (Fixed)"
DOWNLOAD="$SCRIPT_DIR/.bedrock-gdk-launcher-base.zip"
STAGE=""
RELEASE_URL="https://github.com/amha0270/Minecraft-Bedrock-GDK-Launcher/releases/download/BETA/Minecraft-Bedrock-Launcher_MacOS_v0.1.0b.zip"
RELEASE_SHA256="10165c17c992547b95dd873256a9c9fb4b7ed1c590c87b1c1366bc2d17be74d1"
RUNTIME_SHA256="3133debe65896679aff7d381419cf26ea997c4e0ad0a5b28cdab1ea436acf213"

cleanup() {
    [[ -n "$STAGE" && -d "$STAGE" ]] && rm -rf -- "$STAGE"
    [[ -f "$DOWNLOAD" ]] && rm -f -- "$DOWNLOAD"
}

finish() {
    status=$?
    cleanup
    if [[ $status -ne 0 ]]; then
        print ""
        print "Setup stopped. Read the message above, then run this installer again."
    fi
    print ""
    read -r 'reply?Press Return to close this window. ' || true
    exit "$status"
}
trap finish EXIT

fail() {
    print -u2 -- "$1"
    return 1
}

[[ "$(uname -m)" == "arm64" ]] || fail "This setup needs an Apple silicon Mac (M1 or newer)."
command -v curl >/dev/null || fail "curl is missing from macOS."
command -v unzip >/dev/null || fail "unzip is missing from macOS."
command -v shasum >/dev/null || fail "shasum is missing from macOS."
command -v python3 >/dev/null || fail "Install Python 3, then run this installer again."
[[ -d "$SCRIPT_DIR/Launcher Fixes" ]] || fail "Keep the 'Launcher Fixes' folder beside this installer."
[[ ! -e "$INSTALL_DIR" ]] || fail "The install folder already exists: $INSTALL_DIR. Move or rename it first."

STAGE="$(mktemp -d "$SCRIPT_DIR/.bedrock-fixed-stage.XXXXXX")"
print "Downloading the original launcher from its GitHub release..."
curl --fail --location --silent --show-error --output "$DOWNLOAD" "$RELEASE_URL"

actual_sha="$(shasum -a 256 "$DOWNLOAD" | awk '{print $1}')"
[[ "$actual_sha" == "$RELEASE_SHA256" ]] || fail "The downloaded launcher did not match the pinned GitHub release. No install was made."

print "Checking the launcher runtime..."
unzip -q "$DOWNLOAD" -d "$STAGE"
BASE="$STAGE/Minecraft-Bedrock-Launcher_MacOS_v0.1.0b"
[[ -d "$BASE/dist" && -d "$BASE/d3dmetal" ]] || fail "The downloaded launcher archive is missing its runtime folders."
[[ ! -e "$BASE/bottle" && ! -e "$BASE/version" && ! -e "$BASE/.winegdk-data" ]] || fail "The launcher archive unexpectedly contains profile or game data."
runtime_sha="$(shasum -a 256 "$BASE/dist/lib/wine/x86_64-windows/xgameruntime.dll" | awk '{print $1}')"
[[ "$runtime_sha" == "$RUNTIME_SHA256" ]] || fail "The bundled Xbox runtime differs from the version with working Realms."

print "Adding the mouse, keyboard, GameInput, and controller setup..."
cp "$BASE/cli.py" "$BASE/.launcher-base-cli.py"
python3 "$SCRIPT_DIR/Launcher Fixes/patch_launcher.py" "$BASE/cli.py"
cp "$SCRIPT_DIR/Launcher Fixes/runtime_setup.py" "$BASE/runtime_setup.py"
for extra in patch_launcher.py update_client.py build_update.py controller_devices controller_devices.c update-channel.json .launcher-version "Build Launcher Update.command"; do
    cp "$SCRIPT_DIR/Launcher Fixes/$extra" "$BASE/$extra"
done
chmod 755 "$BASE/controller_devices" "$BASE/Build Launcher Update.command"
cp "$SCRIPT_DIR/Launcher Fixes/Start Minecraft Bedrock.command" "$BASE/Start Minecraft Bedrock.command"
cp "$SCRIPT_DIR/Launcher Fixes/requirements.txt" "$BASE/requirements.txt"
cp "$SCRIPT_DIR/Launcher Fixes/README.md" "$BASE/README-Fixed-Setup.md"
chmod 755 "$BASE/Start Minecraft Bedrock.command"
mv "$BASE" "$INSTALL_DIR"
python3 "$INSTALL_DIR/update_client.py" --ensure-gui

print ""
print "Installed: $INSTALL_DIR"
print "Open 'Minecraft Bedrock.app' there, sign in with the recipient's own Microsoft account, and download Minecraft; the newest release is selected by default."
print "The first Play prepares the new Wine input devices and controller runtime."
