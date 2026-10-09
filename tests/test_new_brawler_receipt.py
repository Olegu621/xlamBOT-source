import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import new_brawler_receipt as n
from stage_manager import StageManager
from state_finder import get_state


def receipt(w=1280,h=720,heading=True,button=True,blue=True):
    frame=np.full((h,w,3),(150,12,25),np.uint8)
    if heading:
        g=n._glyph(n.TITLE,h);x,y=round(w*.492),round(h*.16)
        frame[y:y+g.shape[0],x:x+g.shape[1]][g>0]=(255,245,120)
    if button:
        frame[round(h*.81):round(h*.92),round(w*.48):round(w*.68)]=(10,115,250) if blue else (20,230,0)
        g=n._glyph(n.CONTINUE,h);x,y=round(w*.52),round(h*.834)
        frame[y:y+g.shape[0],x:x+g.shape[1]][g>0]=255
    # The other button is Select and must not become the dismissal position.
    frame[round(h*.81):round(h*.92),round(w*.71):round(w*.90)]=(20,230,0)
    return frame


class NewBrawlerTests(unittest.TestCase):
    def test_recognizes_unlock_receipt_and_chooses_continue(self):
        for w,h in [(1280,720),(1920,1080),(960,540)]:
            f=receipt(w,h)
            self.assertEqual(get_state(f),'new_brawler')
            x,y=n.new_brawler_continue_position(f)
            self.assertTrue(.48*w<x<.68*w)
            self.assertTrue(.81*h<y<.92*h)

    def test_requires_independent_heading_lettering_and_blue_button(self):
        for f in [receipt(heading=False),receipt(button=False),receipt(blue=False),(receipt()*.7).astype(np.uint8)]:
            self.assertIsNone(n.new_brawler_continue_position(f))
        rng=np.random.default_rng(67)
        self.assertIsNone(n.new_brawler_continue_position(rng.integers(0,256,(720,1280,3),dtype=np.uint8)))
        self.assertIsNone(n.new_brawler_continue_position(None))

    def test_owner_rechecks_screen_and_obeys_stop_pause_and_retry_limit(self):
        m=StageManager.__new__(StageManager);frame=receipt();calls=[]
        m.runtime_control=None
        m.window_controller=SimpleNamespace(screenshot=lambda:frame,release_all_inputs=lambda:None,click=lambda *p,**kw:calls.append(p))
        with patch('stage_manager.time.monotonic',return_value=100):
            m.dismiss_new_brawler();m.dismiss_new_brawler()
        self.assertEqual(len(calls),1)
        frame=receipt(heading=False)
        with patch('stage_manager.time.monotonic',return_value=102):m.dismiss_new_brawler()
        frame=receipt()
        for stop,pause in [(True,False),(False,True)]:
            m.runtime_control=SimpleNamespace(should_stop=lambda:stop,should_pause=lambda:pause)
            with patch('stage_manager.time.monotonic',return_value=104):m.dismiss_new_brawler()
        self.assertEqual(len(calls),1)
