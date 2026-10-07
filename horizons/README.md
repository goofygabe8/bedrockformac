# Bedrock Horizons 0.1.3 — experimental development build

Original terrain-cache and world-companion code for a Distant Horizons-like Bedrock feature. This is a prototype, not a completed Distant Horizons port. Successful distant-terrain rendering has not been confirmed in Minecraft.

## Native input and startup recovery

Native 0.1.1 produced three startup crashes under Wine. Native 0.1.2 kept optional trust checks untrusted on failure, but its log exposed another missing WinRT service and a failed D3D11On12 overlay; selecting a world also lost mouse control. The game worked after disabling the native mod.

Native 0.1.3 uses a narrow terrain scripting bridge: it does not intercept the window procedure, mouse, keyboard, controller, camera input or cursor capture. It does not hook DirectX presentation or initialize the desktop overlay, built-in modules or overlay menus. Minecraft retains its own input and UI. Graphics3D terrain drawing remains in the game renderer, skips empty batches and restores shader color. An unused WebSocket member no longer activates an unavailable WinRT service during script registration. Optional online trust failures still retain untrusted permissions. The companion receiver also accepts the pinned SDK’s named text-packet types, preserving its checks against player chat and session mismatches.

This rebuild needs in-game confirmation. The installed native mod stays disabled after the regression; re-enable it in **Client Mods…** only for a fresh game launch when ready to try the corrected build. Close Minecraft first: an already loaded DLL cannot be repaired by updating its files. Client package 0.1.3 retains the 0.1.1 companion handshake and settings protocol. Debug symbols and full corresponding native source are included.

## What is implemented

- A portable C++17 terrain core: versioned tiles, CRC validation, world/dimension isolation, bounded cache, conservative LOD aggregation, mesh generation and OBJ export.
- A client JavaScript plugin: bounded disk cache, distance-based surface meshes, edge skirts, controls, opted-in companion negotiation, fragment validation and acknowledgements.
- A narrow native Latite fork patch: nearby read-only surface observations for ordinary players. It preserves the normal server permission checks and the existing restrictions on unrelated client APIs.
- A Realm/BDS/local-world behavior pack: administrator-enabled ahead-of-visit sampling with temporary chunk areas, finite work queues, cleanup, persistent tiles and targeted in-game delivery. No external Realm HTTP service is needed.

## Current limits

**Client-only terrain is approximate and requires an explicit option.** The pinned native SDK cannot prove whether every vertical subchunk was received. It therefore returns observations with `known:false`. These observations use separate JSON cache files and are never exported as verified `.bht` terrain. Strict mode is the default; without the companion it waits for a future chunk-readiness hook.

**The in-game renderer remains unverified.** It submits real geometry through the existing game renderer, but the game projection far plane, fog, material depth behavior and Wine/D3DMetal compatibility need a deliberate gameplay check. A compiled DLL alone does not establish that distant terrain is visible or correctly occluded. This first version renders simplified colored surface geometry, without caves, overhangs or block textures. It does not replace the game's terrain, collision, or normal render distance.

**A Realm owner must activate the companion.** An invited player cannot install it on someone else's Realm. Generation is initially off. Enabling it loads and may generate terrain in the actual world; it is not merely drawing an imagined landscape. Requests are limited to 4096 blocks around each opted-in player, one outstanding tile per player, one active terrain job and a capacity-checked temporary area. This can still cost server time.

The bridge is pinned to Latite commit `9f7463515dd298a496da918285936d78c7416aad` and the local Minecraft **1.26.52.3** executable hash in `latite-bridge/bridge-lock.json`. The existing released Latite v2.9.1 DLL is too old for this target. The main launcher's normal update channel is independent of this experimental project.

## Console and Realm support

Activate **Bedrock-Horizons-Realm-Addon.mcaddon** on the Realm through a supported host device and enable the world's required resource-pack download option. It contains the behavior pack plus a tiny book resource pack using the built-in book texture. Console players receive the book automatically; the menu and per-player saved preferences use server-side scripting. No manual console file installation is needed. These UI paths have not yet been confirmed on physical consoles.

**This release does not add distant terrain rendering to Xbox, PlayStation, Switch, or standard mobile clients.** Required packs distribute supported pack content; they cannot load this Windows DLL or change the console renderer. Native rendering is only for the pinned computer client. Generating server chunks does not increase an unmodified client's view distance. The book explains this rather than promising a console renderer.

### Possible future console renderer

An [independent experimental add-on](https://github.com/FavoringFoil427/Distant-Horizons-UNOFFICIAL_MCPE) uses nearby custom entities whose scaled geometry represents distant terrain. Its README reports a single-player mobile target and explicitly lists multiplayer as unfinished; some rendering assumptions are still unverified. This suggests a possible pack-only approximation for consoles, not proof that it works on Realms or console hardware. A separate renderer would need per-player visibility, multiplayer budgets and hardware confirmation. This release does not implement that technique and does not include its code.

## World companion

Import `Bedrock-Horizons-Realm-Addon.mcaddon` through Minecraft and activate its behavior pack on your world. For a Realm, its owner activates the pack on that Realm. An administrator then runs:

```text
/bhl:config true
```

Use `/bhl:config false` to stop generation. No experiment/beta Script API toggle is requested. See `companion/README.md` for limits and commands.

## Client controls

On **Bedrock for Mac 0.5.5 or newer**, close Minecraft and import **Bedrock-Horizons-Client-Mod.zip** using **Install Add-ons…**. The generic client-mod loader registers it and loads it on future game starts when enabled, only on the compatible game build. **Client Mods…** can disable it. There are no Horizons-specific launcher controls. The included install script also registers the package with this loader; manual loading scripts are legacy developer tools.

Also import **Bedrock-Horizons-Realm-Addon.mcaddon** (companion and book resources together) and activate it on your world. Run `.horizons realm on` to connect to the world companion. This connects settings even when generation is off. Native loading and visible rendering have not been confirmed in a game session.

### Settings book

Each player receives one free book on their first join if an inventory slot is available. Any player can get a replacement with `/bhl:book`, craft it from **one paper**, or find it in Creative. Hold the **Horizons Settings Book** and use it to open the settings menu. `/bhl:menu` and `.horizons menu` open the same menu; `.horizons book` requests the book. These commands do not require cheats. The companion must be active in the world.

The menu has per-player distance, near cutoff, geometry budget, approximation, edge skirts, draw toggle, presets, and connection information. Dot commands and the book synchronize the same settings when the native client is connected. Only operators can change world generation. The book works for everyone in a companion-enabled world; drawing distant terrain still requires the compatible native client on each player's device. The actual book UI and native renderer need in-game confirmation.

The client plugin requires the matching native bridge; a normal resource pack cannot provide these renderer hooks. Place its folder under `%LOCALAPPDATA%/Latite/Plugins/BedrockHorizons` when using the patched client. The default Latite local command prefix is `.`; check your prefix if it was changed.

| Command | Purpose |
|---|---|
| `.horizons status` | Show connection, cache mode and mesh count. |
| `.horizons on` / `.horizons off` | Enable or stop distant drawing. |
| `.horizons realm on` | Opt in to the active world companion. Works for local worlds and BDS too. |
| `.horizons realm off` | Disconnect the companion and return to session-only client caching. |
| `.horizons approximate on` | Allow unverified nearby surface observations in client-only mode. Missing/clipped terrain is possible while chunks load. |
| `.horizons approximate off` | Draw only verified terrain. Default. |
| `.horizons world NAME` | Choose a persistent cache identity for client-only play. Use a different name per world; set it again after connecting. |
| `.horizons distance 512` | Farthest requested/drawn distance in blocks; 128–1024. Visibility still depends on the game's projection. |
| `.horizons near 256` | Keep simplified terrain out of the normal nearby view. Match this to the normal game render distance. |
| `.horizons menu` / `.horizons book` | Open the companion menu or obtain its book. |
| `.horizons skirts on` / `off` | Toggle terrain edge skirts. |
| `.horizons generation on` / `off` | Ask the companion to change generation; operator only. |
| `.horizons quads 768` | Maximum distant quads per frame; 128–2048. Lower values reduce script/render overhead. |

Companion worlds use their own persistent opaque world ID. No account IDs or authentication tokens are stored by this plugin. Client-only mode starts with a new session ID so server address changes or proxy worlds do not mix terrain; an explicit world name enables persistence.

The client cache is limited to 4096 indexed tiles / 32 MiB, with 192 clean resident tiles and at most 32 dirty tiles. Invalid tiles are rejected, rather than filled with invented terrain. Filesystem errors can lose cache entries; this is a disposable terrain cache, not a world backup.

## Building

Portable core:

```sh
cmake -S core -B build/core
cmake --build build/core
```

The native renderer bridge needs Windows MSVC and the upstream build prerequisites; it cannot be compiled unchanged with the Mac's native compiler. `latite-bridge/apply_bridge.py` validates the pinned upstream file hashes before applying the fork. The [native build completed successfully](https://github.com/goofygabe8/bedrockformac/actions/runs/37683878487) and archived its corresponding patched source. The portable Mac core and Windows loader compiled too. No Minecraft session, preparation script, native loading, or gameplay test has been run.

See `latite-bridge/README.md` for the missing full-chunk/subchunk contract. The remaining work is a verified terrain-packet readiness adapter, confirmed far-plane/depth/fog integration, and confirmed gameplay across supported devices.

## License and references

Original `core/`, `client/`, `companion/` and packaging code: MIT (`LICENSE`). Modified Latite source and additions to it: GPL-3.0 (`latite-bridge/UPSTREAM-LICENSE`). A distributed native DLL includes its pinned corresponding source and these fork changes. The bundled ChakraCore script engine is MIT-licensed, pinned to the upstream asset commit and blob checksum in `native/chakra-lock.json`; its notice is included. No Minecraft executable, account data, world data or game assets are distributed.

- [Mojang's subchunk request contract](https://github.com/Mojang/bedrock-protocol-docs/blob/main/additional_docs/SubChunk%20Request%20System%20v1.18.10.md)
- [Stable temporary ticking areas](https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/tickingareamanager?view=minecraft-bedrock-stable)
- [Stable server scripting types used by the companion](https://unpkg.com/@minecraft/server@2.6.0/index.d.ts)
- [Pinned native client source](https://github.com/LatiteClient/Latite/tree/9f7463515dd298a496da918285936d78c7416aad)
