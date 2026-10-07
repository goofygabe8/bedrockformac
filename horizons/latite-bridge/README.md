# Bedrock Horizons: Latite bridge research and source patch

This directory targets Latite source commit `9f7463515dd298a496da918285936d78c7416aad`, whose declared game range is `1.26.5x`. The official released v2.9.1 DLL predates this source and lists 26.44 support. Do not install that old DLL on 1.26.52.3 as if it were this bridge. No client DLL has been built, installed, or executed here.

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

The initial native observation API can safely report a bounded block scan as **provisional**. A completed-chunk/subchunk-readiness adapter is required before it may return `known: true`. Server-provided tiles can separately be confirmed by the companion's loaded-area contract.

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

## Native observation API

`dimension.getSurface(x,z)` accepts exact integer coordinates within 128 blocks of the local player and samples at most four columns per 50 ms. It returns `{known:false,readiness:"unverified",reason:"chunk-completeness-unverified",observed:{height,block,water,color,colorEstimated:true,minY,maxY}}`, or `observed:null` with a reason. `height` is the top face (block y+1); colors are approximate RGB8 values inferred from the block name. Existing `dimension.getBlock` keeps its upstream Operator gate. No chunks are requested, generated, changed, or persistently loaded by this API.

Approximate observations must be kept separate from confirmed `.bht` terrain. A default strict client must reject them. Opt-in approximate rendering is a separate developer option and can produce missing or clipped surfaces while chunks arrive.

`apply_bridge.py` requires the three source files to match the pinned SHA256 values in the lock before changing either. `patched-source/` contains the generated replacement source; `bedrock-horizons-observations.patch` is the corresponding minimal diff. No unrelated upstream source is modified. The fork also corrects relative filesystem path resolution so plugin caches stay inside the plugin directory. These source files have not been compiled with MSVC or exercised in Minecraft.
