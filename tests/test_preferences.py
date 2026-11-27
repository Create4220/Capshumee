import sys,tempfile,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from preference_store import PreferenceStore
class Preferences(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'preferences.json'
        self.store=PreferenceStore(self.path)
    def tearDown(self):self.temp.cleanup()
    def test_context_correction_survives_restart(self):
        self.store.learn('打开卡舒咪软件','打开卡输咪软件')
        self.assertEqual(PreferenceStore(self.path).apply('打开卡舒咪软件')[0],'打开卡输咪软件')
        data=self.path.read_text(encoding='utf-8')
        self.assertNotIn('打开卡舒咪软件',data)
    def test_single_character_not_applied_in_other_context(self):
        self.store.learn('打开卡舒咪软件','打开卡输咪软件')
        self.assertEqual(self.store.apply('这里很舒适')[0],'这里很舒适')
    def test_three_confirmations_allow_multi_character_generalization(self):
        for _ in range(3):self.store.learn('学习甲乙课程','学习丙丁课程')
        self.assertEqual(self.store.apply('今天的甲乙讲义')[0],'今天的丙丁讲义')
    def test_once_per_confirmation_not_per_occurrence(self):
        self.store.learn('甲乙甲乙','丙丁丙丁')
        self.assertTrue(all(r['count']==1 for r in self.store.snapshot()))
    def test_addition_deletion_numbers_not_learned(self):
        for a,b in [('请不要发','请发'),('你好','你好同学'),('密码123','密码456')]:
            self.store.learn(a,b)
        self.assertEqual(self.store.snapshot(),[])
    def test_disabled_neither_learns_nor_applies(self):
        self.store.learn('打开卡舒咪软件','打开卡输咪软件');self.store.set_enabled(False)
        count=len(self.store.snapshot());self.store.learn('学习甲乙','学习丙丁')
        self.assertEqual(len(self.store.snapshot()),count)
        self.assertEqual(self.store.apply('打开卡舒咪软件')[0],'打开卡舒咪软件')
    def test_delete_clear_and_stale_jobs(self):
        revision=self.store.revision;self.store.clear()
        self.store.learn('学习甲乙','学习丙丁',expected_revision=revision)
        self.assertEqual(self.store.snapshot(),[])
        self.store.learn('学习甲乙','学习丙丁')
        self.store.delete(self.store.snapshot()[0]['id'])
        self.assertEqual(PreferenceStore(self.path).snapshot(),[])
    def test_reject_previously_applied_correction(self):
        raw='打开卡舒咪软件';self.store.learn(raw,'打开卡输咪软件')
        shown,used=self.store.apply(raw)
        self.store.learn(raw,raw,shown,used)
        self.assertEqual(self.store.apply(raw)[0],raw)
    def test_corrupt_file_preserved(self):
        self.path.write_bytes(b'bad json')
        store=PreferenceStore(self.path);self.assertFalse(store.writable)
        self.assertEqual(store.learn('学习甲乙','学习丙丁'),0)
        self.assertEqual(self.path.read_bytes(),b'bad json')
    def test_latin_whole_words(self):
        for _ in range(3):self.store.learn('use alpha now','use bravo now')
        self.assertEqual(self.store.apply('alphabet')[0],'alphabet')
    def test_long_rewrite_is_bounded(self):
        self.assertEqual(self.store.learn('甲'*30000,'乙'*30000),0)
if __name__=='__main__':unittest.main()

