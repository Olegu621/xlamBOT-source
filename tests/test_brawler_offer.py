import unittest
from unittest.mock import Mock
from types import SimpleNamespace
import numpy as np
from reward_receipts import _glyph
from brawler_offer import HEADER,CROSS,brawler_offer_close_position
from stage_manager import StageManager
import state_finder


def screen(w=1280,h=720):
    f=np.full((h,w,3),20,np.uint8)
    f[round(h*.15):round(h*.86),round(w*.13):round(w*.89)]=(10,85,205)
    f[round(h*.735):round(h*.84),round(w*.645):round(w*.84)]=(10,210,5)
    f[round(h*.165):round(h*.24),round(w*.837):round(w*.895)]=(240,25,20)
    for encoded,x,y in [(HEADER,697,138),(CROSS,1084,123)]:
        g=_glyph(encoded,h);px,py=round(x*h/720),round(y*h/720)
        f[py:py+g.shape[0],px:px+g.shape[1]][g>0]=255
    return f


class OfferTests(unittest.TestCase):
    def test_positive_offer_and_independent_negative_markers(self):
        for w,h in [(1280,720),(960,540),(1920,1080)]:
            f=screen(w,h)
            p=brawler_offer_close_position(f)
            self.assertIsNotNone(p)
            self.assertEqual(state_finder.get_state(f),'brawler_offer')
            self.assertAlmostEqual(p[0]/w,1111.5/1280,delta=.002)
            self.assertAlmostEqual(p[1]/h,143.5/720,delta=.002)
            for bounds in [(.51,.16,.8,.49),(.83,.16,.92,.25),(.65,.76,.83,.82),(.2,.155,.72,.18)]:
                broken=f.copy();x1,y1,x2,y2=bounds
                broken[round(h*y1):round(h*y2),round(w*x1):round(w*x2)]=20
                self.assertIsNone(brawler_offer_close_position(broken))
        self.assertIsNone(brawler_offer_close_position(None))

    def test_owner_rechecks_screen_freshness_pause_and_retry(self):
        manager=StageManager.__new__(StageManager);manager.runtime_control=None
        frame=screen();fresh=True
        controller=SimpleNamespace(screenshot=lambda:frame,frame_is_fresh=lambda:fresh,
                                   release_all_inputs=Mock(),click=Mock())
        manager.window_controller=controller
        manager.close_brawler_offer();manager.close_brawler_offer()
        self.assertEqual(controller.click.call_count,1)
        manager._brawler_offer_last_tap=-100;frame=np.zeros_like(frame)
        manager.close_brawler_offer();self.assertEqual(controller.click.call_count,1)
        frame=screen();fresh=False
        manager.close_brawler_offer();self.assertEqual(controller.click.call_count,1)
        fresh=True;manager.runtime_control=SimpleNamespace(should_stop=lambda:False,should_pause=lambda:True)
        manager.close_brawler_offer();self.assertEqual(controller.click.call_count,1)
        manager.runtime_control=SimpleNamespace(should_stop=lambda:True,should_pause=lambda:False)
        manager.close_brawler_offer();self.assertEqual(controller.click.call_count,1)
