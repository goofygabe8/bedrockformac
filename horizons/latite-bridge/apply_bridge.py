#!/usr/bin/env python3
"""Apply the narrow read-only Bedrock Horizons source bridge to pinned Latite."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
TARGETS = (
    "src/client/script/globals/GameScriptingObject.cpp",
    "src/client/script/globals/GameScriptingObject.h",
    "src/client/script/libraries/Filesystem.cpp",
)

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
        if relative.endswith("Filesystem.cpp"):
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
    # Both files were fully checked before the first source write.
    for relative, data in replacements.items():
        (source / relative).write_bytes(data)
    print("Applied the observation-only bridge. known remains false; no readiness offsets were invented.")

if __name__ == "__main__":
    main()
