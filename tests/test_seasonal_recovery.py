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
 def test_double_reward_requires_both_matching_stars(self):
  f=reward();f[120:]=[40,130,85]
  source=reward()[176:628,448:836]
  star=cv2.resize(source,(364,408))
  f[192:600,252:616]=star;f[192:600,668:1032]=star
  for w,h in [(960,540),(1280,720),(1920,1080)]:
   self.assertTrue(modern_daily_reward(cv2.resize(f,(w,h))))
  f[192:600,668:1032]=[40,130,85]
  self.assertFalse(modern_daily_reward(f))
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

class XpRewardTests(unittest.TestCase):
 def test_xp_title_card_and_blue_background_required_at_multiple_sizes(self):
  from seasonal_rewards import XP_TITLE,XP_CARD,xp_doubler_reward
  from reward_received import is_reward_received
  f=np.full((720,1280,3),[20,90,230],np.uint8)
  for key,x,y in [(XP_TITLE,435,129),(XP_CARD,552,326)]:
   g=_glyph(key,720);f[y:y+g.shape[0],x:x+g.shape[1]]=g[:,:,None]
  for w,h in [(960,540),(1280,720),(1920,1080)]:
   self.assertTrue(is_reward_received(cv2.resize(f,(w,h))))
  without_title=f.copy();without_title[120:200]=[20,90,230]
  self.assertFalse(xp_doubler_reward(without_title))
  without_card=f.copy();without_card[300:450]=[20,90,230]
  self.assertFalse(xp_doubler_reward(without_card))
  f[570:]=[90,130,40];self.assertFalse(xp_doubler_reward(f))

class PointsGadgetReceiptTests(unittest.TestCase):
 def points(self):
  from seasonal_rewards import POINTS_TITLE,POINTS_ICON
  f=np.full((720,1280,3),[85,55,210],np.uint8)
  for key,x,y in [(POINTS_TITLE,427,147),(POINTS_ICON,602,357)]:
   g=_glyph(key,720);f[y:y+g.shape[0],x:x+g.shape[1]]=g[:,:,None]
  return f
 def gadget(self):
  from seasonal_rewards import GADGET_TITLE,GADGET_OUTLINE
  f=np.full((720,1280,3),[20,75,180],np.uint8)
  g=_glyph(GADGET_TITLE,720);f[183:236,736:998]=g[:,:,None]
  g=_glyph(GADGET_OUTLINE,720);roi=f[236:236+g.shape[0],137:137+g.shape[1]];roi[g>100]=[0,210,10]
  f[313:486,497:1230]=[0,10,25]
  for y in range(330,470,28):f[y:y+5,725:1200]=[30,240,240]
  return f
 def test_receipts_at_multiple_scales(self):
  from reward_received import is_reward_received
  for f in [self.points(),self.gadget()]:
   for w,h in [(960,540),(1280,720),(1920,1080)]:self.assertTrue(is_reward_received(cv2.resize(f,(w,h))))
 def test_points_require_title_icon_and_background(self):
  from seasonal_rewards import points_reward
  for bounds in [(140,210,420,860),(350,440,595,685),(610,720,0,1280)]:
   f=self.points();a,b,c,d=bounds;f[a:b,c:d]=[85,55,85];self.assertFalse(points_reward(f))
 def test_gadget_requires_heading_outline_and_description(self):
  from seasonal_rewards import gadget_reward
  for bounds in [(175,245,730,1005),(210,515,110,420),(313,486,497,1230)]:
   f=self.gadget();a,b,c,d=bounds;f[a:b,c:d]=[20,75,180];self.assertFalse(gadget_reward(f))
 def test_received_action_rechecks_stop_pause_and_retry(self):
  m=StageManager.__new__(StageManager);m.window_controller=Mock();m.window_controller.screenshot.return_value=self.points()
  m._should_stop=Mock(return_value=False);m._should_pause=Mock(return_value=False)
  with patch('stage_manager.time.monotonic',side_effect=[1.,1.5,2.,4.]):
   m.dismiss_received_reward();m.dismiss_received_reward();m.dismiss_received_reward();self.assertEqual(m.window_controller.click.call_count,2)
   m.window_controller.screenshot.return_value=announcement();m.dismiss_received_reward()
  m._should_stop.return_value=True;m.dismiss_received_reward()
  m._should_stop.return_value=False;m._should_pause.return_value=True;m.dismiss_received_reward()
  self.assertEqual(m.window_controller.click.call_count,2)
