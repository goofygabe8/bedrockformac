## Realm distribution and console players

Import the combined `Bedrock-Horizons-Realm-Addon.mcaddon`, activate both its behavior and resource packs on the Realm, and require the Realm resource packs. The resource pack references Minecraft's existing written-book texture; it does not redistribute game assets. Players receive a free book on their first join when there is room, with `/bhl:book` or one paper as replacements. The menu works through server-side forms on standard Bedrock devices. Console UI remains unverified on hardware. Console clients cannot load the native distant renderer; the book explains that limitation. Required packs cannot extend their render distance.

# Bedrock Horizons world companion — experimental 0.1.0

This behavior pack contains the server/world side of Bedrock Horizons. It can load a small area ahead of a player, sample its actual surface, cache the result, and send simplified tiles to an opted-in client. It uses stable `@minecraft/server` 2.6.0 APIs and targets Minecraft Bedrock 26.50 or later. The matching 26.50 release shipped stable API 2.10.0, which retains the older stable API versions.

**This pack has not been run in Minecraft yet.** It requires the Bedrock Horizons client bridge to consume its messages and a working client renderer to display terrain. Installing this behavior pack alone does not increase render distance. It does not bypass a Realm owner's permission or add code to other people's worlds.

## Install on a world or Realm

1. Import the companion `.mcpack`, or put this folder into `behavior_packs` as an unpacked development pack.
2. The world or Realm owner activates **Bedrock Horizons — World Companion (Experimental)** in the world's Behavior Packs. Ordinary invited players cannot activate it on someone else's Realm.
3. An administrator with operator commands runs `/bhl:config true` to enable bounded ahead-of-visit sampling. The initial default is **disabled**. The owner's decision is saved with the world.
4. A client with the matching bridge explicitly opts in. Joining the world alone does not subscribe or send tiles.
5. Run `/bhl:config false` to stop further generation. A player can run `/bhl:disable` to stop only their stream.

The companion does not need the Beta APIs experiment or cheats. Its registered commands explicitly set `cheatsRequired: false`; the administrator command still requires operator privileges. Enabling generation loads and generates real chunks, consumes server time, advances their normal ticking behavior, and may increase the world's stored size. There is no command that pre-generates an entire infinite world.

## Commands and client handshake

| Command | Permission | Purpose |
| --- | --- | --- |
| `/bhl:book` | Any player | Obtain a free settings book, also craftable from one paper. |
| `/bhl:menu` | Any player | Open your settings, presets and connection UI. |
| `/bhl:settings <enabled> <distance> <near> <quads> <approximate> <skirts>` | Any player | Validate and save your own settings; send them to your connected native client. |
| `/bhl:hello <clientVersion> <nonce>` | Any player | Explicitly subscribe; version is `0.1.0` style and nonce is exactly 32 lowercase hexadecimal characters. |
| `/bhl:request <originX> <originZ> [step]` | Any subscribed player | Request one aligned surface tile in the player's current vanilla dimension. Default step: `2`; supported request steps: `1`, `2`, `4`. |
| `/bhl:ack <sequence>` | Any subscribed player | Acknowledge a fully received, validated tile. |
| `/bhl:disable` | Any player | Unsubscribe, discard pending delivery, and cancel that player's queued requests. |
| `/bhl:config <true|false>` | Administrator/operator | Persist the world's generation setting; turning it off cancels queued and active generation. |

Use the native client's command execution path. The pack does not depend on the experimental chat-send event or on `/scriptevent`, which requires operator permissions. Examples for a client developer:

```text
/bhl:hello 0.1.0 0123456789abcdef0123456789abcdef
/bhl:request 0 0 2
/bhl:ack 1
/bhl:disable
```

These commands are intended for the bridge. Manually opting in from an unmodified client will display the encoded tile fragments in chat because the native client interception is responsible for hiding them.

## Exact wire format

Outgoing messages are targeted to the requesting player through stable `Player.sendMessage`. A fresh HELLO response establishes the persistent opaque world identity and echoes the client's session nonce:

```text
BHL1 HELLO 1 <worldUUID32hex> <nonce32hex> <generationEnabled0or1>
BHL1 REQUEST_SETTINGS 1 <worldUUID32hex> <nonce32hex>
BHL1 SETTINGS 1 <worldUUID32hex> <nonce32hex> <enabled0or1> <distance> <near> <quads> <approximate0or1> <skirts0or1>
BHL1 TILE 1 <worldUUID32hex> <nonce32hex> <sequenceDecimal> <partZeroBased> <partCount> <base64Fragment>
```

Each tile's base64 string is 3,192 characters, split into **five** fragments of at most 768 characters. At most one fragment is sent to each subscribed player per tick. The sequence is monotonic per player within the pack session. At most one tile is queued, being generated, or awaiting acknowledgement per player; the next request is allowed only after a matching ACK or expiry. Only ACK a tile after collecting every fragment and verifying its byte length, CRC, metadata, session nonce, and requested coordinates. The native receiver must bound assembly, reject malformed/duplicate conflicting parts, and only suppress verified protocol envelopes from the negotiated session.

When an administrator changes the generation setting, existing opted-in subscribers receive a HELLO status refresh with the same world ID and nonce. This refresh does not subscribe any additional players.

Command failures and generation notices are short ordinary messages, not data frames. HELLO does not assert that a client renderer has been installed or proven to work.

### BHTILE01 binary contract

Every tile is exactly **2,392 bytes**, little endian: 80 header bytes followed by 289 eight-byte vertices. Vertices are row-major: Z first, then X, including the shared seventeenth row and column. A tile has 16×16 cells; width and depth are `16 * step` blocks. Origins must be aligned to that width and depth.

| Offset | Type | Value |
| --- | --- | --- |
| 0 | 8 bytes | ASCII `BHTILE01` |
| 8 | u16 | Header bytes: 80 |
| 10 | u16 | Format version: 1 |
| 12 | u16 | Cells per edge: 16 |
| 14 | u16 | Vertex record bytes: 8 |
| 16 | 16 bytes | Raw world UUID bytes, decoded from the HELLO hex string |
| 32 | i32 | Dimension: Overworld `0`, Nether `1`, End `2` |
| 36 | u32 | Step: power of two |
| 40 | i64 | Origin X |
| 48 | i64 | Origin Z |
| 56 | u64 | Monotonic world tile revision |
| 64 | u32 | Source: `2` (authoritative companion) |
| 68 | u32 | Vertex count: 289 |
| 72 | u32 | IEEE CRC32 of payload bytes 80…2391 |
| 76 | u32 | Reserved: zero |

Each vertex stores i32 height in sixteenths of a block, a flag byte, then RGB8. Flag bit 0 is known; bit 1 is water. An unknown record is eight zero bytes. Heights use the top block's upper face (`block.y + 1`); geometry such as stairs, leaves, and overhangs is simplified. Surface color uses the block's biome-tinted map color, with neutral gray if unavailable. This is a surface LOD approximation, not complete chunk geometry or textured terrain.

The binary codec accepts power-of-two steps up to 16,384. This Realm sampler intentionally generates only steps 1, 2, and 4; larger LOD levels should be downsampled by the client from finer tiles. It supports the three vanilla dimensions only. Nether top surfaces currently represent the roof, so an interior cavern LOD needs a separate sampling policy.

## Fixed resource bounds

- Maximum 16 subscribed players; an idle subscription expires after 1,200 ticks.
- One requested tile per player; global generation queue capped at 16 distinct tiles and deduplicated across players.
- Requests limited to every ten ticks, with tile centers within 4,096 blocks of the requesting player and all tile vertices within ±30,000,000 blocks.
- One temporary ticking area lease at a time. Step 2 usually needs a 3×3 chunk area including edges; step 4 needs at most 5×5. The engine's actual per-pack capacity is checked, with sequential one-chunk fallback when the full tile area does not fit.
- At most 289 surface samples per tile, yielding after each eight samples through `system.runJob`. Chunk loading times out after 200 ticks and a tile job after 600 ticks.
- The script removes its own lease in `finally`, including timeout and cancellation paths. It does not remove command-created or other packs' areas. Late engine completions also clean up the exact old lease ID. After a load timeout, a new lease is not started until the engine settles the previous loading operation.
- Targeted transfer is one fragment per player per tick, with one unacknowledged tile and a 200-tick expiry.
- Persistent LRU cache capped at 64 tiles (about 200 KiB of base64 payload plus metadata); cache freshness is one hour. The world stores an opaque random cache identity, generation setting, revision counter, and terrain tiles. The pack does not store account tokens, player names, or Xbox identifiers.

Disabling generation still allows fresh cached tiles to be served to explicitly subscribed clients. Generation stops when every waiting subscriber leaves or cancels; no background whole-world work remains queued. Ticking areas managed by this API are temporary pack-owned areas. During the restricted shutdown callback, removal may be disallowed; normal active job completion always removes its own lease, and the engine ends temporary pack areas when the pack/world ends. The script never cancels or disables Minecraft's watchdog.

## Known integration work

The native bridge must obtain visited terrain and camera data, intercept verified companion messages, and render LOD meshes through the game's graphics pipeline. The companion's native consumer and render integration are separate code. No working gameplay, Realm, performance, or recovery test is claimed here.

Realms does not support `@minecraft/server-net`, so this companion does not attempt HTTP or WebSocket networking. It uses the existing game connection. A future Dedicated Server transport could share the same binary contract without changing the Realm companion.

## Official API references

- [26.50 API release notes](https://feedback.minecraft.net/hc/en-us/articles/48826825649933-Minecraft-Bedrock-Edition-26-50-Changelog-Wilderness-Bound)
- [TickingAreaManager](https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/tickingareamanager?view=minecraft-bedrock-stable)
- [Dimension surface queries](https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/dimension?view=minecraft-bedrock-stable)
- [Block map color component](https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/blockmapcolorcomponent?view=minecraft-bedrock-stable)
- [CustomCommand and cheatsRequired](https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/customcommand?view=minecraft-bedrock-stable)
- [Command permission levels](https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/commandpermissionlevel?view=minecraft-bedrock-stable)
- [System.runJob](https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/system?view=minecraft-bedrock-stable)
- [Player.sendMessage](https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server/player?view=minecraft-bedrock-stable)
- [Realm Add-On activation](https://help.minecraft.net/hc/en-us/articles/24120525083533-How-to-activate-Minecraft-Add-On)
- [Server-net restriction](https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server-net/minecraft-server-net?view=minecraft-bedrock-experimental)
- [Exact published stable 2.6.0 API declarations](https://unpkg.com/@minecraft/server@2.6.0/index.d.ts)
