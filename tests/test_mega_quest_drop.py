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

    def test_rarity_star_continues_after_tap_header_disappears(self):
        import cv2
        outline=np.array([[320,40],[240,123],[128,151],[159,259],[128,373],[240,401],
                          [322,484],[402,401],[514,372],[483,266],[513,150],[402,123]],np.float32)
        outline+=np.array([320,130],np.float32)
        for w,h in [(1280,720),(1920,1080),(960,540)]:
            for color in [(0,170,40),(210,30,180),(20,80,220),(230,210,10)]:
                frame=screen(w,h)
                frame[round(h*.17):]=color
                frame[:round(h*.17),round(w*.38):round(w*.63)]=color
                points=np.round(outline*np.array([w/1280,h/720])).astype(np.int32)
                cv2.polylines(frame,[points],True,(5,5,5),max(2,round(8*h/720)))
                self.assertTrue(drop.mega_quest_drop(frame))
                self.assertEqual(state_finder.get_state(frame),'star_drop_chaos')
                frame[:round(h*.17)]=color
                self.assertFalse(drop.mega_quest_drop(frame))

    def test_header_with_unrelated_shapes_is_not_an_opening_star(self):
        import cv2
        for vertices in [np.array([[450,200],[800,200],[800,570],[450,570]]),
                         np.array([[640,170],[840,390],[640,610],[440,390]])]:
            frame=screen();frame[120:]=(0,170,40);frame[:120,480:810]=(0,170,40)
            cv2.polylines(frame,[vertices.astype(np.int32)],True,(5,5,5),8)
            self.assertFalse(drop.mega_quest_drop(frame))

    def test_multiple_opening_stars_at_smaller_sizes(self):
        import cv2
        outline=np.array([[320,40],[240,123],[128,151],[159,259],[128,373],[240,401],
                          [322,484],[402,401],[514,372],[483,266],[513,150],[402,123]],np.float32)
        outline-=outline.mean(axis=0)
        for count,scale in [(2,.8),(3,.6),(4,.48)]:
            for w,h in [(1280,720),(960,540),(1920,1080)]:
                frame=screen(w,h);frame[round(h*.17):]=(20,80,220)
                frame[:round(h*.17),round(w*.38):round(w*.63)]=(20,80,220)
                for x in np.linspace(.22,.78,count):
                    pts=outline*scale*np.array([w/1280,h/720])+[w*x,h*.55]
                    cv2.polylines(frame,[np.round(pts).astype(np.int32)],True,(5,5,5),max(2,round(6*h/720)))
                self.assertTrue(drop.mega_quest_drop(frame))
                frame[:round(h*.17)]=0
                self.assertFalse(drop.mega_quest_drop(frame))
