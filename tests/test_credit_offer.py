import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np
from seasonal_rewards import CREDIT_OFFER_CLOSE, CREDIT_OFFER_TOKEN, _glyph, credit_offer_dismiss_position, seasonal_announcement_dismiss_position
from stage_manager import StageManager
import state_finder

def offer():
    frame = np.full((720, 1280, 3), (20, 35, 55), np.uint8)
    frame[110:630, 170:1140] = (160, 10, 240)
    frame[450:500, 700:1040] = (0, 180, 240)
    frame[530:600, 830:1070] = (30, 240, 10)
    frame[116:172, 1070:1147] = (240, 20, 10)
    for encoded, x, y in ((CREDIT_OFFER_CLOSE, 1096, 123), (CREDIT_OFFER_TOKEN, 705, 450)):
        glyph = _glyph(encoded, 720)
        frame[y:y+glyph.shape[0], x:x+glyph.shape[1]] = glyph[:,:,None]
    return frame

class CreditOfferTests(unittest.TestCase):
    def test_three_resolutions_close_only_on_cross(self):
        for w, h in ((960, 540), (1280, 720), (1920, 1080)):
            frame = cv2.resize(offer(), (w, h))
            position = credit_offer_dismiss_position(frame)
            self.assertIsNotNone(position)
            self.assertAlmostEqual(position[0]/w, 1112/1280, delta=.003)
            self.assertAlmostEqual(position[1]/h, 140/720, delta=.003)
            self.assertEqual(state_finder.get_in_game_state(frame), 'seasonal_announcement')

    def test_missing_modal_token_progress_purchase_or_close_prevents_action(self):
        for top, bottom, left, right in ((120, 180, 1070, 1150), (450, 500, 700, 745), (450, 500, 750, 1040), (530, 600, 830, 1070), (120, 180, 250, 470)):
            frame = offer()
            frame[top:bottom, left:right] = (20, 35, 55)
            self.assertIsNone(credit_offer_dismiss_position(frame))
        frame = offer()
        frame[180:470, :100] = (200, 210, 240)
        self.assertIsNone(credit_offer_dismiss_position(frame))

    def test_guarded_close_rechecks_frame_stop_pause_and_retry(self):
        manager = StageManager.__new__(StageManager)
        manager.window_controller = Mock()
        manager.window_controller.screenshot.return_value = offer()
        manager._should_stop = Mock(return_value=False)
        manager._should_pause = Mock(return_value=False)
        with patch('stage_manager.time.monotonic', side_effect=(1., 1.5, 3., 5.)):
            manager.dismiss_seasonal_announcement()
            manager.dismiss_seasonal_announcement()
            manager.dismiss_seasonal_announcement()
            self.assertEqual(manager.window_controller.click.call_count, 2)
            manager.window_controller.screenshot.return_value = np.zeros((720,1280,3), np.uint8)
            manager.dismiss_seasonal_announcement()
        manager._should_stop.return_value = True
        manager.dismiss_seasonal_announcement()
        manager._should_stop.return_value = False
        manager._should_pause.return_value = True
        manager.dismiss_seasonal_announcement()
        self.assertEqual(manager.window_controller.click.call_count, 2)
        manager.window_controller.click.assert_called_with(*seasonal_announcement_dismiss_position(offer()), already_include_ratio=True)
