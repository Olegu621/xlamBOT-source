"""Cancellation during preparation, queue ownership and honest match statistics."""
import importlib
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import test_runtime_consistency  # Installed capture transport boundary double.
import utils
from trophy_observer import TrophyObserver, ParsedGameResult, GameMode, MatchResult


class TrophyAccountingTests(unittest.TestCase):
    def result(self, baseline, outcome=MatchResult.DEFEAT):
        with tempfile.TemporaryDirectory() as folder, utils.config_scope(Path(folder)):
            observer = TrophyObserver()
        observer.current_trophies = baseline
        observer.win_streak = 0
        observer.current_wins = 0
        observer.trophy_samples = []
        observer.match_history = []
        observer.match_counter = 0
        observer.trophies_multiplier = 1
        observer.save_history = Mock()
        with patch('trophy_observer.load_toml_as_dict', return_value={'player_tag': ''}):
            observer.add_trophies(ParsedGameResult(GameMode.TRIO_SHOWDOWN, outcome, 3), 'shelly', {}, False)
        return observer

    def test_unknown_count_does_not_create_a_gain_or_rate_baseline(self):
        observer = self.result(None, MatchResult.VICTORY)
        self.assertIsNone(observer.current_trophies)
        self.assertIsNone(observer.match_history[0]['current_trophies'])
        self.assertIsNone(observer.match_history[0]['trophy_delta'])
        self.assertEqual(observer.match_history[0]['trophy_source'], 'unknown')
        self.assertEqual(observer.win_streak, 1)
        self.assertEqual(observer.trophy_samples, [])

    def test_floor_changes_match_saved_delta(self):
        for baseline, floor in [(1002, 1000), (2002, 2000), (100, 99)]:
            with self.subTest(baseline=baseline):
                observer = self.result(baseline)
                self.assertEqual(observer.current_trophies, floor)
                self.assertEqual(observer.match_history[0]['trophy_delta'], floor-baseline)
                self.assertEqual(observer.match_history[0]['trophy_source'], 'estimated')

    def test_unknown_queue_survives_disk_round_trip(self):
        with tempfile.TemporaryDirectory() as folder, utils.config_scope(Path(folder)):
            utils.save_brawler_data([{'brawler': 'bo', 'type': 'trophies', 'trophies': None,
                                     'push_until': 1000, 'wins': 0}])
            self.assertIsNone(utils.clean_queue(utils.load_brawler_data())[0]['trophies'])


class StartQueueTests(unittest.TestCase):
    def setUp(self):
        package = ModuleType('webui')
        package.__path__ = [str(Path('webui').resolve())]
        self.modules = patch.dict(sys.modules, {'webui': package, 'capture_transport':
            SimpleNamespace(ACTION_UP=1, ACTION_DOWN=0, ACTION_MOVE=2)})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        module = importlib.import_module('webui.device_manager')
        self.manager = module.DeviceRuntimeManager()
        self.manager.resolve_serial = lambda key, serial=None: 'emulator-5554'
        self.queue = [{'brawler': 'shelly', 'type': 'trophies', 'trophies': 100, 'push_until': 1000}]
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        for name, kwargs in [('ensure_profile', {}), ('config_root_for', {'return_value': Path(self.folder.name)})]:
            mock = patch('webui.device_manager.device_profiles.'+name, **kwargs)
            mock.start()
            self.addCleanup(mock.stop)

    def test_stop_and_stop_all_cancel_blocked_preparation(self):
        for stop_all in (False, True):
            with self.subTest(stop_all=stop_all):
                entered, release = threading.Event(), threading.Event()
                def provider(key):
                    entered.set()
                    self.assertTrue(release.wait(3))
                    return self.queue
                self.manager.configure_queue_provider(provider)
                result = {}
                with patch('webui.device_manager.run_bot_instance') as worker:
                    start = threading.Thread(target=lambda: result.update(self.manager.start('device')))
                    start.start()
                    try:
                        self.assertTrue(entered.wait(3))
                        self.manager.stop_all() if stop_all else self.manager.stop('device')
                    finally:
                        release.set()
                        start.join(3)
                    self.assertEqual(result['code'], 'START_CANCELLED')
                    worker.assert_not_called()
                    self.assertFalse(self.manager.get_status('device')['is_running'])

    def test_active_alias_queue_edit_is_rejected_and_idle_edit_works(self):
        entered, release = threading.Event(), threading.Event()
        def worker(*args, **kwargs):
            entered.set()
            release.wait(3)
            return {'ok': True}
        self.manager.configure_queue_provider(lambda key: self.queue)
        with patch('webui.device_manager.run_bot_instance', side_effect=worker):
            self.assertTrue(self.manager.start('device')['ok'])
            self.assertTrue(entered.wait(3))
            try:
                for state in ('running', 'paused'):
                    self.manager._runtimes['device']._set_state(state)
                    with self.assertRaises(ValueError):
                        with self.manager.queue_edit('alias'):
                            self.fail('An alias must not overwrite the active queue')
            finally:
                release.set()
                self.manager.stop('device')
            with self.manager.queue_edit('alias'):
                pass

    def test_empty_queue_start_does_not_leave_starting_state(self):
        self.manager.configure_queue_provider(lambda key: [])
        self.assertEqual(self.manager.start('device')['code'], 'EMPTY_QUEUE')
        self.assertEqual(self.manager.get_status('device')['state'], 'idle')


if __name__ == '__main__':
    unittest.main()
