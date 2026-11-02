"""Opt-in native keyboard integration; fake recorder, no microphone/clipboard.

Close the running app first. Run with CAPSHUMEE_TEST_KEYS=1 on Windows.
The test restores the initial lock state and never reads any editor content.
"""
import os
from pathlib import Path
import sys
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))


@unittest.skipUnless(sys.platform=='win32' and os.environ.get('CAPSHUMEE_TEST_KEYS')=='1',
                     'Opt-in native keyboard test')
class NativeCaps(unittest.TestCase):
    def test_background_poll_hook_and_missing_events(self):
        import ctypes as C
        from ctypes import wintypes as W
        from types import SimpleNamespace
        import dictation_app as g
        g.api(g.user,'FindWindowW',W.HWND,[W.LPCWSTR,W.LPCWSTR])
        if g.user.FindWindowW('CapshumeeWindow','卡输咪'):
            self.fail('Exit the running app before the synthetic keyboard test')

        class Harness(g.App):
            def __init__(self):
                from caps_state import CapsState
                self.caps=CapsState();self.test_mode=False;self.closing=False
                self.enabled=True;self.ready=True;self.error=False;self.recording=False
                self.session_buffer=SimpleNamespace(fallback=True)
                self.hide_at=0;self.starts=0;self.stops=0;self.hook=None
                self.hookproc=g.HOOKPROC(self.key_hook)
                def proc(hwnd,message,wp,lp):
                    if message in (g.WM_CAPS,0x113,0x218):
                        return g.App.window_proc(self,hwnd,message,wp,lp)
                    return g.user.DefWindowProcW(hwnd,message,wp,lp)
                self.wndproc=g.WNDPROC(proc)
                self.instance=g.kernel.GetModuleHandleW(None)
                self.name='CapshumeeCapsIntegrationTest'
                wc=g.WNDCLASS();wc.lpfnWndProc=self.wndproc
                wc.hInstance=self.instance;wc.lpszClassName=self.name
                if not g.user.RegisterClassW(C.byref(wc)):raise OSError('TEST_CLASS')
                self.hwnd=g.user.CreateWindowExW(0,self.name,'',0,0,0,1,1,None,None,self.instance,None)
                if not self.hwnd:raise OSError('TEST_WINDOW')
                g.user.SetTimer(self.hwnd,1,100,None)
            def start(self):
                if not self.recording:
                    self.starts+=1;self.recording=True
            def stop(self):
                if self.recording:
                    self.stops+=1;self.recording=False
            def hook_on(self):
                self.hook=g.user.SetWindowsHookExW(13,self.hookproc,self.instance,0)
                if not self.hook:raise OSError('TEST_HOOK')
            def hook_off(self):
                if self.hook:g.user.UnhookWindowsHookEx(self.hook);self.hook=None

        h=Harness()
        def pump(seconds=.32):
            end=time.monotonic()+seconds;msg=W.MSG()
            while time.monotonic()<end:
                while g.user.PeekMessageW(C.byref(msg),None,0,0,1):
                    g.user.TranslateMessage(C.byref(msg));g.user.DispatchMessageW(C.byref(msg))
                time.sleep(.005)
        initial=bool(g.user.GetKeyState(0x14)&1)
        def toggle():
            values=(g.INPUT*2)()
            for i,flags in enumerate((0,2)):
                values[i].type=1;values[i].ki=g.KEYBDINPUT(0x14,0,flags,0,0)
            self.assertEqual(g.user.SendInput(2,values,C.sizeof(g.INPUT)),2)
            pump()
        def set_lock(on):
            pump(.03)
            if bool(g.user.GetKeyState(0x14)&1)!=on:toggle()
            self.assertEqual(bool(g.user.GetKeyState(0x14)&1),on)
            pump()
        try:
            set_lock(False);pump()
            # Deliberately no hook: timer must recover both missed directions.
            for _ in range(12):
                toggle();self.assertTrue(h.recording)
                toggle();self.assertFalse(h.recording)
            h.hook_on()
            for _ in range(12):
                toggle();self.assertTrue(h.recording)
                toggle();self.assertFalse(h.recording)
            before=h.starts
            # Old notifications with arbitrary payload cannot reverse OFF.
            for _ in range(20):g.user.PostMessageW(h.hwnd,g.WM_CAPS,1,0)
            pump();self.assertFalse(h.recording);self.assertEqual(h.starts,before)
            # A burst that returns to OFF before the queue is drained must
            # not replay old ON commands afterwards.
            burst=(g.INPUT*80)()
            for i in range(80):
                burst[i].type=1;burst[i].ki=g.KEYBDINPUT(0x14,0,2 if i%2 else 0,0,0)
            self.assertEqual(g.user.SendInput(80,burst,C.sizeof(g.INPUT)),80)
            pump();self.assertFalse(bool(g.user.GetKeyState(0x14)&1))
            self.assertFalse(h.recording);self.assertEqual(h.starts,before)
            # On at startup/resume must not start without a fresh off/on.
            set_lock(True);h.stop();h.caps.reset();before=h.starts
            pump(.5);self.assertFalse(h.recording);self.assertEqual(h.starts,before)
            set_lock(False);set_lock(True);self.assertTrue(h.recording)
            h.enabled=False;pump();self.assertFalse(h.recording)
            h.enabled=True;pump();self.assertFalse(h.recording)
            set_lock(False);set_lock(True);self.assertTrue(h.recording)
            # Power resume while ON is fail-closed, even without a timer gap.
            g.user.SendMessageW(h.hwnd,0x218,18,0)
            pump();self.assertFalse(h.recording)
            set_lock(False);set_lock(True);self.assertTrue(h.recording)
            set_lock(False);self.assertFalse(h.recording)
        finally:
            h.enabled=False;h.stop();h.hook_off()
            set_lock(initial)
            g.user.KillTimer(h.hwnd,1);g.user.KillTimer(h.hwnd,2)
            g.user.DestroyWindow(h.hwnd)


if __name__=='__main__':unittest.main()
