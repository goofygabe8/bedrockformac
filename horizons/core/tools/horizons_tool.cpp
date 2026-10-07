#include "horizons.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>

using namespace bedrock_horizons;

namespace {
std::int64_t integer(const std::string& text) {
    std::size_t used = 0;
    const auto result = std::stoll(text, &used, 10);
    if (used != text.size()) throw std::invalid_argument("Invalid integer: " + text);
    return result;
}
std::uint64_t revision(const std::string& text) {
    if (text.empty() || text[0] == '-') throw std::invalid_argument("Invalid revision");
    std::size_t used = 0;
    const auto result = std::stoull(text, &used, 10);
    if (used != text.size()) throw std::invalid_argument("Invalid revision");
    return result;
}
double number(const std::string& text) {
    std::size_t used = 0;
    const auto result = std::stod(text, &used);
    if (used != text.size() || !std::isfinite(result)) throw std::invalid_argument("Invalid number");
    return result;
}
template <class T> T boundedInteger(const std::string& text, std::int64_t minimum, std::int64_t maximum) {
    const auto value = integer(text);
    if (value < minimum || value > maximum) throw std::invalid_argument("Integer outside range");
    return static_cast<T>(value);
}
Source source(const std::string& text) {
    if (text == "visited") return Source::Visited;
    if (text == "authoritative") return Source::Authoritative;
    throw std::invalid_argument("Import source must be visited or authoritative");
}
std::array<std::string, 7> csvFields(const std::string& line) {
    std::array<std::string, 7> result;
    std::stringstream input(line);
    for (auto& field : result)
        if (!std::getline(input, field, ',')) throw std::invalid_argument("CSV needs seven fields");
    std::string extra;
    if (std::getline(input, extra, ',') || (!line.empty() && line.back() == ','))
        throw std::invalid_argument("Too many CSV fields");
    return result;
}
void usage() {
    std::cerr <<
        "Bedrock Horizons terrain core (no Minecraft hooks)\n"
        "  horizons-tool info TILE.bht\n"
        "  horizons-tool mesh TILE.bht OUTPUT.obj [SKIRT_DEPTH]\n"
        "  horizons-tool import-csv INPUT.csv OUTPUT.bht WORLD_UUID DIMENSION ORIGIN_X ORIGIN_Z STEP REVISION SOURCE\n"
        "  horizons-tool aggregate NW.bht NE.bht SW.bht SE.bht OUTPUT.bht\n"
        "SOURCE: visited | authoritative. CSV: x,z,height,r,g,b,water; omit unknown samples.\n"
        "CSV indices range 0..16. Height is the surface top in blocks; water is 0 or 1.\n";
}
void importCsv(int argc, char** argv) {
    if (argc != 11) throw std::invalid_argument("Wrong import-csv argument count");
    Tile tile;
    tile.world = parseWorldId(argv[4]);
    tile.dimension = boundedInteger<std::int32_t>(argv[5], std::numeric_limits<std::int32_t>::min(),
                                                 std::numeric_limits<std::int32_t>::max());
    tile.originX = integer(argv[6]); tile.originZ = integer(argv[7]);
    tile.step = boundedInteger<std::uint32_t>(argv[8], 1, 16384);
    tile.revision = revision(argv[9]); tile.source = source(argv[10]);
    validate(tile);
    if (std::filesystem::file_size(argv[2]) > 65536) throw std::invalid_argument("CSV exceeds 64 KiB");
    std::ifstream input(argv[2]);
    if (!input) throw std::runtime_error("Cannot open CSV");
    std::array<bool, kSamples> seen{};
    std::string line;
    std::size_t lineNumber = 0;
    while (std::getline(input, line)) {
        if (++lineNumber > 1024 || line.size() > 256) throw std::invalid_argument("CSV exceeds line limits");
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty() || line[0] == '#') continue;
        const auto fields = csvFields(line);
        const auto x = boundedInteger<std::size_t>(fields[0], 0, kCells);
        const auto z = boundedInteger<std::size_t>(fields[1], 0, kCells);
        if (seen[z * kEdge + x]) throw std::invalid_argument("Duplicate CSV sample");
        seen[z * kEdge + x] = true;
        const std::array<std::uint8_t, 3> color{
            boundedInteger<std::uint8_t>(fields[3], 0, 255),
            boundedInteger<std::uint8_t>(fields[4], 0, 255),
            boundedInteger<std::uint8_t>(fields[5], 0, 255)};
        tile.at(x, z) = Sample::observed(number(fields[2]), color,
                                       boundedInteger<unsigned>(fields[6], 0, 1) != 0);
    }
    if (input.bad()) throw std::runtime_error("Cannot read CSV");
    writeTile(argv[3], tile);
    std::cout << "Imported " << tile.knownCount() << "/" << kSamples << " observed samples\n";
}
} // namespace

int main(int argc, char** argv) {
    try {
        if (argc < 2) { usage(); return 2; }
        const std::string command = argv[1];
        if (command == "info" && argc == 3) {
            const auto tile = readTile(argv[2]);
            std::cout << "world " << worldIdString(tile.world) << "\ndimension " << tile.dimension
                      << "\norigin " << tile.originX << ' ' << tile.originZ << "\nstep " << tile.step
                      << "\nrevision " << tile.revision << "\nsource " << static_cast<unsigned>(tile.source)
                      << "\nknown " << tile.knownCount() << '/' << kSamples << "\n";
        } else if (command == "mesh" && (argc == 4 || argc == 5)) {
            MeshOptions options;
            if (argc == 5) options.skirtDepth = number(argv[4]);
            const auto mesh = buildMesh(readTile(argv[2]), options);
            writeObj(argv[3], mesh);
            std::cout << "Exported " << mesh.surfaceTriangles << " surface triangles and "
                      << mesh.skirtTriangles << " seam triangles\n";
        } else if (command == "import-csv" && argc == 11) {
            // 10 arguments plus the executable. The function parses exactly
            // this layout; there is no implicit default world or dimension.
            importCsv(argc, argv);
        } else if (command == "aggregate" && argc == 7) {
            std::array<Tile, 4> tiles{readTile(argv[2]), readTile(argv[3]), readTile(argv[4]), readTile(argv[5])};
            const auto& first = tiles[0];
            const auto result = aggregate(first.world, first.dimension, first.originX, first.originZ,
                first.step * 2, {&tiles[0], &tiles[1], &tiles[2], &tiles[3]});
            writeTile(argv[6], result);
            std::cout << "Aggregated " << result.knownCount() << '/' << kSamples << " samples\n";
        } else { usage(); return 2; }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "horizons-tool: " << error.what() << '\n';
        return 1;
    }
}
