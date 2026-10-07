import unittest,math,time
from types import SimpleNamespace
import numpy as np
from gas_guard import corridor_peak
from play import Play

class GasGuardTests(unittest.TestCase):
    def test_thin_cloud_is_not_averaged_into_clean_ground(self):
        mask=np.zeros((240,400),np.uint8);mask[:,145:151]=255
        self.assertGreaterEqual(corridor_peak(mask,[100,100,120,120],(100,0)),.2)
        self.assertEqual(corridor_peak(mask,[100,100,120,120],(-100,0)),0.)
    def test_unseen_ground_is_not_clean(self):
        self.assertEqual(corridor_peak(np.zeros((200,200),np.uint8),[160,80,180,100],(100,0)),1.)
    def test_final_movement_guard_blocks_thin_cloud(self):
        p=Play.__new__(Play);p.gas_mask=np.zeros((240,400),np.uint8);p.gas_mask[:,145:151]=255
        p.gas_reach=3;p.gas_sensitivity=.05;p.is_path_blocked=lambda *a:False
        p.get_actual_player_box=lambda b:b;p.gas_direction_share=lambda *a:0.01
        self.assertFalse(p.safe_memory_step((100,0),[100,100,120,120],[]))
        self.assertEqual(p.prevented_gas_entries,1)
        self.assertTrue(p.safe_memory_step((-100,0),[100,100,120,120],[]))
    def test_escape_cooldown_cannot_keep_a_newly_blocked_direction(self):
        p=Play.__new__(Play);p.frame=np.zeros((240,400,3),np.uint8);p.gas_mask=np.zeros((240,400),np.uint8)
        p.gas_mask[:,125:]=255;p.gas_player_box=[100,100,120,120]
        p.refresh_gas=lambda *a:None;p.gas_in_danger=True;p.gas_escape_direction=(1.,0.)
        p.gas_escape_index=0;p.gas_escape_time=1.;p.gas_escape_cooldown=.35;p.gas_lookahead=4
        p.gas_escapes=0;p.gas_danger_escapes=0;p.get_actual_player_box=lambda b:b
        p._clearest_escape=lambda *a:(-1.,0.);p.is_path_blocked=lambda b,v,w:v[0]>0
        self.assertEqual(p.avoid_gas(current_time=1.1),(-1.,0.))
    def test_visible_clouds_refresh_before_a_second_camera_decision(self):
        p=Play.__new__(Play);p.Detect_gas=object();p.gas_boxes=[[100,100,160,180]]
        p.gas_mask=np.zeros((240,400),np.uint8);p.gas_mask_time=10.;p.gas_detect_interval=.8
        p.gas_player_box=None;p.gas_coverage=0;p.verbose_debug=False;p.update_gas_danger=lambda n:None
        calls=[];p.detect_gas=lambda frame:calls.append(frame)
        from unittest.mock import patch
        with patch('play.time.time',return_value=10.11):p.refresh_gas(np.zeros((240,400,3),np.uint8))
        self.assertEqual(len(calls),1)
