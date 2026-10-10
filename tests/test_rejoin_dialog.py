import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
import numpy as np
from reward_receipts import _glyph
import rejoin_dialog as dialog
import disconnect_dialog
import state_finder
from lobby_automation import LobbyAutomation


def screen(w=1280,h=720):
    frame=np.full((h,w,3),15,np.uint8)
    frame[round(h*.32):round(h*.68),round(w*.24):round(w*.76)]=64
    for encoded,x,y in [(dialog.TITLE,347,268),(dialog.RELOAD,346,435)]:
        glyph=_glyph(encoded,h);px,py=round(x*h/720),round(y*h/720)
        if encoded==dialog.TITLE:
            frame[py:py+glyph.shape[0],px:px+glyph.shape[1]][glyph>205]=245
        else:frame[py:py+glyph.shape[0],px:px+glyph.shape[1]]=glyph[:,:,None]
    return frame


class RejoinTests(unittest.TestCase):
    def test_title_action_and_exact_grey_dialog(self):
        for w,h in [(1280,720),(1920,1080),(960,540)]:
            frame=screen(w,h)
            self.assertIsNotNone(dialog.rejoin_reload_position(frame))
            self.assertEqual(state_finder.get_state(frame),'idle_disconnect')
            frame[:round(h*.44)]=0
            self.assertIsNone(dialog.rejoin_reload_position(frame))
        frame=screen();frame[400:]=0
        self.assertIsNone(dialog.rejoin_reload_position(frame))
        frame=screen();frame[310:420,320:960]=(10,50,170)
        self.assertIsNone(dialog.rejoin_reload_position(frame))
    def test_owner_backoff_and_cached_dialog_cannot_click_lobby(self):
        owner=LobbyAutomation.__new__(LobbyAutomation)
        ctrl=SimpleNamespace(screenshot=lambda: screen(),release_all_inputs=Mock(),click=Mock())
        owner.window_controller=ctrl
        with patch('lobby_automation.time.monotonic',return_value=100):owner.check_for_idle(screen())
        self.assertEqual(ctrl.click.call_count,1)
        with patch('lobby_automation.time.monotonic',return_value=110):owner.check_for_idle(screen())
        self.assertEqual(ctrl.click.call_count,1)
        with patch('lobby_automation.time.monotonic',return_value=130):owner.check_for_idle(screen())
        self.assertEqual(ctrl.click.call_count,2)
        with patch('lobby_automation.time.monotonic',return_value=160):owner.check_for_idle(screen())
        self.assertEqual(ctrl.click.call_count,2)
        ctrl.screenshot=lambda: np.zeros((720,1280,3),np.uint8)
        with patch('lobby_automation.time.monotonic',return_value=200):owner.check_for_idle(screen())
        self.assertEqual(ctrl.click.call_count,2)
