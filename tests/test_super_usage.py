import unittest,cv2,numpy as np,ast,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from ability_buttons import ready_button,AbilityButtons
from super_policy import choose
class SuperTests(unittest.TestCase):
    def test_offset_real_style_gold_button_without_dark_ring_at_three_sizes(self):
        for width,height in [(480,270),(1280,720),(1920,1080)]:
            scale=height/720;f=np.full((height,width,3),(100,70,120),np.uint8);center=(int(width*.743),int(height*.772));r=int(39*scale)
            cv2.circle(f,center,r+2,(240,190,60),-1);cv2.circle(f,center,r,(250,180,0),-1);cv2.circle(f,center,max(3,int(r*.3)),(255,255,255),-1)
            point=ready_button(f,'super',[1512,881]);self.assertIsNotNone(point,(width,height));self.assertLess(np.linalg.norm(np.array(point)-center),5)
            cv2.circle(f,center,r,(0,80,200),-1)
            self.assertIsNone(ready_button(f,'super',[1512,881]))
    def test_spent_button_requires_two_fresh_observations(self):
        f=np.full((720,1280,3),(100,70,120),np.uint8)
        center=(950,556);cv2.circle(f,center,40,(250,180,0),-1);cv2.circle(f,center,12,(255,255,255),-1)
        a=AbilityButtons();points={'super':[1512,881],'gadget':[1645,989],'hypercharge':[1400,990]}
        a.observe(f,points,0);a.observe(f,points,.15);self.assertIsNotNone(a.consume('super',.15))
        a.last_action={'ability':'super','at':.15,'point':list(center)}
        cv2.circle(f,center,40,(0,80,200),-1)
        a.observe(f,points,.3);self.assertFalse(a.last_action.get('button_changed',False))
        a.observe(f,points,.45);self.assertTrue(a.last_action['button_changed'])
    def test_spawnable_does_not_require_attack_line_of_sight(self):
        enemy=[[190,-10,210,10]]
        self.assertTrue(choose('penny',{'super_type':'spawnable'},2,(0,0),enemy,300,150,lambda b:False))
        self.assertFalse(choose('penny',{'super_type':'spawnable'},1,(0,0),enemy,300,150,lambda b:False))
        self.assertFalse(choose('penny',{'super_type':'spawnable'},2,(0,0),[],300,150,lambda b:True))
    def test_damage_super_uses_its_own_range_and_obstacles(self):
        enemy=[[390,-10,410,10]]
        self.assertTrue(choose('brock',{'super_type':'damage'},2,(0,0),enemy,200,500,lambda b:True))
        self.assertFalse(choose('brock',{'super_type':'damage'},2,(0,0),enemy,200,300,lambda b:True))
        self.assertFalse(choose('brock',{'super_type':'damage'},2,(0,0),enemy,200,500,lambda b:False))
    def test_detected_actual_coordinates_are_clicked_and_missing_readiness_cannot_tap(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'play.py').read_text('utf-8'))
        func=next(f for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='Play' for f in c.body if isinstance(f,ast.FunctionDef) and f.name=='use_ability')
        ns={'time':time};exec(compile(ast.Module(body=[func],type_ignores=[]),'play.py','exec'),ns)
        buttons=AbilityButtons();buttons.ready['super']=(950,556);buttons.last_observed=time.time()
        controller=SimpleNamespace(click=Mock());p=SimpleNamespace(work_mode=2,context={'player_data':[0,0,20,20],'enemy_data':[[50,0,70,20]],'walls':[]},current_brawler='penny',brawlers_info={'penny':{'super_type':'spawnable'}},get_entity_pos=lambda b:((b[0]+b[2])/2,(b[1]+b[3])/2),get_brawler_range=lambda b:(0,300,200),is_enemy_hittable=lambda *a:True,behavior_report={'target':[60,10],'target_distance':50},ability_buttons=buttons,window_controller=controller)
        self.assertTrue(ns['use_ability'](p,'super'));controller.click.assert_called_once_with(950,556,delay=.06,already_include_ratio=True)
        self.assertEqual(buttons.last_action['ability'],'super')
        self.assertFalse(ns['use_ability'](p,'super'));self.assertEqual(controller.click.call_count,1)
if __name__=='__main__':unittest.main()
