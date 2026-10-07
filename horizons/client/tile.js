"use strict";
// Original implementation of the shared BHTILE01 format. ES2015/Chakra compatible.
var SIZE = 2392, EDGE = 17, ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
function worldValid(s) { return typeof s === "string" && /^[0-9a-f]{32}$/.test(s) && s !== "00000000000000000000000000000000"; }
function coordinates(x, z, step) {
  return Number.isSafeInteger(x) && Number.isSafeInteger(z) && Number.isInteger(step) &&
    step >= 1 && step <= 16384 && (step & (step - 1)) === 0 &&
    x % (16 * step) === 0 && z % (16 * step) === 0 &&
    x >= -30000000 && z >= -30000000 && x + 16 * step <= 30000000 && z + 16 * step <= 30000000;
}
function crc32(bytes, start) {
  var crc = 0xffffffff;
  for (var i = start || 0; i < bytes.length; i++) {
    crc ^= bytes[i];
    for (var j = 0; j < 8; j++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function base64(bytes) {
  var out = "";
  for (var i = 0; i < bytes.length; i += 3) {
    var v = (bytes[i] << 16) | ((bytes[i + 1] || 0) << 8) | (bytes[i + 2] || 0);
    out += ALPHABET[(v >>> 18) & 63] + ALPHABET[(v >>> 12) & 63] +
      (i + 1 < bytes.length ? ALPHABET[(v >>> 6) & 63] : "=") +
      (i + 2 < bytes.length ? ALPHABET[v & 63] : "=");
  }
  return out;
}
function unbase64(text) {
  if (typeof text !== "string" || text.length !== 3192 || !/^[A-Za-z0-9+/]+==$/.test(text))
    throw new Error("Invalid tile encoding");
  var out = new Uint8Array(SIZE), at = 0;
  for (var i = 0; i < text.length; i += 4) {
    var a = ALPHABET.indexOf(text[i]), b = ALPHABET.indexOf(text[i + 1]);
    var c = text[i + 2] === "=" ? 0 : ALPHABET.indexOf(text[i + 2]);
    var d = text[i + 3] === "=" ? 0 : ALPHABET.indexOf(text[i + 3]);
    var v = (a << 18) | (b << 12) | (c << 6) | d;
    out[at++] = (v >>> 16) & 255;
    if (text[i + 2] !== "=") out[at++] = (v >>> 8) & 255;
    if (text[i + 3] !== "=") out[at++] = v & 255;
  }
  if (at !== SIZE || base64(out) !== text) throw new Error("Noncanonical tile encoding");
  return out;
}
function read64(view, offset, signed) {
  var high = signed ? view.getInt32(offset + 4, true) : view.getUint32(offset + 4, true);
  var value = high * 4294967296 + view.getUint32(offset, true);
  if (!Number.isSafeInteger(value)) throw new Error("Tile integer exceeds exact range");
  return value;
}
function write64(view, offset, value, signed) {
  view.setUint32(offset, value >>> 0, true);
  if (signed) view.setInt32(offset + 4, Math.floor(value / 4294967296), true);
  else view.setUint32(offset + 4, Math.floor(value / 4294967296), true);
}
function decode(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.length !== SIZE) throw new Error("Wrong tile size");
  var view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (String.fromCharCode.apply(null, Array.prototype.slice.call(bytes, 0, 8)) !== "BHTILE01" ||
      view.getUint16(8, true) !== 80 || view.getUint16(10, true) !== 1 ||
      view.getUint16(12, true) !== 16 || view.getUint16(14, true) !== 8 ||
      view.getUint32(68, true) !== 289 || view.getUint32(76, true) !== 0 ||
      view.getUint32(72, true) !== crc32(bytes, 80)) throw new Error("Corrupt or unsupported tile");
  var world = "";
  for (var i = 16; i < 32; i++) world += ("0" + bytes[i].toString(16)).slice(-2);
  var tile = {world: world, dimension: view.getInt32(32, true), step: view.getUint32(36, true),
    x: read64(view, 40, true), z: read64(view, 48, true), revision: read64(view, 56, false),
    source: view.getUint32(64, true), samples: [], approximate: false};
  if ([0, 1, 2].indexOf(tile.dimension) < 0 || [1, 2, 3].indexOf(tile.source) < 0 ||
      !worldValid(tile.world) || !coordinates(tile.x, tile.z, tile.step)) throw new Error("Invalid tile metadata");
  for (var n = 0; n < 289; n++) {
    var offset = 80 + n * 8, flags = bytes[offset + 4];
    if (flags & ~3) throw new Error("Unknown sample flags");
    if (!(flags & 1)) {
      for (var b = 0; b < 8; b++) if (bytes[offset + b]) throw new Error("Invalid unknown sample");
      tile.samples.push(null);
    } else {
      var y = view.getInt32(offset, true) / 16;
      if (Math.abs(y) > 32768) throw new Error("Invalid sample height");
      tile.samples.push({height: y, water: !!(flags & 2), color: [bytes[offset + 5], bytes[offset + 6], bytes[offset + 7]]});
    }
  }
  return tile;
}
function validSample(s) {
  return s && Number.isFinite(s.height) && Math.abs(s.height) <= 32768 &&
    Array.isArray(s.color) && s.color.length === 3 && s.color.every(function(c) {
      return Number.isInteger(c) && c >= 0 && c <= 255;
    }) && typeof s.water === "boolean";
}
function encode(tile) {
  if (tile.approximate || !worldValid(tile.world) || !coordinates(tile.x, tile.z, tile.step) ||
      [0, 1, 2].indexOf(tile.dimension) < 0 || [1, 2, 3].indexOf(tile.source) < 0 ||
      !Number.isSafeInteger(tile.revision) || tile.revision < 0 || tile.samples.length !== 289)
    throw new Error("Invalid tile; observations cannot be encoded as verified terrain");
  var bytes = new Uint8Array(SIZE), view = new DataView(bytes.buffer);
  for (var i = 0; i < 8; i++) bytes[i] = "BHTILE01".charCodeAt(i);
  view.setUint16(8, 80, true); view.setUint16(10, 1, true);
  view.setUint16(12, 16, true); view.setUint16(14, 8, true);
  for (var w = 0; w < 16; w++) bytes[16 + w] = parseInt(tile.world.slice(w * 2, w * 2 + 2), 16);
  view.setInt32(32, tile.dimension, true); view.setUint32(36, tile.step, true);
  write64(view, 40, tile.x, true); write64(view, 48, tile.z, true); write64(view, 56, tile.revision, false);
  view.setUint32(64, tile.source, true); view.setUint32(68, 289, true);
  tile.samples.forEach(function(s, n) {
    if (!s) return;
    if (!validSample(s)) throw new Error("Invalid surface sample");
    var offset = 80 + n * 8;
    view.setInt32(offset, Math.round(s.height * 16), true);
    bytes[offset + 4] = 1 | (s.water ? 2 : 0);
    for (var channel = 0; channel < 3; channel++) bytes[offset + 5 + channel] = s.color[channel];
  });
  view.setUint32(72, crc32(bytes, 80), true);
  return bytes;
}
function key(t) {
  return t.world + "-" + t.dimension + "-" + t.step + "-" + t.x + "-" + t.z + "-" +
    (t.approximate ? "o" : String(t.source));
}
function asciiBytes(text) {
  var bytes = new Uint8Array(text.length);
  for (var i = 0; i < text.length; i++) {
    var c = text.charCodeAt(i);
    if (c > 127) throw new Error("ASCII persistence required");
    bytes[i] = c;
  }
  return bytes;
}
function asciiText(bytes, max) {
  if (!bytes || bytes.length > max) throw new Error("Cache file too large");
  var text = "";
  for (var i = 0; i < bytes.length; i++) {
    if (bytes[i] > 127) throw new Error("Invalid cache encoding");
    text += String.fromCharCode(bytes[i]);
  }
  return text;
}
module.exports = {SIZE: SIZE, EDGE: EDGE, worldValid: worldValid, coordinates: coordinates,
  crc32: crc32, base64: base64, unbase64: unbase64, decode: decode, encode: encode,
  validSample: validSample, key: key, asciiBytes: asciiBytes, asciiText: asciiText};
