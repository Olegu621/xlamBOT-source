import base64
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import cv2
import numpy as np
import loony_loot as loot
from stage_manager import StageManager
import state_finder


def screen(width=1280, height=720):
    frame = np.full((height, width, 3), (12, 80, 40), np.uint8)
    raw = cv2.imdecode(np.frombuffer(base64.b64decode(loot.TITLE), np.uint8), 0)
    glyph = cv2.resize(raw, (round(raw.shape[1]*width/1280), round(raw.shape[0]*height/720)))
    x, y = round(width*19/1280), round(height*27/720)
    frame[y:y+glyph.shape[0], x:x+glyph.shape[1]] = glyph[:, :, None]
    return frame


class LootTests(unittest.TestCase):
    def test_positive_title_at_multiple_resolutions(self):
        for width, height in [(1280,720), (1920,1080), (1920,864), (960,540)]:
            self.assertTrue(loot.is_loony_loot(screen(width,height)))
        self.assertFalse(loot.is_loony_loot(None))
        self.assertFalse(loot.is_loony_loot(np.zeros((720,1280,3),np.uint8)))

    def test_title_outside_reward_header_does_not_authorize_input(self):
        frame = screen()
        shifted = np.roll(frame, 300, axis=0)
        self.assertFalse(loot.is_loony_loot(shifted))

    def test_rarity_background_change_keeps_title_recognizable(self):
        for color in [(0, 170, 0), (0, 100, 255), (180, 0, 180)]:
            frame = screen()
            frame[frame.min(axis=2) <= 210] = color
            self.assertTrue(loot.is_loony_loot(frame))
        self.assertFalse(loot.is_loony_loot(np.full((720,1280,3),255,np.uint8)))

    def test_repeated_opening_steps_recheck_screen_and_obey_stop(self):
        manager = StageManager.__new__(StageManager)
        manager.runtime_control = None
        frame = screen()
        manager.window_controller = SimpleNamespace(screenshot=lambda: frame, press=Mock(), frame_is_fresh=lambda: True, _check_decision=lambda: None)
        with patch.object(manager, '_sleep_interruptible', return_value=False), patch('stage_manager.get_state', side_effect=lambda f: state_finder.is_in_star_drop(f) and 'star_drop_loony'):
            manager.click_star_drop('loony')
            self.assertEqual(manager.window_controller.press.call_count, 8)
            frame = np.zeros_like(frame)
            manager.click_star_drop('loony')
            self.assertEqual(manager.window_controller.press.call_count, 8)
            manager.runtime_control = SimpleNamespace(should_stop=lambda: True, should_pause=lambda: False)
            frame = screen()
            manager.click_star_drop('loony')
            self.assertEqual(manager.window_controller.press.call_count, 8)

    def test_special_hold_releases_on_next_screen_or_pause(self):
        manager = StageManager.__new__(StageManager)
        manager.runtime_control = None
        manager.window_controller = SimpleNamespace(screenshot=Mock(return_value=screen()), press=Mock(), frame_is_fresh=lambda: True, _check_decision=lambda: None)
        with patch('stage_manager.get_state', side_effect=['star_drop_demonic', 'star_drop_demonic', 'lobby']):
            manager.click_star_drop('demonic')
        self.assertEqual(manager.window_controller.press.call_args_list[-1].kwargs,
                         {'touch_up': True, 'touch_down': False})
        self.assertEqual(manager.window_controller.press.call_count, 3)
        manager.window_controller.press.reset_mock()
        manager.runtime_control = SimpleNamespace(should_stop=lambda: False, should_pause=Mock(side_effect=[False, True]))
        with patch('stage_manager.get_state', return_value='star_drop_demonic'):
            manager.click_star_drop('demonic')
        self.assertEqual(manager.window_controller.press.call_count, 2)
        self.assertEqual(manager.window_controller.press.call_args_list[-1].kwargs['touch_down'], False)

    def test_stale_reward_cannot_start_a_hold(self):
        manager = StageManager.__new__(StageManager)
        manager.runtime_control = None
        manager.window_controller = SimpleNamespace(screenshot=lambda: screen(),
            press=Mock(), frame_is_fresh=lambda: False)
        with patch('stage_manager.get_state', return_value='star_drop_demonic'):
            manager.click_star_drop('demonic')
        manager.window_controller.press.assert_not_called()
