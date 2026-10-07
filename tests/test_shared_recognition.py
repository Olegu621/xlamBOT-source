import unittest,ast,threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import cv2,numpy as np
import screen_evidence as e
import state_finder as s
ROOT=Path(__file__).resolve().parents[1]

def lobby(w,h,menu=True,button=True):
    frame=np.full((h,w,3),(15,60,120),np.uint8)
    if menu:
        t=e._scaled(e.MENU,round(16*h/199),round(11*h/199))
        x,y=round(w*.94)-t.shape[1]//2,round(h*.01)
        frame[y:y+t.shape[0],x:x+t.shape[1]]=t
    if button:
        x1,y1,x2,y2=map(round,(w*.76,h*.88,w*.98,h*.98))
        frame[y1:y2,x1:x2]=(255,210,0)
        cv2.putText(frame,'PLAY',(x1+round(w*.03),y2-round(h*.03)),cv2.FONT_HERSHEY_SIMPLEX,h/380,(255,255,255),max(1,round(h/200)))
    return frame

class SharedRecognitionTests(unittest.TestCase):
    def test_current_lobby_is_height_scaled_on_phones_and_emulators(self):
        for w,h in [(335,199),(480,270),(1280,720),(1920,864),(2400,1080)]:
            with self.subTest(w=w,h=h):
                f=lobby(w,h);self.assertTrue(e.current_lobby(f));self.assertTrue(s.is_in_lobby(f))
                x,y=e.play_button_position(f);self.assertGreater(x,w*.76);self.assertGreater(y,h*.88)
    def test_menu_and_play_are_both_required(self):
        for menu,button in [(True,False),(False,True),(False,False)]:
            self.assertFalse(e.current_lobby(lobby(1280,720,menu,button)))
    def test_battle_caption_is_height_scaled_and_bright(self):
        for w,h in [(480,270),(1280,720),(1920,864),(2400,1080)]:
            f=np.full((h,w,3),(90,35,95),np.uint8)
            t=e._scaled(e.TEAMS_LEFT,round(64*h/270),round(14*h/270))
            x,y=round(h*.037),round(h*.030)
            f[y:y+t.shape[0],x:x+t.shape[1]]=t
            self.assertTrue(e.current_showdown_hud(f));self.assertTrue(s.is_in_showdown_match(f))
            self.assertFalse(e.current_showdown_hud((f*.4).astype(np.uint8)))
    def test_menu_and_loading_cannot_start_gameplay(self):
        self.assertFalse(e.current_showdown_hud(lobby(1280,720)))
        self.assertFalse(e.current_showdown_hud(np.full((720,1280,3),45,np.uint8)))
    def test_incompatible_mode_requires_its_actual_lobby_caption(self):
        f=lobby(335,199)
        t=e._scaled(e.KNOCKOUT_RU,39,11)
        f[179:190,153:192]=t
        self.assertEqual(e.unsupported_lobby_mode(f),'knockout')
        self.assertIsNone(e.unsupported_lobby_mode(lobby(335,199)))
        # A translated error reaches the runtime instead of starting an AFK game.
        tree=ast.parse((ROOT/'stage_manager.py').read_text())
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='start_game')
        self.assertLess(ast.unparse(node).index('unsupported_lobby_mode(frame)'),ast.unparse(node).index('state is lobby'))
    def test_offline_adb_response_triggers_rediscovery(self):
        tree=ast.parse((ROOT/'window_controller.py').read_text())
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='reconnect_scrcpy')
        clock=SimpleNamespace(time=lambda:100.,sleep=lambda n:None)
        ns={'time':clock,'scrcpy':SimpleNamespace(EVENT_FRAME='frame')}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'reconnect','exec'),ns)
        obj=SimpleNamespace(scrcpy_client=Mock(),device=SimpleNamespace(get_state=lambda:'offline'),frame_lock=threading.Lock(),force_rediscover=Mock(return_value=True),_create_scrcpy_client=Mock(return_value=Mock()),get_latest_frame=lambda:(np.zeros((2,2,3)),100))
        self.assertTrue(ns['reconnect_scrcpy'](obj,max_retries=1))
        obj.force_rediscover.assert_called_once()
    def test_play_uses_verified_button_instead_of_fixed_menu_coordinates(self):
        tree=ast.parse((ROOT/'stage_manager.py').read_text())
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='start_game')
        text=ast.unparse(node)
        self.assertIn('play_button_position(frame)',text)
        self.assertIn('if button is None:',text)
        self.assertNotIn("press('proceed')",text)

if __name__=='__main__':unittest.main()
