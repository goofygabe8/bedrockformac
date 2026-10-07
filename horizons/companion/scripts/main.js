import {
  world, system, CommandPermissionLevel, CustomCommandParamType, CustomCommandStatus
} from "@minecraft/server";
import {
  WORLD_LIMIT, VERTEX_COUNT, encodeTile, base64Encode, validCachedTile,
  newWorldId, validWorldId, validTileCoordinates
} from "./tile_codec.js";

// Bounds are deliberately independent of client input and persist no account IDs.
const LIMITS = Object.freeze({
  subscribers: 16, queue: 16, cacheTiles: 64, fragmentChars: 768,
  requestCooldownTicks: 10, helloCooldownTicks: 40,
  subscriberIdleTicks: 1200, acknowledgementTicks: 200,
  areaLoadTicks: 200, jobTicks: 600, columnsPerSlice: 8,
  requestRadiusBlocks: 4096, maxGenerationStep: 4, cacheAgeMs: 3600000
});
const PROPERTY = Object.freeze({
  worldId: "bhl:world_id", generation: "bhl:generation_enabled",
  revision: "bhl:revision", index: "bhl:cache_index", tilePrefix: "bhl:tile:"
});
const subscribers = new Map();
const queue = [];
let ready = false;
let worldId = "";
let generationEnabled = false;
let cacheIndex = [];
let revision = 0;
let active = undefined;
let activeLease = undefined;
let loadingLease = undefined;
let leaseCounter = 0;
let stopping = false;

function success(message) {
  return message ? {status: CustomCommandStatus.Success, message} : {status: CustomCommandStatus.Success};
}

function failure(message) { return {status: CustomCommandStatus.Failure, message}; }

function sourcePlayer(origin) {
  const entity = origin.sourceEntity;
  return entity?.typeId === "minecraft:player" && entity.isValid ? entity : undefined;
}

function dimensionNumber(dimension) {
  return {"minecraft:overworld": 0, "minecraft:nether": 1, "minecraft:the_end": 2}[dimension.id];
}

function tileKey(dimension, x, z, step) { return `${dimension}:${step}:${x}:${z}`; }

function validCacheKey(key) {
  if (typeof key !== "string" || key.length > 80) return false;
  const fields = key.split(":").map(Number);
  return fields.length === 4 && [0, 1, 2].includes(fields[0]) &&
    validTileCoordinates(fields[2], fields[3], fields[1]);
}

function initialize() {
  if (ready) return;
  const savedId = world.getDynamicProperty(PROPERTY.worldId);
  worldId = validWorldId(savedId) ? savedId : newWorldId();
  if (savedId !== worldId) world.setDynamicProperty(PROPERTY.worldId, worldId);
  generationEnabled = world.getDynamicProperty(PROPERTY.generation) === true;
  const savedRevision = world.getDynamicProperty(PROPERTY.revision);
  revision = Number.isSafeInteger(savedRevision) && savedRevision >= 0 ? savedRevision : 0;
  try {
    const saved = JSON.parse(world.getDynamicProperty(PROPERTY.index) ?? "[]");
    if (Array.isArray(saved)) {
      const unique = new Set();
      cacheIndex = saved.slice(-LIMITS.cacheTiles).filter(entry => {
        if (!entry || !validCacheKey(entry.key) || unique.has(entry.key) ||
            !Number.isFinite(entry.updated) || !Number.isFinite(entry.used)) return false;
        unique.add(entry.key);
        return true;
      });
    }
  } catch (_) { cacheIndex = []; }
  // A pack reload may leave a previous temporary lease until its engine cleanup.
  // Remove only areas owned by this companion; never command or other pack areas.
  for (const area of world.tickingAreaManager.getAllTickingAreas()) {
    if (area.identifier.startsWith("bhl_lod_")) removeOwnedArea(area.identifier);
  }
  ready = true;
}

function privateNotice(player, message) {
  try { if (player.isValid) player.sendMessage(`[Bedrock Horizons] ${message}`); } catch (_) {}
}

function saveIndex() { world.setDynamicProperty(PROPERTY.index, JSON.stringify(cacheIndex)); }

function readCached(job) {
  const entry = cacheIndex.find(item => item.key === job.key);
  if (!entry || Date.now() - entry.updated > LIMITS.cacheAgeMs) return undefined;
  const encoded = world.getDynamicProperty(PROPERTY.tilePrefix + job.key);
  if (!validCachedTile(encoded, worldId, job.dimensionId, job.x, job.z, job.step)) {
    cacheIndex = cacheIndex.filter(item => item.key !== job.key);
    world.setDynamicProperty(PROPERTY.tilePrefix + job.key, undefined);
    saveIndex();
    return undefined;
  }
  entry.used = Date.now();
  saveIndex();
  return encoded;
}

function storeCached(job, encoded) {
  cacheIndex = cacheIndex.filter(item => item.key !== job.key);
  cacheIndex.sort((a, b) => a.used - b.used);
  while (cacheIndex.length >= LIMITS.cacheTiles) {
    const evicted = cacheIndex.shift();
    world.setDynamicProperty(PROPERTY.tilePrefix + evicted.key, undefined);
  }
  const now = Date.now();
  cacheIndex.push({key: job.key, updated: now, used: now});
  // Register the key before its data so an interrupted write cannot orphan data.
  saveIndex();
  world.setDynamicProperty(PROPERTY.tilePrefix + job.key, encoded);
}

function subscribed(playerId, nonce) {
  const client = subscribers.get(playerId);
  return client && client.nonce === nonce && client.player.isValid &&
    client.expires > system.currentTick ? client : undefined;
}

function liveWaiters(job) {
  return [...job.waiters].filter(([id, nonce]) => {
    const client = subscribed(id, nonce);
    return client && client.pendingKey === job.key &&
      dimensionNumber(client.player.dimension) === job.dimensionId;
  });
}

function ensureJobActive(job) {
  if (stopping || !generationEnabled || active !== job || job.cancelled ||
      system.currentTick > job.deadline || liveWaiters(job).length === 0) {
    throw new Error("Surface request cancelled or timed out.");
  }
}

function removeOwnedArea(identifier) {
  if (!identifier.startsWith("bhl_lod_")) return;
  try {
    const manager = world.tickingAreaManager;
    if (manager.hasTickingArea(identifier)) manager.removeTickingArea(identifier);
  } catch (_) { /* The engine also owns the lifetime of temporary pack areas. */ }
}

async function withArea(job, options, sampleColumns) {
  ensureJobActive(job);
  const manager = world.tickingAreaManager;
  if (!manager.hasCapacity(options)) throw new Error("No temporary chunk capacity is available.");
  const identifier = `bhl_lod_${system.currentTick}_${++leaseCounter}`;
  const lease = {identifier, expired: false};
  activeLease = lease;
  let timeout;
  try {
    const creation = manager.createTickingArea(identifier, options);
    loadingLease = lease;
    // An engine completion arriving after cancellation must clean up its own ID.
    creation.then(() => {
      if (lease.expired || stopping) removeOwnedArea(identifier);
      if (loadingLease === lease) loadingLease = undefined;
    }, () => {
      if (loadingLease === lease) loadingLease = undefined;
    });
    const deadline = new Promise((_, reject) => {
      timeout = system.runTimeout(() => {
        lease.expired = true;
        removeOwnedArea(identifier);
        reject(new Error("Temporary chunks did not load in time."));
      }, LIMITS.areaLoadTicks);
    });
    await Promise.race([creation, deadline]);
    ensureJobActive(job);
    await sampleColumns();
  } finally {
    if (timeout !== undefined) system.clearRun(timeout);
    lease.expired = true;
    removeOwnedArea(identifier);
    if (activeLease === lease) activeLease = undefined;
  }
}

function sampleSurface(dimension, x, z) {
  if (!dimension.isChunkLoaded({x, y: 64, z})) throw new Error("A surface chunk unloaded before sampling.");
  const block = dimension.getTopmostBlock({x, z});
  if (!block) return undefined;
  const color = block.getComponent("minecraft:map_color")?.tintedColor;
  // Map colors are normalized RGBA. Missing colors have an explicit neutral fallback.
  const rgb = color ? [color.red * 255, color.green * 255, color.blue * 255] : [128, 128, 128];
  return {
    height: block.location.y + 1,
    water: block.matches("minecraft:water") || block.matches("minecraft:flowing_water"),
    color: rgb
  };
}

function sampleJob(job, columns, samples) {
  return new Promise((resolve, reject) => {
    function* sampler() {
      try {
        let slice = 0;
        for (const column of columns) {
          ensureJobActive(job);
          samples[column.index] = sampleSurface(job.dimension, column.x, column.z);
          if (++slice === LIMITS.columnsPerSlice) { slice = 0; yield; }
        }
        resolve();
      } catch (error) { reject(error); }
    }
    system.runJob(sampler());
  });
}

async function generate(job) {
  const samples = new Array(VERTEX_COUNT);
  const columns = [];
  const byChunk = new Map();
  for (let z = 0; z <= 16; z++) for (let x = 0; x <= 16; x++) {
    const column = {x: job.x + x * job.step, z: job.z + z * job.step, index: z * 17 + x};
    columns.push(column);
    const chunkKey = `${Math.floor(column.x / 16)}:${Math.floor(column.z / 16)}`;
    if (!byChunk.has(chunkKey)) byChunk.set(chunkKey, []);
    byChunk.get(chunkKey).push(column);
  }
  const options = {
    dimension: job.dimension,
    from: {x: job.x, y: 64, z: job.z},
    to: {x: job.x + 16 * job.step, y: 64, z: job.z + 16 * job.step}
  };
  if (world.tickingAreaManager.hasCapacity(options)) {
    await withArea(job, options, () => sampleJob(job, columns, samples));
  } else {
    // Keep resolution and extent intact when the manager has a smaller budget.
    // At most 25 single-chunk leases, processed sequentially, are needed at step 4.
    for (const chunkColumns of byChunk.values()) {
      const first = chunkColumns[0];
      const chunkX = Math.floor(first.x / 16) * 16;
      const chunkZ = Math.floor(first.z / 16) * 16;
      await withArea(job, {
        dimension: job.dimension,
        from: {x: chunkX, y: 64, z: chunkZ},
        to: {x: chunkX + 15, y: 64, z: chunkZ + 15}
      }, () => sampleJob(job, chunkColumns, samples));
    }
  }
  ensureJobActive(job);
  if (revision >= Number.MAX_SAFE_INTEGER - 1) throw new Error("Surface revision capacity exhausted.");
  world.setDynamicProperty(PROPERTY.revision, ++revision);
  return base64Encode(encodeTile(worldId, job.dimensionId, job.x, job.z, job.step, revision, samples));
}

function beginDelivery(client, key, encoded) {
  if (!client.player.isValid || client.inflight) return false;
  const count = Math.ceil(encoded.length / LIMITS.fragmentChars);
  const seq = ++client.sequence;
  if (!Number.isSafeInteger(seq) || count > 8) return false;
  client.pendingKey = undefined;
  client.inflight = {key, dimensionId: dimensionNumber(client.player.dimension), seq, encoded, count,
    part: 0, expires: system.currentTick + LIMITS.acknowledgementTicks};
  return true;
}

async function workQueue() {
  if (active || loadingLease || stopping || queue.length === 0) return;
  const job = queue.shift();
  active = job;
  job.deadline = system.currentTick + LIMITS.jobTicks;
  try {
    ensureJobActive(job);
    const encoded = await generate(job);
    storeCached(job, encoded);
    for (const [id, nonce] of liveWaiters(job)) beginDelivery(subscribed(id, nonce), job.key, encoded);
  } catch (error) {
    for (const [id, nonce] of liveWaiters(job)) {
      const client = subscribed(id, nonce);
      client.pendingKey = undefined;
      privateNotice(client.player, String(error?.message ?? "Could not sample this terrain.").slice(0, 160));
    }
  } finally {
    if (activeLease) {
      activeLease.expired = true;
      removeOwnedArea(activeLease.identifier);
      activeLease = undefined;
    }
    for (const [id, nonce] of job.waiters) {
      const client = subscribed(id, nonce);
      if (client?.pendingKey === job.key) client.pendingKey = undefined;
    }
    if (active === job) active = undefined;
  }
}

function pump() {
  if (!ready || stopping) return;
  for (const [id, client] of subscribers) {
    if (!client.player.isValid || client.expires <= system.currentTick) {
      subscribers.delete(id);
      continue;
    }
    const dimensionId = dimensionNumber(client.player.dimension);
    if (client.dimensionId !== dimensionId) {
      client.pendingKey = undefined;
      client.inflight = undefined;
      client.dimensionId = dimensionId;
    }
    const delivery = client.inflight;
    if (!delivery) continue;
    if (delivery.expires <= system.currentTick) {
      client.inflight = undefined;
      privateNotice(client.player, "Tile delivery was not acknowledged; request it again.");
      continue;
    }
    if (delivery.part >= delivery.count) continue;
    const fragment = delivery.encoded.slice(
      delivery.part * LIMITS.fragmentChars, (delivery.part + 1) * LIMITS.fragmentChars
    );
    try {
      client.player.sendMessage(`BHL1 TILE 1 ${worldId} ${client.nonce} ${delivery.seq} ${delivery.part} ${delivery.count} ${fragment}`);
      delivery.part++;
    } catch (_) { subscribers.delete(id); }
  }
  queue.splice(0, queue.length, ...queue.filter(job => liveWaiters(job).length > 0));
  void workQueue();
}

function handleHello(player, clientVersion, nonce) {
  initialize();
  const old = subscribers.get(player.id);
  if (old && system.currentTick < old.helloAfter) {
    privateNotice(player, "Please wait before reconnecting the terrain bridge.");
    return;
  }
  if (!old && subscribers.size >= LIMITS.subscribers) {
    privateNotice(player, "The terrain bridge has reached its player limit.");
    return;
  }
  const client = {
    player, nonce, clientVersion, dimensionId: dimensionNumber(player.dimension), sequence: old?.sequence ?? 0,
    helloAfter: system.currentTick + LIMITS.helloCooldownTicks,
    requestAfter: 0, expires: system.currentTick + LIMITS.subscriberIdleTicks,
    pendingKey: undefined, inflight: undefined
  };
  subscribers.set(player.id, client);
  player.sendMessage(`BHL1 HELLO 1 ${worldId} ${nonce} ${generationEnabled ? 1 : 0}`);
}

function handleRequest(player, x, z, step) {
  initialize();
  const client = subscribers.get(player.id);
  if (!client || !subscribed(player.id, client.nonce)) {
    privateNotice(player, "Connect the client bridge with /bhl:hello first.");
    return;
  }
  if (system.currentTick < client.requestAfter) return;
  client.requestAfter = system.currentTick + LIMITS.requestCooldownTicks;
  client.expires = system.currentTick + LIMITS.subscriberIdleTicks;
  if (client.pendingKey || client.inflight) {
    privateNotice(player, "Finish or acknowledge your current tile before requesting another.");
    return;
  }
  const dimensionId = dimensionNumber(player.dimension);
  if (dimensionId === undefined) { privateNotice(player, "Custom dimensions are not supported yet."); return; }
  const centerX = x + 8 * step;
  const centerZ = z + 8 * step;
  if (Math.hypot(centerX - player.location.x, centerZ - player.location.z) > LIMITS.requestRadiusBlocks) {
    privateNotice(player, "Requested terrain is outside the 4096-block sampling radius.");
    return;
  }
  const key = tileKey(dimensionId, x, z, step);
  const job = {key, dimension: player.dimension, dimensionId, x, z, step, waiters: new Map(), cancelled: false};
  const cached = readCached(job);
  if (cached) { beginDelivery(client, key, cached); return; }
  if (!generationEnabled) { privateNotice(player, "The Realm owner has not enabled ahead-of-visit sampling."); return; }
  let pending = active?.key === key && !active.cancelled ? active : queue.find(item => item.key === key);
  if (!pending && queue.length >= LIMITS.queue) {
    privateNotice(player, "The terrain queue is full; try again shortly.");
    return;
  }
  client.pendingKey = key;
  pending ??= job;
  pending.waiters.set(player.id, client.nonce);
  if (pending === job) queue.push(job);
}

function safelyDeferred(player, callback) {
  system.run(() => {
    if (stopping || !player.isValid) return;
    try { callback(); } catch (error) { privateNotice(player, String(error?.message ?? "Terrain bridge unavailable.").slice(0, 160)); }
  });
}

system.beforeEvents.startup.subscribe(event => {
  const registry = event.customCommandRegistry;
  const register = (name, description, mandatoryParameters, optionalParameters, callback, permissionLevel = CommandPermissionLevel.Any) => {
    registry.registerCommand({name, description, permissionLevel, cheatsRequired: false,
      mandatoryParameters, optionalParameters}, callback);
  };
  register("bhl:hello", "Opt in to the experimental Bedrock Horizons terrain bridge.", [
    {name: "clientVersion", type: CustomCommandParamType.String},
    {name: "nonce", type: CustomCommandParamType.String}
  ], [], (origin, clientVersion, nonce) => {
    const player = sourcePlayer(origin);
    if (!player) return failure("This command must be run by a player.");
    if (typeof clientVersion !== "string" || !/^[0-9]+\.[0-9]+\.[0-9]+$/.test(clientVersion) || clientVersion.length > 24 ||
        typeof nonce !== "string" || !/^[0-9a-f]{32}$/.test(nonce)) return failure("Invalid client version or session nonce.");
    safelyDeferred(player, () => handleHello(player, clientVersion, nonce));
    return success();
  });
  register("bhl:request", "Request one bounded surface tile in your current dimension.", [
    {name: "originX", type: CustomCommandParamType.Integer},
    {name: "originZ", type: CustomCommandParamType.Integer}
  ], [{name: "step", type: CustomCommandParamType.Integer}], (origin, x, z, suppliedStep) => {
    const player = sourcePlayer(origin);
    const step = suppliedStep ?? 2;
    if (!player) return failure("This command must be run by a player.");
    if (!validTileCoordinates(x, z, step) || step > LIMITS.maxGenerationStep) {
      return failure(`Use step 1, 2, or 4, aligned origins, and coordinates within ±${WORLD_LIMIT} blocks.`);
    }
    safelyDeferred(player, () => handleRequest(player, x, z, step));
    return success();
  });
  register("bhl:ack", "Acknowledge a fully validated Bedrock Horizons tile.", [
    {name: "sequence", type: CustomCommandParamType.Integer}
  ], [], (origin, sequence) => {
    const player = sourcePlayer(origin);
    if (!player || !Number.isSafeInteger(sequence) || sequence < 1) return failure("Invalid tile acknowledgement.");
    safelyDeferred(player, () => {
      const client = subscribers.get(player.id);
      if (client?.inflight?.seq === sequence && client.inflight.part === client.inflight.count) {
        client.inflight = undefined;
        client.expires = system.currentTick + LIMITS.subscriberIdleTicks;
      }
    });
    return success();
  });
  register("bhl:disable", "Stop your terrain stream without affecting other players.", [], [], origin => {
    const player = sourcePlayer(origin);
    if (!player) return failure("This command must be run by a player.");
    safelyDeferred(player, () => { subscribers.delete(player.id); });
    return success("Your Bedrock Horizons terrain stream is disabled.");
  });
  register("bhl:config", "Administrator: enable or disable bounded ahead-of-visit terrain sampling.", [
    {name: "enabled", type: CustomCommandParamType.Boolean}
  ], [], (origin, enabled) => {
    if (typeof enabled !== "boolean") return failure("Use /bhl:config true or /bhl:config false.");
    const administrator = sourcePlayer(origin);
    system.run(() => {
      if (stopping) return;
      try {
        initialize();
        world.setDynamicProperty(PROPERTY.generation, enabled);
        generationEnabled = enabled;
        if (!enabled) {
          if (active) active.cancelled = true;
          for (const job of queue) for (const [id, nonce] of job.waiters) {
            const client = subscribed(id, nonce);
            if (client?.pendingKey === job.key) client.pendingKey = undefined;
          }
          queue.length = 0;
          if (activeLease) { activeLease.expired = true; removeOwnedArea(activeLease.identifier); }
        }
        for (const client of subscribers.values()) {
          if (client.player.isValid) {
            try { client.player.sendMessage(`BHL1 HELLO 1 ${worldId} ${client.nonce} ${enabled ? 1 : 0}`); } catch (_) {}
          }
        }
        if (administrator) privateNotice(administrator, `Ahead-of-visit sampling ${enabled ? "enabled" : "disabled"}.`);
      } catch (error) { console.warn(`[Bedrock Horizons] Configuration failed: ${String(error?.message ?? error).slice(0, 160)}`); }
    });
    return success();
  }, CommandPermissionLevel.Admin);
});

world.afterEvents.playerLeave.subscribe(event => { subscribers.delete(event.playerId); });
system.beforeEvents.shutdown.subscribe(() => {
  stopping = true;
  if (active) active.cancelled = true;
  queue.length = 0;
  subscribers.clear();
  // Shutdown is a restricted context; removal can fail there. Temporary pack
  // areas are not command-created persistent ticking areas. Normal job exits
  // always remove their lease in finally; never cancel the server watchdog.
  if (activeLease) { activeLease.expired = true; removeOwnedArea(activeLease.identifier); }
});
system.runInterval(pump, 1);
