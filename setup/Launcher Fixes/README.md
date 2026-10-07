# Bedrock for Mac

An unofficial Apple silicon Mac setup for the [Minecraft Bedrock GDK Launcher](https://github.com/amha0270/Minecraft-Bedrock-GDK-Launcher).

## Install on another Mac

1. Unzip **Minecraft-Bedrock-Mac-Fixed-Setup.zip**.
2. Open **Install Fixed Launcher.command**. It downloads and checks the original runtime directly from the upstream release.
3. Open **Start Minecraft Bedrock.command** inside **Minecraft Bedrock GDK Mac (Fixed)**.
4. Sign in with your own Microsoft account and download Minecraft. The newest available release is selected by default, and a successful download becomes the selected version.
5. Connect your controller to macOS before selecting **Play**.

Python 3 and an Apple silicon Mac are required. If macOS blocks an unsigned command, Control-click it and choose Open. Minecraft game files, accounts, saves, and licenses are not included.

## Input and multiplayer

The launcher prepares Wine's mouse and keyboard devices and native GameInput runtime automatically. It detects SDL-recognized gamepads at each game launch and routes their buttons and sticks through Wine's mapped controller path. Common PlayStation and Xbox Wireless IDs are also prepared in advance. The Bluetooth PS4 mapping was used on the working original Mac. Xbox and other pads still need hardware confirmation; support depends on macOS and the bundled SDL runtime recognizing the controller. Pair or plug in the controller before launching the game.

The original Xbox runtime and account flow used by the working Realms setup are retained. **Settings → Audio Output** opens the output device selector.

## Automatic launcher updates

Each Start checks the latest public release at [goofygabe8/bedrockformac](https://github.com/goofygabe8/bedrockformac). New launcher fixes install before the menu opens. Offline or unavailable updates allow the installed launcher to start. Downloaded assets and their files are checked against SHA-256 checksums, and previous code is kept in `.launcher-update-backup` for rollback.

This updates launcher code and controller setup. Minecraft game releases are downloaded through the launcher's Download menu; its default is always the newest listed release. Personal game data and login files are outside the update payload.

## Publish your next fix

After changing your local launcher, open **Build Launcher Update.command**, enter a new release version (such as `0.2.1`), and upload the generated **bedrock-mac-update.zip** to a public GitHub Release tagged `v0.2.1` in `goofygabe8/bedrockformac`. Keep the asset name exactly `bedrock-mac-update.zip`. Recipients receive it on their next Start.

The builder creates patches against the original launcher source saved locally during installation. It includes your launcher changes and helper files without copying accounts, worlds, Wine prefixes, game files, or the upstream runtime into the shared release. New installations use the setup ZIP attached to the release.
