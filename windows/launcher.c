/*
 * cprun.exe - Windows launcher for cprun.
 *
 * Runs the bundled Python with the cprun package:
 *
 *     <install dir>\python\python.exe -I -X utf8 -m cprun <arguments...>
 *
 * The arguments are passed through exactly as typed. The launcher ignores
 * Ctrl+C itself (cprun and the user's program handle it), forwards the exit
 * code, and puts the child in a job object so that closing the launcher also
 * stops cprun.
 *
 * Build (on Linux):  x86_64-w64-mingw32-gcc -municode -O2 -s -o cprun.exe launcher.c
 */
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

static BOOL WINAPI ignore_ctrl(DWORD type) {
    (void)type;
    return TRUE; /* the child process receives Ctrl+C and decides what to do */
}

/* Return the part of the command line after the program name. */
static const wchar_t *skip_program_name(const wchar_t *cmd) {
    if (*cmd == L'"') {
        cmd++;
        while (*cmd && *cmd != L'"') cmd++;
        if (*cmd == L'"') cmd++;
    } else {
        while (*cmd && *cmd != L' ' && *cmd != L'\t') cmd++;
    }
    while (*cmd == L' ' || *cmd == L'\t') cmd++;
    return cmd;
}

static void fail(const wchar_t *what) {
    fwprintf(stderr, L"[CPRUN] Error: %ls (Windows error %lu).\n\n"
                     L"Reinstall cprun with cprun-setup.exe.\n", what, GetLastError());
}

int wmain(void) {
    wchar_t dir[MAX_PATH * 4];
    DWORD n = GetModuleFileNameW(NULL, dir, (DWORD)(sizeof dir / sizeof dir[0]));
    if (n == 0 || n >= sizeof dir / sizeof dir[0]) {
        fail(L"cannot find the cprun installation folder");
        return 5;
    }
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash) *slash = L'\0';

    wchar_t python[MAX_PATH * 4 + 32];
    _snwprintf(python, sizeof python / sizeof python[0], L"%ls\\python\\python.exe", dir);
    python[sizeof python / sizeof python[0] - 1] = L'\0';
    if (GetFileAttributesW(python) == INVALID_FILE_ATTRIBUTES) {
        fail(L"the bundled Python is missing");
        return 5;
    }

    const wchar_t *args = skip_program_name(GetCommandLineW());
    size_t len = wcslen(python) + wcslen(args) + 64;
    wchar_t *cmdline = (wchar_t *)HeapAlloc(GetProcessHeap(), 0, len * sizeof(wchar_t));
    if (!cmdline) {
        fail(L"out of memory");
        return 5;
    }
    _snwprintf(cmdline, len, L"\"%ls\" -I -X utf8 -m cprun %ls", python, args);
    cmdline[len - 1] = L'\0';

    /* Stop cprun (and the program it runs) if this launcher is closed or killed. */
    HANDLE job = CreateJobObjectW(NULL, NULL);
    if (job) {
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION info;
        ZeroMemory(&info, sizeof info);
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(job, JobObjectExtendedLimitInformation, &info, sizeof info);
    }

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof si);
    si.cb = sizeof si;
    ZeroMemory(&pi, sizeof pi);
    SetConsoleCtrlHandler(ignore_ctrl, TRUE);
    if (!CreateProcessW(python, cmdline, NULL, NULL, TRUE, CREATE_SUSPENDED, NULL, NULL, &si, &pi)) {
        fail(L"cannot start the bundled Python");
        return 5;
    }
    if (job) AssignProcessToJobObject(job, pi.hProcess);
    ResumeThread(pi.hThread);
    CloseHandle(pi.hThread);

    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 5;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess);
    return (int)code;
}
