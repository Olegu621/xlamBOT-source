import unittest
import math
import numpy as np
import cv2
from battle_memory import BattleMemory, Steering
from ability_buttons import AbilityButtons, ready_button


def box(x,y):
    return [x-10,y-10,x+10,y+10]


def scene(camera=0, ally=200, enemies=(), player=100):
    return {'player':[box(player-camera,100)], 'teammate':[box(ally-camera,100)],
            'enemy':[box(x-camera,100) for x in enemies],
            'wall':[[x-camera,y,x+20-camera,y+25] for x,y in
                    [(40,30),(130,60),(240,20),(350,80),(480,30)]]}


class MemoryTests(unittest.TestCase):
    def test_stationary_ally_is_ignored_despite_camera_motion_and_recovers(self):
        m=BattleMemory()
        for i in range(25):
            m.update(scene(camera=i*2,player=100+i*2),i*.5,50)
        self.assertTrue(m.camera_valid)
        self.assertEqual(m.idle_count,1)
        self.assertEqual(m.active_allies(scene(48)['teammate'],12,50),[])
        m.update(scene(50,ally=245),12.5,50)
        self.assertEqual(m.idle_count,0)
        self.assertGreater(len(m.paths),0)

    def test_stationary_defender_is_not_ignored_during_a_fight(self):
        m=BattleMemory()
        for i in range(25):
            m.update(scene(enemies=[270]),i*.5,50)
        self.assertEqual(m.idle_count,0)

    def test_danger_is_remembered_then_expires_and_allies_reduce_penalty(self):
        m=BattleMemory();m.update(scene(),0,50)
        m.update(scene(enemies=[300,340]),.5,50)
        for now in [1,2,3,4]:m.update(scene(),now,50)
        alone=m.score((100,100),(1,0),[],4,50)
        together=m.score((100,100),(1,0),[box(150,100),box(180,100)],4,50)
        self.assertGreater(alone,together)
        for now in range(5,15):m.update(scene(),now,50)
        self.assertEqual(m.score((100,100),(1,0),[],14,50),0)

    def test_camera_uncertainty_cannot_label_an_ally_as_idle(self):
        m=BattleMemory()
        for i in range(25):
            data=scene();data['wall']=[];m.update(data,i*.5,50)
        self.assertEqual(m.idle_count,0)
        self.assertFalse(m.stalled(12,3))

    def test_unstuck_requires_actual_lack_of_progress(self):
        m=BattleMemory()
        for i in range(12):m.update(scene(player=100+i*10),i*.5,50)
        self.assertFalse(m.stalled(5.5,3))
        for i in range(12,24):m.update(scene(player=210),i*.5,50)
        self.assertTrue(m.stalled(11.5,3))

    def test_reversal_debounce_never_holds_an_unsafe_direction(self):
        s=Steering();self.assertEqual(s.choose((1,0),0,lambda _:True),(1,0))
        self.assertEqual(s.choose((-1,0),.1,lambda _:True),(1,0))
        self.assertEqual(s.choose((-1,0),.11,lambda _:False),(-1,0))
        self.assertEqual(s.choose((0,0),.2,lambda _:True),(0,0))


class AbilityTests(unittest.TestCase):
    POINTS={'super':[1512,881],'gadget':[1645,989],'hypercharge':[1400,990]}

    def button(self,ability):
        frame=np.full((720,1280,3),25,np.uint8)
        center=tuple(int(v*2/3) for v in self.POINTS[ability])
        color={'super':(255,220,0),'gadget':(0,255,0),'hypercharge':(210,0,255)}[ability]
        cv2.circle(frame,center,42,(0,0,0),-1)
        cv2.circle(frame,center,36,color,-1)
        cv2.circle(frame,center,8,(255,255,255),-1)
        return frame

    def test_each_charged_button_requires_two_frames_and_has_cooldown(self):
        for ability in self.POINTS:
            with self.subTest(ability=ability):
                frame=self.button(ability);a=AbilityButtons()
                self.assertIsNotNone(ready_button(frame,ability,self.POINTS[ability]))
                a.observe(frame,self.POINTS,0);self.assertIsNone(a.consume(ability,0))
                a.observe(frame,self.POINTS,.15);self.assertIsNotNone(a.consume(ability,.15))
                a.observe(frame,self.POINTS,.3);self.assertIsNone(a.consume(ability,.3))
                a.observe(frame,self.POINTS,1.5);self.assertIsNotNone(a.consume(ability,1.5))

    def test_colored_terrain_and_stale_readiness_cannot_press(self):
        frame=np.full((720,1280,3),(210,0,255),np.uint8)
        self.assertIsNone(ready_button(frame,'hypercharge',self.POINTS['hypercharge']))
        a=AbilityButtons();frame=self.button('super');a.observe(frame,self.POINTS,0)
        a.observe(frame,self.POINTS,.15);self.assertIsNone(a.consume('super',1.))


class PhoneHudTests(unittest.TestCase):
    def test_ultrawide_caption_uses_height_scale_and_requires_brightness(self):
        from state_finder import load_template, states_path, is_in_showdown_match
        template=load_template(states_path+'teams_remaining_en.png',1280,720)
        self.assertIsNotNone(template)
        for width in [1280,1600,1920]:
            frame=np.full((720,width,3),35,np.uint8)
            frame[15:15+template.shape[0],20:20+template.shape[1]]=template
            self.assertTrue(is_in_showdown_match(frame))
            self.assertFalse(is_in_showdown_match((frame*.5).astype(np.uint8)))


if __name__=='__main__':unittest.main()
