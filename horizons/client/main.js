"use strict";
var codec = require("tile.js"), Cache = require("cache.js"), mesh = require("mesh.js");
var fs = require("filesystem"), cache = new Cache();
var settings = {enabled: true, approximate: false, distance: 512, near: 256, quads: 768, skirts: true};
var aliases = Object.create(null), worldId = null, persistentWorld = false, dimensionId = -1;
var companion = false, generation = false, nonce = "", helloAt = 0, helloDeadline = 0;
var request = null, assemblies = new Map(), retry = new Map(), samples = null;
var ticks = 0, renderMesh = [], lastMeshRevision = -1, status = "Waiting for a world";
var visibleContext = null;
var strictProbeAfter = 0;
function randomId() {
  var id = ""; for (var i = 0; i < 32; i++) id += Math.floor(Math.random() * 16).toString(16); return id;
}
function notice(text) { clientMessage("[Bedrock Horizons] " + text); }
function saveSettings(sync) {
  try { fs.write("settings.json", codec.asciiBytes(JSON.stringify({settings: settings, aliases: aliases}))); }
  catch (_) { notice("Settings could not be saved."); }
  if (sync !== false && companion && !helloDeadline && world.exists()) {
    game.executeCommand("/bhl:settings " + [settings.enabled, settings.distance, settings.near, settings.quads, settings.approximate, settings.skirts].join(" "));
  }
}
try {
  if (fs.exists("settings.json")) {
    var saved = JSON.parse(codec.asciiText(fs.read("settings.json"), 16000));
    if (saved && saved.settings) {
      ["enabled", "approximate", "skirts"].forEach(function(key) {
        if (typeof saved.settings[key] === "boolean") settings[key] = saved.settings[key];
      });
      [["distance", 128, 1024], ["near", 16, 512], ["quads", 128, 2048]].forEach(function(item) {
        var v = saved.settings[item[0]];
        if (Number.isInteger(v) && v >= item[1] && v <= item[2]) settings[item[0]] = v;
      });
      if (settings.near >= settings.distance) settings.near = Math.floor(settings.distance / 2);
    }
    if (saved && saved.aliases && typeof saved.aliases === "object") {
      Object.keys(saved.aliases).slice(0, 64).forEach(function(key) {
        if (/^[a-z0-9_-]{1,40}$/.test(key) && codec.worldValid(saved.aliases[key])) aliases[key] = saved.aliases[key];
      });
    }
  }
} catch (_) { notice("Using default settings; saved settings were invalid."); }
function currentDimension() {
  var name = String(dimension.getName()).toLowerCase();
  if (["overworld", "minecraft:overworld"].indexOf(name) >= 0) return 0;
  if (["nether", "minecraft:nether"].indexOf(name) >= 0) return 1;
  if (["the end", "theend", "the_end", "end", "minecraft:the_end"].indexOf(name) >= 0) return 2;
  return -1;
}
function position() {
  var player = game.getLocalPlayer();
  if (!player) return null;
  var p = player.getPosition();
  return p && Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z) ? p : null;
}
function reset(stopRemote) {
  if (stopRemote && companion && world.exists()) game.executeCommand("/bhl:disable");
  // New session identity prevents mixing worlds on proxy servers or changing Realm IPs.
  companion = false; generation = false; worldId = randomId(); persistentWorld = false;
  cache.persistent = false; nonce = ""; request = null; assemblies.clear(); retry.clear(); samples = null;
  renderMesh = []; lastMeshRevision = -1; visibleContext = null; dimensionId = -1;
  helloDeadline = 0; status = "Client cache: session only";
}
function connect() {
  if (!world.exists() || !position()) { notice("Join a world before connecting the companion."); return; }
  companion = true; generation = false; nonce = randomId(); helloAt = Date.now(); helloDeadline = helloAt + 10000;
  request = null; assemblies.clear(); samples = null; status = "Connecting to the world companion";
  game.executeCommand("/bhl:hello 0.1.1 " + nonce);
}
function protocol(event) {
  // Targeted server raw/system/object messages only; never consume ordinary player chat.
  if (!companion || typeof event.message !== "string" || event.message.length > 1000 ||
      [0, 6, 10].indexOf(event.type) < 0 || (event.sender && event.sender.length)) return;
  var text = event.message;
  if (event.type === 10 && text[0] === "{") {
    try {
      var objectText = JSON.parse(text);
      if (!objectText || !Array.isArray(objectText.rawtext) || objectText.rawtext.length !== 1 ||
          !objectText.rawtext[0] || typeof objectText.rawtext[0].text !== "string") return;
      text = objectText.rawtext[0].text;
    } catch (_) { return; }
  }
  var hello = /^BHL1 HELLO 1 ([0-9a-f]{32}) ([0-9a-f]{32}) ([01])$/.exec(text);
  if (hello) {
    if (hello[2] !== nonce || !codec.worldValid(hello[1])) return;
    event.cancel = true;
    if (worldId !== hello[1]) { request = null; assemblies.clear(); samples = null; renderMesh = []; }
    worldId = hello[1]; persistentWorld = true; cache.persistent = true;
    generation = hello[3] === "1"; helloDeadline = 0; helloAt = Date.now();
    status = generation ? "World companion connected" : "Companion connected; owner generation is off";
    lastMeshRevision = -1; return;
  }
  var part = /^BHL1 TILE 1 ([0-9a-f]{32}) ([0-9a-f]{32}) ([1-9][0-9]{0,9}) ([0-7]) ([1-8]) ([A-Za-z0-9+/=]{1,768})$/.exec(text);
  var requestOptions = /^BHL1 REQUEST_SETTINGS 1 ([0-9a-f]{32}) ([0-9a-f]{32})$/.exec(text);
  if (requestOptions) {
    if (requestOptions[1] !== worldId || requestOptions[2] !== nonce || helloDeadline) return;
    event.cancel = true; saveSettings(); return;
  }
  var options = /^BHL1 SETTINGS 1 ([0-9a-f]{32}) ([0-9a-f]{32}) ([01]) ([0-9]{3,4}) ([0-9]{2,4}) ([0-9]{3,4}) ([01]) ([01])$/.exec(text);
  if (options) {
    if (options[1] !== worldId || options[2] !== nonce || helloDeadline) return;
    var distance = Number(options[4]), near = Number(options[5]), quads = Number(options[6]);
    if (distance < 128 || distance > 1024 || near < 16 || near >= distance || quads < 128 || quads > 2048) return;
    event.cancel = true;
    settings.enabled = options[3] === "1"; settings.distance = distance; settings.near = near;
    settings.quads = quads; settings.approximate = options[7] === "1"; settings.skirts = options[8] === "1";
    samples = null; renderMesh = []; lastMeshRevision = -1;
    saveSettings(false); notice("Settings updated from your world settings book."); return;
  }
  if (!part || part[1] !== worldId || part[2] !== nonce || !request) return;
  var sequence = Number(part[3]), index = Number(part[4]), count = Number(part[5]);
  if (!Number.isSafeInteger(sequence) || sequence > 2147483647 || index >= count) return;
  var now = Date.now();
  assemblies.forEach(function(a, key) { if (now - a.created > 10000) assemblies.delete(key); });
  var assembly = assemblies.get(sequence);
  if (!assembly) {
    if (assemblies.size >= 4) return;
    assembly = {count: count, created: now, parts: new Array(count), request: request}; assemblies.set(sequence, assembly);
  }
  if (assembly.count !== count || assembly.request !== request ||
      (assembly.parts[index] !== undefined && assembly.parts[index] !== part[6])) return;
  // Matching opted-in envelope: consume it without displaying binary payload in chat.
  event.cancel = true; assembly.parts[index] = part[6];
  for (var i = 0; i < count; i++) if (assembly.parts[i] === undefined) return;
  try {
    var tile = codec.decode(codec.unbase64(assembly.parts.join("")));
    if (tile.world !== worldId || tile.dimension !== dimensionId || tile.source !== 2 ||
        tile.x !== request.x || tile.z !== request.z || tile.step !== request.step)
      throw new Error("Tile does not match requested terrain");
    cache.put(tile); game.executeCommand("/bhl:ack " + sequence);
    status = "World terrain received"; request = null; assemblies.clear(); lastMeshRevision = -1;
  } catch (_) {
    assemblies.delete(sequence); status = "Discarded an invalid terrain tile";
    // No ACK for malformed data. The bounded server timeout releases its delivery.
  }
}
function selectRequest(p) {
  if (!companion || !generation || helloDeadline || request || dimensionId < 0) return;
  var step = 4, span = 16 * step, bx = Math.floor(p.x / span), bz = Math.floor(p.z / span);
  var radius = Math.ceil(settings.distance / span), best = null, now = Date.now();
  for (var dz = -radius; dz <= radius; dz++) for (var dx = -radius; dx <= radius; dx++) {
    var x = (bx + dx) * span, z = (bz + dz) * span;
    var distance = Math.hypot(x + span / 2 - p.x, z + span / 2 - p.z);
    if (distance < settings.near - span || distance > settings.distance || !codec.coordinates(x, z, step)) continue;
    var key = worldId + "-" + dimensionId + "-4-" + x + "-" + z + "-2";
    var cached = cache.get(key);
    if ((cached && now - (cached.receivedAt || 0) < 600000) || (retry.get(key) || 0) > now) continue;
    if (!best || distance < best.distance) best = {x: x, z: z, step: step, key: key, distance: distance, created: now};
  }
  if (best) {
    request = best; retry.set(best.key, now + 60000);
    if (retry.size > 512) retry.delete(retry.keys().next().value);
    game.executeCommand("/bhl:request " + best.x + " " + best.z + " " + step);
  } else if (now - helloAt > 30000) {
    // Keep a quiet opted-in session alive without interrupting a tile transfer.
    helloAt = now; game.executeCommand("/bhl:hello 0.1.1 " + nonce);
  }
}
function beginSampling(p) {
  var step = 2, span = 16 * step, bx = Math.floor(p.x / span), bz = Math.floor(p.z / span);
  var choices = [];
  // Read only the nearby client copy. Never load/request terrain through this path.
  for (var dz = -2; dz <= 2; dz++) for (var dx = -2; dx <= 2; dx++) {
    var x = (bx + dx) * span, z = (bz + dz) * span;
    if (!codec.coordinates(x, z, step)) continue;
    var candidate = {world: worldId, dimension: dimensionId, x: x, z: z, step: step, source: 1,
      revision: Date.now(), samples: new Array(289).fill(null), approximate: settings.approximate};
    var old = cache.get(codec.key(candidate));
    if (!old || Date.now() - old.revision > 30000) choices.push(candidate);
  }
  choices.sort(function(a, b) {
    return Math.hypot(a.x + 16 - p.x, a.z + 16 - p.z) - Math.hypot(b.x + 16 - p.x, b.z + 16 - p.z);
  });
  if (choices.length) samples = {tile: choices[0], index: 0, found: 0};
}
function sampleClient(p) {
  if (typeof dimension.getSurface !== "function") { status = "Native terrain bridge is not installed"; return; }
  if (!settings.approximate && Date.now() < strictProbeAfter) return;
  if (!samples) beginSampling(p);
  if (!samples) return;
  var job = samples, tile = job.tile;
  for (var n = 0; n < 2 && job.index < 289; n++, job.index++) {
    var sx = tile.x + (job.index % 17) * tile.step, sz = tile.z + Math.floor(job.index / 17) * tile.step;
    if (Math.abs(sx - p.x) > 128 || Math.abs(sz - p.z) > 128) continue;
    var read = dimension.getSurface(sx, sz), observed = read && read.observed;
    if (!settings.approximate && read && read.known === false) {
      status = "Strict mode: waiting for a verified chunk-readiness bridge";
      samples = null; strictProbeAfter = Date.now() + 10000; return;
    }
    // Observation-only native bridge never supplies known:true; strict mode rejects it.
    if (!read || (!read.known && !settings.approximate) || !codec.validSample(observed)) continue;
    if (!read.known) tile.approximate = true;
    tile.samples[job.index] = {height: observed.height, water: observed.water, color: observed.color.slice()}; job.found++;
  }
  if (job.index >= 289) {
    if (job.found) { cache.put(tile); status = tile.approximate ? "Approximate visited terrain cached" : "Visited terrain cached"; }
    else if (!companion) status = "Strict mode: waiting for a verified chunk-readiness bridge";
    samples = null;
  }
}
function tick() {
  ticks++;
  if (!world.exists() || !dimension.exists()) return;
  var p = position(); if (!p) return;
  if (!worldId) reset(false);
  var dim = currentDimension();
  if (dim !== dimensionId) {
    dimensionId = dim; request = null; assemblies.clear(); samples = null; renderMesh = []; lastMeshRevision = -1;
  }
  var now = Date.now();
  if (helloDeadline && now > helloDeadline) {
    companion = false; helloDeadline = 0; status = "Companion did not respond";
    notice("The companion did not respond. Its pack must be active in this world.");
  }
  if (request && now - request.created > 45000) { request = null; assemblies.clear(); status = "Terrain request timed out"; }
  if (companion && !helloDeadline && !request && now - helloAt > 30000) {
    helloAt = now; game.executeCommand("/bhl:hello 0.1.1 " + nonce);
  }
  assemblies.forEach(function(a, key) { if (now - a.created > 10000) assemblies.delete(key); });
  if (!settings.enabled || dimensionId < 0) return;
  if (ticks % 20 === 0) selectRequest(p);
  if (!companion) sampleClient(p);
  if (ticks % 40 === 0) cache.flush(2);
  var context = Math.floor(p.x / 16) + ":" + Math.floor(p.z / 16) + ":" + worldId + ":" + dimensionId;
  if (ticks % 20 === 0 && (context !== visibleContext || cache.revision !== lastMeshRevision)) {
    renderMesh = mesh.build(cache.near(worldId, dimensionId, p.x, p.z, settings.distance, settings.approximate), p, settings);
    visibleContext = context; lastMeshRevision = cache.revision;
  }
}
function command(args) {
  var action = (args[0] || "status").toLowerCase();
  if (action === "status") {
    notice(status + "; " + renderMesh.length + " distant quads. " +
      (persistentWorld ? "Persistent world cache." : "Session cache; use 'horizons world NAME' to keep it."));
  } else if (action === "on" || action === "off") {
    settings.enabled = action === "on"; renderMesh = []; lastMeshRevision = -1;
    saveSettings(); notice(settings.enabled ? "Distant terrain enabled." : "Distant terrain disabled.");
  } else if (action === "menu" || action === "book") {
    if (!world.exists()) { notice("Join a companion-enabled world first."); return true; }
    if (!companion) connect();
    game.executeCommand(action === "menu" ? "/bhl:menu" : "/bhl:book");
  } else if (action === "generation" && ["on", "off"].indexOf(args[1]) >= 0) {
    game.executeCommand("/bhl:config " + (args[1] === "on" ? "true" : "false"));
  } else if (action === "skirts" && ["on", "off"].indexOf(args[1]) >= 0) {
    settings.skirts = args[1] === "on"; renderMesh = []; lastMeshRevision = -1;
    saveSettings(); notice(settings.skirts ? "Tile edge seams hidden." : "Tile edge skirts disabled.");
  } else if (action === "realm" || action === "server") {
    if (args[1] === "on") connect();
    else if (args[1] === "off") { reset(true); notice("Using the client cache only."); }
    else notice("Use 'horizons realm on' after the owner activates the companion pack.");
  } else if (action === "approximate" && ["on", "off"].indexOf(args[1]) >= 0) {
    settings.approximate = args[1] === "on"; samples = null; renderMesh = []; lastMeshRevision = -1;
    saveSettings(); notice(settings.approximate ? "Approximate observations enabled; partially loaded terrain may be clipped." : "Only verified terrain will be drawn.");
  } else if (action === "world") {
    var alias = String(args[1] || "").toLowerCase();
    if (!/^[a-z0-9_-]{1,40}$/.test(alias)) { notice("Choose a short world name using letters, numbers, '-' or '_'."); return true; }
    if (!world.exists()) { notice("Join the world first."); return true; }
    if (companion) { notice("The companion already supplies a persistent world identity."); return true; }
    if (!aliases[alias]) {
      if (Object.keys(aliases).length >= 64) { notice("World alias limit reached."); return true; }
      aliases[alias] = randomId();
    }
    worldId = aliases[alias]; persistentWorld = true; cache.persistent = true; samples = null;
    renderMesh = []; lastMeshRevision = -1; saveSettings(); notice("Using the saved terrain for '" + alias + "'. Use a different name for each world.");
  } else if (action === "distance" || action === "near" || action === "quads") {
    var value = Number(args[1]), bounds = action === "distance" ? [128, 1024] : action === "near" ? [16, settings.distance - 16] : [128, 2048];
    if (!Number.isInteger(value) || value < bounds[0] || value > bounds[1]) {
      notice("Use a value between " + bounds[0] + " and " + bounds[1] + "."); return true;
    }
    settings[action] = value;
    if (settings.near >= settings.distance) settings.near = Math.floor(settings.distance / 2);
    renderMesh = []; lastMeshRevision = -1; saveSettings(); notice("Updated " + action + ".");
  } else {
    notice("horizons menu/book | status | on/off | world NAME | realm on/off | generation on/off | approximate on/off | skirts on/off | distance BLOCKS | near BLOCKS | quads COUNT");
  }
  return true;
}
var horizons = new Command("horizons", "Experimental distant terrain controls", "horizons [option]", ["bhl"]);
horizons.on("execute", function(label, args) { return command(args); });
client.getCommandManager().registerCommand(horizons);
client.on("receive-chat", protocol, 100);
client.on("world-tick", function() {
  try { tick(); } catch (_) { settings.enabled = false; renderMesh = []; status = "Terrain bridge stopped after an error"; notice(status); }
});
client.on("render3d", function() {
  if (settings.enabled && world.exists() && renderMesh.length) {
    try { mesh.draw(renderMesh); } catch (_) { renderMesh = []; settings.enabled = false; notice("Distant terrain renderer stopped after an error."); }
  }
});
client.on("leave-game", function() { cache.flush(32); reset(false); });
client.on("transfer", function() { cache.flush(32); reset(false); });
client.on("change-dimension", function() { request = null; assemblies.clear(); samples = null; renderMesh = []; dimensionId = -1; });
client.on("unload-script", function(event) {
  if (event.scriptName !== plugin.name) return;
  if (companion && world.exists()) game.executeCommand("/bhl:disable");
  cache.flush(32); renderMesh = [];
});
notice("Prototype loaded. Use '" + client.getCommandManager().getPrefix() + "horizons' for controls. Native rendering compatibility is not yet confirmed.");
