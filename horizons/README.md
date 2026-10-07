# Bedrock Horizons 0.1.0 — experimental development build

Original terrain-cache and world-companion code for a Distant Horizons-like Bedrock feature. This is a prototype, not a completed Distant Horizons port. No Minecraft game session has been used to validate it.

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

## World companion

Import `Bedrock-Horizons-World-Companion.mcpack` through Minecraft and activate its behavior pack on your world. For a Realm, its owner activates the pack on that Realm. An administrator then runs:

```text
/bhl:config true
```

Use `/bhl:config false` to stop generation. No experiment/beta Script API toggle is requested. See `companion/README.md` for limits and commands.

## Client controls

When the native build is included, `Install Experimental Horizons.command` prepares its plugin and files in this Mac's existing Bedrock runtime. Launch Minecraft normally, then run `Load Experimental Horizons.command` to load the native client for that session. The loader checks the exact game and DLL hashes, refuses multiple game processes, and does not change the stable launcher's startup behavior. To stop using the native client, close Minecraft and launch normally again. Preparation scripts have not been executed against a game.

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

See `latite-bridge/README.md` for the missing full-chunk/subchunk contract. The remaining work is a verified terrain-packet readiness adapter, confirmed far-plane/depth/fog integration, and launcher installation support after those work in game.

## License and references

Original `core/`, `client/`, `companion/` and packaging code: MIT (`LICENSE`). Modified Latite source and additions to it: GPL-3.0 (`latite-bridge/UPSTREAM-LICENSE`). A distributed native DLL includes its pinned corresponding source and these fork changes. The bundled ChakraCore script engine is MIT-licensed, pinned to the upstream asset commit and blob checksum in `native/chakra-lock.json`; its notice is included. No Minecraft executable, account data, world data or game assets are distributed.

- [Mojang's subchunk request contract](https://github.com/Mojang/bedrock-protocol-docs/blob/main/additional_docs/SubChunk%20Request%20System%20v1.18.10.md)
- [Stable temporary ticking areas](https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/tickingareamanager?view=minecraft-bedrock-stable)
- [Stable server scripting types used by the companion](https://unpkg.com/@minecraft/server@2.6.0/index.d.ts)
- [Pinned native client source](https://github.com/LatiteClient/Latite/tree/9f7463515dd298a496da918285936d78c7416aad)
