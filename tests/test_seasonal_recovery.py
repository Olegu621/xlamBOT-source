import unittest
from unittest.mock import Mock,patch
import cv2,numpy as np
from seasonal_rewards import TITLE,FACE,PIN,_glyph,modern_daily_reward,seasonal_announcement_dismiss_position
from stage_manager import StageManager
import state_finder

def reward():
 f=np.full((720,1280,3),[40,130,85],np.uint8)
 glyph=_glyph(TITLE,720);f[32:84,28:358]=20;f[32:84,28:358][glyph>205]=255
 pts=np.array([(160,44),(181,64),(206,72),(199,99),(207,126),(183,132),(160,156),(138,134),(112,127),(119,100),(112,72),(139,65)])*4
 cv2.fillPoly(f,[pts],[0,20,15]);cv2.circle(f,(640,404),105,[20,130,75],-1)
 return f

def announcement():
 f=np.full((720,1280,3),25,np.uint8);f[36:680,140:1140]=[90,130,120]
 for key,x,y in [(FACE,565,266),(PIN,868,116)]:
  g=_glyph(key,720);f[y:y+g.shape[0],x:x+g.shape[1]]=g[:,:,None]
 f[588:656,523:756]=[30,115,235]
 return f

class SeasonalRecoveryTests(unittest.TestCase):
 def test_positive_scales_and_animated_reward_star(self):
  for w,h in [(960,540),(1280,720),(1920,1080)]:
   self.assertTrue(modern_daily_reward(cv2.resize(reward(),(w,h))))
   self.assertIsNotNone(seasonal_announcement_dismiss_position(cv2.resize(announcement(),(w,h))))
 def test_title_without_star_or_dimmed_reward_is_not_enough(self):
  f=reward();f[120:]=80;self.assertFalse(modern_daily_reward(f))
  f=reward();f[:100]=80;self.assertFalse(modern_daily_reward(f))
  self.assertFalse(modern_daily_reward((reward()*.5).astype(np.uint8)))
 def test_generic_button_or_one_illustration_cannot_authorize_dismissal(self):
  f=announcement();f[116:239,868:1007]=80
  self.assertIsNone(seasonal_announcement_dismiss_position(f))
  f=announcement();f[588:656,523:756]=80
  self.assertIsNone(seasonal_announcement_dismiss_position(f))
 def test_owner_rechecks_frame_cancel_and_retry(self):
  m=StageManager.__new__(StageManager);m.window_controller=Mock();m.window_controller.screenshot.return_value=announcement()
  m._should_stop=Mock(return_value=False);m._should_pause=Mock(return_value=False)
  with patch('stage_manager.time.monotonic',side_effect=[1.,2.,2.5,4.]):
   m.dismiss_seasonal_announcement();m.dismiss_seasonal_announcement();m.dismiss_seasonal_announcement()
   self.assertEqual(m.window_controller.click.call_count,2)
   self.assertEqual(m.window_controller.click.call_args.args,(64,360))
   m.window_controller.screenshot.return_value=reward();m.dismiss_seasonal_announcement()
  m._should_pause.return_value=True;m.dismiss_seasonal_announcement()
  m._should_pause.return_value=False;m._should_stop.return_value=True;m.dismiss_seasonal_announcement()
  self.assertEqual(m.window_controller.click.call_count,2)
 def test_announcement_precedes_underlying_lobby(self):
  with patch('state_finder.is_in_lobby',return_value=True):
   self.assertEqual(state_finder.get_in_game_state(announcement()),'seasonal_announcement')
 def test_reward_recognition_keeps_existing_daily_action(self):
  self.assertEqual(state_finder.get_in_game_state(reward()),'daily_reward')
