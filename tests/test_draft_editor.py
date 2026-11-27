import sys,unittest,queue,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from draft_session import DraftSession
class Drafts(unittest.TestCase):
    def test_cancel_discards_late_results(self):
        d=DraftSession();d.begin(1);d.append(1,'synthetic');d.cancel()
        self.assertFalse(d.append(1,'late'));self.assertFalse(d.finish(1,'late'))
        d.begin(2);self.assertEqual(d.raw,'');self.assertFalse(d.append(1,'old'))
    def test_finished_draft_never_changes(self):
        d=DraftSession();d.begin(1);d.append(1,'original');d.finish(1,'shown')
        self.assertFalse(d.append(1,'late'));self.assertEqual(d.displayed,'shown')

@unittest.skipUnless(sys.platform=='win32','Windows controller')
class EditorFlow(unittest.TestCase):
    def setUp(self):
        import dictation_app as gui
        from preference_store import PreferenceStore
        self.gui=gui;self.temp=tempfile.TemporaryDirectory();self.copied=[]
        self.app=gui.App.__new__(gui.App);a=self.app
        a.draft=DraftSession();a.draft.begin(1);a.session=1;a.recording=False
        a.hwnd=None;a.error=False;a.closing=False;a.test_mode=True;a.preview=''
        a.preferences=PreferenceStore(Path(self.temp.name)/'store.json')
        a.inbox=queue.Queue();a.learn_jobs=queue.Queue();a.vocabulary=SimpleNamespace(hwnd=None)
        self.text='';a.editor=SimpleNamespace(set_text=self.set_text,text=lambda:self.text,editable=lambda value:None)
        a.clipboard=SimpleNamespace(write=lambda text:self.copied.append(text) is None)
        a.show=lambda *args:None;a.update_tray=lambda:None
        self.guard=patch.object(gui,'user',SimpleNamespace(InvalidateRect=lambda *x:None,ShowWindow=lambda *x:None))
        self.guard.start()
    def set_text(self,text):self.text=text
    def tearDown(self):self.guard.stop();self.temp.cleanup()
    def finish(self):
        a=self.app
        a.inbox.put({'kind':'final','session':1,'text':'学习甲乙课程'})
        a.inbox.put({'kind':'stopped','session':1});a.results()
    def test_no_external_insertion_or_automatic_clipboard(self):
        self.finish();self.assertEqual(self.copied,[])
        self.assertTrue(self.app.draft.finished);self.assertEqual(self.text,'学习甲乙课程')
        self.assertFalse(hasattr(self.gui,'insert_text'))
    def test_edited_copy_and_background_job(self):
        self.finish();self.text='学习丙丁课程';self.app.copy_draft()
        self.assertEqual(self.copied,['学习丙丁课程'])
        original,edited,shown,used,revision=self.app.learn_jobs.get_nowait()
        self.assertEqual(original,'学习甲乙课程');self.assertEqual(edited,'学习丙丁课程')
        self.assertFalse(self.app.draft.active)
    def test_failed_copy_preserves_draft_and_does_not_learn(self):
        self.finish();self.app.clipboard.write=lambda text:False;self.app.copy_draft()
        self.assertTrue(self.app.draft.active);self.assertTrue(self.app.learn_jobs.empty())
    def test_cancel_never_copies_or_learns(self):
        self.finish();self.app.stop=lambda:None;self.app.caps=SimpleNamespace(reset=lambda:None)
        self.app.cancel_draft()
        self.assertEqual(self.copied,[]);self.assertTrue(self.app.learn_jobs.empty())
        self.app.inbox.put({'kind':'final','session':1,'text':'late'});self.app.results()
        self.assertEqual(self.text,'')
    def test_edit_not_overwritten_by_late_results(self):
        self.finish();self.text='edited by test'
        self.app.inbox.put({'kind':'partial','session':1,'text':'late'})
        self.app.inbox.put({'kind':'final','session':1,'text':'late'});self.app.results()
        self.assertEqual(self.text,'edited by test')
    def test_copy_waits_until_finalization(self):
        self.text='preview';self.app.copy_draft()
        self.assertEqual(self.copied,[]);self.assertTrue(self.app.learn_jobs.empty())
if __name__=='__main__':unittest.main()

