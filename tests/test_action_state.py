import unittest
from unittest.mock import patch
import numpy as np
from state_finder import get_action_state
from test_current_results import screen
from test_onboarding import age_frame


class ActionStateTests(unittest.TestCase):
    def test_current_result_and_age_guide_survive_menu_scaling(self):
        self.assertEqual(get_action_state(screen()), 'end_trio_showdown_3')
        self.assertEqual(get_action_state(age_frame()), 'onboarding')

    def test_disconnect_overlay_keeps_priority_over_lobby(self):
        frame = np.zeros((720, 1280, 3), np.uint8)
        with patch('screen_evidence.current_lobby', return_value=True), \
             patch('disconnect_dialog.idle_disconnect_reload_position', return_value=(200, 300)):
            self.assertEqual(get_action_state(frame), 'idle_disconnect')

    def test_source_frame_is_unchanged_and_short_frames_are_not_upscaled(self):
        frame = np.full((240, 426, 3), 80, np.uint8)
        with patch('state_finder.get_in_game_state', return_value='unknown') as classify:
            self.assertEqual(get_action_state(frame), 'unknown')
            self.assertIs(classify.call_args.args[0], frame)
        frame = np.full((720, 1280, 3), 90, np.uint8)
        with patch('state_finder.get_in_game_state', return_value='unknown') as classify:
            get_action_state(frame)
            self.assertEqual(classify.call_args_list[0].args[0].shape, (360, 640, 3))
            self.assertIs(classify.call_args_list[1].args[0], frame)
        self.assertTrue(np.all(frame == 90))
