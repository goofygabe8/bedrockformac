// Shared wire contract: BHTILE01, 80-byte LE header, 289 eight-byte vertices.
// No Node.js, Buffer, TextEncoder, or browser-only APIs are used in this pack.
export const TILE_BYTES = 2392;
export const VERTEX_COUNT = 289;
export const WORLD_LIMIT = 30000000;
const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

export function validTileCoordinates(x, z, step) {
  return Number.isSafeInteger(x) && Number.isSafeInteger(z) &&
    Number.isInteger(step) && step >= 1 && step <= 16384 &&
    (step & (step - 1)) === 0 && x % (16 * step) === 0 && z % (16 * step) === 0 &&
    x >= -WORLD_LIMIT && z >= -WORLD_LIMIT &&
    x + 16 * step <= WORLD_LIMIT && z + 16 * step <= WORLD_LIMIT;
}

export function newWorldId() {
  // An opaque cache identity, not an authentication secret or a seed.
  let id = "";
  for (let i = 0; i < 32; i++) id += Math.floor(Math.random() * 16).toString(16);
  return id;
}

export function validWorldId(id) {
  return typeof id === "string" && /^[0-9a-f]{32}$/.test(id);
}

function putU64(view, offset, value) {
  view.setUint32(offset, value >>> 0, true);
  view.setUint32(offset + 4, Math.floor(value / 4294967296) >>> 0, true);
}

function putI64(view, offset, value) {
  // All supported coordinates fit exactly into JavaScript integers.
  view.setUint32(offset, value >>> 0, true);
  view.setInt32(offset + 4, Math.floor(value / 4294967296), true);
}

export function crc32(bytes, start = 0) {
  let crc = 0xffffffff;
  for (let i = start; i < bytes.length; i++) {
    crc ^= bytes[i];
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

export function encodeTile(worldId, dimension, originX, originZ, step, revision, samples) {
  if (!validWorldId(worldId) || ![0, 1, 2].includes(dimension) ||
      !validTileCoordinates(originX, originZ, step) ||
      !Number.isSafeInteger(revision) || revision < 1 || samples.length !== VERTEX_COUNT) {
    throw new Error("Invalid surface tile metadata.");
  }
  const bytes = new Uint8Array(TILE_BYTES);
  const view = new DataView(bytes.buffer);
  const magic = "BHTILE01";
  for (let i = 0; i < magic.length; i++) bytes[i] = magic.charCodeAt(i);
  view.setUint16(8, 80, true);
  view.setUint16(10, 1, true);
  view.setUint16(12, 16, true);
  view.setUint16(14, 8, true);
  for (let i = 0; i < 16; i++) bytes[16 + i] = parseInt(worldId.slice(i * 2, i * 2 + 2), 16);
  view.setInt32(32, dimension, true);
  view.setUint32(36, step, true);
  putI64(view, 40, originX);
  putI64(view, 48, originZ);
  putU64(view, 56, revision);
  view.setUint32(64, 2, true); // Authoritative world companion.
  view.setUint32(68, VERTEX_COUNT, true);
  for (let i = 0; i < VERTEX_COUNT; i++) {
    const sample = samples[i];
    if (!sample) continue; // Unknown records are exactly eight zero bytes.
    const offset = 80 + i * 8;
    const height = Math.round(sample.height * 16);
    if (!Number.isFinite(height) || Math.abs(height) > 32768 * 16) {
      throw new Error("Invalid surface height.");
    }
    view.setInt32(offset, height, true);
    bytes[offset + 4] = 1 | (sample.water ? 2 : 0);
    for (let channel = 0; channel < 3; channel++) {
      const color = sample.color[channel];
      if (!Number.isFinite(color)) throw new Error("Invalid surface color.");
      bytes[offset + 5 + channel] = Math.max(0, Math.min(255, Math.round(color)));
    }
  }
  view.setUint32(72, crc32(bytes, 80), true);
  return bytes;
}

export function base64Encode(bytes) {
  let result = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const value = (bytes[i] << 16) | ((bytes[i + 1] ?? 0) << 8) | (bytes[i + 2] ?? 0);
    result += ALPHABET[(value >>> 18) & 63] + ALPHABET[(value >>> 12) & 63] +
      (i + 1 < bytes.length ? ALPHABET[(value >>> 6) & 63] : "=") +
      (i + 2 < bytes.length ? ALPHABET[value & 63] : "=");
  }
  return result;
}

export function base64Decode(encoded) {
  if (typeof encoded !== "string" || encoded.length !== 3192 ||
      !/^[A-Za-z0-9+/]+==$/.test(encoded)) throw new Error("Invalid cached tile encoding.");
  const bytes = new Uint8Array(TILE_BYTES);
  let output = 0;
  for (let i = 0; i < encoded.length; i += 4) {
    const values = [0, 1, 2, 3].map(n => encoded[i + n] === "=" ? 0 : ALPHABET.indexOf(encoded[i + n]));
    const value = (values[0] << 18) | (values[1] << 12) | (values[2] << 6) | values[3];
    bytes[output++] = (value >>> 16) & 255;
    if (encoded[i + 2] !== "=") bytes[output++] = (value >>> 8) & 255;
    if (encoded[i + 3] !== "=") bytes[output++] = value & 255;
  }
  if (output !== TILE_BYTES) throw new Error("Invalid cached tile length.");
  return bytes;
}

export function validCachedTile(encoded, worldId, dimension, x, z, step) {
  try {
    const bytes = base64Decode(encoded);
    const view = new DataView(bytes.buffer);
    if (String.fromCharCode(...bytes.slice(0, 8)) !== "BHTILE01" ||
        view.getUint16(8, true) !== 80 || view.getUint16(10, true) !== 1 ||
        view.getUint16(12, true) !== 16 || view.getUint16(14, true) !== 8 ||
        view.getInt32(32, true) !== dimension || view.getUint32(36, true) !== step ||
        view.getUint32(64, true) !== 2 || view.getUint32(68, true) !== VERTEX_COUNT ||
        view.getUint32(76, true) !== 0 || view.getUint32(72, true) !== crc32(bytes, 80)) return false;
    for (let i = 0; i < 16; i++) if (bytes[16 + i] !== parseInt(worldId.slice(i * 2, i * 2 + 2), 16)) return false;
    const readI64 = offset => view.getInt32(offset + 4, true) * 4294967296 + view.getUint32(offset, true);
    return readI64(40) === x && readI64(48) === z;
  } catch (_) {
    return false;
  }
}
