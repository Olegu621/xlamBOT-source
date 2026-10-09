import unittest
from types import SimpleNamespace
from unittest.mock import patch
import cv2
import numpy as np
import reward_receipts as r
from stage_manager import StageManager
from state_finder import get_state


def paste(frame, encoded, x, y, white=True):
    glyph = r._glyph(encoded, frame.shape[0])
    h, w = glyph.shape
    region = frame[y:y+h, x:x+w]
    if white:
        region[glyph > 205] = 255

    else:
        region[:] = glyph[:,:,None]


def receipt(kind, width=1280, height=720):
    f = np.full((height,width,3), (80,85,210), np.uint8)

    if kind == 'bling':
        paste(f,r.BLING_TITLE,round(width*.418),round(height*.122))
        paste(f,r.BLING_TOKEN,round(width*.480),round(height*.525),False)
    else:
        paste(f,r.CURRENT_SKIN,round(width*.599),round(height*.022))
        paste(f,r.REMAINING,round(width*.735),round(height*.918))
        f[round(height*.81):round(height*.92),round(width*.48):round(width*.68)] = (10,110,245)
        paste(f,r.CONTINUE,round(width*.493),round(height*.826))
    return f


class RewardReceiptTests(unittest.TestCase):
    def test_new_receipts_route_to_bounded_owner_handlers(self):
        for width,height in [(1280,720),(1920,1080)]:
            self.assertEqual(get_state(receipt('bling',width,height)), 'reward_received')
            self.assertEqual(get_state(receipt('skin',width,height)), 'seasonal_announcement')

    def test_skin_preview_without_remaining_items_cannot_authorize_continue(self):
        f=receipt('skin');f[650:,:]=0
        self.assertIsNone(r.skin_receipt_continue_position(f))
        f=receipt('skin');f[:80,:]=0
        self.assertIsNone(r.skin_receipt_continue_position(f))
        f=receipt('skin');f[594:641,600:870]=0
        self.assertIsNone(r.skin_receipt_continue_position(f))

    def test_bling_title_or_currency_icon_in_ordinary_ui_is_insufficient(self):
        f=receipt('bling');f[370:550,590:900]=0
        self.assertFalse(r.bling_receipt(f))
        f=receipt('bling');f[:,:155]=0
        self.assertFalse(r.bling_receipt(f))
        for value in [None,np.zeros((20,20),np.uint8)]:
            self.assertFalse(r.bling_receipt(value))
            self.assertIsNone(r.skin_receipt_continue_position(value))

    def test_skin_continue_never_equips_and_revalidates_changed_screen(self):
        manager=StageManager.__new__(StageManager);manager.runtime_control=None
        frame=receipt('skin');clicks=[]
        manager.window_controller=SimpleNamespace(screenshot=lambda:frame,
            release_all_inputs=lambda:None,click=lambda *a,**kw:clicks.append(a))
        with patch('stage_manager.time.monotonic',side_effect=[1.,1.1,3.]):
            manager.dismiss_seasonal_announcement()
            manager.dismiss_seasonal_announcement()
            frame=np.zeros_like(frame)
            manager.dismiss_seasonal_announcement()
        self.assertEqual(len(clicks),1)
        self.assertLess(clicks[0][0],1280*.69)

    def test_pause_does_not_dismiss_rewards(self):
        manager=StageManager.__new__(StageManager)
        manager.runtime_control=SimpleNamespace(should_stop=lambda:False,should_pause=lambda:True)
        manager.dismiss_seasonal_announcement()
        manager.dismiss_received_reward()




class LockedSkinReceiptTests(unittest.TestCase):
    def frame(self):
        f=receipt('skin')
        f[580:660,:]=35
        f[438:591,844:1191]=0
        paste(f,r.REQUIRED_BRAWLER,856,450)
        return f

    def test_locked_skin_with_remaining_items_uses_receipt_handler(self):
        f=self.frame()
        self.assertTrue(r.locked_skin_receipt(f))
        self.assertEqual(get_state(f),'reward_received')
        self.assertIsNone(r.skin_receipt_continue_position(f))

    def test_locked_skin_preview_or_isolated_label_is_not_a_receipt(self):
        for bounds in [(650,720),(440,500)]:
            f=self.frame();f[bounds[0]:bounds[1]]=0
            self.assertFalse(r.locked_skin_receipt(f))
        f=self.frame();f[490:591,844:1191]=255
        self.assertFalse(r.locked_skin_receipt(f))
        self.assertFalse(r.locked_skin_receipt(None))


class RewardSequenceTests(unittest.TestCase):
    def receipt(self):
        f=np.full((720,1280,3),(0,70,200),np.uint8)
        paste(f,r.REMAINING,941,661)
        f[330:450,550:720]=20
        return f

    def test_remaining_items_reveal_routes_to_interruptible_handler(self):
        f=self.receipt()
        self.assertTrue(r.sequence_receipt(f))
        self.assertEqual(get_state(f),'reward_received')

    def test_counter_without_backdrop_or_item_does_not_authorize_input(self):
        f=self.receipt();f[140:620,:300]=0
        self.assertFalse(r.sequence_receipt(f))
        f=self.receipt();f[330:450,550:720]=(0,70,200)
        self.assertFalse(r.sequence_receipt(f))
        f=self.receipt();f[650:,:]=0
        self.assertFalse(r.sequence_receipt(f))


class RewardSummaryTests(unittest.TestCase):
    def frame(self):
        f=np.full((720,1280,3),(0,70,200),np.uint8)
        paste(f,r.SUMMARY_TITLE,551,73,False)
        return f

    def test_high_summary_title_on_receipt_backdrop_is_dismissible(self):
        self.assertEqual(get_state(self.frame()),'reward_received')

    def test_isolated_summary_header_cannot_dismiss_an_ordinary_menu(self):
        f=self.frame();f[550:]=50
        self.assertFalse(r.summary_receipt(f))
        f=self.frame();f[:160]=50
        self.assertFalse(r.summary_receipt(f))


class CurrentBlingReceiptTests(unittest.TestCase):
    def current(self,w=1280,h=720,title=True,token=True):
        f=np.full((h,w,3),(80,85,210),np.uint8)
        if title:paste(f,r.BLING_TITLE,round(w*.418),round(h*.122))
        if token:paste(f,r.CURRENT_BLING_TOKEN,round(w*.480),round(h*.530),False)
        return f

    def test_current_token_and_legacy_token_both_route_to_receipt(self):
        for w,h in [(1280,720),(1920,1080),(960,540)]:
            self.assertEqual(get_state(self.current(w,h)),'reward_received')
            self.assertTrue(r.bling_receipt(receipt('bling',w,h)))

    def test_current_token_alone_title_alone_and_dimmed_modal_do_not_authorize_tap(self):
        for frame in [self.current(title=False),self.current(token=False),(self.current()*.7).astype(np.uint8)]:
            self.assertFalse(r.bling_receipt(frame))
        frame=self.current();frame[:,:round(frame.shape[1]*.12)]=(230,80,30)
        self.assertFalse(r.bling_receipt(frame))

    def test_dismissal_rechecks_current_pixels_and_never_taps_after_cancel(self):
        m=StageManager.__new__(StageManager);frame=self.current();calls=[]
        m.runtime_control=None
        m.window_controller=SimpleNamespace(screenshot=lambda:frame,release_all_inputs=lambda:None,click=lambda *p,**kw:calls.append(p))
        with patch('stage_manager.time.monotonic',return_value=10):
            m.dismiss_received_reward();m.dismiss_received_reward()
        self.assertEqual(calls,[(640,634)])
        frame=self.current(title=False)
        with patch('stage_manager.time.monotonic',return_value=12):m.dismiss_received_reward()
        frame=self.current()
        for stop,pause in [(True,False),(False,True)]:
            m.runtime_control=SimpleNamespace(should_stop=lambda:stop,should_pause=lambda:pause)
            with patch('stage_manager.time.monotonic',return_value=14):m.dismiss_received_reward()
        self.assertEqual(len(calls),1)
