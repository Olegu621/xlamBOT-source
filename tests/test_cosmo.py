import ast
import json
import math
import random
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import utils
import trophy_reader
from brawler_catalog import BUILT_IN_BRAWLERS, with_built_in_brawlers
from built_in_playstyles import BUILT_IN_PLAYSTYLES
from combat_behavior import CombatBehavior
from super_policy import choose

ROOT = Path(__file__).resolve().parents[1]


class CosmoTests(unittest.TestCase):
    def test_old_installation_gets_catalogue_without_disk_or_queue_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'brawlers_info.json'
            original = b'{"shelly":{"attack_range":490}}'
            path.write_bytes(original)
            with patch.object(utils, 'brawlers_info_file_path', path):
                self.assertIn('cosmo', utils.get_brawler_list())
                self.assertIn('cosmo', trophy_reader._known_brawler_names())
                self.assertEqual(utils.load_brawlers_info()['cosmo']['actual_name'], 'Cosmo')
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_saved_overrides_and_other_brawlers_are_not_replaced(self):
        saved = {'cosmo': {'safe_range': 400}, 'shelly': {'attack_range': 490}}
        merged = with_built_in_brawlers(saved)
        self.assertEqual(merged['cosmo']['safe_range'], 400)
        self.assertEqual(merged['cosmo']['super_range'], 597)
        self.assertEqual(merged['shelly'], saved['shelly'])
        merged['cosmo']['safe_range'] = 0
        self.assertEqual(saved['cosmo']['safe_range'], 400)
        self.assertEqual(BUILT_IN_BRAWLERS['cosmo']['safe_range'], 460.8)

    def test_readable_catalogue_matches_signed_defaults(self):
        table = json.loads((ROOT/'cfg/brawlers_info.json').read_text('utf8'))
        self.assertEqual(table['cosmo'], BUILT_IN_BRAWLERS['cosmo'])

    def test_gadget_requires_an_enemy_in_gadget_range_not_just_attack_range(self):
        import test_runtime_consistency as runtime
        info = utils.load_brawlers_info()['cosmo']
        for distance, visible, expected in ((460, True, True), (490, True, False), (300, False, False)):
            bot = SimpleNamespace(work_mode=4, current_brawler='cosmo', brawlers_info={'cosmo':info},
                context={'player_data':[0,0,0,0], 'enemy_data':[[distance,0,distance,0]], 'walls':[]},
                get_entity_pos=lambda b:(b[0],b[1]), get_distance=math.dist,
                is_enemy_hittable=lambda *a:visible, behavior_report={},
                window_controller=SimpleNamespace(scale_factor=1,click=Mock()),
                ability_buttons=SimpleNamespace(consume=Mock(return_value=(800,600))))
            self.assertEqual(runtime.Play.use_ability(bot,'gadget'),expected)
            self.assertEqual(bot.window_controller.click.call_count,int(expected))
            if not expected:bot.ability_buttons.consume.assert_not_called()

    def test_card_ocr_recognizes_name_and_zero_confusion(self):
        known = utils.load_brawlers_info()
        for text in ('COSMO', 'COSM0', 'Cosmo'):
            self.assertEqual(trophy_reader._match_brawler_name(text.upper(), known), 'cosmo')
        self.assertIsNone(trophy_reader._match_brawler_name('ZZZZZZZZZZZZ', known))

    def test_autopick_adopts_actual_cosmo_not_previous_queue_identity(self):
        from stage_manager import StageManager
        queue = [{'brawler': 'shelly', 'trophies': 900, 'wins': 0}]
        manager = StageManager.__new__(StageManager)
        manager.Lobby_automation = SimpleNamespace(last_picked={'brawler': 'cosmo', 'trophies': 12})
        manager.brawlers_pick_data = queue
        manager.brawler_sort_mode = lambda: 'lowest_to_highest'
        manager.Trophy_observer = Mock()
        manager._adopt_picked_brawler('shelly', 3)
        self.assertEqual(manager._confirmed_brawler, 'cosmo')
        self.assertEqual(queue[0]['brawler'], 'cosmo')
        self.assertEqual(queue[0]['trophies'], 12)
        self.assertEqual(queue[1]['trophies'], 900)
        self.assertTrue(manager._last_switch['confirmed'])

    def test_search_requires_cosmo_card_and_confirmed_detail(self):
        from lobby_automation import LobbyAutomation
        window = Mock()
        window.screenshot.side_effect = ['lobby', 'brawler_selection', 'brawler_selection', 'brawler_selection', 'lobby']
        bot = SimpleNamespace(window_controller=window, _frame_state=lambda f: f,
            _should_interrupt=lambda *a: False, _sleep_interruptible=lambda *a: False,
            _confirm_brawler_selection=Mock(return_value=True), _last_picked=None)
        reader = SimpleNamespace(read_card=lambda *a, **k: {'brawler': 'cosmo', 'trophies': 12})
        with patch.dict('sys.modules', {'trophy_reader': reader}):
            self.assertEqual(LobbyAutomation.select_brawler(bot, 'Cosmo', lambda: 'lobby'), 'success')
        window.type_text.assert_called_once_with('Cosmo')
        bot._confirm_brawler_selection.assert_called_once()
        self.assertEqual(bot._last_picked['brawler'], 'cosmo')
        window.screenshot.side_effect = ['lobby', 'brawler_selection', 'brawler_selection']
        window.click.reset_mock()
        reader.read_card = lambda *a, **k: {'brawler': 'colt'}
        with patch.dict('sys.modules', {'trophy_reader': reader}):
            self.assertEqual(LobbyAutomation.select_brawler(bot, 'cosmo', lambda: 'lobby'), 'failed')
        self.assertEqual(window.click.call_count, 1)

    def test_orbit_distance_floor_in_balanced_and_pressure_modes(self):
        for level in (3, 5):
            plan = CombatBehavior().plan(level, (0, 0), [[290,-10,310,10]], [], 576, 460.8,
                                        64, 100, 0, brawler='cosmo')
            self.assertLess(plan['movement'][0], 0)
            self.assertTrue(plan['report']['fire_allowed'])
            self.assertGreaterEqual(plan['report']['preferred_distance'], 460)

    def test_magnet_cannot_be_used_through_wall_or_outside_own_range(self):
        info = utils.load_brawlers_info()['cosmo']
        for distance, visible, expected in ((590, True, True), (610, True, False), (300, False, False)):
            enemy = [[distance-10,-10,distance+10,10]]
            self.assertEqual(choose('cosmo', info, 4, (0,0), enemy,576,597,lambda b: visible), expected)

    def strategy(self, distance, gas=None):
        attacked = Mock()
        info = utils.load_brawlers_info()['cosmo']
        context = dict(brawler='cosmo', current_brawler='cosmo', brawlers_info={'cosmo': info},
            persistent_data={}, must_brawler_hold_attack=lambda *a: False,
            get_brawler_range=lambda b: (460.8,576,597), get_entity_pos=lambda b: (0,0),
            player_data=[-10,-10,10,10], walls=[], JOYSTICK_RADIUS=100,
            is_path_blocked=lambda *a: False, get_random_movement=lambda: (0,-100),
            is_there_poison_gas=lambda *a: gas or dict(up=0,down=0,left=0,right=0),
            is_there_enemy=lambda e: bool(e), enemy_data=[[distance-10,-10,distance+10,10]],
            teammate_data=[], find_closest_enemy=lambda *a: ((distance,0),distance),
            find_closest_teammate=lambda *a: (None,None), is_enemy_hittable=lambda *a: True,
            is_super_ready=False, is_gadget_ready=False, is_hypercharge_ready=False,
            attack=attacked, use_super=Mock(), use_gadget=Mock(), use_hypercharge=Mock(),
            seconds_to_hold_attack_after_reaching_max=0, TILE_SIZE=64)
        _, code = utils.load_playstyle_script('aggressive.xlambot')
        movement, state = utils.interpret_playstyle_code(compile(code,'<cosmo-test>','exec'), context)
        return movement, state, attacked

    def test_classic_aggression_kites_close_strafes_far_and_approaches_outside_range(self):
        close, state, attacked = self.strategy(300)
        self.assertEqual(state['archetype'], 'ORBIT_CONTROLLER')
        self.assertLess(close[0], 0)
        attacked.assert_called_once()
        middle, _, _ = self.strategy(490)
        self.assertEqual(middle[0], 0)
        far, _, attacked = self.strategy(620)
        self.assertGreater(far[0], 0)
        attacked.assert_not_called()

    def test_gas_escape_still_overrides_cosmo_spacing(self):
        movement, _, _ = self.strategy(300, dict(up=0,down=0,left=1,right=0))
        self.assertGreater(movement[0], 0)

    def test_embedded_aggression_matches_shipped_readable_strategy(self):
        self.assertEqual(BUILT_IN_PLAYSTYLES['aggressive.xlambot'],
                         (ROOT/'playstyles/aggressive.xlambot').read_text('utf8'))


if __name__ == '__main__':
    unittest.main()
