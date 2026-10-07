#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace bedrock_horizons {

constexpr std::uint16_t kCells = 16;
constexpr std::uint16_t kEdge = kCells + 1;
constexpr std::size_t kSamples = kEdge * kEdge;
constexpr std::size_t kHeaderBytes = 80;
constexpr std::size_t kSampleBytes = 8;
constexpr std::size_t kTileBytes = kHeaderBytes + kSamples * kSampleBytes;
constexpr std::int64_t kWorldLimit = 30000000;
constexpr std::int32_t kHeightLimit = 32768 * 16;

using WorldId = std::array<std::uint8_t, 16>;
enum class Source : std::uint32_t { Visited = 1, Authoritative = 2, Composite = 3 };

// Column height means the TOP face of the visible surface in blocks. The producer
// chooses a stable RGB palette. Empty or unavailable columns must stay unknown.
struct Sample {
    std::int32_t heightSixteenths = 0;
    std::uint8_t flags = 0;
    std::array<std::uint8_t, 3> color{};
    bool known() const noexcept { return (flags & 1U) != 0; }
    bool water() const noexcept { return (flags & 2U) != 0; }
    static Sample observed(double surfaceHeight, std::array<std::uint8_t, 3> rgb,
                           bool isWater = false);
};

// A lattice with 16x16 cells, including shared border samples. step is measured
// in blocks and origin is an exact multiple of 16*step, including below zero.
struct Tile {
    WorldId world{};
    std::int32_t dimension = 0; // 0 overworld, 1 Nether, 2 End; other ids explicit.
    std::uint32_t step = 1;
    std::int64_t originX = 0;
    std::int64_t originZ = 0;
    std::uint64_t revision = 0; // Monotonically increasing within a source.
    Source source = Source::Visited;
    std::array<Sample, kSamples> samples{};
    Sample& at(std::size_t x, std::size_t z);
    const Sample& at(std::size_t x, std::size_t z) const;
    std::size_t knownCount() const noexcept;
};

// Throws std::runtime_error or std::invalid_argument on malformed input.
void validate(const Tile& tile);
WorldId parseWorldId(const std::string& text);
std::string worldIdString(const WorldId& id);
std::uint32_t crc32(const std::uint8_t* bytes, std::size_t size) noexcept;
std::vector<std::uint8_t> encode(const Tile& tile);
Tile decode(const std::uint8_t* bytes, std::size_t size);
Tile readTile(const std::filesystem::path& file);
// Writes a bounded tile through a same-directory temporary file then rename.
// Refuses to overwrite a symlink; does not claim fsync-level durability.
void writeTile(const std::filesystem::path& file, const Tile& tile);

struct TileKey {
    WorldId world{};
    std::int32_t dimension = 0;
    std::uint32_t step = 1;
    std::int64_t originX = 0;
    std::int64_t originZ = 0;
    Source source = Source::Visited;
    bool operator==(const TileKey& other) const noexcept;
};
struct TileKeyHash { std::size_t operator()(const TileKey& key) const noexcept; };
TileKey keyFor(const Tile& tile) noexcept;
// Stable relative path. Callers must use their own trusted cache root.
std::filesystem::path cachePath(const TileKey& key);

struct CacheLimits {
    std::size_t maxTiles = 4096;
    std::size_t maxBytes = 32U * 1024U * 1024U;
};
class TileCache {
public:
    explicit TileCache(CacheLimits limits = {});
    // Returns false for an older revision. Whole-tile replacements allow an
    // authoritative producer to invalidate columns that are no longer known.
    bool put(Tile tile);
    std::optional<Tile> get(const TileKey& key);
    // Blends two sources without pretending unknown terrain is known. By
    // default authoritative known samples win; otherwise visited samples win.
    // Source==Composite is only a derived result, never a trusted provider.
    std::optional<Tile> composite(TileKey location, bool preferAuthoritative = true);
    bool erase(const TileKey& key);
    std::size_t size() const noexcept;
    std::size_t accountedBytes() const noexcept;
private:
    struct Entry { Tile tile; std::uint64_t used = 0; };
    CacheLimits limits_;
    std::uint64_t clock_ = 0;
    std::unordered_map<TileKey, Entry, TileKeyHash> tiles_;
    void evict();
    std::uint64_t touch();
};

// Four children form one parent. Order: north-west, north-east, south-west,
// south-east (positive Z is south). Missing children are represented by null.
// A parent sample requires EVERY member of its bounded 2x2 footprint to be
// known. Height is the maximum; color is averaged in linearized sRGB. Border
// footprints are clamped to the supplied 33x33 lattice, so skirts are needed.
Tile aggregate(const WorldId& world, std::int32_t dimension,
               std::int64_t parentX, std::int64_t parentZ,
               std::uint32_t parentStep, const std::array<const Tile*, 4>& children);

struct Vertex {
    double x = 0, y = 0, z = 0; // X/Z local to Mesh::originX/Z, not world floats.
    double normalX = 0, normalY = 1, normalZ = 0;
    std::array<std::uint8_t, 3> color{};
};
struct Mesh {
    WorldId world{};
    std::int32_t dimension = 0;
    std::int64_t originX = 0, originZ = 0;
    std::uint32_t step = 1;
    std::vector<Vertex> vertices;
    std::vector<std::uint32_t> indices;
    std::size_t surfaceTriangles = 0;
    std::size_t skirtTriangles = 0;
};
struct MeshOptions {
    double skirtDepth = 8; // Vertical seam cover. Never bridges unknown cells.
    bool skirts = true;
    std::size_t maxVertices = 8192;
    std::size_t maxIndices = 32768;
};
// Emits a surface cell only when all four corner samples are known. Surface
// faces point upward. Skirts follow both outer edges and holes, facing outward.
Mesh buildMesh(const Tile& tile, MeshOptions options = {});
void writeObj(const std::filesystem::path& file, const Mesh& mesh);

} // namespace bedrock_horizons
