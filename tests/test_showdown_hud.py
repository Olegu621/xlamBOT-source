import unittest
import cv2
import numpy as np
from showdown_hud import visible_showdown_caption, _caption
import state_finder

class HudTests(unittest.TestCase):
 def test_map_changes_and_team_count_do_not_invalidate_caption(self):
  rng=np.random.default_rng(76)
  for w,h in [(960,540),(1280,720),(1920,1080),(1920,864)]:
   for count in (1,2,3,4):
    frame=rng.integers(0,200,(h,w,3),dtype=np.uint8)
    text=_caption(h);x,y=round(w*.06),round(h*.04)
    patch=frame[y:y+text.shape[0],x:x+text.shape[1]];patch[text>0]=245
    cv2.putText(frame,str(count),(x+text.shape[1],y+text.shape[0]),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2)
    self.assertTrue(visible_showdown_caption(frame))
    self.assertTrue(state_finder.is_in_showdown_match(frame))
    frame=(frame.astype(np.float32)*.7).astype(np.uint8)
    self.assertFalse(visible_showdown_caption(frame))
 def test_menus_noise_and_partial_label_do_not_authorize_battle(self):
  rng=np.random.default_rng(76)
  for color in [0,70,150,255]:
   self.assertFalse(visible_showdown_caption(np.full((720,1280,3),color,np.uint8)))
  for i in range(12):self.assertFalse(visible_showdown_caption(rng.integers(0,256,(720,1280,3),dtype=np.uint8)))
  f=np.zeros((720,1280,3),np.uint8);t=_caption(720);f[29:29+t.shape[0],80:80+t.shape[1]//2]=t[:,:t.shape[1]//2,None]
  self.assertFalse(visible_showdown_caption(f))
  self.assertFalse(visible_showdown_caption(None))

 def test_current_caption_low_resolution_and_dim_modal(self):
  from showdown_hud import CAPTION_CURRENT
  for w,h in [(376,212),(1280,720),(1920,1080)]:
   f=np.full((h,w,3),40,np.uint8);g=_caption(h,encoded=CAPTION_CURRENT,reference_height=212)
   x,y=round(w*.02),round(h*.04)
   f[y:y+g.shape[0],x:x+g.shape[1]][g>0]=245
   self.assertTrue(visible_showdown_caption(f))
   self.assertTrue(state_finder.is_in_showdown_match(f))
   self.assertFalse(visible_showdown_caption((f*.7).astype(np.uint8)))
   f[:]=40;f[y:y+g.shape[0],x:x+g.shape[1]//2][g[:,:g.shape[1]//2]>0]=245
   self.assertFalse(visible_showdown_caption(f))
