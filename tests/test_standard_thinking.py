"""Standard must preserve the navigation budget from before thinking levels."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.chdir(ROOT)
from navigation_safety import MovementArbiter
from thinking_levels import ThinkingQuality
from play import Play
import settings_schema

spec=importlib.util.spec_from_file_location('navigation_before_levels',ROOT/'tests/fixtures/navigation_before_levels.py')
original=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=original
spec.loader.exec_module(original)

class StandardThinkingTests(unittest.TestCase):
    def test_preserves_configured_intervals_after_switching(self):
        p=Play.__new__(Play)
        p.walls_treshold=.43;p.gas_detect_interval=.17
        p.movement_arbiter=MovementArbiter()
        p.configure_thinking('maximum')
        p.configure_thinking('standard')
        self.assertEqual((p.walls_treshold,p.gas_detect_interval),(.43,.17))
        self.assertEqual((p.movement_arbiter.direction_count,p.movement_arbiter.planning_steps),(8,3))
        p.configure_thinking('high');p.configure_thinking('standard')
        self.assertEqual((p.walls_treshold,p.gas_detect_interval),(.43,.17))

    def test_navigation_matches_original_reference(self):
        p=Play.__new__(Play)
        p.walls_treshold=.2;p.gas_detect_interval=.2;p.movement_arbiter=MovementArbiter()
        p.configure_thinking('standard')
        rng=np.random.default_rng(29)
        for i in range(40):
            mask=(rng.random((96,96))<(i%5)*.035).astype(np.uint8)*255
            mask[35:45,30:70]=255 if i%2 else 0
            desired=(120. if i%3 else -120.,30. if i%4 else 0.)
            def walls(move,distance): return move[0]<-.5 and distance>=16
            params=dict(mask=mask,center=(48,48),radius=4,walls_block=walls,frame_size=(96,96),tile=8,
                        escape=bool(i%2),enemies=[(70,30)],teammates=[(40,40)],observed_y=(8,96))
            self.assertEqual(p.movement_arbiter.choose(desired,**params),original.MovementArbiter().choose(desired,**params))

    def test_standard_is_valid_and_invalid_types_raise_value_error(self):
        settings_schema.validate('thinking_mode','standard','medium')
        for value in ('auto',{},[],None,True):
            with self.assertRaises(ValueError): settings_schema.validate('thinking_mode',value,'medium')

    def test_recommendations_include_standard_without_switching(self):
        for selected,fps,cost,expected in (('low',45,.02,'standard'),('standard',10,.10,'low'),('medium',10,.10,'standard'),('high',45,.02,'maximum')):
            q=ThinkingQuality(selected)
            for i in range(fps*50):q.observe(cost,i/fps,60)
            self.assertEqual(q.recommended,expected)
            self.assertEqual(q.mode,selected)

if __name__=='__main__':unittest.main()
