import unittest
from unittest.mock import patch
import numpy as np
from onboarding import Onboarding, age_controls, onboarding_screen, path_direction, template, SID


def age_frame(selected=False):
    frame=np.full((720,1280,3),(10,62,170),dtype=np.uint8)
    sid=template(SID,720)
    frame[62:62+sid.shape[0],32:32+sid.shape[1]]=sid
    frame[330:390,330:963]=(53,74,116)
    x=640 if selected else 540
    frame[322:387,x-50:x+50]=(20,220,10)
    frame[482:562,522:763]=(20,220,10) if selected else (155,155,155)
    return frame


class Controller:
    PID_JOYSTICK=1
    def __init__(self):self.actions=[]
    def click(self,*p):self.actions.append(('click',p))
    def touch_down(self,*p,**kw):self.actions.append(('down',p))
    def touch_move(self,*p,**kw):self.actions.append(('move',p))
    def touch_up(self,*p,**kw):self.actions.append(('up',p))


class Stage:
    def __init__(self,stopped=False):self.window_controller=Controller();self.stopped=stopped
    def _should_stop(self):return self.stopped
    def _should_pause(self):return False
    def _sleep_interruptible(self,seconds):pass


class FirstRunTests(unittest.TestCase):
    def test_menu_animation_cannot_repeat_previous_control(self):
        stage=Stage();handler=Onboarding();handler.age_position=.5
        with patch('onboarding.time.monotonic',return_value=10):
            handler.step(stage,age_frame(True))
        with patch('onboarding.time.monotonic',return_value=10.5):
            handler.step(stage,age_frame(True))
        self.assertEqual(len(stage.window_controller.actions),1)
        with patch('onboarding.time.monotonic',return_value=12):
            handler.step(stage,age_frame(True))
        self.assertEqual(len(stage.window_controller.actions),2)

    def test_small_projectile_cannot_enable_tutorial_attack(self):
        from onboarding import attack_button
        frame=np.zeros((720,1280,3),dtype=np.uint8)
        frame[480:507,1210:1238]=(255,40,10)
        self.assertIsNone(attack_button(frame))
        import cv2
        cv2.circle(frame,(1110,560),38,(255,40,10),-1)
        self.assertIsNotNone(attack_button(frame))

    def test_guided_transition_wait_is_bounded_and_never_applies_to_battle(self):
        handler=Onboarding();handler.phase='guided_upgrade';handler.last_action=10
        with patch('onboarding.time.monotonic',return_value=11):
            self.assertTrue(handler.pending_transition('brawler_selection'))
            self.assertFalse(handler.pending_transition('match'))
        with patch('onboarding.time.monotonic',return_value=14):
            self.assertFalse(handler.pending_transition('brawler_selection'))

    def test_highlighted_shelly_card_retains_identity_during_glow(self):
        from onboarding import ONE_OWNED,SHELLY_NAME,SHELLY_LEVEL_ONE,guided_upgrade
        frame=np.zeros((720,1280,3),dtype=np.uint8)
        for encoded,x,y in [(ONE_OWNED,642,84),(SHELLY_NAME,778,242),(SHELLY_LEVEL_ONE,879,114)]:
            glyph=template(encoded,720).copy()
            if encoded != ONE_OWNED:
                glyph=(glyph.astype(np.float32)*.85+np.array([0,20,10])).clip(0,255).astype(np.uint8)
            frame[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph
        point=guided_upgrade(frame)
        self.assertIsNotNone(point)
        self.assertTrue(620<point[0]<920 and 112<point[1]<290)
        frame[84:110]=0
        self.assertIsNone(guided_upgrade(frame))

    def test_inactive_confirmation_still_allows_age_slider(self):
        stage=Stage()
        with patch('onboarding.random.uniform',return_value=.5):
            self.assertTrue(Onboarding().step(stage,age_frame()))
        self.assertEqual([x[0] for x in stage.window_controller.actions],['down','move','up'])
        self.assertEqual(stage.window_controller.actions[1][1][0],640)

    def test_confirmation_waits_for_observed_slider_position(self):
        stage=Stage();handler=Onboarding();handler.age_position=.5
        self.assertIsNotNone(age_controls(age_frame(True)))
        handler.step(stage,age_frame(True))
        self.assertEqual(stage.window_controller.actions[0][0],'click')

    def test_stop_and_unknown_never_send_inputs(self):
        stage=Stage(True)
        self.assertTrue(Onboarding().step(stage,age_frame()))
        self.assertEqual(stage.window_controller.actions,[])
        self.assertFalse(onboarding_screen(np.zeros((720,1280,3),dtype=np.uint8)))

    def test_ammunition_bar_does_not_block_path(self):
        frame=np.full((720,1280,3),(150,95,110),dtype=np.uint8)
        frame[415:423,625:698]=(240,155,60)
        direction=path_direction(frame,(661,481),(691,366))
        self.assertIsNotNone(direction)
        self.assertLess(direction[1],0)

    def test_full_wall_blocks_route(self):
        frame=np.full((720,1280,3),(150,95,110),dtype=np.uint8)
        frame[330:370,:]=(240,145,110)
        self.assertIsNone(path_direction(frame,(661,481),(691,250)))

    def test_russian_disconnect_requires_both_controls(self):
        from disconnect_dialog import _template,RUSSIAN_TITLE,RUSSIAN_RELOAD,idle_disconnect_reload_position
        for height,width in [(720,1280),(1080,1920)]:
            frame=np.full((height,width,3),65,dtype=np.uint8)
            for encoded,x,y in [(RUSSIAN_TITLE,348,277),(RUSSIAN_RELOAD,348,428)]:
                glyph=_template(encoded,width,height,(1280,720))
                x,y=round(x*width/1280),round(y*height/720)
                frame[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph
            self.assertIsNotNone(idle_disconnect_reload_position(frame))
            frame[round(.55*height):round(.67*height)]=65
            self.assertIsNone(idle_disconnect_reload_position(frame))

    def test_russian_solo_caption_never_confirms_dimmed_modal(self):
        from showdown_hud import _caption,CAPTION_SOLO_RUSSIAN,visible_showdown_caption
        frame=np.zeros((720,1280,3),dtype=np.uint8)
        glyph=_caption(720,encoded=CAPTION_SOLO_RUSSIAN)
        frame[30:30+glyph.shape[0],25:25+glyph.shape[1]]=glyph[:,:,None]
        self.assertTrue(visible_showdown_caption(frame))
        self.assertFalse(visible_showdown_caption((frame*.5).astype(np.uint8)))

    def test_current_russian_trio_counter_excludes_dimmed_battle(self):
        from showdown_hud import _caption,CAPTION_TRIO_RUSSIAN,visible_showdown_caption
        frame=np.zeros((720,1280,3),dtype=np.uint8)
        glyph=_caption(720,encoded=CAPTION_TRIO_RUSSIAN)
        frame[30:30+glyph.shape[0],25:25+glyph.shape[1]]=glyph[:,:,None]
        self.assertTrue(visible_showdown_caption(frame))
        self.assertFalse(visible_showdown_caption((frame*.5).astype(np.uint8)))

    def test_first_result_requires_caption_and_exit(self):
        from onboarding import FIRST_WIN,FIRST_EXIT,first_result_exit
        frame=np.zeros((720,1280,3),dtype=np.uint8)
        for encoded,x,y in [(FIRST_WIN,32,21),(FIRST_EXIT,1068,650)]:
            glyph=template(encoded,720)
            frame[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph
        self.assertIsNotNone(first_result_exit(frame))
        frame[640:]=0
        self.assertIsNone(first_result_exit(frame))

    def test_empty_nickname_is_never_confirmed(self):
        from onboarding import NICK_TITLE,NICK_OK,generated_name_confirm
        frame=age_frame();frame[180:255,315:760]=255
        for encoded,x,y in [(NICK_TITLE,390,80),(NICK_OK,849,198)]:
            glyph=template(encoded,720)
            frame[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph
        self.assertIsNone(generated_name_confirm(frame))
        frame[209:234,395:680]=0
        self.assertIsNotNone(generated_name_confirm(frame))

    def test_upgrade_requires_level_one_price_and_tutorial_hand(self):
        from onboarding import SHELLY_DETAIL_NAME,UPGRADE_PRICE,DETAIL_LEVEL_ONE,guided_upgrade
        frame=np.zeros((720,1280,3),dtype=np.uint8)
        for encoded,x,y in [(SHELLY_DETAIL_NAME,114,151),(UPGRADE_PRICE,969,578),(DETAIL_LEVEL_ONE,929,307)]:
            glyph=template(encoded,720)
            frame[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph
        self.assertIsNone(guided_upgrade(frame))
        frame[350:438,982:1060]=(255,205,130)
        self.assertIsNotNone(guided_upgrade(frame))
        frame[578:610]=0
        self.assertIsNone(guided_upgrade(frame))

    def test_currency_title_alone_does_not_authorize_dismissal(self):
        from onboarding import POWER_TITLE,POWER_ICON,power_receipt
        frame=np.zeros((720,1280,3),dtype=np.uint8)
        title=template(POWER_TITLE,720)
        frame[155:155+title.shape[0],467:467+title.shape[1]]=title
        self.assertFalse(power_receipt(frame))
        icon=template(POWER_ICON,720)
        frame[356:356+icon.shape[0],608:608+icon.shape[1]]=icon
        self.assertTrue(power_receipt(frame))
