"""Package only launcher code for upload as a public GitHub Release asset."""
import base64
import io
import difflib
import hashlib
import json
import re
import sys
import subprocess
import zipfile
from pathlib import Path
from update_client import ALLOWED, REQUIRED, GUI_FILES

ROOT = Path(__file__).resolve().parent

def main():
    value = sys.argv[1] if len(sys.argv) > 1 else input('New launcher release version (for example 0.2.1): ').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise SystemExit('Use three numbers, for example 0.2.1.')
    missing = [name for name in REQUIRED if name not in {'.launcher-version', 'launcher-edits.json'} and not (ROOT / name).is_file()]
    if missing:
        raise SystemExit('Missing launcher files: ' + ', '.join(missing))
    files = {name: (ROOT / name).read_bytes() for name in sorted(ALLOWED) if name not in {'.launcher-version', 'launcher-edits.json'} and (ROOT / name).is_file()}
    source = ROOT/'launcher_gui.swift'
    binary = ROOT/'launcher_gui'
    if source.is_file():
        original = source.read_text()
        updated, count = re.subn(r'^let launcherVersion = "\d+\.\d+\.\d+"$',
                                'let launcherVersion = "' + value + '"', original, flags=re.MULTILINE)
        if count != 1:
            raise SystemExit('The launcher source is missing its embedded version. Update the launcher sources before building.')
        if updated != original:
            source.write_text(updated)
    if source.is_file() and (not binary.is_file() or source.stat().st_mtime > binary.stat().st_mtime):
        print('Compiling the native launcher window…')
        subprocess.run(['/usr/bin/swiftc', '-swift-version', '5', '-O', '-target', 'arm64-apple-macos11.0', str(source), '-o', str(binary)], check=True)
    gui = io.BytesIO()
    with zipfile.ZipFile(gui, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(GUI_FILES):
            source = ROOT/name
            if not source.is_file(): raise SystemExit('Missing GUI asset: ' + name)
            archive.writestr(name, source.read_bytes())
    updater = files['update_client.py'].decode()
    encoded = base64.b64encode(gui.getvalue()).decode()
    updater = re.sub(r'^GUI_PAYLOAD_B64 = ".*"$', 'GUI_PAYLOAD_B64 = "' + encoded + '"', updater, flags=re.MULTILINE)
    files['update_client.py'] = updater.encode()
    base = (ROOT / '.launcher-base-cli.py').read_text()
    current = (ROOT / 'cli.py').read_text()
    edits = [[a, b, current[c:d]] for opcode, a, b, c, d in difflib.SequenceMatcher(None, base, current, autojunk=False).get_opcodes() if opcode != 'equal']
    patch = {'base_sha256': hashlib.sha256(base.encode()).hexdigest(),
             'result_sha256': hashlib.sha256(current.encode()).hexdigest(), 'edits': edits}
    files['launcher-edits.json'] = json.dumps(patch).encode()
    files['.launcher-version'] = (value + '\n').encode()
    manifest = {'version': value, 'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    output = ROOT / 'Launcher Releases' / ('v' + value)
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'bedrock-mac-update.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o100755 if name.endswith('.command') or name == 'controller_devices' else 0o100644) << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr('update-manifest.json', json.dumps(manifest, indent=2))
    (ROOT / '.launcher-version').write_text(value + '\n')
    print('Update ready: ' + str(target))
    print('Upload it to your public GitHub repository as the asset for release v' + value + '.')
    print('Other Macs will install it the next time they open the launcher.')

if __name__ == '__main__':
    main()
