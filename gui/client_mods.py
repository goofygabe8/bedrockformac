"""Declarative native client-mod packages. No mod names or game hashes live here."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath

MANIFEST = 'bedrock-client-mod.json'
ROOT = Path(__file__).resolve().parent


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid client-mod path.')
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or '..' in path.parts or any(':' in p or p.endswith((' ', '.')) for p in path.parts):
        raise ValueError('Unsafe client-mod path.')
    return Path(*path.parts)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def validate(folder, verify=True):
    file = folder/MANIFEST
    if file.stat().st_size > 1024 * 1024: raise ValueError('The client-mod manifest is too large.')
    data = json.loads(file.read_text(encoding='utf-8-sig'))
    if data.get('format_version') != 1 or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', data.get('id', '')):
        raise ValueError('The client-mod manifest has an invalid format or identifier.')
    if not isinstance(data.get('name'), str) or not 1 <= len(data['name']) <= 160:
        raise ValueError('The client-mod manifest needs a name.')
    if not re.fullmatch(r'\d+\.\d+\.\d+', data.get('version', '')):
        raise ValueError('The client-mod manifest needs a version.')
    supported = data.get('game_sha256')
    if not isinstance(supported, list) or not 1 <= len(supported) <= 64 or any(not re.fullmatch('[0-9a-f]{64}', str(v)) for v in supported):
        raise ValueError('The mod must declare its supported Minecraft executable hashes.')
    entry = relative(data.get('entrypoint'))
    if entry.suffix.lower() != '.dll': raise ValueError('A native mod needs a DLL entrypoint.')
    files = data.get('files')
    if not isinstance(files, dict) or not 1 <= len(files) <= 10000:
        raise ValueError('The mod must declare checksums for its files.')
    if entry.as_posix() not in files: raise ValueError('The native entrypoint is not listed in the mod manifest.')
    declared = set()
    for name, expected in files.items():
        path = relative(name)
        if not re.fullmatch('[0-9a-f]{64}', str(expected)) or path.as_posix().casefold() in declared:
            raise ValueError('Invalid or duplicate client-mod checksums.')
        declared.add(path.as_posix().casefold())
        target = folder/path
        if not target.is_file() or target.is_symlink(): raise ValueError('A client-mod file is missing.')
        if verify and digest(target) != expected: raise ValueError('A client-mod file checksum differs. Reinstall this mod.')
    copies = data.get('local_appdata_files', [])
    if not isinstance(copies, list) or len(copies) > 128: raise ValueError('Too many client-mod installation files.')
    destinations = set()
    for copy in copies:
        source, target = relative(copy['source']), relative(copy['destination'])
        if source.as_posix() not in files or target.as_posix().casefold() in destinations:
            raise ValueError('Invalid client-mod installation mapping.')
        destinations.add(target.as_posix().casefold())
    return data


def preferences():
    try:
        data = json.loads((ROOT/'.client-mod-settings.json').read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError): return {}


def installed():
    result = []
    settings = preferences()
    for folder in sorted((ROOT/'client-mods').glob('*')):
        if not folder.is_dir() or folder.is_symlink(): continue
        try:
            data = validate(folder, verify=False)
            if data['id'] != folder.name: continue
            data['enabled'] = settings.get(data['id'], True) is True
            result.append((folder, data))
        except (OSError, ValueError, KeyError, TypeError): continue
    return result


def save_preferences(values):
    known = {data['id'] for _, data in installed()}
    if not isinstance(values, dict) or set(values) - known or any(type(v) is not bool for v in values.values()):
        raise ValueError('Choose installed client mods only.')
    merged = preferences(); merged.update(values)
    temp = ROOT/('.mod-preferences-' + str(uuid.uuid4()))
    try:
        temp.write_text(json.dumps(merged, indent=2)+'\n'); os.chmod(temp, 0o600)
        os.replace(temp, ROOT/'.client-mod-settings.json')
    finally: temp.unlink(missing_ok=True)


def install_archive(source, progress=lambda message: None):
    from addon_installer import extract_archive, version_key
    parent = ROOT/'client-mods'; parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.client-mod-import-', dir=ROOT) as temporary:
        stage = Path(temporary)
        extract_archive(Path(source), stage, [0, 0])
        manifests = list(stage.rglob(MANIFEST))
        if len(manifests) != 1: raise ValueError('Choose a ZIP containing one native client-mod manifest.')
        folder = manifests[0].parent; data = validate(folder)
        actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and p.name != MANIFEST}
        if actual != set(data['files']): raise ValueError('The native mod contains files not covered by its manifest.')
        target = parent/data['id']
        if target.is_symlink(): raise ValueError('The existing client-mod folder is a link.')
        backup = None
        if target.exists():
            previous = validate(target, verify=False)
            if version_key(previous['version']) >= version_key(data['version']):
                return data['name'] + ' is already installed at the same or a newer version.'
            backup = ROOT/'.client-mod-backups'/(data['id']+'-'+str(uuid.uuid4()))
            backup.parent.mkdir(exist_ok=True); os.rename(target, backup)
        try:
            os.rename(folder, target)
        except Exception:
            if backup: os.rename(backup, target)
            raise
        progress('Installed client mod: ' + data['name'])
        return data['name'] + ' installed. It loads automatically with a supported Minecraft version on the next game start. Client mods run native code inside Minecraft.'


def is_mod_archive(path):
    import zipfile
    with zipfile.ZipFile(path) as archive:
        return any(PurePosixPath(name.replace('\\', '/')).name == MANIFEST for name in archive.namelist())


def appdata(prefix, wine):
    env = os.environ.copy(); env.update(WINEPREFIX=str(prefix), WINEDEBUG='-all')
    env.pop('WINEGDK_PREAUTH_DEVICE', None)
    result = subprocess.run([str(wine), 'cmd.exe', '/d', '/c', 'echo %LOCALAPPDATA%'], env=env,
                            capture_output=True, text=True, timeout=15, check=True)
    value = result.stdout.strip()
    if not value.lower().startswith('c:\\users\\') or '..' in value.split('\\'):
        raise ValueError('Could not find the Windows instance’s local app-data folder.')
    destination = (Path(prefix)/'drive_c'/Path(value[3:].replace('\\', '/'))).resolve()
    if not destination.is_relative_to((Path(prefix)/'drive_c/users').resolve()):
        raise ValueError('The mod installation path is outside this Windows instance.')
    return destination


def prepare(prefix, wine, game, progress):
    """Called before launching Minecraft; copy only declared local-appdata files."""
    candidates = [(folder, data) for folder, data in installed() if data['enabled']]
    receipt_file = ROOT/'.client-mod-copy-state.json'
    try:
        previous = json.loads(receipt_file.read_text())
        if not isinstance(previous, dict): previous = {}
    except (OSError, ValueError): previous = {}
    if not candidates and not previous: return []
    fingerprint = digest(game); ready = []; copies = {}
    base = None
    for folder, summary in candidates:
        try:
            data = validate(folder)
            if fingerprint not in data['game_sha256']:
                progress('Skipping ' + data['name'] + ': this Minecraft version is not supported by the mod.'); continue
            # Validate conflicts before changing anything for this mod.
            for mapping in data.get('local_appdata_files', []):
                destination = relative(mapping['destination']).as_posix().casefold()
                sha = data['files'][mapping['source']]
                if destination in copies and copies[destination] != sha:
                    raise ValueError('Conflicting installation files with another enabled mod.')
            if data.get('local_appdata_files') and base is None: base = appdata(prefix, wine)
            changes = []
            for mapping in data.get('local_appdata_files', []):
                source = folder/relative(mapping['source']); target = base/relative(mapping['destination'])
                current = target
                while current != base:
                    if current.is_symlink(): raise ValueError('A declared mod destination is a link.')
                    current = current.parent
                if target.exists() and not target.is_file(): raise ValueError('A declared mod destination is not a file.')
                if not target.exists() or digest(target) != data['files'][mapping['source']]: changes.append((source, target))
            backups = ROOT/'.client-mod-file-backups'/str(uuid.uuid4()); journal = []
            try:
                for index, (source, target) in enumerate(changes):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    old = None
                    if target.exists():
                        backups.mkdir(parents=True, exist_ok=True); old = backups/str(index); shutil.copy2(target, old)
                    temp = target.with_name('.client-mod-copy-'+str(uuid.uuid4()))
                    try:
                        shutil.copy2(source, temp); os.replace(temp, target); journal.append((target, old))
                    finally: temp.unlink(missing_ok=True)
            except Exception:
                for target, old in reversed(journal):
                    if old: shutil.copy2(old, target)
                    else: target.unlink(missing_ok=True)
                raise
            copies.update({relative(m['destination']).as_posix().casefold(): data['files'][m['source']] for m in data.get('local_appdata_files', [])})
            ready.append((folder, data))
        except Exception:
            progress('Skipping ' + summary['name'] + ': its files or installation paths need attention. Reinstall it or disable it in Client Mods.')
    # Remove only unchanged, previously managed copies when a mod is disabled.
    # Keep their backups and disposable per-mod caches; never touch user edits.
    if previous and base is None:
        try: base = appdata(prefix, wine)
        except Exception:
            progress('Could not prepare optional client mods. Minecraft can continue; retry after restarting the launcher.')
            return []
    for name, expected in previous.items():
        try:
            if name.casefold() in copies: continue
            target = base/relative(name)
            current = target
            linked = False
            while current != base:
                if current.is_symlink(): linked = True; break
                current = current.parent
            if linked or not target.is_file() or digest(target) != expected: continue
            backup = ROOT/'.client-mod-file-backups'/str(uuid.uuid4())
            backup.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), backup/'disabled-mod-file')
        except (OSError, ValueError, TypeError, AttributeError):
            progress('A disabled mod has a file that needs manual attention. Its contents were retained.')
    temp = receipt_file.with_name('.mod-copy-state-'+str(uuid.uuid4()))
    try:
        temp.write_text(json.dumps(copies, indent=2)+'\n'); os.chmod(temp, 0o600); os.replace(temp, receipt_file)
    finally: temp.unlink(missing_ok=True)
    return ready


def load_for_game(ready, prefix, wine, game, alive, progress):
    """Only a new launcher-started game loads mods; an adopted game is untouched."""
    if not ready: return
    for _ in range(15):
        if not alive(): return
        time.sleep(1)
    env = os.environ.copy(); env.update(WINEPREFIX=str(prefix), WINEDEBUG='-all')
    env.pop('WINEGDK_PREAUTH_DEVICE', None)
    target = 'Z:' + str(game).replace('/', '\\')
    for folder, data in ready:
        if not alive(): return
        try:
            entry = folder/relative(data['entrypoint'])
            if digest(entry) != data['files'][data['entrypoint']]: raise ValueError('Changed entrypoint.')
            result = subprocess.run([str(wine), str(ROOT/'client_mod_loader.exe'), '--load', target,
                                     'Z:' + str(entry).replace('/', '\\')], env=env, capture_output=True, timeout=25)
            progress(('Loaded ' if result.returncode == 0 else 'Could not load ') + data['name'] +
                     ('. In-game operation still needs confirmation.' if result.returncode == 0 else '. Disable or reinstall it in Client Mods if needed.'))
        except Exception:
            progress('Could not load ' + data['name'] + '. Minecraft can continue without this optional mod.')
