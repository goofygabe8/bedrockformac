# Bedrock for Mac

A Minecraft-themed Mac app for the unofficial [Minecraft Bedrock GDK Launcher](https://github.com/amha0270/Minecraft-Bedrock-GDK-Launcher).

## Install

1. Download **Bedrock-for-Mac.dmg** from the [latest release](https://github.com/goofygabe8/bedrockformac/releases/latest).
2. Open the disk image and drag **Minecraft Bedrock** into **Applications**.
3. Open the app from Applications. Its first launch downloads and checks the upstream Mac runtime and prepares the launcher.
4. Sign in with your Microsoft account, choose a release to download, and press **Play Minecraft**.

An Apple silicon Mac, Rosetta 2, and Python 3 are required. If Python is missing, install it with the Mac installer from python.org. The app is not Apple-notarized. If macOS blocks it, first try opening it, then use System Settings → Privacy & Security → Open Anyway. See [Apple’s instructions](https://support.apple.com/en-us/102445). Game files, licenses, accounts, and saves are not included in the shared app.

Your game versions, sign-in, and worlds live in `~/Library/Application Support/Bedrock for Mac`. The app can be kept in Applications and launched from the Dock.

## Launcher window

The native window has Minecraft-style pixel lettering, block buttons, and a grass-block app icon. It includes Play, installed version selection, downloading any available release (newest by default), Microsoft sign-in, connected controller status, Audio Output, and update controls. Downloaded versions become the selected game version. Microsoft device sign-in links open in your browser, with the code shown in the launcher.

Connect your gamepad before Play, then use Refresh Controllers to check detection. Mouse and keyboard devices and native GameInput files are prepared automatically. SDL-recognized gamepads use the compatibility mapping, including Xbox and PlayStation devices. Bluetooth PS4 input was used on the original Mac; other hardware still needs confirmation. Audio Output opens Wine's audio configuration; choose the output in its Audio tab and restart Minecraft to apply it.

## Updates and existing installations

The app checks this repository's latest public release every time it starts. Downloads and files are verified against SHA-256 checksums. Offline checks allow the installed launcher to open. Game data is outside the update payload, and previous launcher code is kept for rollback.

If you already used the command-based setup, start it to receive the update. Your following start opens the graphical window. A **Minecraft Bedrock.app** appears in your existing launcher folder; drag that app into Applications to keep using that installation's game data. The old command remains a launch shortcut.

The smaller **bedrock-mac-update.zip** asset is for the automatic updater. The **Minecraft-Bedrock-Mac-Fixed-Setup.zip** asset is the command-based installation alternative. For sharing a new installation, send **Bedrock-for-Mac.dmg**.

## Publishing another fix

After changing your local launcher, open **Build Launcher Update.command**, enter a new version (for example `0.3.1`), and upload the generated **bedrock-mac-update.zip** to a public GitHub Release tagged `v0.3.1`. Keep the asset name exactly `bedrock-mac-update.zip`. Changed Swift window code is compiled when building. Recipients receive your update on their next app launch.

The update builder packages code and GUI assets with patches against the original launcher source saved locally. It excludes accounts, worlds, Wine prefixes, game files, and upstream runtime files.

## Credits

The pixel typeface is [Monocraft](https://github.com/IdreesInc/Monocraft), by Idrees Hassan and contributors, distributed under the SIL Open Font License included with the app. The setup and update code and the grass-block icon in this repository are distributed under the MIT license. Upstream software retains its own licensing.
