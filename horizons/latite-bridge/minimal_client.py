"""Build a terrain scripting bridge without Latite's input or desktop overlay.

Called only after apply_bridge.py validates every pinned upstream file hash.
These choices belong to this experimental DLL, not to the generic launcher.
"""
import re

HOOKS = "src/client/memory/hook/hooks/"
EMPTY_CONSTRUCTORS = {
    HOOKS + "DXHooks.cpp": 'DXHooks::DXHooks()\n    : HookGroup("DirectX")',
    HOOKS + "OptionHooks.cpp": "OptionHooks::OptionHooks()",
    HOOKS + "PlayerHooks.cpp": "PlayerHooks::PlayerHooks()",
    HOOKS + "RenderControllerHooks.cpp": "RenderControllerHooks::RenderControllerHooks()",
    HOOKS + "CustomSkinPickerHooks.cpp": 'CustomSkinPickerHooks::CustomSkinPickerHooks()\n    : HookGroup("Windows 10 custom-skin picker workaround")',
    HOOKS + "ScreenViewHooks.cpp": 'ScreenViewHooks::ScreenViewHooks()\n    : HookGroup("ScreenView")',
    "src/client/feature/module/ModuleManager.cpp": "ModuleManager::ModuleManager()",
    "src/client/screen/ScreenManager.cpp": "ScreenManager::ScreenManager()",
}
TARGETS = tuple(EMPTY_CONSTRUCTORS) + (
    HOOKS + "GeneralHooks.cpp",
    HOOKS + "MinecraftGameHooks.cpp",
    "src/client/Latite.cpp",
    "src/client/script/JsScript.cpp",
    "src/client/script/class/classes/JsWebSocket.h",
    "src/client/script/globals/Graphics3DScriptingObject.cpp",
)


def body(text, signature, replacement):
    if text.count(signature) != 1:
        raise SystemExit("Unexpected minimal bridge function: " + signature)
    start = text.index("{", text.index(signature) + len(signature))
    depth = 0
    # Ignore strings and comments when identifying the end of a C++ body.
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/|[{}]'
    for token in re.finditer(tokens, text[start:]):
        value = token.group()
        if value == "{":
            depth += 1
        elif value == "}":
            depth -= 1
            if depth == 0:
                end = start + token.end()
                return text[:start] + "{\n" + replacement + "\n}" + text[end:]
    raise SystemExit("Unclosed minimal bridge function: " + signature)


def apply(relative, text):
    if relative in EMPTY_CONSTRUCTORS:
        return body(text, EMPTY_CONSTRUCTORS[relative],
                    "    // Terrain-only bridge: leave Minecraft input, UI and presentation untouched.")
    if relative == HOOKS + "GeneralHooks.cpp":
        return body(text, 'GenericHooks::GenericHooks()\n    : HookGroup("General")', '''    // Only terrain lifecycle and explicit local chat commands are observed.
    // Do not hook the window procedure, mouse capture, raw input, player input,
    // camera movement, fog, inventory rendering, or release/grab cursor paths.
    MultiPlayerLevel__subTickHook =
        addHook(Signatures::MultiPlayerLevel__subTick.result, MultiPlayerLevel__subTick, "Level::tick");
    ChatScreenController_sendChatMesageHook =
        addHook(Signatures::ChatScreenController_sendChatMessage.result, ChatScreenController_sendChatMessage,
                "ChatScreenController::sendChatMessage");
    if (Signatures::Vtable::Level.result) {
        Level_initializeHook = addHook(reinterpret_cast<uintptr_t*>(Signatures::Vtable::Level.result)[1],
                                       Level_initialize, "Level::initialize");
        Level_startLeaveGameHook = addHook(reinterpret_cast<uintptr_t*>(Signatures::Vtable::Level.result)[2],
                                          Level_startLeaveGame, "Level::startLeaveGame");
    }''')
    if relative == HOOKS + "MinecraftGameHooks.cpp":
        return body(text, "MinecraftGameHooks::MinecraftGameHooks()", '''    // Run scripting tasks after Minecraft's update; preserve device/focus handling.
    _updateHook = addHook(Signatures::MinecraftGame__update.result, _update, "MinecraftGame::_update");''')
    if relative == "src/client/Latite.cpp":
        text = body(text, "void Latite::initialize(HINSTANCE hInst)", '''    this->dllInst = hInst;
    Latite::getPluginManager().init();
    Latite::getEventing().listen<UpdateEvent, &Latite::onUpdate>(this, 2);
    Logger::Info("Terrain bridge: Minecraft owns mouse, keyboard, controller and presentation.");
    getHooks().enable();
    Logger::Info("Enabled terrain scripting hooks; desktop overlay disabled.");''')
        text = body(text, "void Latite::threadsafeInit()", '''    this->gameThreadId = std::this_thread::get_id();
    Latite::getCommandManager().prefix = Latite::get().getCommandPrefix();
    Latite::getPluginManager().loadPrerunScripts();
    Logger::Info("Loaded terrain startup scripts; no D3D11On12 renderer requested.");''')
        return body(text, "void Latite::onUpdate(Event& evGeneric)", '''    if (this->shouldEject.load(std::memory_order_acquire)) {
        if (!this->mainThreadEjectCleanupComplete.load(std::memory_order_acquire)) {
            Latite::getPluginManager().unloadAll();
            this->mainThreadEjectCleanupComplete.store(true, std::memory_order_release);
        }
        this->completeEjectFromRenderThread();
        return;
    }
    while (!this->clientThreadQueue.empty()) {
        auto task = std::move(this->clientThreadQueue.front());
        this->clientThreadQueue.pop();
        task();
    }
    if (!hasInit) {
        threadsafeInit();
        hasInit = true;
    }
    Latite::getPluginManager().runScriptingOperations();''')
    if relative == "src/client/script/JsScript.cpp":
        anchor = "    this->objects.push_back(std::make_shared<D2DScriptingObject>(i++));"
        if text.count(anchor) != 1: raise SystemExit("Unexpected D2D binding")
        return text.replace(anchor, "    // This bridge uses in-game graphics3D only; no Direct2D overlay binding.")
    if relative == "src/client/script/class/classes/JsWebSocket.h":
        anchor = "    winrt::Windows::Networking::Sockets::MessageWebSocket webSocket;"
        if text.count(anchor) != 1: raise SystemExit("Unexpected WebSocket binding")
        return text.replace(anchor, "    // No unused eager WinRT socket activation when registering JS classes.")
    if relative == "src/client/script/globals/Graphics3DScriptingObject.cpp":
        anchor = "    *screenContext->shaderColor = { 1.f, 1.f, 1.f, 1.f };"
        if text.count(anchor) != 1: raise SystemExit("Unexpected terrain shader state")
        text = text.replace(anchor, '''    if (commands.empty()) return;
    if (!screenContext || !screenContext->shaderColor || !screenContext->tess || !levelRenderer ||
        !levelRenderer->getLevelRendererPlayer()) {
        commands.clear();
        return;
    }
    // Always restore the game's shader color, including when drawing throws.
    struct RestoreColor {
        Color* target;
        Color original;
        ~RestoreColor() { *target = original; }
    } restore { screenContext->shaderColor, *screenContext->shaderColor };
    *screenContext->shaderColor = { 1.f, 1.f, 1.f, 1.f };''')
        return text
    raise SystemExit("Unsupported minimal bridge target: " + relative)
