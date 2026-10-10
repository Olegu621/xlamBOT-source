import unittest
from unittest.mock import patch
import cv2
import numpy as np
import state_finder
from screen_evidence import MENU_CURRENT, _scaled, current_lobby


class ClassifierLatencyTests(unittest.TestCase):
    def test_current_menu_and_play_identify_lobby_without_result_scan(self):
        for width, height in [(1280, 720), (960, 540), (1920, 1080)]:
            frame = np.full((height, width, 3), 60, np.uint8)
            cv2.rectangle(frame, (round(width*.74), round(height*.85)),
                          (round(width*.98), round(height*.97)), (255, 210, 0), -1)
            cv2.putText(frame, 'PLAY', (round(width*.79), round(height*.92)),
                        cv2.FONT_HERSHEY_SIMPLEX, height/400, (255,255,255), 3)
            glyph = _scaled(MENU_CURRENT, round(36*height/720), round(27*height/720))
            x,y=round(width*.94),round(height*.027)
            frame[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph
            self.assertTrue(current_lobby(frame))
            with patch.object(state_finder, 'is_in_end_of_a_match', side_effect=AssertionError('expensive scan')):
                self.assertEqual(state_finder.get_state(frame), 'lobby')
            self.assertFalse(current_lobby((frame*.65).astype(np.uint8)))
            frame[round(height*.84):]=60
            self.assertFalse(current_lobby(frame))


    def test_bright_battle_hud_skips_result_and_reward_scans(self):
        from showdown_hud import _caption, CAPTION_RUSSIAN
        for encoded,reference in [(None,720),(CAPTION_RUSSIAN,219)]:
            for width,height in [(1280,720),(960,540),(1920,1080)]:
                frame=np.full((height,width,3),40,np.uint8)
                glyph=_caption(height) if encoded is None else _caption(height,encoded=encoded,reference_height=reference)
                x,y=round(width*.02),round(height*.04)
                frame[y:y+glyph.shape[0],x:x+glyph.shape[1]][glyph>0]=245
                with patch.object(state_finder,'is_in_end_of_a_match',side_effect=AssertionError('result scan')), patch('screen_evidence.daily_reward',side_effect=AssertionError('reward scan')):
                    self.assertEqual(state_finder.get_state(frame),'match')
                with patch.object(state_finder,'is_in_connection_lost',return_value=True):
                    self.assertEqual(state_finder.get_state(frame),'connection_lost')
                with patch('disconnect_dialog.idle_disconnect_reload_position',return_value=(350,450)):
                    self.assertEqual(state_finder.get_state(frame),'idle_disconnect')
                frame=(frame*.7).astype(np.uint8)
                with patch('screen_evidence.daily_reward',return_value=True) as reward:
                    self.assertEqual(state_finder.get_state(frame),'daily_reward')
                    reward.assert_called_once()
