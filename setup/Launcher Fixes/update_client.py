"""Check a public GitHub release channel before launching Minecraft."""
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALLOWED = {
    'launcher-edits.json', 'runtime_setup.py', 'update_client.py', 'build_update.py',
    'controller_devices', 'controller_devices.c', 'requirements.txt',
    'Start Minecraft Bedrock.command', 'Build Launcher Update.command',
    'README-Fixed-Setup.md', '.launcher-version',
}
EXECUTABLE = {'controller_devices', 'Start Minecraft Bedrock.command', 'Build Launcher Update.command'}
REQUIRED = {'launcher-edits.json', 'runtime_setup.py', 'update_client.py', 'controller_devices', '.launcher-version'}


def version(value):
    if not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise ValueError('Release versions must look like v0.2.0.')
    return tuple(map(int, value.lstrip('v').split('.')))


def fetch(url, limit, timeout=5):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'Bedrock-Mac-Fixed-Updater',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content = response.read(limit + 1)
    if len(content) > limit:
        raise ValueError('Update download exceeded its allowed size.')
    return content


def apply_archive(data, expected_version):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) - ALLOWED - {'update-manifest.json'}:
            raise ValueError('Update contains unexpected files.')
        if sum(item.file_size for item in archive.infolist()) > 8 * 1024 * 1024:
            raise ValueError('Update archive is too large.')
        manifest = json.loads(archive.read('update-manifest.json'))
        files = manifest['files']
        if version(manifest['version']) != version(expected_version):
            raise ValueError('Release and payload versions differ.')
        if not REQUIRED <= set(files) or set(files) != set(names) - {'update-manifest.json'}:
            raise ValueError('Update is missing required files.')
        contents = {name: archive.read(name) for name in files}
        for name, content in contents.items():
            if name not in ALLOWED or hashlib.sha256(content).hexdigest() != files[name]:
                raise ValueError('Update file checksum did not match.')
        if version(contents['.launcher-version'].decode().strip()) != version(expected_version):
            raise ValueError('Payload version is invalid.')
    edits = json.loads(contents.pop('launcher-edits.json'))
    base = (ROOT / '.launcher-base-cli.py').read_text()
    if hashlib.sha256(base.encode()).hexdigest() != edits['base_sha256']:
        raise ValueError('Original launcher source checksum did not match.')
    previous_end = 0
    for start, end, replacement in edits['edits']:
        if not isinstance(start, int) or not isinstance(end, int) or not isinstance(replacement, str):
            raise ValueError('Invalid launcher patch.')
        if not previous_end <= start <= end <= len(base):
            raise ValueError('Overlapping launcher patch.')
        previous_end = end
    generated = base
    for start, end, replacement in reversed(edits['edits']):
        generated = generated[:start] + replacement + generated[end:]
    if hashlib.sha256(generated.encode()).hexdigest() != edits['result_sha256']:
        raise ValueError('Patched launcher checksum did not match.')
    contents['cli.py'] = generated.encode()
    # Keep the previous code for rollback; account, game, and world files are outside this list.
    backup = ROOT / '.launcher-update-backup'
    backup.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.launcher-update-', dir=ROOT) as stage_name:
        stage = Path(stage_name)
        for name, content in contents.items():
            (stage / name).write_bytes(content)
            os.chmod(stage / name, 0o755 if name in EXECUTABLE else 0o644)
        changed = []
        try:
            for name in sorted(contents, key=lambda item: item == '.launcher-version'):
                target = ROOT / name
                previous = backup / name
                if target.is_file():
                    shutil.copy2(target, previous)
                else:
                    previous.unlink(missing_ok=True)
                os.replace(stage / name, target)
                changed.append(name)
        except Exception:
            for name in reversed(changed):
                previous = backup / name
                if previous.exists():
                    shutil.copy2(previous, ROOT / name)
                else:
                    (ROOT / name).unlink(missing_ok=True)
            raise


def check():
    try:
        config = json.loads((ROOT / 'update-channel.json').read_text())
        repository = config.get('github_repository', '').strip()
        if not repository:
            return
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Invalid GitHub update repository.')
        print('Checking for launcher updates...', flush=True)
        release = json.loads(fetch('https://api.github.com/repos/' + repository + '/releases/latest', 1024 * 1024))
        target = release['tag_name']
        current = (ROOT / '.launcher-version').read_text().strip()
        if version(target) <= version(current):
            return
        asset = next(item for item in release['assets'] if item['name'] == 'bedrock-mac-update.zip')
        digest = asset.get('digest') or ''
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
            raise ValueError('Release asset is missing GitHub checksum metadata.')
        url = asset['browser_download_url']
        if not url.startswith('https://github.com/' + repository + '/releases/download/'):
            raise ValueError('Unexpected update download location.')
        print('Installing launcher update ' + target + '...', flush=True)
        data = fetch(url, 8 * 1024 * 1024, timeout=20)
        if hashlib.sha256(data).hexdigest() != digest[7:]:
            raise ValueError('Downloaded update checksum did not match.')
        apply_archive(data, target)
        print('Launcher updated. Starting Minecraft launcher...', flush=True)
    except Exception as error:
        print('Launcher update unavailable; continuing with the installed copy. (' + str(error) + ')', flush=True)


if __name__ == '__main__':
    check()
