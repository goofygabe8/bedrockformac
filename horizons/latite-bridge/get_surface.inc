// Bedrock Horizons fork addition. GPL-3.0, following Latite's license.
// A returned air/block is not proof that all server subchunks have arrived.
// This API intentionally reports observations with known=false.
JsValueRef GameScriptingObject::dimensionGetSurface(JsValueRef callee, bool isConstructor, JsValueRef* arguments,
                                                    unsigned short argCount, void* callbackState) {
    if (!Chakra::VerifyArgCount(argCount, 3)) return JS_INVALID_REFERENCE;
    if (!Chakra::VerifyParameters({{arguments[1], JsNumber}, {arguments[2], JsNumber}}))
        return JS_INVALID_REFERENCE;

    JsValueRef result;
    JS::JsCreateObject(&result);
    Chakra::SetPropertyBool(result, L"known", false);
    Chakra::SetPropertyString(result, L"readiness", L"unverified");
    Chakra::SetPropertyString(result, L"reason", L"chunk-completeness-unverified");
    Chakra::SetProperty(result, L"observed", Chakra::GetNull());
    auto unavailable = [&](const wchar_t* reason) {
        Chakra::SetPropertyString(result, L"reason", reason);
        return result;
    };

    const double requestedX = Chakra::GetNumber(arguments[1]);
    const double requestedZ = Chakra::GetNumber(arguments[2]);
    if (!std::isfinite(requestedX) || !std::isfinite(requestedZ) ||
        std::floor(requestedX) != requestedX || std::floor(requestedZ) != requestedZ ||
        std::abs(requestedX) > 30000000.0 || std::abs(requestedZ) > 30000000.0)
        return unavailable(L"invalid-coordinates");

    auto* client = SDK::ClientInstance::get();
    if (!client) return unavailable(L"client-unavailable");
    auto* player = client->getLocalPlayer();
    auto* source = client->getRegion();
    if (!player || !player->dimension || !source) return unavailable(L"world-unavailable");

    const auto& position = player->getPos();
    if (!std::isfinite(position.x) || !std::isfinite(position.z) ||
        std::abs(requestedX - position.x) > 128.0 || std::abs(requestedZ - position.z) > 128.0)
        return unavailable(L"outside-observation-radius");

    const auto& dimensionName = player->dimension->dimensionName;
    int minY = 0, maxY = 0;
    if (dimensionName == "Overworld" || dimensionName == "overworld" || dimensionName == "minecraft:overworld") {
        minY = -64; maxY = 319;
    } else if (dimensionName == "Nether" || dimensionName == "nether" || dimensionName == "minecraft:nether") {
        minY = 0; maxY = 127;
    } else if (dimensionName == "The End" || dimensionName == "the_end" || dimensionName == "minecraft:the_end") {
        minY = 0; maxY = 255;
    } else {
        return unavailable(L"unsupported-dimension");
    }

    // Bound synchronous work on the game thread. This is a developer prototype.
    static auto budgetStart = std::chrono::steady_clock::now();
    static unsigned scansInBudget = 0;
    const auto now = std::chrono::steady_clock::now();
    if (now - budgetStart >= std::chrono::milliseconds(50)) {
        budgetStart = now;
        scansInBudget = 0;
    }
    if (scansInBudget >= 4) return unavailable(L"observation-budget-exhausted");
    ++scansInBudget;

    const int x = static_cast<int>(requestedX), z = static_cast<int>(requestedZ);
    // This is only a missing-chunk guard. It is NOT a completeness guarantee.
    if (!source->getChunkAt(BlockPos{x, 64, z})) return unavailable(L"chunk-unavailable");
    for (int y = maxY; y >= minY; --y) {
        const BlockPos blockPosition{x, y, z};
        if (!source->hasBlock(blockPosition)) return unavailable(L"block-unavailable");
        auto* block = source->getBlock(x, y, z);
        if (!block || !block->legacyBlock) return unavailable(L"block-unavailable");
        const std::string name = block->legacyBlock->namespacedId.getString();
        if (name.empty()) return unavailable(L"block-name-unavailable");
        if (name == "minecraft:air" || name == "minecraft:cave_air" || name == "minecraft:void_air") continue;

        const bool water = name == "minecraft:water" || name == "minecraft:flowing_water";
        std::array<int, 3> rgb{128, 128, 128};
        if (water) rgb = {45, 86, 172};
        else if (name.find("leaves") != std::string::npos) rgb = {62, 112, 45};
        else if (name == "minecraft:grass_block" || name == "minecraft:grass") rgb = {107, 145, 62};
        else if (name.find("snow") != std::string::npos || name == "minecraft:quartz_block") rgb = {234, 241, 241};
        else if (name == "minecraft:sand" || name.find("sandstone") != std::string::npos) rgb = {216, 206, 149};
        else if (name.find("deepslate") != std::string::npos) rgb = {75, 75, 79};
        else if (name == "minecraft:netherrack") rgb = {111, 57, 54};
        else if (name == "minecraft:end_stone") rgb = {217, 217, 153};
        else if (name == "minecraft:dirt" || name.find("mud") != std::string::npos) rgb = {127, 91, 65};

        JsValueRef observed, color;
        JS::JsCreateObject(&observed);
        JS::JsCreateArray(3, &color);
        for (unsigned i = 0; i < 3; ++i)
            JS::JsSetIndexedProperty(color, Chakra::MakeInt(i), Chakra::MakeInt(rgb[i]));
        Chakra::SetPropertyNumber(observed, L"height", y + 1);
        Chakra::SetPropertyString(observed, L"block", util::StrToWStr(name));
        Chakra::SetPropertyBool(observed, L"water", water);
        Chakra::SetProperty(observed, L"color", color);
        Chakra::SetPropertyBool(observed, L"colorEstimated", true);
        Chakra::SetPropertyNumber(observed, L"minY", minY);
        Chakra::SetPropertyNumber(observed, L"maxY", maxY);
        Chakra::SetProperty(result, L"observed", observed);
        return result;
    }
    // Do not cache all-air columns as confirmed void terrain.
    return unavailable(L"no-observed-surface");
}

