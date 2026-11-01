"""Local tray dictation; session-only clipboard fallback after recording ends."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import queue
import secrets
import struct
import subprocess
import sys
sys.dont_write_bytecode = True
import threading
import time
import winreg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'app'))
from offline_policy import require_dedicated_host
from inference_guard import audit
from dictation_worker import encode_command
from session_buffer import SessionBuffer
from private_clipboard import PrivateClipboard

user = C.WinDLL('user32', use_last_error=True)
kernel = C.WinDLL('kernel32', use_last_error=True)
shell = C.WinDLL('shell32', use_last_error=True)
gdi = C.WinDLL('gdi32', use_last_error=True)
winmm = C.WinDLL('winmm', use_last_error=True)
LRESULT = C.c_ssize_t
ULONG_PTR = C.c_size_t
WNDPROC = C.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
HOOKPROC = C.WINFUNCTYPE(LRESULT, C.c_int, W.WPARAM, W.LPARAM)

class WNDCLASS(C.Structure):
    _fields_ = [('style',W.UINT),('lpfnWndProc',WNDPROC),('cbClsExtra',C.c_int),
                ('cbWndExtra',C.c_int),('hInstance',W.HINSTANCE),('hIcon',W.HICON),
                ('hCursor',W.HANDLE),('hbrBackground',W.HBRUSH),('lpszMenuName',W.LPCWSTR),('lpszClassName',W.LPCWSTR)]
class NID(C.Structure):
    _fields_ = [('cbSize',W.DWORD),('hWnd',W.HWND),('uID',W.UINT),('uFlags',W.UINT),
                ('uCallbackMessage',W.UINT),('hIcon',W.HICON),('szTip',W.WCHAR*128),
                ('dwState',W.DWORD),('dwStateMask',W.DWORD),('szInfo',W.WCHAR*256),
                ('uVersion',W.UINT),('szInfoTitle',W.WCHAR*64),('dwInfoFlags',W.DWORD),('guidItem',C.c_byte*16),('hBalloonIcon',W.HICON)]
class PAINT(C.Structure):
    _fields_ = [('hdc',W.HDC),('fErase',W.BOOL),('rcPaint',W.RECT),('fRestore',W.BOOL),('fIncUpdate',W.BOOL),('rgbReserved',C.c_byte*32)]
class KBD(C.Structure):
    _fields_ = [('vkCode',W.DWORD),('scanCode',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('dwExtraInfo',ULONG_PTR)]
class GUITHREAD(C.Structure):
    _fields_ = [('cbSize',W.DWORD),('flags',W.DWORD),('hwndActive',W.HWND),('hwndFocus',W.HWND),
                ('hwndCapture',W.HWND),('hwndMenuOwner',W.HWND),('hwndMoveSize',W.HWND),('hwndCaret',W.HWND),('rcCaret',W.RECT)]
class KEYBDINPUT(C.Structure):
    _fields_ = [('wVk',W.WORD),('wScan',W.WORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',ULONG_PTR)]
class MOUSEINPUT(C.Structure):
    _fields_ = [('dx',W.LONG),('dy',W.LONG),('mouseData',W.DWORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',ULONG_PTR)]
class INPUTUNION(C.Union):
    _fields_ = [('ki',KEYBDINPUT),('mi',MOUSEINPUT)]
class INPUT(C.Structure):
    _anonymous_ = ('value',)
    _fields_ = [('type',W.DWORD),('value',INPUTUNION)]
class WAVEFORMAT(C.Structure):
    _fields_ = [('wFormatTag',W.WORD),('nChannels',W.WORD),('nSamplesPerSec',W.DWORD),
                ('nAvgBytesPerSec',W.DWORD),('nBlockAlign',W.WORD),('wBitsPerSample',W.WORD),('cbSize',W.WORD)]
class WAVEHDR(C.Structure):
    pass
WAVEHDR._fields_ = [('lpData',C.c_void_p),('dwBufferLength',W.DWORD),('dwBytesRecorded',W.DWORD),
                   ('dwUser',ULONG_PTR),('dwFlags',W.DWORD),('dwLoops',W.DWORD),('lpNext',C.POINTER(WAVEHDR)),('reserved',ULONG_PTR)]

def api(dll, name, result, args):
    fn = getattr(dll, name);fn.restype=result;fn.argtypes=args;return fn
api(kernel,'GetModuleHandleW',W.HMODULE,[W.LPCWSTR])
api(kernel,'CreateMutexW',W.HANDLE,[C.c_void_p,W.BOOL,W.LPCWSTR])
api(kernel,'CloseHandle',W.BOOL,[W.HANDLE])
api(user,'RegisterClassW',W.ATOM,[C.POINTER(WNDCLASS)])
api(user,'CreateWindowExW',W.HWND,[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p])
api(user,'DefWindowProcW',LRESULT,[W.HWND,W.UINT,W.WPARAM,W.LPARAM])
api(user,'PostMessageW',W.BOOL,[W.HWND,W.UINT,W.WPARAM,W.LPARAM])
api(user,'GetMessageW',C.c_int,[C.POINTER(W.MSG),W.HWND,W.UINT,W.UINT])
api(user,'PeekMessageW',W.BOOL,[C.POINTER(W.MSG),W.HWND,W.UINT,W.UINT,W.UINT])
api(user,'TranslateMessage',W.BOOL,[C.POINTER(W.MSG)])
api(user,'DispatchMessageW',LRESULT,[C.POINTER(W.MSG)])
api(user,'DestroyWindow',W.BOOL,[W.HWND])
api(user,'ShowWindow',W.BOOL,[W.HWND,C.c_int])
api(user,'SetWindowPos',W.BOOL,[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT])
api(user,'SetTimer',ULONG_PTR,[W.HWND,ULONG_PTR,W.UINT,C.c_void_p])
api(user,'KillTimer',W.BOOL,[W.HWND,ULONG_PTR])
api(user,'GetForegroundWindow',W.HWND,[])
api(user,'SetForegroundWindow',W.BOOL,[W.HWND])
api(user,'GetWindowThreadProcessId',W.DWORD,[W.HWND,C.POINTER(W.DWORD)])
api(user,'GetGUIThreadInfo',W.BOOL,[W.DWORD,C.POINTER(GUITHREAD)])
api(user,'GetKeyState',C.c_short,[C.c_int])
api(user,'GetAsyncKeyState',C.c_short,[C.c_int])
api(user,'GetCursorPos',W.BOOL,[C.POINTER(W.POINT)])
api(user,'CreatePopupMenu',W.HMENU,[])
api(user,'AppendMenuW',W.BOOL,[W.HMENU,W.UINT,ULONG_PTR,W.LPCWSTR])
api(user,'TrackPopupMenu',W.UINT,[W.HMENU,W.UINT,C.c_int,C.c_int,C.c_int,W.HWND,C.c_void_p])
api(user,'DestroyMenu',W.BOOL,[W.HMENU])
api(user,'SetWindowsHookExW',W.HANDLE,[C.c_int,HOOKPROC,W.HINSTANCE,W.DWORD])
api(user,'UnhookWindowsHookEx',W.BOOL,[W.HANDLE])
api(user,'CallNextHookEx',LRESULT,[W.HANDLE,C.c_int,W.WPARAM,W.LPARAM])
api(user,'LoadIconW',W.HICON,[W.HINSTANCE,C.c_void_p])
api(user,'LoadImageW',W.HANDLE,[W.HINSTANCE,W.LPCWSTR,W.UINT,C.c_int,C.c_int,W.UINT])
api(user,'SendMessageW',LRESULT,[W.HWND,W.UINT,W.WPARAM,W.LPARAM])
api(user,'DrawIconEx',W.BOOL,[W.HDC,C.c_int,C.c_int,W.HICON,C.c_int,C.c_int,W.UINT,W.HBRUSH,W.UINT])
api(user,'DestroyIcon',W.BOOL,[W.HICON])
api(user,'LoadCursorW',W.HANDLE,[W.HINSTANCE,C.c_void_p])
api(user,'InvalidateRect',W.BOOL,[W.HWND,C.POINTER(W.RECT),W.BOOL])
api(user,'BeginPaint',W.HDC,[W.HWND,C.POINTER(PAINT)])
api(user,'EndPaint',W.BOOL,[W.HWND,C.POINTER(PAINT)])
api(user,'GetClientRect',W.BOOL,[W.HWND,C.POINTER(W.RECT)])
api(user,'FillRect',C.c_int,[W.HDC,C.POINTER(W.RECT),W.HBRUSH])
api(user,'DrawTextW',C.c_int,[W.HDC,W.LPCWSTR,C.c_int,C.POINTER(W.RECT),W.UINT])
api(user,'SystemParametersInfoW',W.BOOL,[W.UINT,W.UINT,C.c_void_p,W.UINT])
api(user,'MessageBoxW',C.c_int,[W.HWND,W.LPCWSTR,W.LPCWSTR,W.UINT])
api(user,'SendInput',W.UINT,[W.UINT,C.POINTER(INPUT),C.c_int])
api(user,'RegisterWindowMessageW',W.UINT,[W.LPCWSTR])
api(shell,'Shell_NotifyIconW',W.BOOL,[W.DWORD,C.POINTER(NID)])
api(gdi,'CreateSolidBrush',W.HBRUSH,[W.DWORD])
api(gdi,'DeleteObject',W.BOOL,[W.HANDLE])
api(gdi,'SetTextColor',W.DWORD,[W.HDC,W.DWORD])
api(gdi,'SetBkMode',C.c_int,[W.HDC,C.c_int])
api(gdi,'SelectObject',W.HANDLE,[W.HDC,W.HANDLE])
api(gdi,'GetStockObject',W.HANDLE,[C.c_int])
api(gdi,'CreateFontW',W.HANDLE,[C.c_int,C.c_int,C.c_int,C.c_int,C.c_int,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.LPCWSTR])
api(winmm,'waveInGetNumDevs',W.UINT,[])
api(winmm,'waveInOpen',W.UINT,[C.POINTER(W.HANDLE),W.UINT,C.POINTER(WAVEFORMAT),ULONG_PTR,ULONG_PTR,W.DWORD])
for name in ('waveInPrepareHeader','waveInUnprepareHeader','waveInAddBuffer'):
    api(winmm,name,W.UINT,[W.HANDLE,C.POINTER(WAVEHDR),W.UINT])
for name in ('waveInStart','waveInReset','waveInClose'):
    api(winmm,name,W.UINT,[W.HANDLE])

WM_TRAY, WM_RESULT, WM_CAPS = 0x8001, 0x8002, 0x8003
WM_WIM_DATA = 0x3C0
APP_NAME = '卡输咪'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = '卡输咪'

def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY) as key:
            return winreg.QueryValueEx(key,RUN_NAME)[0] == startup_command()
    except OSError:
        return False

def startup_command():
    return '"'+str(ROOT/'卡输咪.exe')+'"'

def set_startup(enabled):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key,RUN_NAME,0,winreg.REG_SZ,startup_command())
        else:
            try:winreg.DeleteValue(key,RUN_NAME)
            except FileNotFoundError:pass

def focus_target():
    foreground = user.GetForegroundWindow()
    info = GUITHREAD();info.cbSize=C.sizeof(info)
    tid = user.GetWindowThreadProcessId(foreground,None) if foreground else 0
    focus = info.hwndFocus if tid and user.GetGUIThreadInfo(tid,C.byref(info)) else None
    return foreground, focus

def insert_text(text, target):
    if not text:
        return True
    if not target[0] or focus_target() != target:
        return False
    if any(user.GetAsyncKeyState(vk)&0x8000 for vk in (0x10,0x11,0x12,0x5B,0x5C)):
        return False
    units = struct.unpack('<'+'H'*(len(text.encode('utf-16-le'))//2),text.encode('utf-16-le'))
    inputs = (INPUT*(len(units)*2))()
    for i,unit in enumerate(units):
        for release in (0,1):
            item=inputs[2*i+release];item.type=1
            item.ki=KEYBDINPUT(0,unit,4|(2 if release else 0),0,0)
    # Single batch prevents other key events interleaving inside a sentence.
    return user.SendInput(len(inputs),inputs,C.sizeof(INPUT)) == len(inputs)

class Audio:
    def __init__(self, owner):
        self.owner=owner;self.handle=None;self.buffers=[];self.session=0

    def start(self, session):
        self.session=session
        fmt=WAVEFORMAT(1,1,16000,32000,2,16,0)
        handle=W.HANDLE()
        code=winmm.waveInOpen(C.byref(handle),0xFFFFFFFF,C.byref(fmt),self.owner.hwnd,0,0x10000)
        if code:
            raise OSError('MICROPHONE_OPEN_'+str(code))
        self.handle=handle
        try:
            for _ in range(8):
                raw=C.create_string_buffer(3200)
                header=WAVEHDR(C.cast(raw,C.c_void_p),3200,0,session,0,0,None,0)
                self.buffers.append((raw,header))
                if winmm.waveInPrepareHeader(handle,C.byref(header),C.sizeof(header)):
                    raise OSError('MICROPHONE_PREPARE')
                if winmm.waveInAddBuffer(handle,C.byref(header),C.sizeof(header)):
                    raise OSError('MICROPHONE_BUFFER')
            if winmm.waveInStart(handle):raise OSError('MICROPHONE_START')
        except Exception:
            self.stop();raise

    def data(self, pointer, requeue=True):
        if not self.handle:return
        header=C.cast(pointer,C.POINTER(WAVEHDR)).contents
        if header.dwUser != self.session:return
        if header.dwBytesRecorded:
            self.owner.send('A',self.session,C.string_at(header.lpData,header.dwBytesRecorded))
        if requeue:
            header.dwBytesRecorded=0
            winmm.waveInAddBuffer(self.handle,C.byref(header),C.sizeof(header))

    def stop(self):
        if not self.handle:return
        winmm.waveInReset(self.handle)
        # Reset returns pending buffers via window messages. Drain before freeing headers.
        msg=W.MSG()
        while user.PeekMessageW(C.byref(msg),self.owner.hwnd,WM_WIM_DATA,WM_WIM_DATA,1):
            self.data(msg.lParam,False)
        for _,header in self.buffers:
            winmm.waveInUnprepareHeader(self.handle,C.byref(header),C.sizeof(header))
        winmm.waveInClose(self.handle)
        self.handle=None;self.buffers=[]

class App:
    def __init__(self, test_mode=False):
        require_dedicated_host()
        self.test_mode=test_mode;self.enabled=True;self.recording=False;self.ready=False
        self.closing=False;self.session=0;self.session_buffer=SessionBuffer();self.caps_down=False
        self.clipboard_copy_failed=False
        self.caps_state=bool(user.GetKeyState(0x14)&1)
        self.status='正在准备本地识别…';self.preview='';self.hide_at=0;self.error=False
        self.inbox=queue.Queue();self.outbox=queue.Queue(maxsize=300)
        self.hook=None;self.process=None;self.dropped=False
        self.wndproc=WNDPROC(self.window_proc);self.hookproc=HOOKPROC(self.key_hook)
        instance=kernel.GetModuleHandleW(None)
        self.classname='CapshumeeWindow'
        wc=WNDCLASS();wc.lpfnWndProc=self.wndproc;wc.hInstance=instance
        wc.lpszClassName=self.classname;wc.hCursor=user.LoadCursorW(None,C.c_void_p(32512))
        if not user.RegisterClassW(C.byref(wc)) and C.get_last_error()!=1410:
            raise OSError('WINDOW_CLASS')
        self.hwnd=user.CreateWindowExW(0x08000000|0x80|0x8,self.classname,APP_NAME,0x80000000,0,0,470,142,None,None,instance,None)
        if not self.hwnd:raise OSError('WINDOW_CREATE')
        self.audio=Audio(self)
        self.clipboard=PrivateClipboard(self.hwnd)
        self.font=gdi.CreateFontW(-18,0,0,0,400,0,0,0,1,0,0,5,0,'Microsoft YaHei UI')
        self.nid=NID();self.nid.cbSize=C.sizeof(self.nid);self.nid.hWnd=self.hwnd
        self.nid.uID=1;self.nid.uFlags=1|2|4;self.nid.uCallbackMessage=WM_TRAY
        self.small_icon=user.LoadImageW(None,str(ROOT/'assets/capshumee.ico'),1,16,16,0x10)
        self.large_icon=user.LoadImageW(None,str(ROOT/'assets/capshumee.ico'),1,32,32,0x10)
        if not self.small_icon or not self.large_icon:raise OSError('APPLICATION_ICON')
        self.nid.hIcon=self.small_icon
        user.SendMessageW(self.hwnd,0x80,0,self.small_icon)
        user.SendMessageW(self.hwnd,0x80,1,self.large_icon)
        self.nid.szTip=APP_NAME+' · 本地离线 · 等待 Caps Lock'
        self.taskbar_message=user.RegisterWindowMessageW('TaskbarCreated')
        if not test_mode:
            shell.Shell_NotifyIconW(0,C.byref(self.nid))
        self.token=secrets.token_hex(16)
        # One fixed local child, before installing the GUI's deny-all subprocess hook.
        self.process=subprocess.Popen([str(ROOT/'runtime/host/asr-python.exe'),'-I','-B',
            str(ROOT/'app/dictation_worker.py'),'--pipe-token',self.token],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            cwd=ROOT,creationflags=0x08000000,bufsize=0)
        sys.addaudithook(audit)
        threading.Thread(target=self.writer,daemon=True).start()
        threading.Thread(target=self.reader,daemon=True).start()
        self.send('H',0,self.token.encode('ascii'))
        if not test_mode:
            self.hook=user.SetWindowsHookExW(13,self.hookproc,instance,0)
            if not self.hook:raise OSError('CAPS_HOOK')
        user.SetTimer(self.hwnd,1,200,None)

    def send(self, kind, session=0, payload=b''):
        try:self.outbox.put_nowait(encode_command(kind,session,payload))
        except queue.Full:
            if not self.dropped:
                self.dropped=True
                self.inbox.put({'kind':'error','code':'AUDIO_BACKLOG'})
                user.PostMessageW(self.hwnd,WM_RESULT,0,0)

    def writer(self):
        try:
            while True:
                body=self.outbox.get()
                if body is None:break
                self.process.stdin.write(body)
                self.process.stdin.flush()
        except (OSError,ValueError):
            pass
        finally:
            try:self.process.stdin.close()
            except (OSError,ValueError):pass

    def reader(self):
        try:
            for line in self.process.stdout:
                if len(line)>32768:break
                self.inbox.put(json.loads(line.decode('utf-8')))
                user.PostMessageW(self.hwnd,WM_RESULT,0,0)
        except (OSError,ValueError):pass
        finally:
            self.inbox.put({'kind':'worker_exited'})
            user.PostMessageW(self.hwnd,WM_RESULT,0,0)

    def key_hook(self, code, wp, lp):
        if code>=0:
            key=C.cast(lp,C.POINTER(KBD)).contents
            if key.vkCode==0x14:
                if wp in (0x100,0x104) and not self.caps_down:
                    self.caps_down=True;self.caps_state=not self.caps_state
                    user.PostMessageW(self.hwnd,WM_CAPS,int(self.caps_state),0)
                elif wp in (0x101,0x105):self.caps_down=False
        return user.CallNextHookEx(self.hook,code,wp,lp)

    def show(self, seconds=0):
        area=W.RECT();user.SystemParametersInfoW(48,0,C.byref(area),0)
        user.SetWindowPos(self.hwnd,W.HWND(-1),area.right-490,area.bottom-165,470,142,0x10)
        user.ShowWindow(self.hwnd,4)
        self.hide_at=time.monotonic()+seconds if seconds else 0
        user.InvalidateRect(self.hwnd,None,False)

    def update_tray(self):
        label='录音中' if self.recording else ('已暂停' if not self.enabled else '等待 Caps Lock')
        self.nid.szTip=APP_NAME+' · '+label+' · 完全本地'
        if not self.test_mode:
            shell.Shell_NotifyIconW(1,C.byref(self.nid))

    def start(self):
        if self.recording or not self.enabled:return
        if not self.ready or self.error:
            self.status='识别器尚未就绪，请稍后再按 Caps Lock';self.show(4);return
        if not self.clipboard.clear_previous():
            self.status='剪贴板被占用，请稍后重新按 Caps Lock';self.show(5);return
        self.session+=1;self.preview='';self.dropped=False
        self.clipboard_copy_failed=False
        self.session_buffer.begin(self.session,focus_target())
        self.send('S',self.session)
        try:
            self.audio.start(self.session)
        except OSError:
            self.session_buffer.stopping(self.session,True)
            self.send('E',self.session)
            self.status='无法打开麦克风：请检查默认输入设备及麦克风权限'
            self.show(8);return
        self.recording=True
        self.status='● 正在录音 · Caps Lock 熄灭即停止'
        self.preview='边说边预览，停顿后输入当前窗口'
        self.show();self.update_tray()

    def stop(self):
        if not self.recording:return
        self.audio.stop();self.recording=False
        self.session_buffer.stopping(self.session,focus_target()==self.session_buffer.target)
        self.send('E',self.session)
        self.status='已停止录音，正在整理最后一句…'
        self.show();self.update_tray()

    def results(self):
        while True:
            try:message=self.inbox.get_nowait()
            except queue.Empty:break
            kind=message.get('kind')
            if kind=='ready':
                self.ready=True;self.status='已就绪 · Caps Lock 亮起开始录音'
            elif kind in ('partial','final'):
                if self.error:continue
                text=message.get('text','');session=message.get('session')
                if not self.session_buffer.accepts(session):continue
                if session==self.session:
                    self.preview=text[-180:];user.InvalidateRect(self.hwnd,None,False)
                if kind=='final' and text:
                    outcome=self.session_buffer.final(session,text,insert_text)
                    if outcome=='fallback':
                        self.status='本轮已暂存 · 停止后右键托盘复制'
                        self.preview=self.session_buffer.text[-180:];self.show()
                    elif outcome=='inserted' and not self.recording:
                        self.status='已输入 · 麦克风已关闭';self.show(3)
            elif kind=='stopped' and not self.recording and message.get('session')==self.session:
                if focus_target()!=self.session_buffer.target:
                    self.session_buffer.target_changed()
                outcome=self.session_buffer.complete(self.session)
                if outcome=='buffered':
                    self.status='本轮已暂存 · 右键托盘复制本轮输出';self.show(8)
                elif outcome!='stale':
                    self.status='已停止 · 麦克风已关闭';self.show(3)
            elif kind=='unloaded':
                if not self.recording:self.preview='';self.status='模型内存已释放 · 等待 Caps Lock'
            elif kind=='engine_phase' and message.get('step')=='model' and self.recording and not self.session_buffer.fallback:
                self.status='● 正在加载本地模型 · 录音继续'
                user.InvalidateRect(self.hwnd,None,False)
            elif kind=='engine_phase' and message.get('step')=='loaded' and self.recording and not self.session_buffer.fallback:
                self.status='● 正在录音 · Caps Lock 熄灭即停止'
                user.InvalidateRect(self.hwnd,None,False)
            elif kind in ('error','worker_exited') and not self.closing:
                self.error=True;self.stop()
                self.status='识别进程异常，请从托盘退出后重新启动'
                self.preview='未保存录音；未联网';self.show(10)
        self.update_tray()

    def menu(self):
        menu=user.CreatePopupMenu()
        user.AppendMenuW(menu,1 if not self.ready else 0,101,'暂停 Caps Lock 输入' if self.enabled else '启用 Caps Lock 输入')
        user.AppendMenuW(menu,1 if self.recording else 0,102,'释放模型内存')
        user.AppendMenuW(menu,1 if self.recording else 0,103,'开机自启：'+('已开启' if startup_enabled() else '已关闭'))
        user.AppendMenuW(menu,0,104,'使用说明 / 隐私')
        user.AppendMenuW(menu,0 if self.session_buffer.finished and self.session_buffer.text else 1,106,'复制本轮输出')
        user.AppendMenuW(menu,0x800,0,None)
        user.AppendMenuW(menu,0,105,'退出')
        point=W.POINT();user.GetCursorPos(C.byref(point));user.SetForegroundWindow(self.hwnd)
        command=user.TrackPopupMenu(menu,0x100|0x2,point.x,point.y,0,self.hwnd,None)
        user.DestroyMenu(menu);user.PostMessageW(self.hwnd,0,0,0)
        if command==101:
            self.stop();self.enabled=not self.enabled;self.update_tray()
        elif command==102:self.send('U')
        elif command==103:
            try:set_startup(not startup_enabled())
            except OSError:user.MessageBoxW(self.hwnd,'无法修改当前用户的开机启动项。',APP_NAME,0x10)
        elif command==104:
            user.MessageBoxW(self.hwnd,
                'Caps Lock 亮起：录音；熄灭：停止。\n停顿后自动输入；目标切换或写入失败时，\n停止后只暂存；右键托盘“复制本轮输出”才复制。\n下一轮清空缓存及仍属于本程序的剪贴板内容。\n\n全部识别在本机完成，不保存录音。\n剪贴板带 Windows 禁同步、禁历史记录标记。\n文字粘贴到其他软件后由该软件处理。\n模型空闲 90 秒释放。\n\n右键托盘可暂停、自启开关或退出。',APP_NAME,0)
        elif command==106:
            if self.session_buffer.retry_copy(self.clipboard.write):
                self.clipboard_copy_failed=False
                self.status='本轮全部文字已复制 · 可按 Ctrl+V 粘贴';self.show(8)
            else:
                self.clipboard_copy_failed=True
                self.status='剪贴板被占用 · 请稍后重试复制';self.show(8)
        elif command==105:user.DestroyWindow(self.hwnd)

    def paint(self):
        ps=PAINT();dc=user.BeginPaint(self.hwnd,C.byref(ps));rect=W.RECT()
        user.GetClientRect(self.hwnd,C.byref(rect))
        brush=gdi.CreateSolidBrush(0x00251B16);user.FillRect(dc,C.byref(rect),brush);gdi.DeleteObject(brush)
        old=gdi.SelectObject(dc,self.font);gdi.SetBkMode(dc,1)
        gdi.SetTextColor(dc,0x00C5EAA3 if self.recording else 0x00E6DFD3)
        user.DrawIconEx(dc,16,12,self.large_icon,24,24,0,None,3)
        title=W.RECT(52,12,452,38);user.DrawTextW(dc,self.status,-1,C.byref(title),0x20|0x8000)
        gdi.SetTextColor(dc,0x00F8F7F4)
        body=W.RECT(18,48,452,126);user.DrawTextW(dc,self.preview,-1,C.byref(body),0x10|0x8000)
        gdi.SelectObject(dc,old);user.EndPaint(self.hwnd,C.byref(ps))

    def window_proc(self, hwnd, message, wp, lp):
        try:
            if message==WM_CAPS:
                if wp:self.start()
                else:self.stop()
                return 0
            if message==WM_WIM_DATA:
                self.audio.data(lp);return 0
            if message==WM_RESULT:self.results();return 0
            if message==WM_TRAY and (lp&0xFFFF) in (0x205,0x203):self.menu();return 0
            if hasattr(self,'taskbar_message') and message==self.taskbar_message:
                if not self.test_mode:shell.Shell_NotifyIconW(0,C.byref(self.nid))
                return 0
            if message==0xF:
                if hasattr(self,'font'):self.paint();return 0
            if message==0x14:return 1
            if message==0x21:return 3  # MA_NOACTIVATE: preview never steals the caret.
            if message==0x113:
                if self.recording and not self.session_buffer.fallback and focus_target()!=self.session_buffer.target:
                    self.session_buffer.target_changed()
                    self.status='目标已切换 · 本轮结果仅暂存'
                    user.InvalidateRect(self.hwnd,None,False)
                if self.hide_at and time.monotonic()>=self.hide_at and not self.recording:
                    self.preview='';self.hide_at=0;user.ShowWindow(self.hwnd,0)
                return 0
            if message==0x10:user.DestroyWindow(hwnd);return 0
            if message==2:
                self.close();user.PostQuitMessage(0);return 0
        except Exception:
            # Never log exception arguments or application text.
            if hasattr(self,'status'):
                self.status='本地输入发生错误，请退出后重试'
        return user.DefWindowProcW(hwnd,message,wp,lp)

    def close(self):
        if self.closing:return
        self.closing=True
        if self.hook:user.UnhookWindowsHookEx(self.hook)
        self.audio.stop();self.recording=False
        self.update_tray()
        if not self.test_mode:shell.Shell_NotifyIconW(2,C.byref(self.nid))
        user.KillTimer(self.hwnd,1)
        self.send('Q')
        try:self.outbox.put_nowait(None)
        except queue.Full:pass
        if self.process:
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.terminate()
        if hasattr(self,'font'):gdi.DeleteObject(self.font)
        if hasattr(self,'small_icon'):user.DestroyIcon(self.small_icon)
        if hasattr(self,'large_icon'):user.DestroyIcon(self.large_icon)

    def run(self):
        msg=W.MSG()
        while user.GetMessageW(C.byref(msg),None,0,0)>0:
            user.TranslateMessage(C.byref(msg));user.DispatchMessageW(C.byref(msg))

def main():
    require_dedicated_host()
    mutex=kernel.CreateMutexW(None,False,'Local\\Capshumee')
    if C.get_last_error()==183:
        kernel.CloseHandle(mutex);return
    try:
        app=App();app.run()
    except Exception:
        user.MessageBoxW(None,'卡输咪启动失败。请检查本地文件和离线保护设置。',APP_NAME,0x10)
    finally:
        kernel.CloseHandle(mutex)

if __name__=='__main__':
    main()
