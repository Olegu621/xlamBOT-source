import unittest
import numpy as np
import onboarding as o
from onboarding_assets_en import ASSETS


def put(frame,name,x,y):
    glyph=o.template(ASSETS[name],720)
    frame[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph


class EnglishOnboardingTests(unittest.TestCase):
    def test_generated_nickname_requires_nonempty_field_and_identity(self):
        f=np.zeros((720,1280,3),np.uint8)
        sid=o.template(o.SID,720);f[62:62+sid.shape[0],32:32+sid.shape[1]]=sid
        put(f,'NICK_TITLE',387,69);put(f,'NICK_OK',850,199)
        f[194:245,346:717]=255
        self.assertIsNone(o.generated_name_confirm(f))
        f[210:233,420:610]=0
        self.assertIsNotNone(o.generated_name_confirm(f))
        f[62:120,:250]=0
        self.assertIsNone(o.generated_name_confirm(f))

    def test_reward_targets_the_current_icon_and_requires_tutorial_hint(self):
        f=np.zeros((720,1280,3),np.uint8)
        put(f,'REWARD_HINT',161,241);put(f,'LOBBY_ROAD_REWARD',327,64)
        self.assertIsNone(o.first_reward_guide(f))
        f[105:180,230:335]=(255,205,130)
        p=o.first_reward_guide(f)
        self.assertIsNotNone(p);self.assertGreater(p[0],320)
        f[64:96,327:356]=0
        self.assertIsNone(o.first_reward_guide(f))

    def test_instruction_requires_english_title_and_button(self):
        f=np.zeros((720,1280,3),np.uint8)
        put(f,'UPGRADE_INFO',300,55)
        self.assertIsNone(o.instruction_confirm(f))
        put(f,'INFO_CONFIRM',563,620)
        self.assertIsNotNone(o.instruction_confirm(f))
        f[:144]=0
        self.assertIsNone(o.instruction_confirm(f))

    def test_english_card_header_is_not_truncated_by_russian_region(self):
        f=np.zeros((720,1280,3),np.uint8)
        put(f,'ONE_OWNED',644,83);put(f,'SHELLY_NAME',780,243);put(f,'SHELLY_LEVEL_ONE',885,113)
        self.assertIsNotNone(o.guided_upgrade(f))
        f[83:107]=0
        self.assertIsNone(o.guided_upgrade(f))

    def test_upgrade_requires_first_level_price_and_hand(self):
        f=np.zeros((720,1280,3),np.uint8)
        put(f,'SHELLY_DETAIL_NAME',112,144);put(f,'DETAIL_LEVEL_ONE',929,305)
        price=o.template(o.UPGRADE_PRICE,720)
        f[578:578+price.shape[0],969:969+price.shape[1]]=price
        self.assertIsNone(o.guided_upgrade(f))
        f[350:438,982:1060]=(255,205,130)
        self.assertIsNotNone(o.guided_upgrade(f))
        f[305:338,929:954]=0
        self.assertIsNone(o.guided_upgrade(f))

    def test_confirmation_title_does_not_authorize_purchase_without_hand(self):
        f=np.zeros((720,1280,3),np.uint8)
        put(f,'UPGRADE_TWO_TITLE',410,72)
        price=o.template(o.UPGRADE_CONFIRM_PRICE,720)
        f[646:646+price.shape[0],869:869+price.shape[1]]=price
        self.assertIsNone(o.guided_upgrade(f))
        f[500:605,850:990]=(255,205,130)
        self.assertIsNotNone(o.guided_upgrade(f))

    def test_guided_play_requires_the_hand_and_current_play_button(self):
        f=np.zeros((720,1280,3),np.uint8)
        put(f,'GUIDE_PLAY_HINT',880,442);put(f,'GUIDE_PLAY',1054,631)
        self.assertIsNone(o.guided_play(f))
        f[510:610,980:1080]=(255,205,130)
        self.assertIsNotNone(o.guided_play(f))
        f[631:670]=0
        self.assertIsNone(o.guided_play(f))

    def test_first_solo_win_requires_current_english_caption_and_exit(self):
        f=np.zeros((720,1280,3),np.uint8)
        put(f,'FIRST_WIN',33,18);put(f,'FIRST_EXIT',1094,651)
        self.assertIsNotNone(o.first_result_exit(f))
        f[651:]=0
        self.assertIsNone(o.first_result_exit(f))
