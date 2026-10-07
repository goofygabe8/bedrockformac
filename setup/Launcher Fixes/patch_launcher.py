"""Apply the small Mac fixes to the pinned public launcher release."""

import hashlib
import sys
from pathlib import Path


EXPECTED_SHA256 = "d912588009167e8785f8e7a6a04e1de0f7b7fcd8d87b4826191308271614db77"


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Cannot apply launcher update ({label}); the downloaded source did not match.")
    return text.replace(old, new, 1)


def main(path):
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if actual != EXPECTED_SHA256:
        raise SystemExit("Cannot apply launcher update; its source checksum did not match.")

    text = replace_once(
        text,
        "import subprocess\nimport os\n",
        "import subprocess\nimport os\nfrom pathlib import Path\nfrom runtime_setup import ensure_wine_input\nfrom launcher_settings import prepare_launch_settings, settings, save_settings\n",
        "input setup import",
    )
    text = replace_once(
        text,
        'DEFAULT_WINE_COMMAND      = ROOT + "/dist/bin/wine"\n',
        'DEFAULT_WINE_COMMAND      = ROOT + "/dist/bin/wine"\n'
        'DEFAULT_WINECFG_COMMAND   = ROOT + "/dist/lib/wine/x86_64-windows/winecfg.exe"\n',
        "audio device selector",
    )
    text = replace_once(
        text,
        "    ):\n    env = os.environ.copy()\n",
        "    ):\n    ensure_wine_input(WINEPREFIX_PATH, WINE_COMMAND)\n    prepare_launch_settings(WINEPREFIX_PATH, WINE_COMMAND)\n    env = os.environ.copy()\n",
        "pre-launch input setup",
    )
    text = replace_once(
        text,
        '        "D3DMETAL_UPSCALER_PROFILE": UPSCALER_PROFILE\n        })\n',
        '        "D3DMETAL_UPSCALER_PROFILE": UPSCALER_PROFILE,\n        })\n'
        '    env.pop("WINEGDK_PREAUTH_DEVICE", None)\n'
        '    if GRAPHICS_BACKEND == "d3dmetal":\n'
        '        env.setdefault("D3DM_MTL4", "0")  # Metal 3 keeps server UI correct with MSAA.\n',
        "original account flow and graphics compatibility",
    )
    text = replace_once(
        text,
        "[WINE_COMMAND, GAME_EXE_PATH], env=env,\n",
        "[WINE_COMMAND, GAME_EXE_PATH], env=env, cwd=os.path.dirname(GAME_EXE_PATH),\n",
        "game working directory",
    )
    text = replace_once(
        text,
        "def Setting():\n",
        'def ConfigureAudio():\n'
        '    env = os.environ.copy()\n'
        '    env.update({"WINEPREFIX": DEFAULT_WINEPREFIX})\n'
        '    subprocess.run([DEFAULT_WINE_COMMAND, DEFAULT_WINECFG_COMMAND], env=env)\n'
        '    print("Audio device changes apply after restarting Minecraft.")\n\n\n'
        'def Setting():\n',
        "audio output setting",
    )
    text = replace_once(
        text,
        "main_list = ['Logout', 'Download', 'Select Version', 'HIGH RES MODE Toggle', 'Graphics Backend', 'Back', 'Quit']",
        "main_list = ['Logout', 'Download', 'Select Version', 'HIGH RES MODE Toggle', 'Audio Output', 'Graphics Backend', 'Back', 'Quit']",
        "audio output menu",
    )
    text = replace_once(
        text,
        "main_list = ['Login', 'HIGH RES MODE Toggle', 'Back', 'Quit']",
        "main_list = ['Login', 'HIGH RES MODE Toggle', 'Audio Output', 'Back', 'Quit']",
        "audio output menu",
    )
    text = replace_once(
        text,
        '    elif main_option == "Graphics Backend":\n',
        '    elif main_option == "Audio Output":\n'
        '        ConfigureAudio()\n'
        '        Setting()\n'
        '    elif main_option == "Graphics Backend":\n',
        "audio output action",
    )
    text = replace_once(
        text,
        '    HIGH_RES_MODE = check_high_res(DEFAULT_WINEPREFIX_REG)\n',
        '    HIGH_RES_MODE = settings(DEFAULT_WINEPREFIX)["values"]["high_resolution"]\n',
        "shared high resolution preference",
    )
    text = replace_once(
        text,
        '        if HIGH_RES_MODE:\n'
        '            toggle_high_res(DEFAULT_WINEPREFIX, DEFAULT_WINEPREFIX_REG, DEFAULT_WINES_COMMAND, False)\n'
        '        elif HIGH_RES_MODE == False:\n'
        '            toggle_high_res(DEFAULT_WINEPREFIX, DEFAULT_WINEPREFIX_REG, DEFAULT_WINES_COMMAND, True)\n'
        '        else:\n'
        '            toggle_high_res(DEFAULT_WINEPREFIX, DEFAULT_WINEPREFIX_REG, DEFAULT_WINES_COMMAND, True)\n',
        '        save_settings({"high_resolution": not HIGH_RES_MODE})\n'
        '        print("High Resolution changes apply on the next Minecraft launch.")\n',
        "high resolution queue",
    )
    text = replace_once(
        text,
        '    )[::-1]\n',
        '    , key=lambda v: tuple(int(part) for part in v.split(".")), reverse=True)\n',
        "numeric release ordering",
    )
    text = replace_once(
        text,
        '    version_option, version_index = pick(available_versions, version_title)\n',
        '    version_option, version_index = pick(available_versions, version_title, default_index=0)\n',
        "newest release default",
    )
    text = replace_once(
        text,
        '    if version_option == "Back":\n        back()\n',
        '    if version_option == "Back":\n        return back()\n',
        "download back action",
    )
    text = replace_once(
        text,
        '    back()\n\n\ndef Quit():\n',
        '    if Path(DEFAULT_VERSIONS_DIR + f"/{version_option}/Minecraft.Windows.exe").is_file():\n'
        '        set_version(DEFAULT_VERSIONS_DIR + "/.version", version_option)\n'
        '    back()\n\n\ndef Quit():\n',
        "activate downloaded version",
    )

    text = replace_once(
        text,
        '    versions = check_versions(DEFAULT_VERSIONS_DIR)\n    if versions:\n        main_title = "Select Game Version:"',
        '    versions = check_versions(DEFAULT_VERSIONS_DIR)\n    if versions:\n        versions = sorted(versions, key=lambda v: tuple(int(part) for part in v.split(".")), reverse=True)\n        main_title = "Select Game Version:"',
        "newest installed version default",
    )
    text = replace_once(
        text,
        '                last_version = versions[-1]\n                set_version(DEFAULT_VERSIONS_DIR + "/.version", versions[-1])',
        '                last_version = max(versions, key=lambda v: tuple(int(part) for part in v.split(".")))\n                set_version(DEFAULT_VERSIONS_DIR + "/.version", last_version)',
        "initial selected version",
    )
    source.write_text(text, encoding="utf-8")
    print("Launcher updates installed.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_launcher.py /path/to/cli.py")
    main(sys.argv[1])
