import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import brawler_detail as d
import state_finder
from stage_manager import StageManager
from lobby_automation import LobbyAutomation

def screen(w=1280,h=720,missing=None):
 f=np.full((h,w,3),(10,120,240),np.uint8)
 for name,x,y in [('PROFILE',.04,.76),('CHAT',.12,.76),('HANGER',.20,.76),('HOME',.93,.01)]:
  if name==missing:continue
  g=d._glyph(getattr(d,name),h);a,b=round(w*x),round(h*y);f[b:b+g.shape[0],a:a+g.shape[1]]=g
 if missing!='SELECT':f[round(h*.87):round(h*.95),round(w*.02):round(w*.25)]=(245,195,0)
 return f

class DetailTests(unittest.TestCase):
 def test_resolution_and_aspect(self):
  for w,h in [(960,540),(1280,720),(1920,1080),(1920,864)]:
   self.assertIsNotNone(d.detail_home_position(screen(w,h)))
   p=d.detail_select_position(screen(w,h));self.assertTrue(p[0]<w*.3 and p[1]>h*.84)
 def test_independent_evidence_required(self):
  for missing in ['HOME','PROFILE','CHAT','HANGER','SELECT']:self.assertIsNone(d.detail_select_position(screen(missing=missing)))
  self.assertIsNone(d.detail_home_position(None))
  self.assertIsNone(d.detail_home_position(np.zeros((720,1280),np.uint8)))
 def test_detail_before_generic_shop(self):
  self.assertEqual(state_finder.get_in_game_state(screen()),'brawler_detail')
 def test_selection_refresh_and_cancel(self):
  a=LobbyAutomation.__new__(LobbyAutomation);events=[]
  a.window_controller=SimpleNamespace(screenshot=lambda:events.append('frame') or screen(),click=lambda *x,**k:events.append(('click',k)))
  self.assertTrue(a._confirm_brawler_selection());self.assertEqual(events,['frame',('click',{'already_include_ratio':True})]);events.clear()
  for stop,pause in [(True,False),(False,True)]:
   c=SimpleNamespace(should_stop=lambda:stop,should_pause=lambda:pause)
   self.assertFalse(a._confirm_brawler_selection(c))
  self.assertEqual(events,[])
 def test_bounded_retry_no_blind_tap(self):
  a=LobbyAutomation.__new__(LobbyAutomation);events=[]
  a.window_controller=SimpleNamespace(screenshot=lambda:events.append('frame') or screen(missing='SELECT'),click=lambda *x,**k:events.append('click'))
  with patch.object(a,'_sleep_interruptible',return_value=False):self.assertFalse(a._confirm_brawler_selection())
  self.assertEqual(events,['frame']*3)
 def test_recovery_recheck_and_stop(self):
  m=StageManager.__new__(StageManager);m.runtime_control=None;calls=[];f=screen()
  m.window_controller=SimpleNamespace(screenshot=lambda:f,release_all_inputs=lambda:None,click=lambda *x,**k:calls.append(x))
  with patch.object(m,'_sleep_interruptible',return_value=False):
   m.close_brawler_detail();f=screen(missing='HOME');m.close_brawler_detail();f=screen()
   m.runtime_control=SimpleNamespace(should_stop=lambda:True,should_pause=lambda:False);m.close_brawler_detail()
  self.assertEqual(len(calls),1)

 def test_detail_recognition_does_not_depend_on_health_panel(self):
  for w,h in [(960,540),(1280,720),(1920,1080),(1920,864)]:
   for y in (.52,.60,.68):
    f=screen(w,h);f[round(h*y):round(h*y)+20,round(w*.74):round(w*.74)+40]=255
    self.assertIsNotNone(d.detail_home_position(f))
    self.assertIsNotNone(d.detail_select_position(f))

 def test_heart_layout_preserves_independent_controls(self):
  for w,h in [(732,412),(1280,720),(1920,1080)]:
   f=screen(w,h,missing='HANGER');g=d._glyph(d.HEART,h);x,y=round(w*.38),round(h*.87)
   f[y:y+g.shape[0],x:x+g.shape[1]]=g
   self.assertEqual(state_finder.get_in_game_state(f),'brawler_detail')
   self.assertIsNotNone(d.detail_select_position(f))
   for missing in ['HOME','PROFILE','CHAT','SELECT']:
    bad=screen(w,h,missing=missing)
    bad[round(h*.70):round(h*.84),round(w*.19):round(w*.29)]=(10,120,240)
    bad[y:y+g.shape[0],x:x+g.shape[1]]=g
    self.assertIsNone(d.detail_select_position(bad))
