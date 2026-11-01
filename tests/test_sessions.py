import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from session_buffer import SessionBuffer
class Sessions(unittest.TestCase):
    def setUp(self):
        self.state=SessionBuffer();self.copied=[]
        self.copy=lambda text:self.copied.append(text) is None
        self.state.begin(1,(1,2))
    def test_no_automatic_clipboard_write(self):
        self.state.final(1,'first ',lambda *args:True)
        self.state.final(1,'second ',lambda *args:False)
        self.state.stopping(1,False)
        self.state.final(1,'last',lambda *args:True)
        self.assertEqual(self.state.complete(1,self.copy),'buffered')
        self.assertEqual(self.copied,[])
        self.assertTrue(self.state.retry_copy(self.copy))
        self.assertEqual(self.copied,['first second last'])
    def test_next_session_discards_old_results(self):
        self.state.final(1,'old',lambda *args:False)
        self.state.begin(2,(3,4))
        self.assertEqual(self.state.text,'')
        self.assertEqual(self.state.final(1,'late',lambda *args:False),'stale')
        self.assertEqual(self.state.complete(1,self.copy),'stale')
        self.assertFalse(self.state.retry_copy(self.copy))
    def test_normal_input_preserves_clipboard(self):
        self.state.final(1,'text',lambda *args:True);self.state.stopping(1,True)
        self.assertEqual(self.state.complete(1,self.copy),'inserted')
        self.assertEqual(self.copied,[])
    def test_empty_session_does_not_copy(self):
        self.state.stopping(1,False)
        self.assertEqual(self.state.complete(1,self.copy),'empty')
        self.assertFalse(self.state.retry_copy(self.copy))
    def test_manual_copy_can_retry(self):
        self.state.final(1,'text',lambda *args:False);self.state.stopping(1,True);self.state.complete(1)
        self.assertFalse(self.state.retry_copy(lambda text:False))
        self.assertTrue(self.state.retry_copy(self.copy))
if __name__=='__main__':unittest.main()
