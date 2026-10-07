"""Package an MSVC build and its corresponding fork source; no gameplay execution."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import zipfile

source, build, output = map(Path, sys.argv[1:4])
output.mkdir(parents=True, exist_ok=True)
dll = build / "Latite.dll"
if not dll.is_file():
    raise SystemExit("Expected Release native DLL is missing")
shutil.copy2(dll, output / "Latite.dll")
shutil.copy2(source / "LICENSE", output / "Latite-GPL-3.0.txt")
with zipfile.ZipFile(output / "Latite-Horizons-Corresponding-Source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source.rglob("*")):
        if path.is_file() and ".git" not in path.relative_to(source).parts:
            archive.write(path, "Latite-Horizons/" + path.relative_to(source).as_posix())
    # Dependency source fetched by the pinned CMake project, including its licenses.
    deps = build / "_deps"
    if deps.is_dir():
        for root in sorted(deps.glob("*-src")):
            for path in sorted(root.rglob("*")):
                if path.is_file() and ".git" not in path.relative_to(root).parts:
                    archive.write(path, "Latite-Horizons/dependency-source/" + root.name + "/" + path.relative_to(root).as_posix())
    tools = Path(__file__).resolve().parent
    for path in sorted((tools.parent / "latite-bridge").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            archive.write(path, "fork-patch/" + path.relative_to(tools.parent / "latite-bridge").as_posix())
    archive.write(tools / "build-native.yml", "build-native.yml")
metadata = {
    "schema": 1,
    "status": "compiled-experimental; not gameplay-validated",
    "upstream_commit": "9f7463515dd298a496da918285936d78c7416aad",
    "game_sha256": "4a92bfa3ce2428b40ee517b7c1125d9f6f79274382de03846351992663b2e2e4",
    "dll_sha256": hashlib.sha256(dll.read_bytes()).hexdigest(),
    "license": "GPL-3.0",
    "known_client_columns": False,
}
(output / "native-build.json").write_text(json.dumps(metadata, indent=2) + "\n")
