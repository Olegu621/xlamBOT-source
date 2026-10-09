import unittest
import numpy as np
from reward_receipts import _glyph
import current_results as result
import state_finder


def screen(w=1280,h=720):
    frame=np.full((h,w,3),(20,110,245),np.uint8)
    rank=_glyph(result.RANK_FOUR,h)
    x,y=round(24*h/720),round(20*h/720)
    frame[y:y+rank.shape[0],x:x+rank.shape[1]][rank>205]=(245,245,40)
    text=_glyph(result.PROCEED,h)
    x,y=round(1064*h/720),round(650*h/720)
    frame[y:y+text.shape[0],x:x+text.shape[1]][text>205]=245
    return frame


class CurrentResultTests(unittest.TestCase):
    def test_rank_four_with_proceed_across_resolutions(self):
        for w,h in [(1280,720),(1920,1080),(960,540)]:
            frame=screen(w,h)
            self.assertTrue(result.current_fourth_place(frame))
            self.assertEqual(state_finder.get_state(frame),'end_trio_showdown_3')
            self.assertFalse(result.current_fourth_place((frame*.7).astype(np.uint8)))
    def test_missing_rank_or_action_or_button_does_not_authorize(self):
        frame=screen();frame[:130,:400]=0
        self.assertFalse(result.current_fourth_place(frame))
        frame=screen();frame[600:]=0
        self.assertFalse(result.current_fourth_place(frame))
        frame=screen();frame[630:710,1024:1250]=(180,20,30)
        text=_glyph(result.PROCEED,720)
        frame[650:650+text.shape[0],1064:1064+text.shape[1]][text>205]=245
        self.assertFalse(result.current_fourth_place(frame))
        self.assertFalse(result.current_fourth_place(None))
