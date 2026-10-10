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

 def test_russian_live_caption_resolutions_and_modal_gate(self):
  from showdown_hud import CAPTION_RUSSIAN
  for w,h in [(388,219),(960,540),(1280,720),(1920,1080)]:
   frame=np.full((h,w,3),40,np.uint8)
   glyph=_caption(h,encoded=CAPTION_RUSSIAN,reference_height=219)
   x,y=round(w*.02),round(h*.04)
   frame[y:y+glyph.shape[0],x:x+glyph.shape[1]][glyph>0]=245
   self.assertTrue(visible_showdown_caption(frame))
   self.assertTrue(state_finder.is_in_showdown_match(frame))
   self.assertFalse(visible_showdown_caption((frame*.7).astype(np.uint8)))
   frame[:]=40
   frame[y:y+glyph.shape[0],x:x+glyph.shape[1]//2][glyph[:,:glyph.shape[1]//2]>0]=245
   self.assertFalse(visible_showdown_caption(frame))

 def test_recorded_russian_lettering_survives_resampling(self):
  import base64
  lettering=cv2.cvtColor(cv2.imdecode(np.frombuffer(base64.b64decode('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'),np.uint8),1),cv2.COLOR_BGR2RGB)
  frame=np.full((219,388,3),40,np.uint8)
  frame[8:20,7:100]=lettering
  for h in (219,720,1080):
   current=cv2.resize(frame,(round(388*h/219),h))
   self.assertTrue(visible_showdown_caption(current))
   self.assertFalse(visible_showdown_caption((current*.7).astype(np.uint8)))

 def test_english_solo_caption_rejects_dimmed_modal_and_partial_text(self):
  from showdown_hud import CAPTION_SOLO_ENGLISH
  for h in (540,720,1080):
   f=np.full((h,round(h*16/9),3),40,np.uint8)
   g=_caption(h,encoded=CAPTION_SOLO_ENGLISH)
   x,y=round(h*.04),round(h*.04)
   f[y:y+g.shape[0],x:x+g.shape[1]][g>0]=245
   self.assertTrue(visible_showdown_caption(f))
   self.assertFalse(visible_showdown_caption((f*.7).astype(np.uint8)))
   f[:]=40
   f[y:y+g.shape[0],x:x+g.shape[1]//2][g[:,:g.shape[1]//2]>0]=245
   self.assertFalse(visible_showdown_caption(f))
