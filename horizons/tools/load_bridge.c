/* Original MIT-licensed loader for the user's own experimental Minecraft mod. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <wchar.h>

static DWORD minecraft_pid(void) {
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return 0;
    PROCESSENTRY32W entry = {0}; entry.dwSize = sizeof(entry);
    DWORD result = 0; unsigned count = 0;
    if (Process32FirstW(snapshot, &entry)) do {
        if (!_wcsicmp(entry.szExeFile, L"Minecraft.Windows.exe")) { result = entry.th32ProcessID; count++; }
    } while (Process32NextW(snapshot, &entry));
    CloseHandle(snapshot);
    return count == 1 ? result : 0;
}
static ULONG_PTR module_base(DWORD pid, const wchar_t* name) {
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
    if (snapshot == INVALID_HANDLE_VALUE) return 0;
    MODULEENTRY32W entry = {0}; entry.dwSize = sizeof(entry); ULONG_PTR result = 0;
    if (Module32FirstW(snapshot, &entry)) do {
        if (!_wcsicmp(entry.szModule, name)) { result = (ULONG_PTR)entry.modBaseAddr; break; }
    } while (Module32NextW(snapshot, &entry));
    CloseHandle(snapshot); return result;
}
int wmain(int argc, wchar_t** argv) {
    if (argc != 2) { fwprintf(stderr, L"Usage: load-bridge.exe DLL_PATH\n"); return 2; }
    DWORD pid = minecraft_pid();
    if (!pid) { fwprintf(stderr, L"Exactly one Minecraft game must be running in this launcher.\n"); return 3; }
    if (!wcscmp(argv[1], L"--status")) {
        wprintf(L"Native client: %ls\nScript engine: %ls\n",
            module_base(pid, L"Latite.dll") ? L"loaded" : L"not loaded",
            module_base(pid, L"ChakraCore.dll") ? L"loaded" : L"not loaded");
        return 0;
    }
    if (module_base(pid, L"Latite.dll")) { fwprintf(stderr, L"The native client is already loaded. Restart Minecraft before replacing it.\n"); return 4; }
    wchar_t path[32768]; DWORD length = GetFullPathNameW(argv[1], 32768, path, NULL);
    if (!length || length >= 32768 || GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) return 5;
    HANDLE process = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION | PROCESS_VM_WRITE |
        PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, FALSE, pid);
    if (!process) { fwprintf(stderr, L"Cannot access the selected Minecraft process.\n"); return 6; }
    FARPROC localLoad = GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "LoadLibraryW");
    HMODULE owner = NULL;
    if (!localLoad || !GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
        GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCWSTR)localLoad, &owner)) { CloseHandle(process); return 7; }
    wchar_t ownerPath[MAX_PATH];
    if (!GetModuleFileNameW(owner, ownerPath, MAX_PATH)) { CloseHandle(process); return 7; }
    const wchar_t* ownerName = wcsrchr(ownerPath, L'\\'); ownerName = ownerName ? ownerName + 1 : ownerPath;
    ULONG_PTR remoteOwner = module_base(pid, ownerName);
    if (!remoteOwner) { CloseHandle(process); return 7; }
    LPTHREAD_START_ROUTINE remoteLoad = (LPTHREAD_START_ROUTINE)(remoteOwner + ((ULONG_PTR)localLoad - (ULONG_PTR)owner));
    SIZE_T bytes = ((SIZE_T)length + 1) * sizeof(wchar_t), written = 0;
    void* remotePath = VirtualAllocEx(process, NULL, bytes, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!remotePath) { CloseHandle(process); return 8; }
    if (!WriteProcessMemory(process, remotePath, path, bytes, &written) || written != bytes) {
        VirtualFreeEx(process, remotePath, 0, MEM_RELEASE); CloseHandle(process); return 9;
    }
    HANDLE thread = CreateRemoteThread(process, NULL, 0, remoteLoad, remotePath, 0, NULL);
    if (!thread) { VirtualFreeEx(process, remotePath, 0, MEM_RELEASE); CloseHandle(process); return 10; }
    DWORD completed = WaitForSingleObject(thread, 15000);
    // A timed-out thread can still read the path. Let Minecraft reclaim that small allocation on exit.
    if (completed == WAIT_OBJECT_0) VirtualFreeEx(process, remotePath, 0, MEM_RELEASE);
    CloseHandle(thread); CloseHandle(process);
    if (completed != WAIT_OBJECT_0 || !module_base(pid, L"Latite.dll")) {
        fwprintf(stderr, L"The native library did not finish loading.\n"); return 11;
    }
    wprintf(L"Native library loaded. This does not verify rendering or terrain compatibility.\n"); return 0;
}
