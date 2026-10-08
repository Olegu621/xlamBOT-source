import unittest
import ast,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from combat_behavior import CombatBehavior,unique

def box(x,y=0):return [x-10,y-10,x+10,y+10]

class CombatBehaviorTests(unittest.TestCase):
    def test_blocked_close_enemy_cannot_silence_visible_enemy_in_range(self):
        policy = CombatBehavior()
        blocked, visible = box(10), box(260)
        policy.target = (10, 0)
        policy.seen = 0
        plan = self.choose(2, [blocked, visible], now=.1, policy=policy,
                           visible=lambda b: b == visible)
        self.assertEqual(plan['target'], visible)
        self.assertTrue(plan['report']['fire_allowed'])

    def choose(self,mode,enemies,allies=(),attack=300,now=0,policy=None,visible=None):
        return (policy or CombatBehavior()).plan(mode,(0,0),enemies,allies,attack,150,40,100,now,visible)
    def test_modes_use_different_distances_without_ranged_point_blank_rush(self):
        distances=[self.choose(m,[box(250)])['report']['preferred_distance'] for m in range(1,6)]
        self.assertEqual(distances,sorted(distances,reverse=True))
        self.assertGreater(distances[-1],40)
        self.assertLess(self.choose(5,[box(60)])['movement'][0],0)
        self.assertGreater(self.choose(5,[box(60)],attack=90)['movement'][0],0)
    def test_numerical_disadvantage_is_tolerated_only_at_higher_aggression(self):
        opponents=[box(100,-25),box(100,25)]
        self.assertEqual(self.choose(2,opponents)['report']['intent'],'retreat')
        self.assertEqual(self.choose(3,opponents)['report']['intent'],'retreat')
        self.assertNotEqual(self.choose(4,opponents)['report']['reason'],'outnumbered')
        self.assertNotEqual(self.choose(3,opponents,[box(-50)])['report']['reason'],'outnumbered')
        crowd=[box(100,y) for y in [-60,-20,20,60]]
        self.assertEqual(self.choose(5,crowd)['report']['reason'],'outnumbered')
    def test_target_stays_stable_during_minor_distance_jitter(self):
        p=CombatBehavior()
        first=self.choose(4,[box(200,-30),box(220,30)],policy=p)
        second=self.choose(4,[box(215,-30),box(210,30)],now=.05,policy=p)
        self.assertLess(first['report']['target'][1],0)
        self.assertLess(second['report']['target'][1],0)
    def test_accessible_target_beats_a_slightly_closer_blocked_target(self):
        plan=self.choose(4,[box(150),box(180,40)],visible=lambda b:b[1]>0)
        self.assertGreater(plan['report']['target'][1],0)
        self.assertTrue(plan['report']['fire_allowed'])
    def test_regroups_without_visible_enemies_and_resets_target(self):
        p=CombatBehavior();self.choose(4,[box(200)],policy=p)
        plan=self.choose(2,[],[box(-200)],now=.2,policy=p)
        self.assertIsNone(p.target)
        self.assertEqual(plan['report']['intent'],'regroup')
        self.assertLess(plan['movement'][0],0)
        self.assertFalse(plan['report']['fire_allowed'])
    def test_duplicate_detections_do_not_create_a_fictitious_group(self):
        plan=self.choose(3,[box(100),box(101)])
        self.assertEqual(plan['report']['near_enemies'],1)
        self.assertNotEqual(plan['report']['reason'],'outnumbered')
    def test_retreat_does_not_follow_an_ally_toward_the_enemy(self):
        plan=self.choose(1,[box(100)],[box(50)])
        self.assertLess(plan['movement'][0],0)
    def test_unknown_range_is_finite_and_mode_change_drops_stale_target(self):
        p=CombatBehavior();self.choose(5,[box(50,-30)],attack=0,policy=p)
        plan=self.choose(2,[box(100,30)],attack=0,policy=p)
        self.assertGreater(plan['report']['preferred_distance'],0)
        self.assertGreater(plan['report']['target'][1],0)
class CombatIntegrationTests(unittest.TestCase):
    def test_classic_modes_keep_original_targets_firing_and_movement(self):
        source=Path(__file__).resolve().parents[1]/'play.py'
        tree=ast.parse(source.read_text('utf-8'))
        function=next(f for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='Play' for f in c.body if isinstance(f,ast.FunctionDef) and f.name=='get_movement')
        for level in (2,4):
            fired=Mock();context={'enemy_data':[box(150),box(180,40)],'attack':fired}
            def strategy(code, received):
                self.assertIs(received,context)
                received['attack']()
                return (25,-80),{}
            ns={'interpret_playstyle_code':strategy}
            exec(compile(ast.Module(body=[function],type_ignores=[]),'play.py','exec'),ns)
            policy=Mock()
            fake=SimpleNamespace(work_mode=level,behavior=policy,behavior_report={'fire_allowed':False},playstyle_code=None,context=context,try_ready_super=Mock())
            self.assertEqual(ns['get_movement'](fake),(25,-80))
            fired.assert_called_once();policy.plan.assert_not_called()
            self.assertTrue(fake.behavior_report['fire_allowed'])

    def test_selected_target_is_used_for_attack_without_losing_threat_context(self):
        source=Path(__file__).resolve().parents[1]/'play.py'
        tree=ast.parse(source.read_text('utf-8'))
        function=next(f for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='Play' for f in c.body if isinstance(f,ast.FunctionDef) and f.name=='get_movement')
        received=[]
        ns={'time':time,'JOYSTICK_RADIUS':100,'interpret_playstyle_code':lambda code,context:(received.append(context) or (0,100),{})}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'play.py','exec'),ns)
        policy=CombatBehavior()
        enemies=[box(150),box(180,40)]
        fake=SimpleNamespace(context={'player_data':box(0),'enemy_data':enemies,'teammate_data':[],'walls':[]},behavior=policy,work_mode=5,current_brawler='brock',TILE_SIZE=40,window_controller=SimpleNamespace(scale_factor=1),get_entity_pos=lambda b:((b[0]+b[2])/2,(b[1]+b[3])/2),get_brawler_range=lambda b:(150,300,400),is_enemy_hittable=lambda p,e,w,s:e[1]>0,persistent_data={'time_since_holding_attack':None},playstyle_code=None,attack=Mock(),try_ready_super=Mock(return_value=False))
        ns['get_movement'](fake)
        self.assertEqual(received[0]['enemy_data'],[enemies[1]])
        self.assertEqual(fake.context['enemy_data'],enemies)
        fake.context['enemy_data']=[];fake.persistent_data['time_since_holding_attack']=0
        ns['get_movement'](fake)
        fake.attack.assert_called_once_with(touch_up=True,touch_down=False)
        self.assertIsNone(fake.persistent_data['time_since_holding_attack'])

if __name__=='__main__':unittest.main()
