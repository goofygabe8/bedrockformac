"""Desktop CoreInputView compatibility for the pinned WineForge runtime.

Minecraft calls ICoreInputView3.TryShowWithKind when a text field is focused.
The bundled Wine stub returns E_NOTIMPL, which Minecraft raises as an unhandled
exception. A desktop without a Windows input pane can legitimately return
S_OK with result=FALSE. Apply that behavior to TryShow, TryShowWithKind and
TryHide, preserving the DLL's original stack allocation and unwind records.

Upstream implementation:
https://github.com/wine-mirror/wine/blob/master/dlls/windows.ui.core.textinput/main.c
API behavior:
https://learn.microsoft.com/en-us/uwp/api/windows.ui.viewmanagement.core.coreinputview.tryshow

Only the exact pinned binary is modified. No game executables are changed.
"""

import hashlib
import json
import os
import struct
import subprocess
import time
from pathlib import Path

DLL = 'windows.ui.core.textinput.dll'
ORIGINAL_SHA256 = '2d4ba9e4d59f122d8210162768ce5414bb2fe489f6c9da166df65e6372bb4ed1'

# RVA, original body, output pointer register. These three methods have no
# nonvolatile register saves, only a 0x38/0x48-byte allocation in their prologue.
ROUTINES = (
    (0x1bb0, '4883ec38f60595540000017513b8014000804883c438c3660f1f84000000000048895424284c8d0d2f6600004c8d05ad6c000048894c2420488d156154000031c9e8da430000b8014000804883c438c3', 'rdx'),
    (0x1c00, '4883ec38f60545540000017513b8014000804883c438c3660f1f84000000000048895424284c8d0ddf6500004c8d050d6c000048894c2420488d151154000031c9e88a430000b8014000804883c438c3', 'rdx'),
    (0x1c50, '4883ec48f605f5530000017513b8014000804883c448c3660f1f8400000000004c894424304c8d0d0c6600004c8d05dd6b000089542428488d15c253000048894c242031c9e836430000b8014000804883c448c3', 'r8'),
)


def replacement(original, register):
    """x64 Windows ABI: check output, *output=FALSE, return S_OK / E_POINTER."""
    frame = original[3]
    test = bytes.fromhex('4885d2' if register == 'rdx' else '4d85c0')
    store = bytes.fromhex('c60200' if register == 'rdx' else '41c60000')
    epilogue = bytes((0x48, 0x83, 0xc4, frame, 0xc3))
    success = store + bytes.fromhex('31c0') + epilogue
    failure = bytes.fromhex('b803400080') + epilogue
    code = original[:4] + test + bytes((0x74, len(success))) + success + failure
    return code + b'\x90' * (len(original) - len(code))


def patch_bytes(data):
    """Generate the patch only from its known original fingerprint."""
    if hashlib.sha256(data).hexdigest() != ORIGINAL_SHA256:
        raise RuntimeError('The text-input runtime differs from the supported Mac runtime. No DLL was modified.')
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[:2] != b'MZ' or data[pe:pe+4] != b'PE\0\0' or struct.unpack_from('<H', data, pe+4)[0] != 0x8664:
        raise RuntimeError('The text-input DLL is not the expected x64 PE image.')
    count = struct.unpack_from('<H', data, pe+6)[0]
    optional_size = struct.unpack_from('<H', data, pe+20)[0]
    sections = []
    for index in range(count):
        start = pe + 24 + optional_size + index*40
        size, rva, raw_size, raw = struct.unpack_from('<IIII', data, start+8)
        sections.append((rva, raw_size, raw))
    def offset(rva):
        for virtual, size, raw in sections:
            if virtual <= rva < virtual + size:
                return raw + rva - virtual
        raise RuntimeError('A text-input patch address is outside the DLL.')
    updated = bytearray(data)
    for rva, before_hex, register in ROUTINES:
        before = bytes.fromhex(before_hex)
        start = offset(rva)
        if data[start:start+len(before)] != before:
            raise RuntimeError('A text-input method did not match its pinned code.')
        updated[start:start+len(before)] = replacement(before, register)
    return bytes(updated)


def is_patched(data):
    # Reconstruct the known original from the patched methods, then check the
    # whole-file fingerprint. Arbitrary changes elsewhere are never accepted.
    restored = bytearray(data)
    for rva, before_hex, register in ROUTINES:
        before = bytes.fromhex(before_hex)
        # The pinned image uses identical RVAs and raw offsets for .text.
        if data[rva:rva+len(before)] != replacement(before, register):
            return False
        restored[rva:rva+len(before)] = before
    return hashlib.sha256(restored).hexdigest() == ORIGINAL_SHA256


def ensure_text_input(root, prefix):
    root, prefix = Path(root).resolve(), Path(prefix)
    processes = subprocess.run(['/bin/ps', '-axo', 'comm='], capture_output=True, text=True, check=True)
    for line in processes.stdout.splitlines():
        path = Path(line.strip())
        if path.name == 'Minecraft.Windows.exe' and path.parent.parent == root/'version':
            raise RuntimeError('Close Minecraft before preparing text input.')
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
            raise RuntimeError('The installed text-input DLL is not the supported runtime. No DLL was modified.')
        changes.append((path, existing))
    if not changes:
        return
    backup = root/'.text-input-backups'/str(time.time_ns())
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
            temporary = path.with_name('.text-input-' + str(time.time_ns()))
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
                temporary = path.with_name('.text-input-restore-' + str(time.time_ns()))
                temporary.write_bytes(previous)
                os.chmod(temporary, 0o644)
                os.replace(temporary, path)
        raise
