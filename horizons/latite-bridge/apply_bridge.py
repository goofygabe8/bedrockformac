#!/usr/bin/env python3
"""Apply the narrow read-only Bedrock Horizons source bridge to pinned Latite."""
import hashlib
import json
from pathlib import Path
import sys
import minimal_client

HERE = Path(__file__).resolve().parent
TARGETS = (
    "src/client/script/globals/GameScriptingObject.cpp",
    "src/client/script/globals/GameScriptingObject.h",
    "src/client/script/libraries/Filesystem.cpp",
    "src/client/script/JsPlugin.cpp",
    "src/client/script/PluginManager.cpp",
) + minimal_client.TARGETS

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python apply_bridge.py PATH_TO_PINNED_LATITE_SOURCE")
    source = Path(sys.argv[1]).resolve()
    lock = json.loads((HERE / "bridge-lock.json").read_text())
    originals = {}
    for relative in TARGETS:
        target = source / relative
        data = target.read_bytes()
        if hashlib.sha256(data).hexdigest() != lock["patch_source_sha256"][relative]:
            raise SystemExit("Refusing modified or unsupported source: " + relative)
        originals[relative] = data
    additions = (HERE / "get_surface.inc").read_text()
    replacements = {}
    for relative, data in originals.items():
        newline = "\r\n" if b"\r\n" in data else "\n"
        text = data.decode("utf-8").replace("\r\n", "\n")
        if relative in minimal_client.TARGETS:
            text = minimal_client.apply(relative, text)
        elif relative.endswith("JsPlugin.cpp"):
            start = text.index('    // Check plugin permissions\n    checkTrusted();')
            text = text[:start] + text[start:].replace('    // Check plugin permissions\n    checkTrusted();', '''    // Online trust is optional. An unavailable WinRT HTTP/crypto service must
    // retain normal untrusted permissions instead of terminating the host game.
    try {
        checkTrusted();
    } catch (winrt::hresult_error const& error) {
        trusted = false;
        Logger::Warn("Plugin trust service unavailable (HRESULT 0x{:08X}); retaining untrusted permissions.",
                     static_cast<uint32_t>(error.code().value));
    } catch (std::exception const&) {
        trusted = false;
        Logger::Warn("Plugin trust service failed; retaining untrusted permissions.");
    }''', 1)
            text = text.replace('    auto myScript = std::make_shared<JsPlugin>(scriptPath);', '    auto myScript = std::make_shared<JsPlugin>(scriptPath);')
            text = text.replace('    if (JS::JsCreateRuntime(', '    Logger::Info("Creating runtime for plugin {}", util::WStrToStr(getFolderName()));\n    if (JS::JsCreateRuntime(', 1)
            text = text.replace('    this->mainScript = loadAndRunScript(', '    Logger::Info("Running main script for plugin {}", util::WStrToStr(getFolderName()));\n    this->mainScript = loadAndRunScript(', 1)
        elif relative.endswith("PluginManager.cpp"):
            anchor = '            bool res = loadPlugin(dirEntry.path().filename().wstring(), true) == nullptr;'
            if text.count(anchor) != 1: raise SystemExit("Unexpected plugin startup anchor")
            text = text.replace(anchor, '''            bool res = true;
            Logger::Info("Loading startup plugin {}", dirEntry.path().filename().string());
            try {
                res = loadPlugin(dirEntry.path().filename().wstring(), true) == nullptr;
            } catch (winrt::hresult_error const& error) {
                Logger::Warn("Skipping startup plugin {}: unavailable WinRT service (HRESULT 0x{:08X}).",
                             dirEntry.path().filename().string(), static_cast<uint32_t>(error.code().value));
            } catch (std::exception const& error) {
                Logger::Warn("Skipping startup plugin {} after C++ startup error: {}",
                             dirEntry.path().filename().string(), error.what());
            }''')
        elif relative.endswith("Filesystem.cpp"):
            start = text.index('std::wstring Filesystem::getPath(')
            end = text.index('\nnamespace {', start)
            text = text[:start] + '// Bedrock Horizons fork: plugin caches must not resolve into the game CWD.\nstd::wstring Filesystem::getPath(std::wstring relPath) {\n    const fs::path requested(relPath);\n    return requested.is_absolute() ? requested.wstring()\n                                   : (owner->getFolderPath() / requested).wstring();\n}\n' + text[end:]
        elif relative.endswith(".cpp"):
            include_anchor = '#include "GameScriptingObject.h"\n'
            bind_anchor = '    Chakra::DefineFunc(dimensionObj, dimensionGetBlock, L"getBlock", this);\n'
            function_anchor = 'JsValueRef GameScriptingObject::dimensionGetBlock('
            for anchor in (include_anchor, bind_anchor, function_anchor):
                if text.count(anchor) != 1: raise SystemExit("Unexpected source anchor: " + relative)
            text = text.replace(include_anchor, include_anchor + '#include <cmath>\n')
            text = text.replace(bind_anchor, bind_anchor + '    Chakra::DefineFunc(dimensionObj, dimensionGetSurface, L"getSurface", this);\n')
            text = text.replace(function_anchor, additions + function_anchor)
        else:
            anchor = '    static JsValueRef CALLBACK dimensionGetBlock('
            if text.count(anchor) != 1: raise SystemExit("Unexpected header anchor")
            declaration = '    static JsValueRef CALLBACK dimensionGetSurface(JsValueRef callee, bool isConstructor, JsValueRef* arguments,\n' \
                          '                                                   unsigned short argCount, void* callbackState);\n'
            text = text.replace(anchor, declaration + anchor)
        replacements[relative] = text.replace("\n", newline).encode("utf-8")
    # Every target and replacement is checked before the first source write.
    for relative, data in replacements.items():
        (source / relative).write_bytes(data)
    print("Applied the minimal terrain bridge. Local terrain scanning is disabled; no game offsets were invented.")

if __name__ == "__main__":
    main()
