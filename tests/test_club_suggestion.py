import unittest
from unittest.mock import Mock,patch
import cv2,numpy as np
from club_suggestion import _cross,club_suggestion_close_position
from stage_manager import StageManager
import state_finder

def modal():
 f=np.full((720,1280,3),20,np.uint8)
 f[67:145,248:1028]=[37,141,244];f[145:657,248:1028]=[16,93,229]
 for i in range(5):
  f[239+75*i:300+75*i,275:1000]=[111,96,109]
  f[301+75*i:307+75*i,275:1000]=0
 f[77:123,970:1032]=[230,45,35]
 glyph=_cross(720);f[77:123,970:1032][glyph>0]=255
 return f

class ClubSuggestionTests(unittest.TestCase):
 def test_modal_at_multiple_scales_and_ultrawide(self):
  for w,h in [(1280,720),(960,540),(1920,1080)]:
   self.assertIsNotNone(club_suggestion_close_position(cv2.resize(modal(),(w,h))))
  wide=np.full((720,1600,3),20,np.uint8);wide[:,160:1440]=modal()
  self.assertIsNotNone(club_suggestion_close_position(wide))
 def test_isolated_close_and_incomplete_or_dimmed_modal_refused(self):
  f=modal();f[150:650,250:960]=20
  self.assertIsNone(club_suggestion_close_position(f))
  f=modal();f[535:590,275:1000]=[16,93,229]
  self.assertIsNone(club_suggestion_close_position(f))
  self.assertIsNone(club_suggestion_close_position((modal()*.5).astype(np.uint8)))
 def test_fresh_frame_stop_pause_and_retry_interval(self):
  m=StageManager.__new__(StageManager);m.window_controller=Mock();m.window_controller.screenshot.return_value=modal()
  m._should_stop=Mock(return_value=False);m._should_pause=Mock(return_value=False)
  with patch('stage_manager.time.monotonic',side_effect=[1.,2.,2.5,4.]):
   m.close_club_suggestion();m.close_club_suggestion();m.close_club_suggestion()
   self.assertEqual(m.window_controller.click.call_count,2)
   m.window_controller.screenshot.return_value=np.zeros((720,1280,3),np.uint8)
   m.close_club_suggestion();self.assertEqual(m.window_controller.click.call_count,2)
  m._should_pause.return_value=True;m.close_club_suggestion()
  m._should_pause.return_value=False;m._should_stop.return_value=True;m.close_club_suggestion()
  self.assertEqual(m.window_controller.click.call_count,2)
 def test_modal_precedes_underlying_lobby(self):
  with patch('state_finder.is_in_lobby',return_value=True):
   self.assertEqual(state_finder.get_in_game_state(modal()),'club_suggestion')
