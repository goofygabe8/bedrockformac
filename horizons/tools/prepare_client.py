"""Explicit experimental-client preparation. Never invoked by the stable launcher."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

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
    env = os.environ.copy(); env.update(WINEPREFIX=str(PREFIX), WINEDEBUG="-all")
    # Ask this prefix for its own app-data path rather than guessing a Wine user name.
    result = subprocess.run([str(WINE), "cmd.exe", "/d", "/c", "echo %LOCALAPPDATA%"], env=env,
                            capture_output=True, text=True, timeout=15, check=True)
    windows_path = result.stdout.strip()
    if not windows_path.lower().startswith("c:\\users\\") or ".." in windows_path.split("\\"):
        raise SystemExit("Could not resolve this launcher's local app-data folder.")
    app_data = PREFIX / "drive_c" / Path(windows_path[3:].replace("\\", "/"))
    if not app_data.resolve().is_relative_to((PREFIX / "drive_c/users").resolve()):
        raise SystemExit("The resolved app-data path is outside this launcher.")
    destination = app_data / "Latite/Plugins/BedrockHorizons"
    if sys.argv[1] == "install":
        destination.mkdir(parents=True, exist_ok=True)
        for name in ("main.js", "cache.js", "mesh.js", "tile.js", "plugin.json"):
            shutil.copy2(PACKAGE / "client" / name, destination / name)
        engine = native / "ChakraCore.dll"
        if engine.is_file():
            if digest(engine) != metadata.get("chakra_sha256"): raise SystemExit("The script engine checksum does not match.")
            assets = app_data / "Latite/Assets"; assets.mkdir(parents=True, exist_ok=True)
            shutil.copy2(engine, assets / engine.name)
        bridge_dir = ROOT / "experimental-horizons"; bridge_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(native / "Latite.dll", bridge_dir / "Latite.dll")
        shutil.copy2(PACKAGE / "tools/load-bridge.exe", bridge_dir / "load-bridge.exe")
        print("Experimental client prepared. Launch Minecraft normally, then use Load Experimental Horizons.command.")
        return
    listing = subprocess.run(["/bin/ps", "-axo", "comm="], capture_output=True, text=True, timeout=5, check=True).stdout
    running = []
    for line in listing.splitlines():
        path = Path(line.strip())
        if path.name == "Minecraft.Windows.exe" and path.parent.parent == ROOT / "version": running.append(path)
    if len(running) != 1: raise SystemExit("Launch one Minecraft game from Bedrock for Mac first.")
    if digest(running[0]) != EXPECTED_GAME:
        raise SystemExit("This experimental bridge supports only the pinned Minecraft 1.26.52.3 executable.")
    bridge_dir = ROOT / "experimental-horizons"
    if not (destination / "main.js").is_file() or not (bridge_dir / "Latite.dll").is_file():
        raise SystemExit("Use Install Experimental Horizons.command first.")
    if digest(bridge_dir / "Latite.dll") != metadata["dll_sha256"]:
        raise SystemExit("The installed bridge differs from this package; reinstall it first.")
    dll_path = "Z:" + str(bridge_dir / "Latite.dll").replace("/", "\\")
    subprocess.run([str(WINE), str(bridge_dir / "load-bridge.exe"), dll_path], env=env, check=True, timeout=25)
    print("Use .horizons status in Minecraft. For the companion, use .horizons realm on. Rendering is experimental.")

if __name__ == "__main__":
    try: main()
    except (OSError, ValueError, subprocess.SubprocessError) as error: raise SystemExit(str(error))
