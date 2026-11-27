"""Native editable floating window and local vocabulary manager."""
import ctypes as C
from ctypes import wintypes as W

u=C.WinDLL('user32',use_last_error=True)
SUBPROC=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM)
def bind(name,result,args):
    fn=getattr(u,name);fn.restype=result;fn.argtypes=args;return fn
bind('CreateWindowExW',W.HWND,[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p])
bind('SendMessageW',C.c_ssize_t,[W.HWND,W.UINT,W.WPARAM,W.LPARAM])
bind('SetWindowTextW',W.BOOL,[W.HWND,W.LPCWSTR])
bind('GetWindowTextLengthW',C.c_int,[W.HWND])
bind('GetWindowTextW',C.c_int,[W.HWND,W.LPWSTR,C.c_int])
bind('MoveWindow',W.BOOL,[W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.BOOL])
bind('EnableWindow',W.BOOL,[W.HWND,W.BOOL])
bind('SetFocus',W.HWND,[W.HWND])
bind('GetClientRect',W.BOOL,[W.HWND,C.POINTER(W.RECT)])
bind('GetWindowLongPtrW',C.c_ssize_t,[W.HWND,C.c_int])
bind('SetWindowLongPtrW',C.c_ssize_t,[W.HWND,C.c_int,C.c_ssize_t])
bind('CallWindowProcW',C.c_ssize_t,[C.c_void_p,W.HWND,W.UINT,W.WPARAM,W.LPARAM])
bind('IsDialogMessageW',W.BOOL,[W.HWND,C.POINTER(W.MSG)])
bind('DefWindowProcW',C.c_ssize_t,[W.HWND,W.UINT,W.WPARAM,W.LPARAM])
bind('DestroyWindow',W.BOOL,[W.HWND])
bind('ShowWindow',W.BOOL,[W.HWND,C.c_int])
bind('MessageBoxW',C.c_int,[W.HWND,W.LPCWSTR,W.LPCWSTR,W.UINT])

def send_text(hwnd,message,text,wp=0):
    value=C.create_unicode_buffer(text)
    return u.SendMessageW(hwnd,message,wp,C.addressof(value))

def read_text(hwnd):
    size=u.GetWindowTextLengthW(hwnd)
    value=C.create_unicode_buffer(size+1)
    u.GetWindowTextW(hwnd,value,len(value))
    return value.value

class FloatingEditor:
    def __init__(self,app):
        self.app=app;self.hwnd=app.hwnd;self.positioned=False;self.refreshing=False
        self.edit=self.control('EDIT','',0x50211144,201)
        self.copy=self.control('BUTTON','复制',0x50010001,202)
        self.cancel=self.control('BUTTON','取消',0x50010000,203)
        # Large multiline draft; scrolling is native, not a truncated preview.
        u.SendMessageW(self.edit,0xC5,1000000,0)
        self.editproc=SUBPROC(self.edit_proc)
        self.old_editproc=u.SetWindowLongPtrW(self.edit,-4,C.cast(self.editproc,C.c_void_p).value)
        if not self.old_editproc:raise OSError('EDIT_SUBCLASS')
        self.layout();self.editable(False)
    def control(self,kind,title,style,identifier):
        h=u.CreateWindowExW(0x200 if kind=='EDIT' else 0,kind,title,style,
                           16,54,100,40,self.hwnd,W.HMENU(identifier),None,None)
        if not h:raise OSError('EDITOR_CONTROL')
        u.SendMessageW(h,0x30,self.app.font,1)
        return h
    def layout(self):
        rect=W.RECT();u.GetClientRect(self.hwnd,C.byref(rect))
        width=max(300,rect.right);height=max(210,rect.bottom)
        u.MoveWindow(self.edit,16,54,width-32,max(80,height-118),True)
        u.MoveWindow(self.copy,width-220,height-48,96,32,True)
        u.MoveWindow(self.cancel,width-112,height-48,96,32,True)
    def editable(self,ready):
        u.SendMessageW(self.edit,0xCF,not ready,0)
        u.EnableWindow(self.copy,bool(ready))
        style=u.GetWindowLongPtrW(self.hwnd,-20)
        u.SetWindowLongPtrW(self.hwnd,-20,style&~0x08000000 if ready else style|0x08000000)
    def set_text(self,text):
        u.SetWindowTextW(self.edit,text.replace('\r\n','\n').replace('\n','\r\n'))
        # Follow new speech only while read-only; never reset user's editor caret.
        u.SendMessageW(self.edit,0xB1,-1,-1)
        u.SendMessageW(self.edit,0xB7,0,0)
    def text(self):return read_text(self.edit)
    def edit_proc(self,hwnd,message,wp,lp):
        try:
            # Native Ctrl+C / Cut also use private Windows clipboard markers.
            # Learning is intentionally only on the whole-draft Copy button.
            if message in (0x301,0x300):
                if not self.app.draft.finished:return 0
                start=C.c_uint();end=C.c_uint()
                u.SendMessageW(hwnd,0xB0,C.addressof(start),C.addressof(end))
                data=self.text().encode('utf-16-le')[start.value*2:end.value*2]
                if data and self.app.clipboard.write(data.decode('utf-16-le','replace')):
                    if message==0x300:send_text(hwnd,0xC2,'',1)
                return 0
            return u.CallWindowProcW(C.c_void_p(self.old_editproc),hwnd,message,wp,lp)
        except Exception:return 0

class VocabularyWindow:
    def __init__(self,app,gui):
        self.app=app;self.gui=gui;self.hwnd=None;self.ids=[]
        self.proc=gui.WNDPROC(self.window_proc)
        self.name='CapshumeeVocabulary'
        wc=gui.WNDCLASS();wc.lpfnWndProc=self.proc
        wc.hInstance=gui.kernel.GetModuleHandleW(None);wc.lpszClassName=self.name
        wc.hCursor=gui.user.LoadCursorW(None,C.c_void_p(32512));wc.hbrBackground=W.HBRUSH(6)
        if not gui.user.RegisterClassW(C.byref(wc)) and C.get_last_error()!=1410:raise OSError('VOCABULARY_CLASS')
    def control(self,kind,title,style,x,y,w,h,identifier):
        handle=u.CreateWindowExW(0,kind,title,style,x,y,w,h,self.hwnd,W.HMENU(identifier),None,None)
        if not handle:raise OSError('VOCABULARY_CONTROL')
        u.SendMessageW(handle,0x30,self.app.font,1)
        return handle
    def open(self):
        if self.hwnd:
            u.ShowWindow(self.hwnd,5);self.gui.user.SetForegroundWindow(self.hwnd);self.refresh();return
        self.hwnd=u.CreateWindowExW(0x10080,self.name,'偏好词库 · 仅本机保存',0x00C80000,
                                   180,160,660,470,None,None,self.gui.kernel.GetModuleHandleW(None),None)
        if not self.hwnd:raise OSError('VOCABULARY_WINDOW')
        self.control('STATIC','复制确认后学习词语修正；不保存完整录音和整篇文字。',0x50000000,16,14,610,28,300)
        self.enabled=self.control('BUTTON','启用本地调词与学习',0x50010003,16,46,500,30,301)
        self.list=self.control('LISTBOX','',0x50B10101,16,88,610,260,302)
        u.SendMessageW(self.list,0x194,1200,0)
        for label,x,w,identifier in [('删除选中',16,110,303),('清空词库',138,110,304),('关闭',516,110,305)]:
            self.control('BUTTON',label,0x50010000,x,366,w,34,identifier)
        u.SendMessageW(self.hwnd,0x80,0,self.app.small_icon);u.SendMessageW(self.hwnd,0x80,1,self.app.large_icon)
        self.refresh();u.ShowWindow(self.hwnd,5);self.gui.user.SetForegroundWindow(self.hwnd)
    def refresh(self):
        if not self.hwnd:return
        u.SendMessageW(self.enabled,0xF1,int(self.app.preferences.enabled),0)
        u.SendMessageW(self.list,0x184,0,0)
        self.ids=[]
        for rule in self.app.preferences.snapshot():
            mode='已停用' if not rule['enabled'] else ('通用' if rule['count']>=3 and len(rule['source'])>=2 else '上下文优先')
            label=f"{rule['source']} → {rule['target']}    已确认 {rule['count']} 次 · {mode}"
            send_text(self.list,0x180,label);self.ids.append(rule['id'])
        if not self.ids:send_text(self.list,0x180,'还没有偏好词。停止录音、修改文字并点击复制后，将自动积累。')
    def window_proc(self,hwnd,message,wp,lp):
        try:
            if message==0x111:
                command=wp&0xFFFF
                if command==301:
                    self.app.preferences.set_enabled(bool(u.SendMessageW(self.enabled,0xF0,0,0)));self.refresh()
                elif command==303:
                    index=u.SendMessageW(self.list,0x188,0,0)
                    if 0<=index<len(self.ids):self.app.preferences.delete(self.ids[index]);self.refresh()
                elif command==304:
                    if u.MessageBoxW(hwnd,'清空所有本地偏好词？此操作不会清除当前草稿。','清空词库',0x24)==6:
                        self.app.preferences.clear();self.refresh()
                elif command==305:u.DestroyWindow(hwnd)
                return 0
            if message==0x10:u.DestroyWindow(hwnd);return 0
            if message==2:self.hwnd=None;return 0
        except Exception:
            u.MessageBoxW(hwnd,'本地词库无法保存，请检查当前用户目录的写入权限。','偏好词库',0x10)
        return u.DefWindowProcW(hwnd,message,wp,lp)

