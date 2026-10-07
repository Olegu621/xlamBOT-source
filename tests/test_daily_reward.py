import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import screen_evidence as e
import state_finder as s
from stage_manager import StageManager

def reward(w=480,h=270,title=True,action=True):
    f=np.full((h,w,3),(80,30,90),np.uint8)
    for encoded,x,y,enabled in [(e.DAILY_WINS,.02,.037,title),(e.TAP_REWARD,.44,.063,action)]:
        if not enabled:continue
        raw=e._scaled(encoded,133,21) if encoded==e.DAILY_WINS else e._scaled(encoded,68,17)
        rh,rw=raw.shape[:2];t=e._scaled(encoded,round(rw*h/270),round(rh*h/270))
        x,y=round(x*w),round(y*h);f[y:y+t.shape[0],x:x+t.shape[1]]=t
    return f

class DailyRewardTests(unittest.TestCase):
    def test_two_captions_are_required_at_different_resolutions(self):
        for w,h in [(480,270),(1280,720),(1920,864)]:
            f=reward(w,h);self.assertTrue(e.daily_reward(f));self.assertEqual(s.get_state(f),'daily_reward')
        for title,action in [(True,False),(False,True),(False,False)]:self.assertFalse(e.daily_reward(reward(title=title,action=action)))
    def test_stale_state_cannot_click_lobby_and_repeated_clicks_are_limited(self):
        manager=StageManager.__new__(StageManager);manager.runtime_control=None;clicks=[]
        f=reward();manager.window_controller=SimpleNamespace(screenshot=lambda:f,release_all_inputs=lambda:None,click=lambda *a,**k:clicks.append(a))
        with patch('stage_manager.time.monotonic',side_effect=[1.,1.1,2.]):
            manager.dismiss_daily_reward();manager.dismiss_daily_reward();f=np.zeros((270,480,3),np.uint8);manager.dismiss_daily_reward()
        self.assertEqual(clicks,[(240.,135.)])
    def test_pause_prevents_reward_click(self):
        manager=StageManager.__new__(StageManager);manager.runtime_control=SimpleNamespace(should_stop=lambda:False,should_pause=lambda:True)
        manager.dismiss_daily_reward()

    def test_coins_need_caption_gold_stack_and_blue_reward_background(self):
        f=np.full((270,480,3),(0,70,200),np.uint8)
        t=e._scaled(e.COINS,81,25);f[33:58,200:281]=t
        self.assertFalse(e.coin_reward(f))
        f[80:200,170:310]=(255,180,0)
        self.assertTrue(e.coin_reward(f));self.assertEqual(s.get_state(f),'daily_reward')
        f[:]=50;f[33:58,200:281]=t;f[80:200,170:310]=(255,180,0)
        self.assertFalse(e.coin_reward(f))
