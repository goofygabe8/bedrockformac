"""Normalize an empty HTTP request path in the pinned WineForge signer.

The bundled sign_request rejects a successfully parsed URL when both the path
and query are empty. Minecraft requests an Xbox token for https://avty.xboxlive.com
while joining a Realm. The observed failure is get_path_and_query / E_FAIL.
RFC 9112 section 3.2.1 specifies '/' for an empty URI path. Use that path and
continue through the original allocation, signing and error handling code.

Only the exact supported DLL is accepted. This does not replace authentication,
change token audiences, or skip a signature check. No game binary is modified.
"""

import hashlib
import json
import os
import struct
import subprocess
import time
from pathlib import Path

DLL = 'xgameruntime.dll'
ORIGINAL_SHA256 = '3133debe65896679aff7d381419cf26ea997c4e0ad0a5b28cdab1ea436acf213'
BLOCK_RVA = 0x672ef
CONTINUE_RVA = 0x667ac
SLASH_RVA = 0x138c72  # NUL-terminated '/' suffix of the original L"https://".
ORIGINAL_BLOCK = bytes.fromhex('4889d941bf05400080ff158aca1200488d058bbe0c004889442450e964f5ffff')


def replacement():
    # Entered only after WinHttpCrackUrl succeeds and path+query length is zero.
    # R14D = path length; ESI = query length (zero); R12D = combined length.
    # Preserve the function prologue, stack layout and all unwind information.
    code = b'\x48\x8d\x05' + struct.pack('<i', SLASH_RVA - (BLOCK_RVA + 7))
    code += bytes.fromhex('48898424f8000000')  # URL_COMPONENTS.lpszUrlPath
    code += bytes.fromhex('41be01000000')      # mov r14d, 1
    code += bytes.fromhex('4589f4')            # mov r12d, r14d
    code += b'\xe9' + struct.pack('<i', CONTINUE_RVA - (BLOCK_RVA + len(code) + 5))
    return code.ljust(len(ORIGINAL_BLOCK), b'\x90')


def offset(data, rva):
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[:2] != b'MZ' or data[pe:pe+4] != b'PE\0\0' or struct.unpack_from('<H', data, pe+4)[0] != 0x8664:
        raise RuntimeError('The Xbox runtime is not the supported x64 PE image.')
    count = struct.unpack_from('<H', data, pe+6)[0]
    optional_size = struct.unpack_from('<H', data, pe+20)[0]
    for index in range(count):
        section = pe + 24 + optional_size + index * 40
        size, virtual, raw_size, raw = struct.unpack_from('<IIII', data, section+8)
        if virtual <= rva < virtual + raw_size:
            return raw + rva - virtual
    raise RuntimeError('The Xbox runtime patch address is outside the DLL.')


def is_patched(data):
    try:
        start = offset(data, BLOCK_RVA)
        if data[start:start+len(ORIGINAL_BLOCK)] != replacement():
            return False
        restored = bytearray(data)
        restored[start:start+len(ORIGINAL_BLOCK)] = ORIGINAL_BLOCK
        return hashlib.sha256(restored).hexdigest() == ORIGINAL_SHA256
    except (ValueError, struct.error, RuntimeError):
        return False


def patch_bytes(data):
    if hashlib.sha256(data).hexdigest() != ORIGINAL_SHA256:
        raise RuntimeError('The Xbox runtime differs from the supported Mac runtime. No DLL was modified.')
    start = offset(data, BLOCK_RVA)
    slash = offset(data, SLASH_RVA)
    guard = offset(data, 0x667a6)
    if (data[start:start+len(ORIGINAL_BLOCK)] != ORIGINAL_BLOCK or
            data[slash:slash+4] != b'/\0\0\0' or
            data[guard:guard+6] != bytes.fromhex('0f84430b0000')):
        raise RuntimeError('The Xbox request-path code did not match its pinned implementation.')
    updated = bytearray(data)
    updated[start:start+len(ORIGINAL_BLOCK)] = replacement()
    return bytes(updated)


def ensure_auth_path(root, prefix):
    root, prefix = Path(root).resolve(), Path(prefix)
    listing = subprocess.run(['/bin/ps', '-axo', 'comm='], capture_output=True, text=True, check=True)
    for line in listing.stdout.splitlines():
        path = Path(line.strip())
        if path.name == 'Minecraft.Windows.exe' and path.parent.parent == root/'version':
            raise RuntimeError('Close Minecraft before preparing Realm authentication.')
    source = root/'dist/lib/wine/x86_64-windows'/DLL
    target = prefix/'drive_c/windows/system32'/DLL
    original = source.read_bytes()
    patched = original if is_patched(original) else patch_bytes(original)
    changes = []
    for path in (source, target):
        existing = path.read_bytes() if path.is_file() else None
        if existing == patched:
            continue
        if existing is not None and hashlib.sha256(existing).hexdigest() != ORIGINAL_SHA256:
            raise RuntimeError('The installed Xbox DLL is not the supported runtime. No DLL was modified.')
        changes.append((path, existing))
    if not changes:
        return
    backup = root/'.realm-auth-backups'/str(time.time_ns())
    backup.mkdir(parents=True, mode=0o700)
    os.chmod(backup.parent, 0o700)
    records = []
    for index, (path, contents) in enumerate(changes):
        name = str(index) + '-' + DLL
        if contents is not None:
            (backup/name).write_bytes(contents)
            os.chmod(backup/name, 0o600)
        records.append(dict(path=str(path.relative_to(root)), backup=name if contents is not None else None))
    (backup/'manifest.json').write_text(json.dumps(records, indent=2) + '\n')
    os.chmod(backup/'manifest.json', 0o600)
    written = []
    try:
        for path, previous in changes:
            temporary = path.with_name('.realm-auth-' + str(time.time_ns()))
            try:
                temporary.write_bytes(patched)
                os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o644)
                os.replace(temporary, path)
                written.append((path, previous))
            finally:
                temporary.unlink(missing_ok=True)
    except Exception:
        for path, previous in reversed(written):
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                temporary = path.with_name('.realm-auth-restore-' + str(time.time_ns()))
                temporary.write_bytes(previous)
                os.chmod(temporary, 0o644)
                os.replace(temporary, path)
        raise
