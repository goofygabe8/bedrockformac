"""Explicit experimental-client preparation. Never invoked by the stable launcher."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import importlib.util
import tempfile
import zipfile

PACKAGE = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("BEDROCK_HORIZONS_RUNTIME", str(Path.home() / "Library/Application Support/Bedrock for Mac"))).resolve()
PREFIX = ROOT / "bottle"
WINE = ROOT / "dist/bin/wine"
EXPECTED_GAME = "4a92bfa3ce2428b40ee517b7c1125d9f6f79274382de03846351992663b2e2e4"

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): value.update(block)
    return value.hexdigest()

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("install", "load"):
        raise SystemExit("Use prepare_client.py install or load")
    native = PACKAGE / "native"
    metadata_path = native / "native-build.json"
    if not metadata_path.is_file():
        raise SystemExit("The matching native build is not included. This is the source-only prototype package.")
    metadata = json.loads(metadata_path.read_text())
    if metadata.get("game_sha256") != EXPECTED_GAME or digest(native / "Latite.dll") != metadata.get("dll_sha256"):
        raise SystemExit("The native build metadata or checksum does not match.")
    if not WINE.is_file() or not PREFIX.is_dir(): raise SystemExit("Install Bedrock for Mac before preparing this experimental mod.")
    if sys.argv[1] == "install" and (ROOT / "client_mods.py").is_file() and (PACKAGE / "bedrock-client-mod.json").is_file():
        sys.path.insert(0, str(ROOT))
        import client_mods
        with tempfile.TemporaryDirectory(prefix=".mod-import-", dir=ROOT) as temp:
            archive = Path(temp) / "client-mod.zip"
            manifest = json.loads((PACKAGE / "bedrock-client-mod.json").read_text())
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
                for name in ["bedrock-client-mod.json"] + list(manifest["files"]):
                    output.write(PACKAGE / name, name)
            print(client_mods.install_archive(archive))
        print("The generic launcher loads this installed client mod on the next Minecraft start.")
        return
    env = os.environ.copy(); env.update(WINEPREFIX=str(PREFIX), WINEDEBUG="-all")
    # Manual loading is optional. It does not add a Horizons-specific launcher feature.
    result = subprocess.run([str(WINE), "cmd.exe", "/d", "/c", "echo %LOCALAPPDATA%"], env=env,
                            capture_output=True, text=True, timeout=15, check=True)
    windows_path = result.stdout.strip()
    if not windows_path.lower().startswith("c:\\users\\") or ".." in windows_path.split("\\"):
        raise SystemExit("Could not resolve this launcher's local app-data folder.")
    app_data = PREFIX / "drive_c" / Path(windows_path[3:].replace("\\", "/"))
    destination = app_data / "Latite/Plugins/BedrockHorizons"
    registered = ROOT / "client-mods/bedrock-horizons/native/Latite.dll"
    bridge_dir = registered.parent if registered.is_file() else ROOT / "experimental-horizons"
    if sys.argv[1] == "install":
        raise SystemExit("Update Bedrock for Mac to 0.5.5 or later, then use Install Add-ons to import this client-mod ZIP.")
    listing = subprocess.run(["/bin/ps", "-axo", "comm="], capture_output=True, text=True, timeout=5, check=True).stdout
    running = []
    for line in listing.splitlines():
        path = Path(line.strip())
        if path.name == "Minecraft.Windows.exe" and path.parent.parent == ROOT / "version": running.append(path)
    if len(running) != 1: raise SystemExit("Launch one Minecraft game from Bedrock for Mac first.")
    if digest(running[0]) != EXPECTED_GAME:
        raise SystemExit("This experimental bridge supports only the pinned Minecraft 1.26.52.3 executable.")
    if not (destination / "main.js").is_file() or not (bridge_dir / "Latite.dll").is_file():
        raise SystemExit("Use Install Experimental Horizons.command first.")
    if digest(bridge_dir / "Latite.dll") != metadata["dll_sha256"]:
        raise SystemExit("The installed bridge differs from this package; reinstall it first.")
    dll_path = "Z:" + str(bridge_dir / "Latite.dll").replace("/", "\\")
    subprocess.run([str(WINE), str(PACKAGE / "tools/load-bridge.exe"), dll_path], env=env, check=True, timeout=25)
    print("Use .horizons status in Minecraft. For the companion, use .horizons realm on. Rendering is experimental.")

if __name__ == "__main__":
    try: main()
    except (OSError, ValueError, subprocess.SubprocessError) as error: raise SystemExit(str(error))
