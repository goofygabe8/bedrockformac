# Portable terrain core

This library has no dependency on Minecraft, Wine, graphics APIs or an account.
Build the CMake project or compile `src/horizons.cpp` and `tools/horizons_tool.cpp`
with C++17 and `include/` on the include path.

`horizons-tool` can inspect tiles, export an OBJ mesh, import explicitly known
CSV samples and aggregate four child tiles. Run it without arguments to see
the syntax. Unknown samples stay zero/unknown. Aggregation requires every
sample in the bounded footprint before producing a known parent sample.

Tiles use `BHTILE01`: an 80-byte little-endian header and 17x17 eight-byte
surface vertices, totaling 2392 bytes. See `include/horizons.hpp` for the
contract and cache/mesh limits. Heights are top faces in 1/16 blocks; RGB is
the producer's palette. The final row and column cover shared edges.

The CLI does not gather terrain from Minecraft or render into the game.
The native bridge, client plugin and companion are separate consumers.
