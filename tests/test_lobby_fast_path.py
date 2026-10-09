import unittest
from unittest.mock import patch
import numpy as np
import state_finder


class LobbyFastPathTests(unittest.TestCase):
    def test_confirmed_controls_skip_large_result_scan(self):
        frame = np.zeros((720,1280,3), np.uint8)
        with patch('screen_evidence.current_lobby', return_value=True), \
             patch('state_finder.is_in_end_of_a_match', side_effect=AssertionError('unnecessary result scan')):
            self.assertEqual(state_finder.get_in_game_state(frame), 'lobby')

    def test_overlays_still_take_priority_over_lobby(self):
        frame = np.zeros((720,1280,3), np.uint8)
        with patch('screen_evidence.current_lobby', return_value=True), \
             patch('disconnect_dialog.idle_disconnect_reload_position', return_value=(200,300)):
            self.assertEqual(state_finder.get_in_game_state(frame), 'idle_disconnect')
        with patch('screen_evidence.current_lobby', return_value=True), \
             patch('state_finder.team_panel_close_position', return_value=(1200,20)):
            self.assertEqual(state_finder.get_in_game_state(frame), 'team_panel')
