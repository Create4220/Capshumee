"""Win32 Unicode clipboard with Windows history/cloud exclusion markers.

Never reads CF_UNICODETEXT or unrelated clipboard content. Only clears our own
registered format at the start of a new session. Third-party clipboard monitors
are outside this application's control.
"""
import ctypes as C
from ctypes import wintypes as W

FORMATS = (
    ('ExcludeClipboardContentFromMonitorProcessing',b'\x01\x00\x00\x00'),
    ('CanIncludeInClipboardHistory',b'\x00\x00\x00\x00'),
    ('CanUploadToCloudClipboard',b'\x00\x00\x00\x00'),
    ('SenseVoiceLocalDictationSessionPrivateV1',b'SenseVoice-session\x00'),
)

class PrivateClipboard:
    def __init__(self, hwnd):
        self.hwnd=hwnd
        self.user=C.WinDLL('user32',use_last_error=True)
        self.kernel=C.WinDLL('kernel32',use_last_error=True)
        def bind(dll,name,result,args):
            fn=getattr(dll,name);fn.restype=result;fn.argtypes=args
        bind(self.user,'RegisterClipboardFormatW',W.UINT,[W.LPCWSTR])
        bind(self.user,'OpenClipboard',W.BOOL,[W.HWND])
        bind(self.user,'CloseClipboard',W.BOOL,[])
        bind(self.user,'EmptyClipboard',W.BOOL,[])
        bind(self.user,'SetClipboardData',W.HANDLE,[W.UINT,W.HANDLE])
        bind(self.user,'IsClipboardFormatAvailable',W.BOOL,[W.UINT])
        bind(self.user,'CountClipboardFormats',C.c_int,[])
        bind(self.kernel,'GlobalAlloc',W.HGLOBAL,[W.UINT,C.c_size_t])
        bind(self.kernel,'GlobalLock',C.c_void_p,[W.HGLOBAL])
        bind(self.kernel,'GlobalUnlock',W.BOOL,[W.HGLOBAL])
        bind(self.kernel,'GlobalFree',W.HGLOBAL,[W.HGLOBAL])
        self.formats=[(self.user.RegisterClipboardFormatW(name),data) for name,data in FORMATS]
        if any(not code for code,_ in self.formats):raise OSError('CLIPBOARD_FORMAT')
        self.marker=self.formats[-1][0]

    def _allocate(self, data):
        handle=self.kernel.GlobalAlloc(0x2,len(data))  # GMEM_MOVEABLE
        if not handle:raise MemoryError
        pointer=self.kernel.GlobalLock(handle)
        if not pointer:
            self.kernel.GlobalFree(handle);raise MemoryError
        try:C.memmove(pointer,data,len(data))
        finally:self.kernel.GlobalUnlock(handle)
        return handle

    def _write_open(self, text):
        pending=[]
        try:
            for code,data in self.formats+[(13,(text+'\x00').encode('utf-16-le'))]:
                pending.append([code,self._allocate(data)])
            if not self.user.EmptyClipboard():return False
            # Exclusion markers must succeed BEFORE publishing any text.
            for item in pending:
                if not self.user.SetClipboardData(item[0],item[1]):
                    self.user.EmptyClipboard()
                    return False
                item[1]=None  # ownership transferred to Windows
            return True
        except (OSError,MemoryError):
            return False
        finally:
            for _,handle in pending:
                if handle:self.kernel.GlobalFree(handle)

    def write(self, text):
        if not text:return True
        if not self.user.OpenClipboard(self.hwnd):return False
        try:return self._write_open(text)
        finally:self.user.CloseClipboard()

    def clear_previous(self):
        if not self.user.IsClipboardFormatAvailable(self.marker):return True
        if not self.user.OpenClipboard(self.hwnd):return False
        try:
            # Recheck after acquiring the lock; preserve anything copied by others.
            if self.user.IsClipboardFormatAvailable(self.marker):
                return bool(self.user.EmptyClipboard())
            return True
        finally:self.user.CloseClipboard()
