import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from stage_manager import StageManager

class UnknownRecoveryTests(unittest.TestCase):
    def manager(self):
        manager=StageManager.__new__(StageManager);manager.runtime_control=None;self.clicks=[]
        manager.window_controller=SimpleNamespace(screenshot=lambda:np.zeros((720,1280,3),np.uint8),release_all_inputs=lambda:None,click=lambda *a,**k:self.clicks.append(a))
        return manager
    def test_four_second_grace_then_one_and_half_second_interval(self):
        manager=self.manager()
        with patch('stage_manager.time.monotonic',side_effect=[1.,4.99,5.,5.5,6.49,6.5]),patch('stage_manager.get_state',return_value='unknown'):
            for i in range(6):manager.recover_unknown()
        self.assertEqual(self.clicks,[(1203.1999999999998,25.200000000000003)]*2)
    def test_known_fresh_screen_cannot_be_clicked_from_stale_unknown_state(self):
        manager=self.manager()
        manager._unknown_since=0
        for state in ['lobby','match','match_making','daily_reward','team_panel']:
            with patch('stage_manager.get_state',return_value=state):manager.recover_unknown()
        self.assertEqual(self.clicks,[])
    def test_pause_and_stop_cancel_recovery(self):
        manager=self.manager()
        for stop,pause in [(True,False),(False,True)]:
            manager.runtime_control=SimpleNamespace(should_stop=lambda:stop,should_pause=lambda:pause);manager.recover_unknown()
        self.assertEqual(self.clicks,[])

    def test_known_state_restarts_the_full_grace_period(self):
        manager=self.manager()
        with patch('stage_manager.time.monotonic',side_effect=[1.,5.,6.,9.99,10.]),patch('stage_manager.get_state',return_value='unknown'):
            manager.recover_unknown()
            manager.recover_unknown()
            manager.reset_unknown_recovery()
            manager.recover_unknown()
            manager.recover_unknown()
            self.assertEqual(len(self.clicks),1)
            manager.recover_unknown()
        self.assertEqual(len(self.clicks),2)
