"""Background actions for the native Mac launcher; UI messages use JSON lines."""
import contextlib
import io
import importlib
import hashlib
import tempfile
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent
CATALOG = 'https://raw.githubusercontent.com/MinecraftBedrockArchiver/GdkLinks/master/urls.json'
XODUS = ROOT / 'dist/bin/xodus-cli'
WINE = ROOT / 'dist/bin/wine'
PREFIX = ROOT / 'bottle'
VERSIONS = ROOT / 'version'


def emit(kind, **values):
    print(json.dumps(dict(kind=kind, **values)), flush=True)


def execute(args, **kw):
    result = subprocess.run([str(item) for item in args], cwd=ROOT,
                            capture_output=True, text=True, **kw)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or 'Operation failed.').strip()[-1200:])
    return result.stdout.strip()


def catalogue():
    request = urllib.request.Request(CATALOG, headers={'User-Agent': 'BedrockForMac'})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)['release']


def sort_key(value):
    return tuple(map(int, value.split('.')))


def controllers():
    try:
        ids = execute([ROOT/'controller_devices', ROOT/'dist/lib/wine/x86_64-unix/libSDL2-2.0.0.dylib'], timeout=8).splitlines()
    except Exception:
        return []
    labels = {'054c': 'PlayStation controller', '045e': 'Xbox controller', '057e': 'Nintendo controller', '2dc8': '8BitDo controller'}
    return [labels.get(item[:4], 'Game controller') for item in dict.fromkeys(ids) if re.fullmatch(r'[0-9a-f]{4}/[0-9a-f]{4}', item)]


def update():
    import update_client
    before = (ROOT/'.launcher-version').read_text().strip()
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        update_client.check()
        if (ROOT/'.launcher-version').read_text().strip() != before:
            importlib.invalidate_caches()
            update_client = importlib.reload(update_client)
        update_client.ensure_gui()
    after = (ROOT/'.launcher-version').read_text().strip()
    message = output.getvalue().strip()
    if before == after and 'unavailable' not in message.lower():
        message = 'Your launcher is up to date.'
    emit('result', ok=True, version=after, restart=before != after,
         message=message or 'Your launcher is up to date.')


def ensure_runtime():
    if (ROOT/'dist/bin/wine').is_file() and (ROOT/'d3dmetal/gptk').is_dir():
        return
    emit('progress', message='Downloading the game runtime for your Mac…')
    url = 'https://github.com/amha0270/Minecraft-Bedrock-GDK-Launcher/releases/download/BETA/Minecraft-Bedrock-Launcher_MacOS_v0.1.0b.zip'
    expected = '10165c17c992547b95dd873256a9c9fb4b7ed1c590c87b1c1366bc2d17be74d1'
    with tempfile.TemporaryDirectory(prefix='.runtime-setup-', dir=ROOT) as temporary:
        stage = Path(temporary)
        archive = stage/'runtime.zip'
        digest = hashlib.sha256()
        with urllib.request.urlopen(url, timeout=30) as response, archive.open('wb') as output:
            total = int(response.headers.get('Content-Length') or 354272590)
            received = 0; last = 0
            while True:
                chunk = response.read(1024*1024)
                if not chunk: break
                output.write(chunk); digest.update(chunk); received += len(chunk)
                if time.monotonic() - last > 1:
                    emit('progress', message='Downloading the Mac runtime… ' + str(min(100, received*100//total)) + '%')
                    last = time.monotonic()
        if digest.hexdigest() != expected:
            raise RuntimeError('Runtime download checksum did not match. Open the launcher again to retry.')
        emit('progress', message='Installing the Mac runtime…')
        execute(['/usr/bin/unzip', '-q', archive, '-d', stage], timeout=180)
        base = stage/'Minecraft-Bedrock-Launcher_MacOS_v0.1.0b'
        source = (base/'cli.py').read_bytes()
        if hashlib.sha256(source).hexdigest() != 'd912588009167e8785f8e7a6a04e1de0f7b7fcd8d87b4826191308271614db77':
            raise RuntimeError('The upstream launcher source did not match this setup.')
        (ROOT/'.launcher-base-cli.py').write_bytes(source)
        (ROOT/'cli.py').write_bytes(source)
        from patch_launcher import main as patch
        with contextlib.redirect_stdout(io.StringIO()): patch(ROOT/'cli.py')
        shutil.copy2(base/'utls.py', ROOT/'utls.py')
        for name in ('dist', 'd3dmetal'):
            if (ROOT/name).exists():
                # Only fill absent runtime files on a retried setup.
                shutil.copytree(base/name, ROOT/name, dirs_exist_ok=True, symlinks=True)
            else:
                shutil.move(str(base/name), ROOT/name)


def bootstrap():
    ensure_runtime()
    python = ROOT/'.venv/bin/python'
    if not python.is_file():
        emit('progress', message='Preparing your launcher for the first start…')
        execute([sys.executable, '-m', 'venv', ROOT/'.venv'], timeout=90)
    ready = subprocess.run([str(python), '-c', 'import pick, requests'], capture_output=True).returncode == 0
    if not ready:
        emit('progress', message='Installing launcher dependencies…')
        execute([python, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', ROOT/'requirements.txt'], timeout=180)
    emit('progress', message='Checking for launcher updates…')
    update()


def status():
    installed = sorted([path.name for path in VERSIONS.iterdir() if path.is_dir() and (path/'Minecraft.Windows.exe').is_file() and re.fullmatch(r'\d+(?:\.\d+)+', path.name)], key=sort_key, reverse=True) if VERSIONS.is_dir() else []
    selected = (VERSIONS/'.version').read_text().strip() if (VERSIONS/'.version').is_file() else ''
    if selected not in installed:
        selected = installed[0] if installed else ''
        if selected:
            (VERSIONS/'.version').write_text(selected)
    account = execute([XODUS, 'status'], timeout=15)
    match = re.search(r'Signed in as:\s*(.+)', account)
    # The upstream status may omit the colon.
    if not match: match = re.search(r'Signed in as\s+(.+)', account)
    emit('result', ok=True, installed=installed, selected=selected,
         account=re.sub(r'\s*\(PUID[^)]*\)', '', match.group(1)).strip() if match else '', controllers=controllers(),
         version=(ROOT/'.launcher-version').read_text().strip())


def login():
    emit('progress', message='Opening Microsoft sign-in… Follow the sign-in link below if needed.')
    process = subprocess.Popen([str(XODUS), 'login'], cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in process.stdout:
        if any(word in line.lower() for word in ('code', 'https://', 'signed', 'failed', 'error')):
            emit('progress', message=line.strip())
    if process.wait():
        raise RuntimeError('Sign-in did not finish. Try signing in again.')
    emit('result', ok=True, message='Sign-in completed.')


def play(value):
    if not re.fullmatch(r'\d+(?:\.\d+)+', value): raise RuntimeError('Select an installed game version.')
    game = VERSIONS/value/'Minecraft.Windows.exe'
    if not game.is_file(): raise RuntimeError('Download this game version first.')
    (VERSIONS/'.version').write_text(value)
    from runtime_setup import ensure_wine_input
    emit('progress', message='Preparing mouse, keyboard, and controller input…')
    with contextlib.redirect_stdout(io.StringIO()):
        ensure_wine_input(PREFIX, WINE)
    env = os.environ.copy()
    env.pop('WINEGDK_PREAUTH_DEVICE', None)
    env.update(WINEPREFIX=str(PREFIX), GRAPHICS_BACKEND='d3dmetal',
               D3DMETAL_RUNTIME_DIR=str(ROOT/'d3dmetal/gptk'), D3DMETAL_UPSCALER_PROFILE='amd',
               D3DM_VENDOR_ID='4098', D3DM_DEVICE_ID='29631', D3DM_DEVICE_DESCRIPTION='AMD Radeon RX 6800 XT',
               WINEDLLOVERRIDES='cryptbase=n,b;vrclient=;vrclient_x64=;openvr_api=;wineopenxr=;amd_ags_x64=')
    logs = ROOT/'.gui-logs'
    logs.mkdir(exist_ok=True, mode=0o700)
    target = logs/'last-game.log'
    emit('progress', message='Minecraft is starting. Keep the controller connected.')
    process = subprocess.Popen([str(WINE), str(game)], cwd=game.parent, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', bufsize=1)
    with target.open('w') as output:
        os.chmod(target, 0o600)
        for line in process.stdout:
            output.write(line)
            if 'https://www.microsoft.com/link' in line and 'enter code' in line:
                emit('progress', message='Sign in at https://www.microsoft.com/link — code: ' + line.split()[-1])
    code = process.wait()
    if code: raise RuntimeError('Minecraft stopped unexpectedly. Details are saved in .gui-logs/last-game.log.')
    emit('result', ok=True, message='Minecraft closed. Ready to play again.')


def download(value):
    if not re.fullmatch(r'\d+(?:\.\d+)+', value): raise RuntimeError('Select a game release to download.')
    data = catalogue()
    if value not in data: raise RuntimeError('This release is no longer listed. Refresh the versions.')
    folder = VERSIONS/value
    folder.mkdir(parents=True, exist_ok=True)
    emit('progress', message='Downloading Minecraft ' + value + '… This can take several minutes.')
    process = subprocess.Popen([str(XODUS), 'streaming', data[value][0], str(folder), '--market', 'neutral', '--numbers'], cwd=ROOT,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    last = 0
    for line in process.stdout:
        if time.monotonic() - last > 2:
            # Only show simple numeric progress, never account/runtime diagnostics.
            match = re.search(r'\b(\d{1,3}(?:\.\d+)?)%', line)
            if match: emit('progress', message='Downloading Minecraft ' + value + '… ' + match.group(0))
            last = time.monotonic()
    if process.wait(): raise RuntimeError('Download failed. Check your connection and Microsoft sign-in, then try again.')
    emit('progress', message='Preparing the downloaded game…')
    temporary = folder/('.launcher-decrypt-' + str(time.time_ns()))
    try:
        execute([XODUS, 'decrypt', folder, temporary], timeout=240)
        executable = temporary/'Minecraft.Windows.exe'
        if not executable.is_file(): raise RuntimeError('The game could not be prepared. Check that your account owns Minecraft for Windows.')
        os.replace(executable, folder/'Minecraft.Windows.exe')
    finally:
        if temporary.exists(): shutil.rmtree(temporary)
    (VERSIONS/'.version').write_text(value)
    emit('result', ok=True, message='Minecraft ' + value + ' is ready to play.')


def main():
    os.chdir(ROOT)
    action = sys.argv[1]
    if action == 'bootstrap': bootstrap()
    elif action == 'status': status()
    elif action == 'catalog': emit('result', ok=True, releases=sorted(catalogue(), key=sort_key, reverse=True))
    elif action == 'update': update()
    elif action == 'login': login()
    elif action == 'logout':
        execute([XODUS, 'logout'], timeout=30)
        emit('result', ok=True, message='Signed out.')
    elif action == 'play': play(sys.argv[2])
    elif action == 'download': download(sys.argv[2])
    elif action == 'select':
        value = sys.argv[2]
        if not re.fullmatch(r'\d+(?:\.\d+)+', value) or not (VERSIONS/value/'Minecraft.Windows.exe').is_file(): raise RuntimeError('Select an installed version.')
        (VERSIONS/'.version').write_text(value)
        emit('result', ok=True, message='Selected Minecraft ' + value + '.')
    elif action == 'audio':
        env = os.environ.copy(); env.update(WINEPREFIX=str(PREFIX)); env.pop('WINEGDK_PREAUTH_DEVICE', None)
        emit('progress', message='Choose your output device in the Audio tab. Restart Minecraft to apply it.')
        execute([WINE, ROOT/'dist/lib/wine/x86_64-windows/winecfg.exe'], env=env)
        emit('result', ok=True, message='Audio settings closed. Restart Minecraft to apply changes.')
    else: raise RuntimeError('Unknown launcher action.')

if __name__ == '__main__':
    try: main()
    except Exception as error:
        emit('result', ok=False, message=str(error))
        sys.exit(1)
