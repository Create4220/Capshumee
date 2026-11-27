"""Synthetic editor + official public WAV only; never opens microphone or real clipboard."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
from types import SimpleNamespace
import json,sys,time,wave
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'));sys.path.insert(0,str(ROOT/'scripts'))
import dictation_app as gui
from floating_editor import u
from observe import endpoints

def main():
    app=gui.App(test_mode=True)
    copied=[];clipboard=app.clipboard
    app.clipboard=SimpleNamespace(clear_previous=lambda:True,write=lambda text:copied.append(text) is None)
    app.audio=SimpleNamespace(start=lambda session:None,stop=lambda:None)
    def pump():
        msg=W.MSG()
        while gui.user.PeekMessageW(C.byref(msg),None,0,0,1):
            if msg.message!=0x12:gui.user.TranslateMessage(C.byref(msg));gui.user.DispatchMessageW(C.byref(msg))
        app.results()
    def until(predicate):
        end=time.monotonic()+40
        while not predicate():
            if time.monotonic()>end:raise TimeoutError('EDITOR_SMOKE_TIMEOUT')
            pump();time.sleep(.01)
    try:
        until(lambda:app.ready)
        app.start()
        with wave.open(str(ROOT/'samples/public/sensevoice-zh.wav'),'rb') as sample:
            raw=sample.readframes(sample.getnframes())
        for offset in range(0,len(raw),3200):app.send('A',app.session,raw[offset:offset+3200])
        app.stop();until(lambda:app.draft.finished)
        assert app.editor.text() and not copied
        assert not (u.GetWindowLongPtrW(app.editor.edit,-16)&0x800)
        # Only synthetic content is read back from this owned window.
        baseline='打开卡舒咪软件';corrected='打开卡输咪软件'
        app.draft.parts=[baseline];app.draft.displayed=baseline
        long_text='\r\n'.join('Synthetic paragraph %d - editor scrolling test'%i for i in range(1000))
        app.editor.set_text(long_text)
        assert len(app.editor.text())==len(long_text)
        assert u.SendMessageW(app.editor.edit,0xBA,0,0)>=1000
        u.SendMessageW(app.editor.edit,0xB6,0,900)
        assert u.SendMessageW(app.editor.edit,0xCE,0,0)>0
        app.show();gui.user.SetWindowPos(app.hwnd,W.HWND(-1),80,80,620,620,0x10);pump()
        app.show()
        gui.api(gui.user,'GetWindowRect',W.BOOL,[W.HWND,C.POINTER(W.RECT)])
        rect=W.RECT();gui.user.GetWindowRect(app.hwnd,C.byref(rect))
        assert rect.left==80 and rect.top==80
        assert u.GetWindowLongPtrW(app.hwnd,-16)&0x00C00000
        app.editor.set_text(corrected);gui.user.SendMessageW(app.hwnd,0x111,202,app.editor.copy)
        assert copied==[corrected] and not app.draft.active
        until(lambda:bool(app.preferences.snapshot()))
        assert app.preferences.apply(baseline)[0]==corrected
        app.vocabulary.open();pump()
        assert len(app.vocabulary.ids)>0
        app.preferences.delete(app.vocabulary.ids[0]);app.vocabulary.refresh()
        assert not app.vocabulary.ids
        # Cancellation drops late results without a clipboard write or new rule.
        app.draft.begin(777);app.draft.append(777,'synthetic cancelled')
        app.editor.set_text('synthetic cancelled');app.cancel_draft()
        app.inbox.put({'kind':'final','session':777,'text':'late'});app.results()
        assert not app.editor.text() and copied==[corrected] and not app.preferences.snapshot()
        observations=[];errors=[]
        import os
        for pid in (os.getpid(),app.process.pid):
            rows,failures=endpoints(pid);observations+=rows;errors+=failures
        assert not observations and not errors
        print(json.dumps({'passed':True,'microphone_opened':False,'real_clipboard_read_or_written':False,
            'public_audio_recognition':True,'editable_native_control':True,'scroll_lines':1000,
            'window_position_retained':True,'edited_copy':True,'local_learning':True,
            'vocabulary_management':True,'cancel_discards_late_results':True,
            'observed_network_endpoints':0,'private_text_returned':False}))
    finally:
        app.close();gui.user.DestroyWindow(app.hwnd)
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'passed':False,'error_type':type(exc).__name__,'private_text_returned':False}))
        raise SystemExit(1)

