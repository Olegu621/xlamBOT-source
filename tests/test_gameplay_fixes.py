import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import cv2
import numpy as np
from local_navigation import blocked,detour
from battle_perception import own_player,respawning,_caption

ROOT=Path(__file__).resolve().parents[1]

def method(file,cls,name,namespace):
    tree=ast.parse((ROOT/file).read_text('utf-8'))
    node=next(x for c in tree.body if isinstance(c,ast.ClassDef) and c.name==cls for x in c.body if isinstance(x,ast.FunctionDef) and x.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),file,'exec'),namespace)
    return namespace[name]

class GameplayFixTests(unittest.TestCase):
    def test_round_corners_allow_a_clear_path_but_not_wall_crossing(self):
        walls=[[20,20,40,40]]
        self.assertFalse(blocked((5,5),(11,11),10,walls))
        self.assertTrue(blocked((5,30),(50,30),5,walls))
        self.assertTrue(blocked((10,10),(14,14),10,walls))
        self.assertTrue(blocked((0,0),(100,0),5,[[40,-10,60,10]]))

    def test_initial_overlap_can_only_move_away_from_wall(self):
        wall=[[0,0,20,20]]
        self.assertFalse(blocked((25,10),(40,10),10,wall))
        self.assertTrue(blocked((25,10),(22,10),10,wall))

    def test_detour_finds_a_safe_corner_without_crossing_the_wall(self):
        walls=[[30,-20,50,20]]
        route=detour((0,0),(100,0),5,40,walls)
        self.assertIsNotNone(route)
        self.assertGreater(abs(route[1]),.1)
        self.assertFalse(blocked((0,0),(route[0]*40,route[1]*40),5,walls))
        self.assertIsNone(detour((0,0),(100,0),5,40,[]))

    def test_enemy_and_ally_cannot_be_the_player_even_when_ranked_first(self):
        data={'player':[[101,69,187,218],[570,240,710,420]],'enemy':[[104,70,186,218]],'teammate':[]}
        self.assertEqual(own_player(data)['player'],[[570,240,710,420]])
        self.assertEqual(own_player({'player':[[101,69,187,218]],'enemy':[[104,70,186,218]]})['player'],[])

    def test_respawn_caption_scales_without_matching_blank_battle(self):
        for h,w in [(720,1280),(1080,1920),(720,1600)]:
            frame=np.zeros((h,w,3),np.uint8);caption=_caption(h);th,tw=caption.shape
            y=int(h*.35);x=(w-tw)//2
            frame[y:y+th,x:x+tw]=caption[:,:,None]
            self.assertTrue(respawning(frame))
            self.assertFalse(respawning(np.zeros_like(frame)))

    def test_named_selection_replaces_stale_sorted_card_only_after_confirmation(self):
        import sys,time
        fake_reader=SimpleNamespace(read_card=Mock(return_value={'brawler':'byron','trophies':687}))
        namespace={'normalize_brawler_filename':lambda x:x,'load_brawlers_info':lambda:{},'load_toml_as_dict':lambda p:{'brawlers_menu':[1,1],'first_brawler_icon':[2,2],'select_brawler':[3,3]},'get_state':lambda f:f,'time':SimpleNamespace(sleep=lambda t:None)}
        select=method('lobby_automation.py','LobbyAutomation','select_brawler',namespace)
        window=Mock(width_ratio=1,height_ratio=1);window.screenshot.side_effect=['lobby','brawler_selection','brawler_selection','brawler_selection','lobby'];window.type_text.return_value=True
        bot=SimpleNamespace(window_controller=window,_frame_state=namespace['get_state'],_last_picked={'brawler':'carl','trophies':32},_confirm_brawler_selection=lambda *a:True,_should_interrupt=lambda *a:False,_sleep_interruptible=lambda *a:False)
        with patch.dict(sys.modules,{'trophy_reader':fake_reader}):
            # Cached recognition still says lobby; the new frame is the grid.
            self.assertEqual(select(bot,'byron',lambda:'lobby'),'success')
        self.assertEqual(bot._last_picked,{'brawler':'byron','trophies':687})
        fake_reader.read_card.return_value={'brawler':'carl'};window.screenshot.side_effect=['lobby','brawler_selection','brawler_selection'];window.click.reset_mock()
        with patch.dict(sys.modules,{'trophy_reader':fake_reader}):
            self.assertEqual(select(bot,'byron',lambda:'brawler_selection'),'failed')
        self.assertEqual(window.click.call_count,1) # menu only, not the wrong card

    def test_slow_name_ocr_requires_a_new_grid_observation_before_card_tap(self):
        import sys
        expired=[False]
        def read_card(*a,**kw):
            expired[0]=True
            return {'brawler':'vince','trophies':None}
        for next_screen,expected,clicks in [('brawler_selection','success',2),('shop','stuck',1)]:
            with self.subTest(next_screen=next_screen):
                frames=iter(['lobby','brawler_selection','brawler_selection',next_screen,'lobby'])
                def screenshot():
                    expired[0]=False
                    return next(frames)
                def click(*a,**kw):
                    self.assertFalse(expired[0],'OCR expired the decision; refresh before input')
                window=Mock(screenshot=screenshot,click=Mock(side_effect=click))
                namespace={'normalize_brawler_filename':lambda x:x,'load_brawlers_info':lambda:{},
                           'load_toml_as_dict':lambda p:{'brawlers_menu':[1,1],'first_brawler_icon':[2,2]}}
                select=method('lobby_automation.py','LobbyAutomation','select_brawler',namespace)
                bot=SimpleNamespace(window_controller=window,_frame_state=lambda f:f,
                    _confirm_brawler_selection=Mock(return_value=True),_last_picked=None,
                    _should_interrupt=lambda *a:False,_sleep_interruptible=lambda *a:False)
                with patch.dict(sys.modules,{'trophy_reader':SimpleNamespace(read_card=read_card)}):
                    self.assertEqual(select(bot,'vince',lambda:'lobby'),expected)
                self.assertEqual(window.click.call_count,clicks)
                if expected=='stuck':bot._confirm_brawler_selection.assert_not_called()

if __name__=='__main__':unittest.main()
