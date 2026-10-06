"""Thinking levels keep classic navigation and only tune detector cadence."""
import os
import sys
import unittest
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.chdir(ROOT)
from thinking_levels import ThinkingQuality
import settings_schema


def load_configure_thinking():
    tree = ast.parse((ROOT / 'play.py').read_text(encoding='utf-8'))
    play = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Play')
    function = next(node for node in play.body if isinstance(node, ast.FunctionDef) and node.name == 'configure_thinking')
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'play.py', 'exec'), namespace)
    return namespace['configure_thinking']


class Play:
    configure_thinking = load_configure_thinking()

class StandardThinkingTests(unittest.TestCase):
    def test_preserves_configured_intervals_after_switching(self):
        p=Play.__new__(Play)
        p.walls_treshold=.43;p.gas_detect_interval=.17
        p.configure_thinking('maximum')
        p.configure_thinking('standard')
        self.assertEqual((p.walls_treshold,p.gas_detect_interval),(.43,.17))
        p.configure_thinking('high');p.configure_thinking('standard')
        self.assertEqual((p.walls_treshold,p.gas_detect_interval),(.43,.17))

    def test_levels_only_increase_detector_frequency(self):
        p=Play.__new__(Play)
        p.walls_treshold=.43;p.gas_detect_interval=.17
        values=[]
        for level in ('low','medium','high','maximum'):
            p.configure_thinking(level)
            values.append((p.walls_treshold,p.gas_detect_interval))
        self.assertEqual(values, sorted(values, reverse=True))

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
