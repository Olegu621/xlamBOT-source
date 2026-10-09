import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
import numpy as np
from reward_receipts import _glyph
import mega_quest_drop as drop
import state_finder
from stage_manager import StageManager


def screen(w=1280,h=720):
    frame=np.full((h,w,3),(150,35,210),np.uint8)
    for encoded,x,y in [(drop.TITLE,79,10),(drop.TAP,556,45)]:
        glyph=_glyph(encoded,h)
        px,py=round(x*h/720),round(y*h/720)
        frame[py:py+glyph.shape[0],px:px+glyph.shape[1]]=glyph[:,:,None]
    return frame


class MegaQuestTests(unittest.TestCase):
    def test_two_headers_and_reward_backdrop_required(self):
        for w,h in [(1280,720),(1920,1080),(960,540)]:
            frame=screen(w,h)
            self.assertTrue(drop.mega_quest_drop(frame))
            self.assertEqual(state_finder.get_state(frame),'star_drop_chaos')
            self.assertFalse(drop.mega_quest_drop((frame*.7).astype(np.uint8)))
            frame[:round(h*.17),round(w*.38):round(w*.63)]=0
            self.assertFalse(drop.mega_quest_drop(frame))
        self.assertFalse(drop.mega_quest_drop(None))
        self.assertFalse(drop.mega_quest_drop(np.full((720,1280,3),255,np.uint8)))

    def test_owner_taps_stop_when_screen_changes_stales_or_pauses(self):
        manager=StageManager.__new__(StageManager)
        manager.runtime_control=None
        controller=SimpleNamespace(screenshot=lambda: screen(),press=Mock(),
                                   frame_is_fresh=lambda: True,_check_decision=lambda: None)
        manager.window_controller=controller
        with patch.object(manager,'_sleep_interruptible',return_value=False),patch('stage_manager.get_state',side_effect=['star_drop_chaos','star_drop_chaos','lobby']):
            manager.click_star_drop('chaos')
        self.assertEqual(controller.press.call_count,2)
        self.assertTrue(all(call.kwargs=={} for call in controller.press.call_args_list))
        controller.press.reset_mock();controller.frame_is_fresh=lambda: False
        with patch('stage_manager.get_state',return_value='star_drop_chaos'):
            manager.click_star_drop('chaos')
        controller.press.assert_not_called()
        manager.runtime_control=SimpleNamespace(should_stop=lambda: False,should_pause=lambda: True)
        manager.click_star_drop('chaos')
        controller.press.assert_not_called()
