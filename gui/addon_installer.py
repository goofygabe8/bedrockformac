"""Install Bedrock archives into the GDK shared pack store, without editing worlds."""
import contextlib
import fcntl
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

MAX_BYTES = 1024 * 1024 * 1024
MAX_FILES = 40000
KINDS = {'resource_packs': 'Resource pack', 'behavior_packs': 'Behavior pack', 'skin_packs': 'Skin pack'}


def shared_store(prefix):
    users = Path(prefix) / 'drive_c/users'
    existing = list(users.glob('*/AppData/Roaming/Minecraft Bedrock/Users/Shared/games/com.mojang'))
    if len(existing) == 1:
        return existing[0]
    raise ValueError('Launch Minecraft once, then close it before installing add-ons.' if not existing
                     else 'More than one Windows profile has Minecraft data. Choose a single launcher instance first.')


def version_key(value):
    if isinstance(value, list) and len(value) == 3 and all(type(n) is int and 0 <= n <= 2147483647 for n in value):
        return tuple(value)
    if isinstance(value, str):
        match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?', value)
        if match:
            return tuple(map(int, match.groups()))
    raise ValueError('The pack manifest has an invalid version.')


def pack_info(folder):
    manifest = folder / 'manifest.json'
    if manifest.stat().st_size > 1024 * 1024:
        raise ValueError('The pack manifest is too large.')
    data = json.loads(manifest.read_text(encoding='utf-8-sig'))
    header = data['header']
    identifier = str(uuid.UUID(header['uuid']))
    version = version_key(header['version'])
    types = {m['type'] for m in data['modules']}
    if types <= {'resources'} and types:
        kind = 'resource_packs'
    elif types <= {'data', 'script', 'client_data'} and types:
        kind = 'behavior_packs'
    elif types == {'skin_pack'}:
        kind = 'skin_packs'
    else:
        raise ValueError('This is not a supported resource, behavior, or skin pack. World imports are not supported here.')
    name = header.get('name')
    if not isinstance(name, str) or not name.strip():
        raise ValueError('The pack manifest is missing its name.')
    # Display a localized name where a standard localization file exists.
    lang = folder / 'texts/en_US.lang'
    if lang.is_file() and lang.stat().st_size < 1024 * 1024:
        for line in lang.read_text(encoding='utf-8-sig', errors='replace').splitlines():
            key, sep, value = line.partition('=')
            if sep and key.strip() == name:
                name = value.strip(); break
    name = re.sub(r'§.', '', name)
    name = ''.join(c for c in name if c.isprintable())[:160]
    return dict(uuid=identifier, version=list(version), name=name, kind=kind, type=KINDS[kind])


def installed_packs(store):
    result = []
    for kind in KINDS:
        for folder in sorted((store / kind).glob('*')):
            if not folder.is_dir() or folder.is_symlink():
                continue
            try:
                info = pack_info(folder)
                if info['kind'] == kind:
                    result.append((folder, info))
            except (OSError, ValueError, KeyError, TypeError):
                continue
    return result


def extract_archive(source, destination, budget):
    """Every nested archive shares the same expanded-byte/file budget."""
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        budget[1] += len(entries)
        if budget[1] > MAX_FILES:
            raise ValueError('The add-on contains too many files (limit: 40,000).')
        seen = set()
        for entry in entries:
            name = entry.filename.replace('\\', '/')
            path = PurePosixPath(name)
            if (path.is_absolute() or not path.parts or '..' in path.parts or
                    any(':' in part or '\x00' in part or part.endswith((' ', '.')) for part in path.parts)):
                raise ValueError('The archive contains an unsafe filename.')
            key = str(path).casefold()
            if key in seen:
                raise ValueError('The archive contains duplicate filenames.')
            seen.add(key)
            mode = entry.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR) or entry.flag_bits & 1:
                raise ValueError('Encrypted files and archive links are not supported.')
            if entry.is_dir():
                (destination / path).mkdir(parents=True, exist_ok=True)
                continue
            budget[0] += entry.file_size
            if budget[0] > MAX_BYTES:
                raise ValueError('The expanded add-on exceeds 1 GB.')
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            received = 0
            with archive.open(entry) as incoming, target.open('xb') as outgoing:
                while True:
                    chunk = incoming.read(1024 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > entry.file_size:
                        raise ValueError('The archive has an invalid file size.')
                    outgoing.write(chunk)


def discover(source, stage, budget, depth=0):
    if depth > 3:
        raise ValueError('The add-on contains too many nested archives.')
    stage.mkdir()
    extract_archive(source, stage, budget)
    if any(stage.rglob('level.dat')):
        raise ValueError('This archive contains a world. Use a .mcpack or .mcaddon instead.')
    manifests = [p for p in stage.rglob('manifest.json') if '__MACOSX' not in p.parts]
    roots = [p.parent for p in manifests]
    if any(a != b and a in b.parents for a in roots for b in roots):
        raise ValueError('The archive contains overlapping pack folders.')
    packs = [(folder, pack_info(folder)) for folder in roots]
    nested = [p for p in stage.rglob('*') if p.suffix.lower() in ('.mcpack', '.mcaddon')
              and '__MACOSX' not in p.parts and not any(root == p.parent or root in p.parents for root in roots)]
    for index, item in enumerate(nested):
        packs.extend(discover(item, stage.parent / (stage.name + '-nested-' + str(index)), budget, depth + 1))
    if not packs:
        raise ValueError('No Bedrock pack manifest was found. Java mods and ordinary downloads cannot be installed here.')
    return packs


@contextlib.contextmanager
def install_lock(prefix):
    target = Path(prefix).parent / '.addon-install.lock'
    with target.open('a') as lock:
        os.chmod(target, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another add-on installation is running. Wait for it to finish.')
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def install(prefix, paths, progress=lambda message: None, before_commit=lambda: None):
    with install_lock(prefix):
        return install_locked(prefix, paths, progress, before_commit)


def install_locked(prefix, paths, progress, before_commit):
    store = shared_store(prefix)
    # Staging in the same filesystem allows rename and rollback instead of partial packs.
    with tempfile.TemporaryDirectory(prefix='.addon-stage-', dir=store) as temporary:
        stage = Path(temporary)
        candidates = []
        budget = [0, 0]
        if not paths or len(paths) > 32:
            raise ValueError('Select between 1 and 32 add-on files.')
        for index, value in enumerate(paths):
            source = Path(value)
            if not source.is_file() or source.suffix.lower() not in ('.mcpack', '.mcaddon', '.zip'):
                raise ValueError('Choose .mcpack, .mcaddon, or Bedrock pack .zip files.')
            if source.stat().st_size > MAX_BYTES:
                raise ValueError('The selected archive exceeds 1 GB.')
            progress('Reading ' + source.name + '…')
            candidates.extend(discover(source, stage / ('archive-' + str(index)), budget))
            if len(candidates) > 256:
                raise ValueError('Import at most 256 packs at a time.')
        unique = {}
        for folder, info in candidates:
            key = (info['kind'], info['uuid'])
            if key in unique:
                raise ValueError('Two selected packs share an identifier. Import one version at a time.')
            unique[key] = (folder, info)
        existing = installed_packs(store)
        plan, skipped = [], []
        for folder, info in unique.values():
            matches = [(p, i) for p, i in existing if i['uuid'] == info['uuid'] and i['kind'] == info['kind']]
            if len(matches) > 1:
                raise ValueError('Multiple installed copies of ' + info['name'] + ' exist. Resolve them in the Packs Folder first.')
            if matches and version_key(matches[0][1]['version']) >= version_key(info['version']):
                skipped.append(info['name']); continue
            parent = store / info['kind']
            if parent.is_symlink():
                raise ValueError('The pack destination is a link. Restore the normal Minecraft pack folder first.')
            parent.mkdir(exist_ok=True)
            destination = matches[0][0] if matches else parent / ('launcher-' + info['uuid'])
            if destination.is_symlink() or (not matches and destination.exists()):
                raise ValueError('A different folder already occupies the pack destination.')
            plan.append((folder, info, destination))
        backups = Path(prefix).parent / '.addon-backups' / str(uuid.uuid4())
        journal = []
        before_commit()
        try:
            for index, (folder, info, destination) in enumerate(plan):
                progress('Installing ' + info['name'] + '…')
                backup = None
                if destination.exists():
                    backups.mkdir(parents=True, exist_ok=True)
                    backup = backups / (str(index) + '-' + destination.name)
                    os.rename(destination, backup)
                journal.append((destination, backup))
                os.rename(folder, destination)
        except Exception:
            for destination, backup in reversed(journal):
                if destination.exists():
                    shutil.rmtree(destination)
                if backup and backup.exists():
                    os.rename(backup, destination)
            raise
    names = [info['name'] for _, info, _ in plan]
    message = ('Installed: ' + ', '.join(names) + '. ' if names else '')
    if skipped:
        message += 'Already installed at the same or a newer version: ' + ', '.join(skipped) + '. '
    message += 'Launch Minecraft and activate packs in World Settings → Resource Packs / Behavior Packs, or Settings → Global Resources for textures. Realm packs are activated by the Realm owner.'
    return dict(message=message, installed=names, skipped=skipped)
