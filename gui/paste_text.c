/* MIT: explicit, foreground-only Unicode text insertion for the Mac launcher.
 * Text arrives over stdin, never a process argument or temporary file.
 * CR/LF/tab are spaces; this helper never sends Enter or submits commands.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <wchar.h>
#include <stdlib.h>
#include <fcntl.h>
#include <io.h>

static DWORD find_game(const wchar_t *expected) {
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return 0;
    PROCESSENTRY32W entry = {0}; entry.dwSize = sizeof(entry);
    DWORD result = 0; unsigned count = 0;
    if (Process32FirstW(snapshot, &entry)) do {
        if (_wcsicmp(entry.szExeFile, L"Minecraft.Windows.exe")) continue;
        HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, entry.th32ProcessID);
        if (!process) continue;
        wchar_t path[32768]; DWORD length = 32768;
        if (QueryFullProcessImageNameW(process, 0, path, &length) && !_wcsicmp(path, expected)) {
            result = entry.th32ProcessID; count++;
        }
        CloseHandle(process);
    } while (Process32NextW(snapshot, &entry));
    CloseHandle(snapshot); return count == 1 ? result : 0;
}
static BOOL game_focused(DWORD pid) {
    DWORD current = 0;
    HWND window = GetForegroundWindow();
    if (!window) return FALSE;
    GetWindowThreadProcessId(window, &current);
    return current == pid;
}
int wmain(int argc, wchar_t **argv) {
    if (argc != 2) { fputs("Choose one running Minecraft instance.\n", stderr); return 2; }
    wchar_t expected[32768];
    DWORD path_length = GetFullPathNameW(argv[1], 32768, expected, NULL);
    if (!path_length || path_length >= 32768) return 3;
    DWORD pid = find_game(expected);
    if (!pid || !game_focused(pid)) {
        fputs("Paste canceled: click the Minecraft text field during the countdown.\n", stderr); return 4;
    }
    if (GetAsyncKeyState(VK_CONTROL) < 0 || GetAsyncKeyState(VK_MENU) < 0 ||
        GetAsyncKeyState(VK_LWIN) < 0 || GetAsyncKeyState(VK_RWIN) < 0) {
        fputs("Paste canceled: release modifier keys first.\n", stderr); return 5;
    }
    _setmode(_fileno(stdin), _O_BINARY);
    char bytes[65537]; size_t length = fread(bytes, 1, sizeof(bytes), stdin);
    if (!length || length > 65536) { fputs("Paste supports up to 16,384 text characters.\n", stderr); return 6; }
    int units = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, bytes, (int)length, NULL, 0);
    if (units < 1 || units > 16384) return 6;
    wchar_t *text = calloc((size_t)units + 1, sizeof(wchar_t));
    if (!text) return 7;
    if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, bytes, (int)length, text, units)) { free(text); return 8; }
    unsigned inserted = 0;
    for (int index = 0; index < units; index++) {
        wchar_t ch = text[index];
        if (ch == L'\r' || ch == L'\n' || ch == L'\t') ch = L' ';
        if (ch < 32 || ch == 127) continue;
        if (!game_focused(pid)) {
            free(text); fputs("Paste stopped because Minecraft lost focus. Some text may already be inserted.\n", stderr); return 9;
        }
        INPUT input[2] = {0};
        input[0].type = input[1].type = INPUT_KEYBOARD;
        input[0].ki.wScan = input[1].ki.wScan = ch;
        input[0].ki.dwFlags = KEYEVENTF_UNICODE;
        input[1].ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
        if (SendInput(2, input, sizeof(INPUT)) != 2) {
            free(text); fputs("Minecraft did not accept the text input.\n", stderr); return 10;
        }
        inserted++; Sleep(2);
    }
    free(text); printf("Sent %u text units. Press Enter yourself only when ready.\n", inserted); return 0;
}
