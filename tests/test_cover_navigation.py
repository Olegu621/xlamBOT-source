import unittest, time, math
from bush_cover import BushCover
from local_navigation import blocked,detour
class CoverTests(unittest.TestCase):
    def call(self,p,now=0,enemies=(),bushes=None,safe=lambda *a:True,player=(0,0)):
        return p.plan(player,bushes if bushes is not None else [[-40,-40,40,40]],enemies,40,100,now,200,lambda b:True,safe)
    def test_holds_cover_and_short_pulse_every_three_seconds(self):
        p=BushCover()
        self.assertEqual(self.call(p)['movement'],(0,0))
        self.assertEqual(self.call(p,2.99)['movement'],(0,0))
        self.assertNotEqual(self.call(p,3)['movement'],(0,0))
        self.assertEqual(self.call(p,3.13)['movement'],(0,0))
        self.assertNotEqual(self.call(p,6)['movement'],(0,0))
    def test_flees_to_other_bush_and_attacks_close_enemy(self):
        r=self.call(BushCover(),enemies=[[50,-10,70,10]],bushes=[[-40,-40,40,40],[-240,-40,-160,40]])
        self.assertLess(r['movement'][0],0);self.assertTrue(r['report']['fire_allowed']);self.assertEqual(r['report']['intent'],'seek_cover')
    def test_own_sprite_occlusion_does_not_abandon_entered_bush(self):
        p=BushCover();safe=lambda *a:True
        first=p.plan((0,0),[[100,-40,180,40]],[],40,100,0,200,lambda b:True,safe)
        self.assertGreater(first['movement'][0],0)
        inside=p.plan((0,0),[],[],40,100,1,200,lambda b:True,safe,offset=(140,0))
        self.assertEqual(inside['report']['intent'],'hide');self.assertEqual(inside['movement'],(0,0))
        fleeing=p.plan((0,0),[[-240,-40,-160,40]],[],40,100,2,200,lambda b:True,safe,attacked=True,offset=(140,0))
        self.assertEqual(fleeing['report']['reason'],'under_attack');self.assertLess(fleeing['movement'][0],0)
    def test_cover_exclusion_tracks_camera_motion(self):
        p=BushCover();safe=lambda *a:True
        p.plan((0,0),[[-40,-40,40,40],[160,-40,240,40]],[],40,100,0,200,lambda b:True,safe,attacked=True)
        r=p.plan((-100,0),[[-140,-40,-60,40],[60,-40,140,40]],[],40,100,1,200,lambda b:True,safe,offset=(100,0))
        self.assertEqual(r['report']['intent'],'seek_cover');self.assertGreater(r['movement'][0],0)
    def test_gas_covered_bush_not_selected_and_exposed_one_excluded(self):
        p=BushCover();r=self.call(p,bushes=[[-40,-40,40,40],[160,-40,240,40]],safe=lambda point,margin:point[0]>100)
        self.assertGreater(r['movement'][0],0)
        self.assertEqual(self.call(p,1,bushes=[[-40,-40,40,40]])['report']['reason'],'no_safe_bush')
    def test_approaching_enemy_changes_cover_without_claiming_detection_of_vision(self):
        p=BushCover();self.call(p,enemies=[[210,-10,230,10]])
        r=self.call(p,.1,enemies=[[190,-10,210,10]],bushes=[[-40,-40,40,40],[-240,-40,-160,40]])
        self.assertEqual(r['report']['intent'],'seek_cover')
class NavigationTests(unittest.TestCase):
    def test_small_real_opening_is_passable_but_solid_wall_is_not(self):
        walls=[[-100,0,-3,100],[3,0,100,100]]
        self.assertFalse(blocked((0,-60),(0,150),25,walls))
        self.assertTrue(blocked((0,-60),(0,150),25,[[-100,0,100,100]]))
        self.assertTrue(blocked((15,-60),(15,150),25,walls))
    def test_bent_obstacle_returns_collision_free_detour(self):
        walls=[[30,-80,70,80],[70,40,150,80]]
        route=detour((0,0),(100,0),10,40,walls)
        self.assertIsNotNone(route)
        self.assertFalse(blocked((0,0),(route[0]*40,route[1]*40),10,walls))
        self.assertGreater(abs(route[1]),.1)
    def test_gap_alignment_and_bounded_cost(self):
        walls=[[-100,0,-3,100],[3,0,100,100]]
        route=detour((20,-60),(0,100),25,40,walls)
        self.assertIsNotNone(route)
        self.assertLess(route[0],0)
        self.assertFalse(blocked((20,-60),(20+route[0]*40,-60+route[1]*40),25,walls))
class DamageTests(unittest.TestCase):
    def frame(self,width):
        import numpy as np
        f=np.zeros((720,1280,3),np.uint8)
        f[210:216,605:605+width]=[80,230,70]
        return f
    def test_damage_requires_two_frames_and_missing_bar_is_unknown(self):
        from incoming_damage import IncomingDamage
        p=IncomingDamage();box=[590,190,690,330]
        self.assertFalse(p.observe(self.frame(70),box,0))
        self.assertFalse(p.observe(self.frame(40),box,.1))
        self.assertTrue(p.observe(self.frame(40),box,.2))
        self.assertTrue(p.observe(self.frame(40),box,1))
        self.assertFalse(p.observe(self.frame(40),box,4))
        p=IncomingDamage();p.observe(self.frame(70),box,0)
        self.assertFalse(p.observe(self.frame(0),box,.1))
        self.assertFalse(p.observe(self.frame(0),box,.2))
    def test_damage_without_visible_enemy_excludes_the_current_bush(self):
        p=BushCover()
        r=p.plan((0,0),[[-40,-40,40,40],[160,-40,240,40]],[],40,100,0,200,lambda b:True,lambda *a:True,attacked=True)
        self.assertEqual(r['report']['intent'],'seek_cover')
        self.assertEqual(r['report']['reason'],'under_attack')
        self.assertGreater(r['movement'][0],0)
    def test_wall_route_reaches_destination_without_corner_oscillation(self):
        walls=[[30,-80,70,80],[70,40,150,80]];p=(0,0);goal=(200,0)
        for _ in range(100):
            d=(goal[0]-p[0],goal[1]-p[1]);length=math.hypot(*d)
            if length<15:break
            v=detour(p,d,10,40,walls) or (d[0]/length,d[1]/length)
            q=(p[0]+v[0]*10,p[1]+v[1]*10)
            self.assertFalse(blocked(p,q,10,walls));p=q
        self.assertLess(math.dist(p,goal),15)
if __name__=='__main__':unittest.main()
