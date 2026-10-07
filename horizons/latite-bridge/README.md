# Bedrock Horizons: Latite bridge research and source patch

This directory targets Latite source commit `9f7463515dd298a496da918285936d78c7416aad`, whose declared game range is `1.26.5x`. The official released v2.9.1 DLL predates this source and lists 26.44 support. Do not install that old DLL on 1.26.52.3 as if it were this bridge. The native DLL compiled successfully in the Windows GitHub build at https://github.com/goofygabe8/bedrockformac/actions/runs/37683878487. Native 0.1.1 was installed and produced three matching startup crashes under Wine. The newer patch handles optional online trust-check failures and logs/skips per-plugin startup errors; gameplay remains unverified.

## Confirmed source integration

- `game.getLocalPlayer().getPosition()` gives the local position. `world.getName()` and `dimension.getName()` identify the current world and dimension.
- `dimension.getBlock(x,y,z)` reads the current client BlockSource, but upstream restricts it to an operator. The bridge must expose a specific read-only observation method while leaving upstream operator restrictions on unrelated APIs intact.
- `game.executeCommand('/bhl:hello ...')` sends a normal player command request and lets the server enforce command permission. The companion registers its opt-in requests for ordinary players. This API needs no new permission bypass.
- `client.on('receive-chat', event => { ...; event.cancel = true; })` can consume only protocol messages without showing them in chat. Do not read or store the event's Xbox user ID.
- `graphics3D.drawQuad` queues world-coordinate vertices for `LevelRenderer::renderLevel`; `finish(true)` selects the normal `ui_fill_color` material in the current implementation. Fog, depth behavior, projection far plane, and Wine/D3DMetal compatibility remain unverified.
- `require('filesystem').read(path)` returns a `Uint8Array`; `write(path, bytes)` accepts one. Relative paths are inside the plugin folder. Use ASCII JSON encoding to avoid upstream wide-stream encoding ambiguity.
- Plugins use `main.js` and `plugin.json` (name, author, version, description), under `%LOCALAPPDATA%/Latite/Plugins`.

## Exact missing terrain contract

`BlockSource.h` has `getChunkAt(BlockPos)->void*`, `hasBlock`, and `hasChunksAt`, but no `LevelChunk` structure, received-subchunk readiness, or heightmap accessor. `areChunksFullyLoaded` is declared with an unknown `void` return. A non-null pointer or returned air is not proof that a full vertical column arrived. The bridge must not turn incomplete client columns into confirmed terrain. Dimension min/max heights are not exposed either.

The 0.1.3 crash report identifies an access violation inside the game called from the bridge’s `BlockSource::getChunkAt` scan. Even an observation-only read is unsafe until the native ABI is established. Version 0.1.4 disables local scans entirely. Server-provided tiles use the separate companion loaded-area contract.

## Windows build route

The upstream CMake project explicitly requires MSVC, C++23, a Windows SDK, WindowsApp/DirectX/Direct2D libraries, and MinGW `ld.exe` for embedded resources. This cannot be built unchanged with the local Mac Zig compiler. A Windows builder can use the upstream Release preset:

```powershell
git clone https://github.com/LatiteClient/Latite.git Latite-Horizons
Set-Location Latite-Horizons
git checkout --detach 9f7463515dd298a496da918285936d78c7416aad
python ..\latite-bridge\apply_bridge.py .
cmake --preset x64-release
cmake --build out/build/x64-release
```

Follow upstream's Visual Studio 2026 build prerequisites. A successful build would still require deliberate game compatibility validation before enabling the bridge in the public launcher.

## Evidence and license

- [Pinned supported versions](https://github.com/LatiteClient/Latite/blob/9f7463515dd298a496da918285936d78c7416aad/src/client/Latite.h)
- [Client terrain and command bindings](https://github.com/LatiteClient/Latite/blob/9f7463515dd298a496da918285936d78c7416aad/src/client/script/globals/GameScriptingObject.cpp)
- [Graphics3D rendering](https://github.com/LatiteClient/Latite/blob/9f7463515dd298a496da918285936d78c7416aad/src/client/script/globals/Graphics3DScriptingObject.cpp)
- [BlockSource SDK](https://github.com/LatiteClient/Latite/blob/9f7463515dd298a496da918285936d78c7416aad/src/mc/common/world/level/BlockSource.h)
- [Upstream build requirements](https://github.com/LatiteClient/Latite/blob/9f7463515dd298a496da918285936d78c7416aad/CMakeLists.txt)
- [Official v2.9.1 release](https://github.com/LatiteClient/Latite/releases/tag/v2.9.1)

`bridge-lock.json` records a static scan of the local game executable. Unique signature matches are evidence of matching byte patterns, not proof of class layout, calling convention, renderer state, or runtime compatibility.

Latite is GPL-3.0. Any distributed modified Latite DLL must include the corresponding fork source, upstream copyright/license, and patch notices. This bridge does not redistribute Minecraft code or binaries.

## Disabled native observation API

`dimension.getSurface(x,z)` remains as a compatibility entry point, but returns `{available:false,known:false,readiness:"disabled",reason:"native-client-sampling-disabled",observed:null}`. It performs no game-memory reads and calls no BlockSource methods. The client JavaScript also stops issuing probes, including the former default strict-mode probe.

The reader requires a confirmed native ABI and full-column readiness adapter before restoration. The approximate toggle cannot reactivate it. World-companion tile delivery is independent of this reader, but the renderer still requires gameplay confirmation.

`apply_bridge.py` validates every upstream file hash in `bridge-lock.json` before writing any source. `minimal_client.py` removes unrelated input and desktop-overlay integration. Relative cache paths resolve inside the plugin directory. The distributed DLL includes complete corresponding native source; obsolete generated observation patches were retired instead of being presented as current.
