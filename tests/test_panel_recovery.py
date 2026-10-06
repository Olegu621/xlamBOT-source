import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
import team_panel
import disconnect_dialog
import built_in_playstyles
import state_finder
import settings_schema
import brawler_calibration
import device_profiles
import utils
from stage_manager import StageManager

def overlay(width=1280, height=720, heading=True, close=True):
    frame = np.full((height, width, 3), 30, np.uint8)
    for encoded, x, y, enabled in [(team_panel.HEADING, .555, .008, heading),
                                    (team_panel.CLOSE, .941, 0, close)]:
        if enabled:
            image = team_panel._template(encoded, width, height)
            left, top = int(width*x), int(height*y)
            frame[top:top+image.shape[0], left:left+image.shape[1]] = image
    return frame

def idle_overlay(width=680, height=380, title=True, reload=True):
    frame = np.full((height, width, 3), 55, np.uint8)
    for encoded, x, y, enabled in [(disconnect_dialog.TITLE, 182/680, 144/380, title),
                                    (disconnect_dialog.RELOAD, 177/680, 218/380, reload)]:
        if enabled:
            image = disconnect_dialog._template(encoded, width, height)
            left, top = round(width*x), round(height*y)
            frame[top:top+image.shape[0], left:left+image.shape[1]] = image
    return frame

class RecoveryTests(unittest.TestCase):
    def test_idle_disconnect_requires_title_and_reload_at_any_resolution(self):
        for width, height in [(680, 380), (1280, 720), (1920, 864), (1920, 1080)]:
            frame = idle_overlay(width, height)
            self.assertIsNotNone(disconnect_dialog.idle_disconnect_reload_position(frame))
            self.assertEqual(state_finder.get_in_game_state(frame), "idle_disconnect")
        self.assertIsNone(disconnect_dialog.idle_disconnect_reload_position(idle_overlay(title=False)))
        self.assertIsNone(disconnect_dialog.idle_disconnect_reload_position(idle_overlay(reload=False)))

    def test_overlay_requires_heading_and_close_button(self):
        for width,height in [(445,247),(960,540),(1280,720),(1920,1080)]:
            self.assertIsNotNone(team_panel.team_panel_close_position(overlay(width,height)))
        for heading,close in [(True,False),(False,True),(False,False)]:
            self.assertIsNone(team_panel.team_panel_close_position(overlay(heading=heading,close=close)))

    def test_overlay_wins_before_lobby(self):
        with patch.object(state_finder,'is_in_connection_lost',return_value=False), \
             patch('reward_choice.is_reward_choice',return_value=False), \
             patch.object(state_finder,'is_in_lobby',return_value=True):
            self.assertEqual(state_finder.get_in_game_state(overlay()),'team_panel')

    def test_cached_state_cannot_close_a_different_screen(self):
        manager=StageManager.__new__(StageManager)
        manager.runtime_control=None
        clicks=[]
        frame=overlay()
        manager.window_controller=SimpleNamespace(screenshot=lambda:frame,release_all_inputs=lambda:None,
                                                  click=lambda *a,**kw:clicks.append((a,kw)))
        with patch('stage_manager.time.monotonic',side_effect=[1.,1.2,2.]):
            manager.close_team_panel()
            manager.close_team_panel()
            frame=overlay(heading=False,close=True)
            manager.close_team_panel()
        self.assertEqual(len(clicks),1)
        self.assertTrue(clicks[0][1]['already_include_ratio'])
        manager.runtime_control=SimpleNamespace(should_stop=lambda:True,should_pause=lambda:False)
        manager.close_team_panel()
        self.assertEqual(len(clicks),1)

    def test_generic_menu_close_never_taps_team_panel(self):
        manager=StageManager.__new__(StageManager)
        clicks=[]
        manager.window_controller=SimpleNamespace(
            screenshot=lambda:overlay(), release_all_inputs=lambda:None,
            click=lambda *a,**kw:clicks.append((a,kw)))
        manager.close_known_menu()
        self.assertEqual(clicks, [])

    def test_brawler_selection_requires_two_independent_markers(self):
        with patch.object(state_finder, 'is_template_in_region', side_effect=[True, False]):
            self.assertFalse(state_finder.is_in_brawler_selection(np.zeros((720,1280,3),np.uint8)))


class PlaystyleTests(unittest.TestCase):
    def test_only_two_playstyles_are_exposed_and_legacy_names_migrate(self):
        self.assertEqual(set(built_in_playstyles.BUILT_IN_PLAYSTYLES),
                         {"aggressive.xlambot", "survivor.xlambot"})
        self.assertEqual({item["filename"] for item in utils.get_playstyles_list()},
                         {"aggressive.xlambot", "survivor.xlambot"})
        self.assertEqual(built_in_playstyles.canonical_playstyle("showdown_survivor.xlambot"),
                         "survivor.xlambot")
class CalibrationTests(unittest.TestCase):
    def test_variable_point_set_and_fixed_coordinates(self):
        for original,value in [([],['brawlers_menu']),(['brawlers_menu'],['brawlers_menu','brawlers_card_00']),
                               (['brawlers_card_00','brawlers_card_08'],['brawlers_card_00'])]:
            settings_schema.validate('point_keys',value,original,'brawler_calibration.point_keys')
        for bad in [['attack'],[1],['brawlers_menu','brawlers_menu'],[{}]]:
            with self.assertRaises(ValueError):
                settings_schema.validate('point_keys',bad,[],'brawler_calibration.point_keys')
        with self.assertRaises(ValueError):
            settings_schema.validate('brawlers_card_00',[1,2,3],[1,2])

    def test_repeated_save_migrates_legacy_keys_and_isolates_devices(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            shutil.copytree(ROOT/'cfg',root/'cfg')
            with patch.object(utils,'PROJECT_ROOT',root),patch.object(utils,'DATA_ROOT',root):
                a=brawler_calibration.read('test-A')
                b=brawler_calibration.read('test-B')
                brawler_calibration.save('test-A',{'brawlers_menu':[400,300]}, {}, [1600,900])
                with device_profiles.use_profile('test-A'):
                    cfg=utils.load_toml_as_dict('cfg/buttons_config.toml')
                    cfg['brawler_calibration']['point_keys'].append('brawlers_card_08')
                    utils.save_dict_as_toml(cfg,'cfg/buttons_config.toml')
                    utils.invalidate_toml_cache('cfg/buttons_config.toml')
                for _ in range(2):
                    saved=brawler_calibration.save('test-A',{'brawlers_card_00':[1113.6,303.6]}, {}, [1600,900])
                    self.assertTrue(saved['ok'])
                cfg=device_profiles.read_settings('test-A')['buttons_config']
                self.assertEqual(cfg['brawler_calibration']['point_keys'],['brawlers_card_00','brawlers_menu'])
                self.assertEqual(cfg['brawlers_first_card'],[1113.6,303.6])
                self.assertEqual(brawler_calibration.read('test-B'),b)

if __name__ == '__main__':
    unittest.main()
