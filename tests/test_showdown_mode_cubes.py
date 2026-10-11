import unittest
from unittest.mock import patch
import numpy as np
from showdown_mode import event_screen,trio_choice,selected_trio,TrioSelector
from mode_assets import EVENT_NAV,TRIO_CHOICE,TRIO_LOBBY
from onboarding_assets import ROAD_HOME
from onboarding import template
from power_cubes import visible_cubes,choose_cube

class ModeCubeTests(unittest.TestCase):
    def test_unrecognized_event_returns_through_confirmed_home_and_waits(self):
        from test_onboarding import Stage
        stage=Stage();selector=TrioSelector();selector.swipes=3
        stage.window_controller.swipe=lambda *args,**kwargs:stage.window_controller.actions.append(('swipe',args))
        frame=np.zeros((720,1280,3),np.uint8)
        for encoded,x,y in [(EVENT_NAV,1087,5),(ROAD_HOME,1200,8)]:
            glyph=template(encoded,720);frame[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph
        with patch('showdown_mode.time.monotonic',return_value=10):
            self.assertFalse(selector.step(stage,frame))
        self.assertEqual(len(stage.window_controller.actions),1)
        self.assertGreater(stage.window_controller.actions[0][1][0],1152)
        with patch('showdown_mode.time.monotonic',return_value=20):
            selector.step(stage,frame)
        self.assertEqual(len(stage.window_controller.actions),1)
        with patch('showdown_mode.time.monotonic',return_value=41):
            selector.step(stage,frame)
        self.assertEqual(stage.window_controller.actions[-1][0],'swipe')

    def test_missing_frame_or_unrecognized_home_cannot_trigger_recovery_taps(self):
        from test_onboarding import Stage
        stage=Stage();selector=TrioSelector();selector.swipes=3
        selector.step(stage,None)
        selector.step(stage,np.zeros((720,1280,3),np.uint8))
        self.assertEqual(stage.window_controller.actions,[])

    def test_current_trio_win_needs_next_button_and_bright_letters(self):
        from showdown_mode import trio_win_next
        from mode_assets import TRIO_WIN,RESULT_NEXT
        frame=np.zeros((720,1280,3),np.uint8)
        for encoded,x,y in [(TRIO_WIN,33,9),(RESULT_NEXT,1074,651)]:
            glyph=template(encoded,720);frame[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph
        self.assertIsNotNone(trio_win_next(frame))
        self.assertIsNone(trio_win_next((frame*.4).astype(np.uint8)))
        frame[640:]=0
        self.assertIsNone(trio_win_next(frame))

    def test_rotating_cube_glow_is_not_lost_at_green_box_edge(self):
        import cv2
        from pathlib import Path
        patch=cv2.cvtColor(cv2.imread(str(Path(__file__).parent/'fixtures/loose_power_cube.png')),cv2.COLOR_BGR2RGB)
        frame=np.zeros((720,1280,3),np.uint8)
        frame[300:400,700:800]=patch
        points=visible_cubes(frame)
        self.assertEqual(len(points),1)
        self.assertLess(abs(points[0][0]-751),3)
        self.assertLess(abs(points[0][1]-357),3)

    def test_trio_requires_popup_icon_and_event_navigation(self):
        frame=np.zeros((720,1280,3),np.uint8)
        for glyph,x,y in [(EVENT_NAV,1087,5),(ROAD_HOME,1200,8),(TRIO_CHOICE,60,513)]:
            image=template(glyph,720);frame[y:y+image.shape[0],x:x+image.shape[1]]=image
        frame[520:588,148:235]=(255,210,0)
        self.assertTrue(event_screen(frame))
        self.assertIsNotNone(trio_choice(frame))
        self.assertFalse(selected_trio(frame))
        frame[:90]=0
        self.assertIsNone(trio_choice(frame))

    def test_unknown_or_stop_never_opens_mode_menu(self):
        from test_onboarding import Stage
        stage=Stage();selector=TrioSelector()
        self.assertFalse(selector.step(stage,np.zeros((720,1280,3),np.uint8)))
        self.assertEqual(stage.window_controller.actions,[])
        stage.stopped=True
        self.assertFalse(selector.step(stage,np.zeros((720,1280,3),np.uint8),lobby=True))

    def test_cubes_require_gold_core_and_exclude_small_badge(self):
        frame=np.zeros((720,1280,3),np.uint8)
        frame[320:359,700:740]=(60,220,65)
        frame[332:344,711:725]=(240,210,60)
        frame[300:320,500:520]=(60,220,65)
        frame[420:459,800:840]=(60,220,65)
        self.assertEqual(visible_cubes(frame),[(720.,339.5)])

    def test_enemy_gas_and_entity_badges_are_not_collection_targets(self):
        target=(720,340);player=(640,400);mask=np.zeros((720,1280),np.uint8)
        self.assertEqual(choose_cube([target],player,[],[],40,mask),target)
        self.assertIsNone(choose_cube([target],player,[(650,405)],[],40,mask))
        self.assertIsNone(choose_cube([target],player,[],[target],40,mask))
        mask[310:370,690:750]=255
        self.assertIsNone(choose_cube([target],player,[],[],40,mask))

    def test_english_new_tile_requires_navigation_and_large_yellow_tile(self):
        from showdown_mode import english_new_showdown
        from mode_assets import NEW_EVENT_EN
        frame=np.zeros((720,1280,3),np.uint8)
        frame[175:610,83:340]=(255,220,0)
        for encoded,x,y in [(EVENT_NAV,1087,5),(ROAD_HOME,1200,8),(NEW_EVENT_EN,155,365)]:
            glyph=template(encoded,720);frame[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph
        self.assertIsNotNone(english_new_showdown(frame))
        frame[:90]=0
        self.assertIsNone(english_new_showdown(frame))
        frame[175:340]=0
        self.assertIsNone(english_new_showdown(frame))
