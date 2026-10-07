"use strict";
var codec = require("tile.js"), fs = require("filesystem");
var MAX_DISK = 4096, MAX_BYTES = 32 * 1024 * 1024, MAX_RESIDENT = 192;
var keyPattern = /^[0-9a-f]{32}-[012]-(?:[0-9]{1,5})--?[0-9]{1,8}--?[0-9]{1,8}-[123o]$/;
function Cache() {
  this.index = []; this.resident = new Map(); this.dirty = new Map(); this.indexDirty = false;
  this.revision = 0; this.persistent = true; this.errors = 0;
  try {
    if (!fs.exists("cache")) fs.createDirectory("cache");
    if (fs.exists("cache/index.json")) {
      var saved = JSON.parse(codec.asciiText(fs.read("cache/index.json"), 1024 * 1024));
      if (Array.isArray(saved)) {
        var seen = new Set();
        this.index = saved.slice(-MAX_DISK).filter(function(e) {
          if (!e || !keyPattern.test(e.key) || seen.has(e.key) || !Number.isFinite(e.used)) return false;
          e.bytes = Number.isInteger(e.bytes) && e.bytes >= 0 && e.bytes <= 50000 ? e.bytes : 50000;
          seen.add(e.key); return true;
        });
      }
    }
  } catch (_) { this.index = []; this.errors++; }
}
Cache.prototype.get = function(key) {
  if (!keyPattern.test(key)) return null;
  var live = this.resident.get(key), entry = this.index.find(function(e) { return e.key === key; });
  if (!live && entry) {
    try {
      var suffix = key.endsWith("-o") ? ".json" : ".b64";
      var text = codec.asciiText(fs.read("cache/" + key + suffix), 50000);
      if (suffix === ".b64") live = codec.decode(codec.unbase64(text));
      else {
        live = JSON.parse(text);
        if (!live || live.approximate !== true || !codec.worldValid(live.world) ||
            [0, 1, 2].indexOf(live.dimension) < 0 || live.source !== 1 ||
            !codec.coordinates(live.x, live.z, live.step) || !Array.isArray(live.samples) ||
            live.samples.length !== 289 || !Number.isSafeInteger(live.revision) ||
            live.samples.some(function(s) { return s !== null && !codec.validSample(s); }))
          throw new Error("Invalid observations");
      }
      if (codec.key(live) !== key) throw new Error("Mismatched cache namespace");
      this.resident.set(key, live);
    } catch (_) { this.index = this.index.filter(function(e) { return e.key !== key; }); this.indexDirty = true; this.errors++; return null; }
  }
  if (live) {
    this.resident.delete(key); this.resident.set(key, live);
    if (entry) entry.used = Date.now();
    this.evictResident();
  }
  return live || null;
};
Cache.prototype.evictResident = function() {
  // At most 32 dirty tiles plus the clean resident cap. No dirty observations are lost.
  while (this.resident.size > MAX_RESIDENT + this.dirty.size) {
    var candidate = null;
    for (var key of this.resident.keys()) { if (!this.dirty.has(key)) { candidate = key; break; } }
    if (!candidate) break;
    this.resident.delete(candidate);
  }
};
Cache.prototype.put = function(tile) {
  var key = codec.key(tile), old = this.resident.get(key);
  if (!keyPattern.test(key) || (old && old.revision > tile.revision)) return false;
  this.resident.delete(key); this.resident.set(key, tile);
  if (this.persistent) {
    if (this.dirty.size >= 32 && !this.dirty.has(key)) this.flush(2);
    if (this.dirty.size < 32 || this.dirty.has(key)) this.dirty.set(key, tile);
  }
  this.revision++; this.evictResident(); return true;
};
Cache.prototype.flush = function(limit) {
  var written = 0;
  for (var pair of this.dirty) {
    if (written >= limit) break;
    var key = pair[0], tile = pair[1], suffix = tile.approximate ? ".json" : ".b64";
    try {
      var text = tile.approximate ? JSON.stringify(tile) : codec.base64(codec.encode(tile));
      fs.write("cache/" + key + suffix, codec.asciiBytes(text));
      this.index = this.index.filter(function(e) { return e.key !== key; });
      this.index.push({key: key, used: Date.now(), bytes: text.length}); this.indexDirty = true;
      this.dirty.delete(key); written++;
    } catch (_) { this.errors++; this.dirty.delete(key); written++; }
  }
  this.index.sort(function(a, b) { return a.used - b.used; });
  var bytesUsed = this.index.reduce(function(sum, e) { return sum + e.bytes; }, 0);
  while (this.index.length > MAX_DISK || bytesUsed > MAX_BYTES) {
    var old = this.index.shift();
    bytesUsed -= old.bytes;
    try { fs.delete("cache/" + old.key + (old.key.endsWith("-o") ? ".json" : ".b64")); } catch (_) {}
    this.indexDirty = true;
  }
  if (this.indexDirty) {
    try { fs.write("cache/index.json", codec.asciiBytes(JSON.stringify(this.index))); this.indexDirty = false; }
    catch (_) { this.errors++; }
  }
  this.evictResident();
};
Cache.prototype.near = function(world, dim, x, z, radius, approximate) {
  var keys = new Set(), prefix = world + "-" + dim + "-", self = this;
  this.index.forEach(function(e) { if (e.key.indexOf(prefix) === 0) keys.add(e.key); });
  this.resident.forEach(function(t, key) { if (key.indexOf(prefix) === 0) keys.add(key); });
  var result = [];
  // Parse only filenames before loading, keeping disk reads within the nearby window.
  keys.forEach(function(key) {
    var m = /^([0-9a-f]{32})-([012])-(\d+)-(-?\d+)-(-?\d+)-([123o])$/.exec(key);
    if (!m || (m[6] === "o" && !approximate)) return;
    var step = Number(m[3]), ox = Number(m[4]), oz = Number(m[5]);
    var dx = Math.max(ox - x, x - (ox + 16 * step), 0);
    var dz = Math.max(oz - z, z - (oz + 16 * step), 0);
    if (dx * dx + dz * dz > radius * radius) return;
    result.push({key: key, distance: dx * dx + dz * dz});
  });
  result.sort(function(a, b) { return a.distance - b.distance; });
  return result.slice(0, MAX_RESIDENT).map(function(e) { return self.get(e.key); }).filter(Boolean);
};
module.exports = Cache;
