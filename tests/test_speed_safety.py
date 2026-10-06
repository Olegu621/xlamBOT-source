import importlib.util
import ast
import math
import random
import time
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));os.chdir(ROOT)
import navigation_safety as nav

# These control methods need no ADB connection. Load their actual source bodies
# without importing the transport's optional scrcpy distribution dependency.
def method(filename, class_name, name):
    tree=ast.parse((ROOT/filename).read_text(encoding='utf-8'))
    cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name==class_name)
    function=next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name==name)
    namespace={'time':time,'math':math,'random':random}
    exec(compile(ast.Module(body=[function],type_ignores=[]),filename,'exec'),namespace)
    return namespace[name]

WindowController=type('WindowController',(),{'move':method('window_controller.py','WindowController','move')})
BotInstance=type('BotInstance',(),{'manage_time_tasks':method('bot_instance.py','BotInstance','manage_time_tasks')})

spec=importlib.util.spec_from_file_location('speed_reference',ROOT/'tests/fixtures/navigation_before_levels.py')
reference=importlib.util.module_from_spec(spec);sys.modules[spec.name]=reference;spec.loader.exec_module(reference)

class SpeedSafetyTests(unittest.TestCase):
    def test_integral_coverage_preserves_boundary_and_fractional_results(self):
        rng=np.random.default_rng(32)
        for shape in [(21,37),(720,1280)]:
            mask=rng.integers(0,256,shape,dtype=np.uint8)
            fast=nav._GasIntegral(mask)
            for _ in range(100):
                x,y=rng.uniform(-50,shape[1]+50),rng.uniform(-50,shape[0]+50)
                radius=float(rng.uniform(.1,60))
                self.assertEqual(nav.patch_share(fast,x,y,radius),reference.patch_share(mask,x,y,radius))

    def test_memory_decay_remains_identical_with_expiry_and_resize(self):
        new=nav.GasMemory(.6);old=reference.GasMemory(.6)
        for stamp,shape,boxes in [(1.,(720,1280),[[10,200,150,350]]),(1.,(720,1280),[[300,200,400,300]]),(1.07,(720,1280),[[80,180,170,400]]),
                                  (1.28,(720,1280),[]),(1.7,(720,1280),[]),(1.8,(360,640),[[30,130,150,200]])]:
            frame=np.zeros((*shape,3),np.uint8)
            expected=old.update(frame,boxes,stamp,.21,1.)
            actual=new.update(frame,boxes,stamp,.21,1.)
            self.assertEqual(actual[0],expected[0]);np.testing.assert_array_equal(actual[1],expected[1])

    def test_movement_start_preserves_touch_order_without_wait(self):
        controller=WindowController.__new__(WindowController)
        controller.are_we_moving=False;controller.original_movement_joystick=(120,600)
        controller.width_ratio=controller.height_ratio=1.;controller.PID_JOYSTICK=7
        controller.re_apply_movement=False
        inputs=[]
        controller.touch_down=lambda *a,**kw:inputs.append(('down',a,kw))
        controller.touch_move=lambda *a,**kw:inputs.append(('move',a,kw))
        with patch.object(random,'randint',return_value=0),patch.object(time,'sleep') as sleep:
            controller.move(80,0)
            controller.move(80,0)
        sleep.assert_not_called()
        self.assertEqual([r[0] for r in inputs],['down','move'])
        self.assertEqual(inputs[1][1],(200,600));self.assertTrue(controller.are_we_moving)

    def test_new_screen_is_handled_before_periodic_timer(self):
        bot=BotInstance.__new__(BotInstance)
        bot.Time_management=SimpleNamespace(state_check=lambda:False,no_detections_check=lambda:False,idle_check=lambda:False)
        bot.webhook_ping_every_minutes=0
        bot.get_latest_state=Mock(return_value='team_panel');bot.handle_detected_state=Mock()
        bot.manage_time_tasks(None);bot.manage_time_tasks(None)
        bot.handle_detected_state.assert_called_once_with('team_panel')
        bot.get_latest_state.return_value='lobby'
        bot.manage_time_tasks(None)
        self.assertEqual(bot.handle_detected_state.call_count,2)

if __name__=='__main__':unittest.main()
