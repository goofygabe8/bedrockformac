"""Prepare the Wine prefix for Minecraft input before each game launch."""

import filecmp
import os
import shutil
import subprocess
import time
from pathlib import Path


REQUIRED_SERVICES = ("PlugPlay", "RpcSs", "winebus", "winehid")
GAMEINPUT_FILES = (
    "GameInputBridge.dll",
    "GameInputRawInputProxy.exe",
    "GameInputRedist.dll",
    "GameInputRedistService.exe",
)

GAMEINPUT_REG = r'''Windows Registry Editor Version 5.00

[HKEY_LOCAL_MACHINE\Software\Microsoft\GameInput]
"RedistDir"="C:\\Program Files\\Microsoft GameInput\\x64"

[HKEY_LOCAL_MACHINE\Software\Wow6432Node\Microsoft\GameInput]
"RedistDir"="C:\\Program Files\\Microsoft GameInput\\x64"

[HKEY_LOCAL_MACHINE\System\CurrentControlSet\Services\GameInputRedistService]
"Description"="GameInput Redist Service"
"DisplayName"="GameInput Redist Service"
"ErrorControl"=dword:00000000
"ImagePath"="C:\\Program Files\\Microsoft GameInput\\x64\\GameInputRedistService.exe"
"ObjectName"="LocalSystem"
"Start"=dword:00000003
"Type"=dword:00000010
'''

# SDL's XInput-compatible path is the working mapping for this Bluetooth DS4.
DS4_REG = r'''Windows Registry Editor Version 5.00

[HKEY_LOCAL_MACHINE\System\CurrentControlSet\Services\WineBus\Devices\054c/09cc]
"Hidraw"=dword:00000000
'''


def missing_input_services(prefix):
    """Read section names only; never expose registry credentials."""
    try:
        lines = (Path(prefix) / "system.reg").read_text(errors="replace").splitlines()
    except OSError:
        return list(REQUIRED_SERVICES)
    sections = {
        line.split("]", 1)[0].lstrip("[").replace("\\\\", "\\").casefold()
        for line in lines if line.startswith("[")
    }
    # Wine persists the CurrentControlSet registry link under ControlSet001.
    roots = (r"System\CurrentControlSet\Services", r"System\ControlSet001\Services")
    return [name for name in REQUIRED_SERVICES
            if not any((root + "\\" + name).casefold() in sections for root in roots)]


def _registry_value_is_set(registry_path, section_name, value_line):
    """Check one value in a Wine .reg section without exposing registry data."""
    try:
        lines = Path(registry_path).read_text(errors="replace").splitlines()
    except OSError:
        return False
    wanted = section_name.replace("\\\\", "\\").casefold()
    active = False
    for line in lines:
        if line.startswith("["):
            current = line.split("]", 1)[0].lstrip("[").replace("\\\\", "\\").casefold()
            active = current == wanted
        elif active and line.strip() == value_line:
            return True
    return False


def _private_registry_backup(prefix):
    backup = Path(__file__).resolve().parent / ".setup-backups" / str(time.time_ns())
    backup.mkdir(parents=True, mode=0o700)
    os.chmod(backup.parent, 0o700)
    os.chmod(backup, 0o700)
    for name in ("system.reg", "user.reg", "userdef.reg"):
        source = Path(prefix) / name
        if source.is_file():
            target = backup / name
            shutil.copy2(source, target)
            os.chmod(target, 0o600)


def _import_registry(prefix, wine_command, registry_text):
    """Import a small launcher-owned registry fragment into the selected prefix."""
    prefix = Path(prefix)
    _private_registry_backup(prefix)
    patch = prefix.parent / (".launcher-setup-" + str(time.time_ns()) + ".reg")
    try:
        patch.write_text(registry_text, encoding="utf-8")
        os.chmod(patch, 0o600)
        env = os.environ.copy()
        env.update(WINEPREFIX=str(prefix), WINEDEBUG="-all", WINEDLLOVERRIDES="mscoree,mshtml=")
        env.pop("WINEGDK_PREAUTH_DEVICE", None)
        result = subprocess.run([str(wine_command), "regedit", "/S", str(patch)], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if result.returncode:
            raise RuntimeError("Wine registry setup failed; regedit exit " + str(result.returncode))
    finally:
        patch.unlink(missing_ok=True)


def _ensure_gameinput_files(prefix):
    prefix = Path(prefix)
    source_dir = Path(__file__).resolve().parent / "dist" / "x64"
    target_dir = prefix / "drive_c" / "Program Files" / "Microsoft GameInput" / "x64"
    missing = [name for name in GAMEINPUT_FILES if not (source_dir / name).is_file()]
    if missing:
        raise RuntimeError("Bundled GameInput files are missing; cannot prepare controller input.")
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in GAMEINPUT_FILES:
        source, target = source_dir / name, target_dir / name
        if not target.is_file() or not filecmp.cmp(source, target, shallow=False):
            shutil.copy2(source, target)


def _gameinput_registry_is_set(prefix):
    prefix = Path(prefix)
    system_reg = prefix / "system.reg"
    values = (
        (r"Software\Microsoft\GameInput", '"RedistDir"="C:\\\\Program Files\\\\Microsoft GameInput\\\\x64"'),
        (r"Software\Wow6432Node\Microsoft\GameInput", '"RedistDir"="C:\\\\Program Files\\\\Microsoft GameInput\\\\x64"'),
        (r"System\ControlSet001\Services\GameInputRedistService", '"ImagePath"="C:\\\\Program Files\\\\Microsoft GameInput\\\\x64\\\\GameInputRedistService.exe"'),
    )
    return all(_registry_value_is_set(system_reg, section, value) for section, value in values)


def _controller_ids():
    """Ask the bundled SDL library for recognized gamepads, without logging names."""
    root = Path(__file__).resolve().parent
    probe = root / "controller_devices"
    library = root / "dist/lib/wine/x86_64-unix/libSDL2-2.0.0.dylib"
    devices = {"054c/09cc", "054c/05c4", "054c/0ce6", "045e/02e0", "045e/0b13"}
    if probe.is_file() and library.is_file():
        try:
            result = subprocess.run([str(probe), str(library)], capture_output=True,
                                    text=True, timeout=8)
            for line in result.stdout.splitlines():
                if len(line) == 9 and line[4] == "/":
                    int(line[:4], 16)
                    int(line[5:], 16)
                    devices.add(line.lower())
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return sorted(devices)


def _controller_registry(prefix):
    system_reg = Path(prefix) / "system.reg"
    base = r"System\ControlSet001\Services\WineBus"
    fragments = []
    options = ('"Enable SDL"=dword:00000001', '"Map Controllers"=dword:00000001')
    if not all(_registry_value_is_set(system_reg, base, value) for value in options):
        fragments.append("[HKEY_LOCAL_MACHINE\\System\\CurrentControlSet\\Services\\WineBus]\n" + "\n".join(options))
    for device in _controller_ids():
        section = base + "\\Devices\\" + device
        value = '"Hidraw"=dword:00000000'
        if not _registry_value_is_set(system_reg, section, value):
            fragments.append("[HKEY_LOCAL_MACHINE\\System\\CurrentControlSet\\Services\\WineBus\\Devices\\" + device + "]\n" + value)
    return "Windows Registry Editor Version 5.00\n\n" + "\n\n".join(fragments) if fragments else None


def _ds4_mapping_is_set(prefix):
    key = r"System\ControlSet001\Services\WineBus\Devices\054c/09cc"
    value = '"Hidraw"=dword:00000000'
    return _registry_value_is_set(Path(prefix) / "system.reg", key, value)


def ensure_wine_input(prefix, wine_command):
    """Wineboot installs the synthetic HID mouse/keyboard and their services.

    A prefix can contain user.reg while still lacking its initial device setup.
    Testing user.reg alone leaves GameInput unable to enumerate any input.
    """
    prefix = Path(prefix)
    missing = missing_input_services(prefix)
    if missing:
        print("Completing mouse and keyboard device setup...")
        _private_registry_backup(prefix)
        env = os.environ.copy()
        env.update(WINEPREFIX=str(prefix), WINEDEBUG="-all", WINEDLLOVERRIDES="mscoree,mshtml=")
        env.pop("WINEGDK_PREAUTH_DEVICE", None)
        wineboot = Path(wine_command).parent / "wineboot"
        result = subprocess.run([str(wineboot), "-u"], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if result.returncode:
            raise RuntimeError("Mouse and keyboard setup failed; Wineboot exit " + str(result.returncode))
        print("Mouse and keyboard device setup completed.")

    _ensure_gameinput_files(prefix)
    missing_registry = []
    if not _gameinput_registry_is_set(prefix):
        missing_registry.append(GAMEINPUT_REG)
    controller_registry = _controller_registry(prefix)
    if controller_registry:
        missing_registry.append(controller_registry)
    if missing_registry:
        header = "Windows Registry Editor Version 5.00"
        sections = [fragment.partition("\n")[2].lstrip() for fragment in missing_registry]
        _import_registry(prefix, wine_command, header + "\n\n" + "\n\n".join(sections))
