"use strict";
// Heightfield only: does not claim caves, overhangs, textures or gameplay collision.
function build(tiles, player, settings) {
  var result = [], covered = new Set();
  tiles = tiles.slice().sort(function(a, b) {
    return (a.approximate ? 1 : 0) - (b.approximate ? 1 : 0) || b.source - a.source || a.step - b.step;
  });
  for (var t = 0; t < tiles.length && result.length < settings.quads; t++) {
    var tile = tiles[t], middleX = tile.x + 8 * tile.step, middleZ = tile.z + 8 * tile.step;
    var distance = Math.hypot(middleX - player.x, middleZ - player.z);
    var stride = distance > 768 ? 8 : distance > 384 ? 4 : distance > 192 ? 2 : 1;
    for (var z = 0; z < 16; z += stride) for (var x = 0; x < 16; x += stride) {
      if (result.length >= settings.quads) break;
      var wx = tile.x + x * tile.step, wz = tile.z + z * tile.step, width = stride * tile.step;
      var dd = Math.hypot(wx + width / 2 - player.x, wz + width / 2 - player.z);
      if (dd < settings.near || dd > settings.distance) continue;
      // Never interpolate across unobserved lattice entries, including interiors.
      var available = true;
      for (var zz = z; zz <= z + stride && available; zz++) for (var xx = x; xx <= x + stride; xx++) {
        if (!tile.samples[zz * 17 + xx]) { available = false; break; }
      }
      if (!available) continue;
      var cellKeys = [], overlap = false;
      // Shared 2-block raster prevents a coarser source from overlaying a finer one.
      for (var rz = wz; rz < wz + width; rz += 2) for (var rx = wx; rx < wx + width; rx += 2) {
        var ck = Math.floor(rx / 2) + ":" + Math.floor(rz / 2);
        if (covered.has(ck)) overlap = true;
        cellKeys.push(ck);
      }
      if (overlap) continue;
      cellKeys.forEach(function(ck) { covered.add(ck); });
      var a = tile.samples[z * 17 + x], b = tile.samples[z * 17 + x + stride];
      var c = tile.samples[(z + stride) * 17 + x + stride], d = tile.samples[(z + stride) * 17 + x];
      var color = [0, 1, 2].map(function(channel) {
        return Math.round((a.color[channel] + b.color[channel] + c.color[channel] + d.color[channel]) / 4);
      });
      // Quad winding matches upward surface. No through-wall/debug rendering mode.
      var vertices = [{x: wx, y: a.height, z: wz}, {x: wx, y: d.height, z: wz + width},
        {x: wx + width, y: c.height, z: wz + width}, {x: wx + width, y: b.height, z: wz}];
      result.push({vertices: vertices, color: color});
      // Small skirts at tile edges hide adjacent resolution seams; never exceed budget.
      if (settings.skirts && (x === 0 || z === 0 || x + stride === 16 || z + stride === 16)) {
        var edges = [];
        if (x === 0) edges.push([vertices[0], vertices[1]]);
        if (z + stride === 16) edges.push([vertices[1], vertices[2]]);
        if (x + stride === 16) edges.push([vertices[2], vertices[3]]);
        if (z === 0) edges.push([vertices[3], vertices[0]]);
        for (var e = 0; e < edges.length && result.length < settings.quads; e++) {
          var p = edges[e][0], q = edges[e][1], depth = Math.min(width, 8);
          result.push({vertices: [q, p, {x: p.x, y: p.y - depth, z: p.z},
            {x: q.x, y: q.y - depth, z: q.z}], color: color.map(function(v) { return Math.round(v * 0.8); })});
        }
      }
    }
  }
  return result;
}
function draw(mesh) {
  if (!mesh.length) return;
  mesh.forEach(function(quad) {
    graphics3D.setColor(new Color(quad.color[0] / 255, quad.color[1] / 255, quad.color[2] / 255, 1));
    var p = quad.vertices;
    graphics3D.drawQuad(new Vector3(p[0].x, p[0].y, p[0].z), new Vector3(p[1].x, p[1].y, p[1].z),
      new Vector3(p[2].x, p[2].y, p[2].z), new Vector3(p[3].x, p[3].y, p[3].z));
  });
  // Pinned Latite source: true selects normal material; false enables renderThrough.
  graphics3D.finish(true);
}
module.exports = {build: build, draw: draw};
