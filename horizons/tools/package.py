"""Build the experimental Mac client bundle and optional world behavior pack."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else ROOT / "build/packages"
OUTPUT.mkdir(parents=True, exist_ok=True)
def archive_tree(source, target, prefix=""):
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file(): archive.write(path, prefix + path.relative_to(source).as_posix())

pack = OUTPUT / "Bedrock-Horizons-World-Companion.mcpack"
archive_tree(ROOT / "companion", pack)
with tempfile.TemporaryDirectory(prefix="bhl-package-", dir=ROOT / "build") as temporary:
    staging = Path(temporary) / "Bedrock Horizons Experimental"
    staging.mkdir()
    for directory in ("client", "companion", "core", "latite-bridge", "tools"):
        shutil.copytree(ROOT / directory, staging / directory,
                        ignore=shutil.ignore_patterns("horizons-tool", "__pycache__", "*.pyc", "build"))
    for name in ("README.md", "LICENSE", "Install Experimental Horizons.command", "Load Experimental Horizons.command"):
        shutil.copy2(ROOT / name, staging / name)
    shutil.copy2(pack, staging / pack.name)
    native = ROOT / "native-artifacts"
    if (native / "native-build.json").is_file():
        shutil.copytree(native, staging / "native")
        resources = ROOT / "native-resources"
        for path in resources.iterdir():
            if path.is_file(): shutil.copy2(path, staging / "native" / path.name)
        metadata = json.loads((staging / "native/native-build.json").read_text())
        if hashlib.sha256((staging / "native/Latite.dll").read_bytes()).hexdigest() != metadata["dll_sha256"]:
            raise SystemExit("Native artifact checksum differs")
        metadata["chakra_sha256"] = hashlib.sha256((staging / "native/ChakraCore.dll").read_bytes()).hexdigest()
        (staging / "native/native-build.json").write_text(json.dumps(metadata, indent=2) + "\n")
    archive_tree(staging, OUTPUT / "Bedrock-Horizons-Experimental.zip", staging.name + "/")
    shutil.copy2(ROOT / "README.md", OUTPUT / "Bedrock-Horizons-README.md")

records = {}
for name in ("Bedrock-Horizons-Experimental.zip", "Bedrock-Horizons-World-Companion.mcpack", "Bedrock-Horizons-README.md"):
    path = OUTPUT / name
    records[name] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
(OUTPUT / "Bedrock-Horizons-checksums.json").write_text(json.dumps(records, indent=2) + "\n")
print(json.dumps(records, indent=2))
