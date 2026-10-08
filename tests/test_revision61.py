import unittest,math
from unittest.mock import patch
import numpy as np
import cv2
import state_finder
from menu_controls import _arrow,back_arrow_position
from gas_guard import coverage_integral,corridor_peak
from play import Play

class Revision61Tests(unittest.TestCase):
 def test_fps_overlay_cannot_hide_lower_back_arrow(self):
  for w,h in [(960,540),(1280,720),(1920,1080),(1920,864)]:
   f=np.full((h,w,3),30,np.uint8);glyph=_arrow(h);x,y=round(h*38/720),round(h*34/720)
   f[y:y+glyph.shape[0],x:x+glyph.shape[1]]=glyph[:,:,None]
   cv2.putText(f,'FPS:53',(round(h*.03),round(h*.03)),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)
   self.assertIsNotNone(back_arrow_position(f))
   with patch.object(state_finder,'is_in_lobby',return_value=False),patch.object(state_finder,'team_panel_close_position',return_value=None),patch.object(state_finder,'is_in_brawler_selection',return_value=True):
    self.assertIsNotNone(state_finder.menu_back_position(f))
   with patch.object(state_finder,'is_in_brawler_selection',return_value=False),patch.object(state_finder,'is_in_shop',return_value=False),patch.object(state_finder,'is_in_brawl_pass',return_value=False):
    self.assertIsNone(state_finder.menu_back_position(f))
  self.assertIsNone(back_arrow_position(np.full((720,1280,3),255,np.uint8)))
 def test_integral_matches_original_peak_for_clouds_borders_and_fractional_boxes(self):
  rng=np.random.default_rng(42)
  for shape in [(40,60),(240,400)]:
   mask=(rng.random(shape)<.27).astype(np.uint8)*255;table=coverage_integral(mask)
   for i in range(150):
    x,y=rng.uniform(-2,shape[1]+2),rng.uniform(-2,shape[0]+2);r=rng.uniform(1,20);box=[x-r,y-r,x+r,y+r];v=rng.normal(size=2);reach=rng.uniform(.1,4)
    self.assertEqual(corridor_peak(mask,box,v,reach),corridor_peak(mask,box,v,reach,integral=table))
 def test_integral_does_not_survive_failed_decision_or_changed_mask(self):
  p=Play.__new__(Play);p.gas_mask=np.zeros((20,20),np.uint8)
  p._loop_decision=lambda *a:(_ for _ in ()).throw(RuntimeError('decision failed'))
  with self.assertRaises(RuntimeError):p.loop('bo',{},0)
  self.assertIsNone(p._decision_gas_integral)
  p.gas_mask[:]=255
  p._loop_decision=lambda *a:int(p._decision_gas_integral[1][-1,-1])
  self.assertEqual(p.loop('bo',{},1),400)
  self.assertIsNone(p._decision_gas_integral)
