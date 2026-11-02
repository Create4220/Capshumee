import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from caps_state import CapsState


class CapsReconciliation(unittest.TestCase):
    def setUp(self):
        self.caps=CapsState();self.now=0;self.recording=False;self.starts=0;self.stops=0

    def sample(self,on,held=False,available=True,elapsed=.1,fail_start=False):
        self.now+=elapsed
        action=self.caps.sample(on,held,available,self.recording,self.now)
        if action=='start':
            self.starts+=1
            self.recording=not fail_start
        elif action=='stop':
            self.stops+=1;self.recording=False
        return action

    def turn_on(self):
        self.sample(True,True);self.sample(True)

    def test_startup_on_requires_off_then_on(self):
        for _ in range(10):self.sample(True)
        self.assertEqual(self.starts,0)
        self.sample(False);self.turn_on();self.assertTrue(self.recording)

    def test_poll_recovers_missing_key_notifications(self):
        self.sample(False)
        for _ in range(50):
            self.turn_on();self.assertTrue(self.recording)
            self.sample(False);self.assertFalse(self.recording)
        self.assertEqual((self.starts,self.stops),(50,50))

    def test_off_repairs_recording_even_without_armed_edge(self):
        self.recording=True
        self.sample(False);self.assertFalse(self.recording)

    def test_repeat_and_missing_keyup_do_not_invert(self):
        self.sample(False)
        for _ in range(20):self.sample(True,True)
        self.assertEqual(self.starts,0)
        # No key-up event needed: the sampled physical release is sufficient.
        self.sample(True);self.assertTrue(self.recording)
        for _ in range(20):self.sample(True)
        self.assertEqual(self.starts,1)
        self.sample(False,True);self.assertFalse(self.recording)
        self.sample(False);self.turn_on();self.assertEqual(self.starts,2)

    def test_delayed_notification_cannot_start_when_off(self):
        self.sample(False)
        # All queued messages only cause more OFF state samples.
        for _ in range(20):self.sample(False)
        self.assertEqual(self.starts,0)

    def test_short_unstable_on_is_not_recorded(self):
        self.sample(False);self.sample(True);self.sample(False,elapsed=.01)
        self.assertEqual(self.starts,0)

    def test_unready_or_paused_on_requires_new_cycle(self):
        self.sample(False);self.turn_on();self.assertTrue(self.recording)
        self.sample(True,available=False);self.assertFalse(self.recording)
        for _ in range(10):self.sample(True)
        self.assertEqual(self.starts,1)
        self.sample(False);self.turn_on();self.assertEqual(self.starts,2)

    def test_sleep_or_blocked_message_loop_stops_and_disarms(self):
        self.sample(False);self.turn_on()
        self.sample(True,elapsed=3);self.assertFalse(self.recording)
        for _ in range(10):self.sample(True)
        self.assertEqual(self.starts,1)
        self.sample(False);self.turn_on();self.assertEqual(self.starts,2)

    def test_failed_start_not_retried_until_next_off_on(self):
        self.sample(False);self.sample(True)
        self.sample(True,fail_start=True)
        for _ in range(10):self.sample(True)
        self.assertEqual(self.starts,1);self.assertFalse(self.recording)
        self.sample(False);self.turn_on();self.assertEqual(self.starts,2)

    def test_pause_resume_between_timer_ticks_clears_old_arm(self):
        self.sample(False);self.caps.reset()
        for _ in range(10):self.sample(True)
        self.assertEqual(self.starts,0)


if __name__=='__main__':unittest.main()
