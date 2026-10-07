#include "horizons.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <limits>
#include <random>
#include <sstream>
#include <stdexcept>

namespace bedrock_horizons {
namespace {
constexpr std::array<std::uint8_t, 8> kMagic{{'B','H','T','I','L','E','0','1'}};
constexpr std::size_t kEntryBudget = sizeof(Tile) + sizeof(TileKey) + 256;

[[noreturn]] void invalid(const std::string& message) {
    throw std::invalid_argument(message);
}
void require(bool condition, const std::string& message) {
    if (!condition) invalid(message);
}
bool powerOfTwo(std::uint32_t value) { return value && !(value & (value - 1U)); }
bool validSource(Source source) {
    return source == Source::Visited || source == Source::Authoritative ||
           source == Source::Composite;
}
void writeUnsigned(std::vector<std::uint8_t>& output, std::size_t offset,
                   std::uint64_t value, std::size_t count) {
    for (std::size_t n = 0; n < count; ++n)
        output[offset + n] = static_cast<std::uint8_t>(value >> (n * 8));
}
std::uint64_t readUnsigned(const std::uint8_t* data, std::size_t offset, std::size_t count) {
    std::uint64_t result = 0;
    for (std::size_t n = 0; n < count; ++n)
        result |= static_cast<std::uint64_t>(data[offset + n]) << (n * 8);
    return result;
}
// Explicit two's-complement interpretation avoids implementation-defined
// unsigned-to-signed conversions on malformed files.
std::int32_t signed32(std::uint64_t value) {
    return value <= 0x7fffffffU ? static_cast<std::int32_t>(value)
        : static_cast<std::int32_t>(static_cast<std::int64_t>(value) - 0x100000000LL);
}
std::int64_t signed64(std::uint64_t value) {
    return value <= static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())
        ? static_cast<std::int64_t>(value)
        : -1 - static_cast<std::int64_t>(~value);
}
int hexDigit(char value) {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10;
    return -1;
}
void atomicWrite(const std::filesystem::path& file, const std::uint8_t* data,
                 std::size_t size) {
    require(!file.empty(), "Empty output path");
    std::error_code error;
    const auto status = std::filesystem::symlink_status(file, error);
    if (!error && std::filesystem::is_symlink(status)) invalid("Output is a symbolic link");
    if (!file.parent_path().empty()) std::filesystem::create_directories(file.parent_path());
    // The directory is supplied by the caller and must be trusted. Exclusive
    // creation refuses a preexisting temporary file or symbolic link.
    std::filesystem::path temporary;
    std::FILE* output = nullptr;
    std::random_device random;
    for (unsigned attempt = 0; attempt < 32 && !output; ++attempt) {
        temporary = file;
        temporary += ".tmp-" + std::to_string(random()) + "-" + std::to_string(random());
#ifdef _WIN32
        output = _wfopen(temporary.c_str(), L"wbx");
#else
        output = std::fopen(temporary.c_str(), "wbx");
#endif
    }
    if (!output) throw std::runtime_error("Cannot create exclusive temporary output");
    bool complete = std::fwrite(data, 1, size, output) == size;
    if (std::fclose(output) != 0) complete = false;
    if (!complete) {
        std::filesystem::remove(temporary, error);
        throw std::runtime_error("Cannot write complete output");
    }
    // Recheck the target. A caller-controlled private directory is required to
    // avoid parent-directory races; remote tiles cannot choose cache paths.
    error.clear();
    if (std::filesystem::is_symlink(std::filesystem::symlink_status(file, error))) {
        std::filesystem::remove(temporary, error);
        invalid("Output became a symbolic link");
    }
    error.clear();
    std::filesystem::rename(temporary, file, error);
    if (error) {
        std::error_code cleanup;
        std::filesystem::remove(temporary, cleanup);
        throw std::runtime_error("Cannot replace output: " + error.message());
    }
}
std::array<std::uint8_t, 3> averageColor(const std::vector<const Sample*>& samples) {
    std::array<std::uint8_t, 3> result{};
    for (std::size_t channel = 0; channel < 3; ++channel) {
        double sum = 0;
        for (const auto* sample : samples)
            sum += std::pow(static_cast<double>(sample->color[channel]) / 255.0, 2.2);
        result[channel] = static_cast<std::uint8_t>(std::lround(
            255.0 * std::pow(sum / static_cast<double>(samples.size()), 1.0 / 2.2)));
    }
    return result;
}
} // namespace

Sample Sample::observed(double surfaceHeight, std::array<std::uint8_t, 3> rgb, bool isWater) {
    require(std::isfinite(surfaceHeight), "Non-finite surface height");
    require(surfaceHeight >= -32768.0 && surfaceHeight <= 32768.0, "Surface height out of range");
    Sample result;
    result.heightSixteenths = static_cast<std::int32_t>(std::llround(surfaceHeight * 16.0));
    result.flags = static_cast<std::uint8_t>(1U | (isWater ? 2U : 0U));
    result.color = rgb;
    return result;
}
Sample& Tile::at(std::size_t x, std::size_t z) {
    if (x >= kEdge || z >= kEdge) throw std::out_of_range("Tile sample coordinate");
    return samples[z * kEdge + x];
}
const Sample& Tile::at(std::size_t x, std::size_t z) const {
    if (x >= kEdge || z >= kEdge) throw std::out_of_range("Tile sample coordinate");
    return samples[z * kEdge + x];
}
std::size_t Tile::knownCount() const noexcept {
    return static_cast<std::size_t>(std::count_if(samples.begin(), samples.end(),
        [](const Sample& sample) { return sample.known(); }));
}
void validate(const Tile& tile) {
    require(std::any_of(tile.world.begin(), tile.world.end(), [](auto x) { return x != 0; }),
            "World id must be explicit and nonzero");
    require(powerOfTwo(tile.step) && tile.step <= 16384, "Invalid tile step");
    require(validSource(tile.source), "Unknown tile source");
    const auto span = static_cast<std::int64_t>(kCells) * tile.step;
    require(tile.originX % span == 0 && tile.originZ % span == 0, "Unaligned tile origin");
    require(tile.originX >= -kWorldLimit && tile.originZ >= -kWorldLimit &&
            tile.originX <= kWorldLimit - span && tile.originZ <= kWorldLimit - span,
            "Tile outside bounded world coordinates");
    for (const auto& sample : tile.samples) {
        require((sample.flags & ~3U) == 0, "Unknown sample flags");
        if (sample.known()) {
            require(sample.heightSixteenths >= -kHeightLimit &&
                    sample.heightSixteenths <= kHeightLimit, "Sample height outside range");
        } else {
            require(sample.flags == 0 && sample.heightSixteenths == 0 &&
                    sample.color == std::array<std::uint8_t, 3>{}, "Unknown sample must be zero");
        }
    }
}
WorldId parseWorldId(const std::string& text) {
    require(text.size() == 32 || text.size() == 36, "World id must be a UUID or 32 hex digits");
    if (text.size() == 36)
        for (const auto offset : {8U, 13U, 18U, 23U})
            require(text[offset] == '-', "Malformed UUID separators");
    std::string digits;
    for (std::size_t n = 0; n < text.size(); ++n) {
        if (text.size() == 36 && (n == 8 || n == 13 || n == 18 || n == 23)) continue;
        require(hexDigit(text[n]) >= 0, "Non-hex character in world id");
        digits += text[n];
    }
    WorldId result{};
    for (std::size_t n = 0; n < result.size(); ++n)
        result[n] = static_cast<std::uint8_t>(hexDigit(digits[n * 2]) * 16 + hexDigit(digits[n * 2 + 1]));
    require(std::any_of(result.begin(), result.end(), [](auto x) { return x != 0; }), "World id is zero");
    return result;
}
std::string worldIdString(const WorldId& id) {
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (std::size_t n = 0; n < id.size(); ++n) {
        if (n == 4 || n == 6 || n == 8 || n == 10) output << '-';
        output << std::setw(2) << static_cast<unsigned>(id[n]);
    }
    return output.str();
}
std::uint32_t crc32(const std::uint8_t* bytes, std::size_t size) noexcept {
    std::uint32_t result = 0xffffffffU;
    for (std::size_t n = 0; n < size; ++n) {
        result ^= bytes[n];
        for (unsigned bit = 0; bit < 8; ++bit)
            result = (result >> 1U) ^ ((result & 1U) ? 0xedb88320U : 0U);
    }
    return result ^ 0xffffffffU;
}
std::vector<std::uint8_t> encode(const Tile& tile) {
    validate(tile);
    std::vector<std::uint8_t> output(kTileBytes, 0);
    std::copy(kMagic.begin(), kMagic.end(), output.begin());
    writeUnsigned(output, 8, kHeaderBytes, 2);
    writeUnsigned(output, 10, 1, 2);
    writeUnsigned(output, 12, kCells, 2);
    writeUnsigned(output, 14, kSampleBytes, 2);
    std::copy(tile.world.begin(), tile.world.end(), output.begin() + 16);
    writeUnsigned(output, 32, static_cast<std::uint32_t>(tile.dimension), 4);
    writeUnsigned(output, 36, tile.step, 4);
    writeUnsigned(output, 40, static_cast<std::uint64_t>(tile.originX), 8);
    writeUnsigned(output, 48, static_cast<std::uint64_t>(tile.originZ), 8);
    writeUnsigned(output, 56, tile.revision, 8);
    writeUnsigned(output, 64, static_cast<std::uint32_t>(tile.source), 4);
    writeUnsigned(output, 68, kSamples, 4);
    for (std::size_t n = 0; n < kSamples; ++n) {
        const auto offset = kHeaderBytes + n * kSampleBytes;
        writeUnsigned(output, offset, static_cast<std::uint32_t>(tile.samples[n].heightSixteenths), 4);
        output[offset + 4] = tile.samples[n].flags;
        std::copy(tile.samples[n].color.begin(), tile.samples[n].color.end(), output.begin() + offset + 5);
    }
    writeUnsigned(output, 72, crc32(output.data() + kHeaderBytes, kTileBytes - kHeaderBytes), 4);
    return output;
}
Tile decode(const std::uint8_t* bytes, std::size_t size) {
    require(bytes && size == kTileBytes, "Tile must contain exactly 2392 bytes");
    require(std::equal(kMagic.begin(), kMagic.end(), bytes), "Unknown tile magic");
    require(readUnsigned(bytes, 8, 2) == kHeaderBytes && readUnsigned(bytes, 10, 2) == 1 &&
            readUnsigned(bytes, 12, 2) == kCells && readUnsigned(bytes, 14, 2) == kSampleBytes &&
            readUnsigned(bytes, 68, 4) == kSamples && readUnsigned(bytes, 76, 4) == 0,
            "Unsupported tile schema");
    require(readUnsigned(bytes, 72, 4) == crc32(bytes + kHeaderBytes, size - kHeaderBytes),
            "Tile payload checksum mismatch");
    Tile result;
    std::copy(bytes + 16, bytes + 32, result.world.begin());
    result.dimension = signed32(readUnsigned(bytes, 32, 4));
    result.step = static_cast<std::uint32_t>(readUnsigned(bytes, 36, 4));
    result.originX = signed64(readUnsigned(bytes, 40, 8));
    result.originZ = signed64(readUnsigned(bytes, 48, 8));
    result.revision = readUnsigned(bytes, 56, 8);
    result.source = static_cast<Source>(readUnsigned(bytes, 64, 4));
    for (std::size_t n = 0; n < kSamples; ++n) {
        const auto offset = kHeaderBytes + n * kSampleBytes;
        result.samples[n].heightSixteenths = signed32(readUnsigned(bytes, offset, 4));
        result.samples[n].flags = bytes[offset + 4];
        std::copy(bytes + offset + 5, bytes + offset + 8, result.samples[n].color.begin());
    }
    validate(result);
    return result;
}
Tile readTile(const std::filesystem::path& file) {
    require(std::filesystem::file_size(file) == kTileBytes, "Unexpected tile file size");
    std::array<std::uint8_t, kTileBytes> bytes{};
    std::ifstream input(file, std::ios::binary);
    if (!input.read(reinterpret_cast<char*>(bytes.data()), bytes.size()))
        throw std::runtime_error("Cannot read complete tile");
    if (input.peek() != std::char_traits<char>::eof()) invalid("Tile changed length while reading");
    return decode(bytes.data(), bytes.size());
}
void writeTile(const std::filesystem::path& file, const Tile& tile) {
    const auto bytes = encode(tile);
    atomicWrite(file, bytes.data(), bytes.size());
}
bool TileKey::operator==(const TileKey& other) const noexcept {
    return world == other.world && dimension == other.dimension && step == other.step &&
           originX == other.originX && originZ == other.originZ && source == other.source;
}
std::size_t TileKeyHash::operator()(const TileKey& key) const noexcept {
    std::uint64_t hash = 14695981039346656037ULL;
    const auto mix = [&hash](std::uint64_t value, unsigned bytes) {
        for (unsigned n = 0; n < bytes; ++n) {
            hash ^= (value >> (n * 8)) & 255U;
            hash *= 1099511628211ULL;
        }
    };
    for (auto byte : key.world) mix(byte, 1);
    mix(static_cast<std::uint32_t>(key.dimension), 4);
    mix(key.step, 4);
    mix(static_cast<std::uint64_t>(key.originX), 8);
    mix(static_cast<std::uint64_t>(key.originZ), 8);
    mix(static_cast<std::uint32_t>(key.source), 4);
    return static_cast<std::size_t>(hash ^ (hash >> 32));
}
TileKey keyFor(const Tile& tile) noexcept {
    return {tile.world, tile.dimension, tile.step, tile.originX, tile.originZ, tile.source};
}
std::filesystem::path cachePath(const TileKey& key) {
    Tile check;
    check.world = key.world; check.dimension = key.dimension; check.step = key.step;
    check.originX = key.originX; check.originZ = key.originZ; check.source = key.source;
    validate(check);
    return std::filesystem::path(worldIdString(key.world)) / std::to_string(key.dimension) /
        std::to_string(static_cast<std::uint32_t>(key.source)) / std::to_string(key.step) /
        (std::to_string(key.originX) + "_" + std::to_string(key.originZ) + ".bht");
}
TileCache::TileCache(CacheLimits limits) : limits_(limits) {
    require(limits_.maxTiles > 0 && limits_.maxTiles <= 65536, "Invalid tile cache count limit");
    require(limits_.maxBytes >= kEntryBudget && limits_.maxBytes <= 256U * 1024U * 1024U,
            "Invalid tile cache storage budget");
    tiles_.max_load_factor(0.7F);
}
std::uint64_t TileCache::touch() {
    if (clock_ == std::numeric_limits<std::uint64_t>::max()) {
        std::vector<Entry*> entries;
        entries.reserve(tiles_.size());
        for (auto& entry : tiles_) entries.push_back(&entry.second);
        std::sort(entries.begin(), entries.end(), [](auto a, auto b) { return a->used < b->used; });
        clock_ = 0;
        for (auto* entry : entries) entry->used = ++clock_;
    }
    return ++clock_;
}
void TileCache::evict() {
    while (tiles_.size() > limits_.maxTiles || accountedBytes() > limits_.maxBytes) {
        auto oldest = tiles_.end();
        for (auto current = tiles_.begin(); current != tiles_.end(); ++current)
            if (oldest == tiles_.end() || current->second.used < oldest->second.used) oldest = current;
        if (oldest == tiles_.end()) break;
        tiles_.erase(oldest);
    }
}
bool TileCache::put(Tile tile) {
    validate(tile);
    const auto key = keyFor(tile);
    auto found = tiles_.find(key);
    if (found != tiles_.end() && tile.revision < found->second.tile.revision) return false;
    const auto used = touch();
    if (found != tiles_.end()) found->second = Entry{std::move(tile), used};
    else tiles_.emplace(key, Entry{std::move(tile), used});
    evict();
    return true;
}
std::optional<Tile> TileCache::get(const TileKey& key) {
    auto found = tiles_.find(key);
    if (found == tiles_.end()) return std::nullopt;
    found->second.used = touch();
    return found->second.tile;
}
std::optional<Tile> TileCache::composite(TileKey location, bool preferAuthoritative) {
    location.source = Source::Visited;
    auto visited = get(location);
    location.source = Source::Authoritative;
    auto authoritative = get(location);
    if (!visited && !authoritative) return std::nullopt;
    Tile result = visited ? *visited : *authoritative;
    if (visited && authoritative) {
        for (std::size_t n = 0; n < kSamples; ++n) {
            const auto& preferred = preferAuthoritative ? authoritative->samples[n] : visited->samples[n];
            const auto& fallback = preferAuthoritative ? visited->samples[n] : authoritative->samples[n];
            result.samples[n] = preferred.known() ? preferred : fallback;
        }
        result.revision = std::max(visited->revision, authoritative->revision);
    }
    result.source = Source::Composite;
    return result;
}
bool TileCache::erase(const TileKey& key) { return tiles_.erase(key) != 0; }
std::size_t TileCache::size() const noexcept { return tiles_.size(); }
std::size_t TileCache::accountedBytes() const noexcept { return tiles_.size() * kEntryBudget; }

Tile aggregate(const WorldId& world, std::int32_t dimension, std::int64_t parentX,
               std::int64_t parentZ, std::uint32_t parentStep,
               const std::array<const Tile*, 4>& children) {
    require(powerOfTwo(parentStep) && parentStep >= 2 && parentStep <= 16384,
            "Invalid parent LOD step");
    Tile result;
    result.world = world; result.dimension = dimension; result.originX = parentX;
    result.originZ = parentZ; result.step = parentStep; result.source = Source::Composite;
    validate(result);
    const auto childStep = parentStep / 2;
    const auto childSpan = static_cast<std::int64_t>(kCells) * childStep;
    for (std::size_t n = 0; n < children.size(); ++n) {
        if (!children[n]) continue;
        validate(*children[n]);
        require(children[n]->world == world && children[n]->dimension == dimension &&
                children[n]->step == childStep &&
                children[n]->originX == parentX + static_cast<std::int64_t>(n % 2) * childSpan &&
                children[n]->originZ == parentZ + static_cast<std::int64_t>(n / 2) * childSpan,
                "Child does not belong to parent tile");
        result.revision = std::max(result.revision, children[n]->revision);
    }
    const auto lookup = [&children](std::size_t x, std::size_t z) -> const Sample* {
        // Prefer the eastern/southern owner of a shared border, then a known
        // duplicate from the adjacent child. Conflicts keep the greater height.
        const Sample* best = nullptr;
        for (std::size_t n = 0; n < 4; ++n) {
            if (!children[n]) continue;
            const auto offsetX = (n % 2) * kCells, offsetZ = (n / 2) * kCells;
            if (x < offsetX || z < offsetZ || x > offsetX + kCells || z > offsetZ + kCells) continue;
            const auto& candidate = children[n]->at(x - offsetX, z - offsetZ);
            if (candidate.known() && (!best || candidate.heightSixteenths > best->heightSixteenths))
                best = &candidate;
        }
        return best;
    };
    for (std::size_t z = 0; z < kEdge; ++z) for (std::size_t x = 0; x < kEdge; ++x) {
        std::vector<const Sample*> footprint;
        footprint.reserve(4);
        bool complete = true;
        for (std::size_t dz = 0; dz <= (z == kCells ? 0U : 1U); ++dz)
            for (std::size_t dx = 0; dx <= (x == kCells ? 0U : 1U); ++dx) {
                const auto* sample = lookup(x * 2 + dx, z * 2 + dz);
                if (!sample) complete = false;
                else footprint.push_back(sample);
            }
        if (!complete || footprint.empty()) continue;
        const auto tallest = *std::max_element(footprint.begin(), footprint.end(),
            [](auto a, auto b) { return a->heightSixteenths < b->heightSixteenths; });
        auto& sample = result.at(x, z);
        sample.heightSixteenths = tallest->heightSixteenths;
        sample.flags = static_cast<std::uint8_t>(1U | (std::all_of(footprint.begin(), footprint.end(),
            [](auto p) { return p->water(); }) ? 2U : 0U));
        sample.color = averageColor(footprint);
    }
    validate(result);
    return result;
}

Mesh buildMesh(const Tile& tile, MeshOptions options) {
    validate(tile);
    require(std::isfinite(options.skirtDepth) && options.skirtDepth >= 0 &&
            options.skirtDepth <= 65536, "Invalid skirt depth");
    require(options.maxVertices >= 4 && options.maxVertices <= 1048576 &&
            options.maxIndices >= 6 && options.maxIndices <= 6291456, "Invalid mesh allocation limits");
    Mesh mesh;
    mesh.world = tile.world; mesh.dimension = tile.dimension;
    mesh.originX = tile.originX; mesh.originZ = tile.originZ; mesh.step = tile.step;
    constexpr auto absent = std::numeric_limits<std::uint32_t>::max();
    std::array<std::uint32_t, kSamples> vertices;
    vertices.fill(absent);
    std::array<bool, kCells * kCells> cells{};
    const auto addVertex = [&mesh, &options](Vertex vertex) -> std::uint32_t {
        if (mesh.vertices.size() >= options.maxVertices) invalid("Mesh vertex budget exceeded");
        mesh.vertices.push_back(vertex);
        return static_cast<std::uint32_t>(mesh.vertices.size() - 1);
    };
    const auto vertexFor = [&](std::size_t x, std::size_t z) -> std::uint32_t {
        auto& index = vertices[z * kEdge + x];
        if (index == absent) {
            const auto& sample = tile.at(x, z);
            index = addVertex({static_cast<double>(x * tile.step), sample.heightSixteenths / 16.0,
                static_cast<double>(z * tile.step), 0, 0, 0, sample.color});
        }
        return index;
    };
    const auto triangle = [&mesh, &options](std::uint32_t a, std::uint32_t b, std::uint32_t c) {
        if (mesh.indices.size() > options.maxIndices - 3) invalid("Mesh index budget exceeded");
        mesh.indices.insert(mesh.indices.end(), {a, b, c});
        const auto& p = mesh.vertices[a]; const auto& q = mesh.vertices[b]; const auto& r = mesh.vertices[c];
        const auto ux = q.x - p.x, uy = q.y - p.y, uz = q.z - p.z;
        const auto vx = r.x - p.x, vy = r.y - p.y, vz = r.z - p.z;
        const auto nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
        for (auto index : {a, b, c}) {
            mesh.vertices[index].normalX += nx;
            mesh.vertices[index].normalY += ny;
            mesh.vertices[index].normalZ += nz;
        }
    };
    for (std::size_t z = 0; z < kCells; ++z) for (std::size_t x = 0; x < kCells; ++x) {
        if (!tile.at(x, z).known() || !tile.at(x + 1, z).known() ||
            !tile.at(x, z + 1).known() || !tile.at(x + 1, z + 1).known()) continue;
        cells[z * kCells + x] = true;
        const auto nw = vertexFor(x, z), ne = vertexFor(x + 1, z);
        const auto sw = vertexFor(x, z + 1), se = vertexFor(x + 1, z + 1);
        triangle(nw, sw, se); triangle(nw, se, ne);
        mesh.surfaceTriangles += 2;
    }
    const auto hasCell = [&cells](int x, int z) {
        return x >= 0 && z >= 0 && x < kCells && z < kCells &&
               cells[static_cast<std::size_t>(z) * kCells + static_cast<std::size_t>(x)];
    };
    const auto skirt = [&](std::size_t ax, std::size_t az, std::size_t bx, std::size_t bz) {
        const auto topA = mesh.vertices[vertexFor(ax, az)], topB = mesh.vertices[vertexFor(bx, bz)];
        Vertex a = topA, b = topB, c = topA, d = topB;
        a.normalX = a.normalY = a.normalZ = 0;
        b.normalX = b.normalY = b.normalZ = 0;
        c.normalX = c.normalY = c.normalZ = 0;
        d.normalX = d.normalY = d.normalZ = 0;
        c.y -= options.skirtDepth; d.y -= options.skirtDepth;
        const auto ia = addVertex(a), ib = addVertex(b), ic = addVertex(c), id = addVertex(d);
        triangle(ia, ib, id); triangle(ia, id, ic);
        mesh.skirtTriangles += 2;
    };
    if (options.skirts && options.skirtDepth > 0) {
        for (int z = 0; z < kCells; ++z) for (int x = 0; x < kCells; ++x) {
            if (!hasCell(x, z)) continue;
            const auto ux = static_cast<std::size_t>(x), uz = static_cast<std::size_t>(z);
            if (!hasCell(x, z - 1)) skirt(ux, uz, ux + 1, uz);
            if (!hasCell(x + 1, z)) skirt(ux + 1, uz, ux + 1, uz + 1);
            if (!hasCell(x, z + 1)) skirt(ux + 1, uz + 1, ux, uz + 1);
            if (!hasCell(x - 1, z)) skirt(ux, uz + 1, ux, uz);
        }
    }
    for (auto& vertex : mesh.vertices) {
        const auto length = std::sqrt(vertex.normalX * vertex.normalX + vertex.normalY * vertex.normalY +
                                      vertex.normalZ * vertex.normalZ);
        if (length > 0 && std::isfinite(length)) {
            vertex.normalX /= length; vertex.normalY /= length; vertex.normalZ /= length;
        } else { vertex.normalX = vertex.normalZ = 0; vertex.normalY = 1; }
    }
    return mesh;
}
void writeObj(const std::filesystem::path& file, const Mesh& mesh) {
    require(mesh.vertices.size() <= 1048576 && mesh.indices.size() <= 6291456 &&
            mesh.indices.size() % 3 == 0, "Invalid mesh export size");
    std::ostringstream output;
    output << "# Bedrock Horizons terrain mesh; local X/Z origin " << mesh.originX << ' ' << mesh.originZ
           << "\n# world " << worldIdString(mesh.world) << " dimension " << mesh.dimension
           << " step " << mesh.step << "\n" << std::setprecision(12);
    for (const auto& v : mesh.vertices) {
        require(std::isfinite(v.x) && std::isfinite(v.y) && std::isfinite(v.z) &&
                std::isfinite(v.normalX) && std::isfinite(v.normalY) && std::isfinite(v.normalZ),
                "Non-finite mesh vertex");
        output << "v " << v.x << ' ' << v.y << ' ' << v.z;
        for (auto channel : v.color) output << ' ' << static_cast<double>(channel) / 255.0;
        output << '\n';
    }
    for (const auto& v : mesh.vertices)
        output << "vn " << v.normalX << ' ' << v.normalY << ' ' << v.normalZ << '\n';
    for (std::size_t n = 0; n < mesh.indices.size(); n += 3) {
        output << 'f';
        for (std::size_t j = 0; j < 3; ++j) {
            require(mesh.indices[n + j] < mesh.vertices.size(), "Mesh index outside vertex array");
            const auto index = mesh.indices[n + j] + 1;
            output << ' ' << index << "//" << index;
        }
        output << '\n';
    }
    const auto text = output.str();
    require(text.size() <= 256U * 1024U * 1024U, "Mesh export too large");
    atomicWrite(file, reinterpret_cast<const std::uint8_t*>(text.data()), text.size());
}

} // namespace bedrock_horizons
