import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from reward_received import is_reward_received
from seasonal_rewards import CREDITS_TITLE, CREDITS_ICON, _glyph, credits_reward
from stage_manager import StageManager
import state_finder


def receipt():
    frame = np.full((720, 1280, 3), (20, 90, 230), np.uint8)
    title = _glyph(CREDITS_TITLE, 720)
    frame[164:224, 500:780] = title[:,:,None]
    # Anonymous token art; no game account or full screenshot in the repo.
    frame[300:520, 510:800] = (0, 200, 240)
    icon = _glyph(CREDITS_ICON, 720)
    frame[446:492, 590:690] = icon[:,:,None]
    return frame


class CreditsReceiptTests(unittest.TestCase):
    def test_receipt_recognized_at_three_resolutions(self):
        for width, height in ((960, 540), (1280, 720), (1920, 1080)):
            frame = cv2.resize(receipt(), (width, height))
            self.assertTrue(credits_reward(frame))
            self.assertTrue(is_reward_received(frame))
            self.assertEqual(state_finder.get_in_game_state(frame), 'reward_received')

    def test_caption_token_and_backdrop_are_independently_required(self):
        for top, bottom, left, right in ((160, 230, 490, 790), (440, 500, 585, 695), (610, 720, 0, 1280)):
            frame = receipt()
            frame[top:bottom, left:right] = (20, 90, 150)
            self.assertFalse(credits_reward(frame))
        frame = receipt()
        frame[300:520, 510:800] = (30, 50, 80)
        frame[446:492, 590:690] = _glyph(CREDITS_ICON, 720)[:,:,None]
        self.assertFalse(credits_reward(frame))

    def test_fresh_frame_retry_stop_and_pause_still_guard_input(self):
        manager = StageManager.__new__(StageManager)
        manager.window_controller = Mock()
        manager.window_controller.screenshot.return_value = receipt()
        manager._should_stop = Mock(return_value=False)
        manager._should_pause = Mock(return_value=False)
        with patch('stage_manager.time.monotonic', side_effect=(1., 1.5, 2.1, 4.)):
            manager.dismiss_received_reward()
            manager.dismiss_received_reward()
            manager.dismiss_received_reward()
            self.assertEqual(manager.window_controller.click.call_count, 2)
            manager.window_controller.screenshot.return_value = np.zeros((720, 1280, 3), np.uint8)
            manager.dismiss_received_reward()
        manager._should_stop.return_value = True
        manager.dismiss_received_reward()
        manager._should_stop.return_value = False
        manager._should_pause.return_value = True
        manager.dismiss_received_reward()
        self.assertEqual(manager.window_controller.click.call_count, 2)
        manager.window_controller.click.assert_called_with(640, 634, already_include_ratio=True)
