"""Regression checks for the revision-34 TrioSafety rollback."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ClassicGameplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "play.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_triosafety_arbiter_and_motion_tracking_are_absent(self):
        for name in ("navigation_safety", "MovementArbiter", "arbitrate_movement",
                     "ability_movement_is_uncertain", "phaseCorrelate", "update_motion"):
            self.assertNotIn(name, self.source)

    def test_no_blind_proceed_click_when_player_detection_is_missing(self):
        function = next(node for node in ast.walk(self.tree)
                        if isinstance(node, ast.FunctionDef) and node.name == "main")
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
        self.assertFalse(any(isinstance(call.func, ast.Attribute)
                             and call.func.attr == "press" and call.args
                             and isinstance(call.args[0], ast.Constant)
                             and call.args[0].value == "proceed" for call in calls))

    def test_only_confirmed_match_frames_reach_detectors(self):
        play_class = next(node for node in self.tree.body
                          if isinstance(node, ast.ClassDef) and node.name == "Play")
        function = next(node for node in play_class.body
                        if isinstance(node, ast.FunctionDef) and node.name == "main")
        text = ast.unparse(function)
        self.assertIn("if state != 'match'", text)
        self.assertIn("release_all_inputs", text)


if __name__ == "__main__":
    unittest.main()
