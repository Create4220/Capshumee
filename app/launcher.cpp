#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <cwchar>

int WINAPI wWinMain(HINSTANCE,HINSTANCE,PWSTR arguments,int) {
    if (wcscmp(arguments,L"--quit")==0) {
        HWND window=FindWindowW(L"CapshumeeWindow",L"卡输咪");
        if(window) PostMessageW(window,WM_CLOSE,0,0);
        return 0;
    }
    wchar_t executable[MAX_PATH], system[MAX_PATH], command[2048];
    if (!GetModuleFileNameW(nullptr,executable,MAX_PATH) || !GetSystemDirectoryW(system,MAX_PATH)) return 1;
    wchar_t* slash=wcsrchr(executable,L'\\');
    if (!slash) return 1;
    *slash=0;
    swprintf(command,2048,L"\"%ls\\WindowsPowerShell\\v1.0\\powershell.exe\" -NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%ls\\run-local.ps1\" -Dictation",system,executable);
    STARTUPINFOW startup{};startup.cb=sizeof(startup);startup.dwFlags=STARTF_USESHOWWINDOW;startup.wShowWindow=SW_HIDE;
    PROCESS_INFORMATION process{};
    if (!CreateProcessW(nullptr,command,nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,executable,&startup,&process)) {
        MessageBoxW(nullptr,L"无法启动。请确认文件夹中的 run-local.ps1 和本地运行组件完整。",L"卡输咪",MB_ICONERROR);
        return 1;
    }
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess,INFINITE);
    DWORD code=1;GetExitCodeProcess(process.hProcess,&code);CloseHandle(process.hProcess);
    if (code) MessageBoxW(nullptr,L"离线保护检查或启动失败。请检查本地文件、Windows 防火墙和程序路径。",L"卡输咪",MB_ICONERROR);
    return code?1:0;
}
