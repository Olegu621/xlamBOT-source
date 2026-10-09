import json
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import presentation_preferences as preferences


class PCNameTests(unittest.TestCase):
    def test_language_changes_preserve_name_and_concurrent_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'prefs.json'
            with patch('utils.resolve_project_path', return_value=path):
                preferences.save(pc_name='  Игровой ПК  ')
                with ThreadPoolExecutor(2) as pool:
                    list(pool.map(lambda action: preferences.save(**action),
                                  [{'language': 'en'}, {'pc_name': 'Second PC'}]))
                self.assertEqual(preferences.read(), {'language': 'en', 'pc_name': 'Second PC'})
                preferences.save(pc_name='')
                self.assertEqual(preferences.read()['pc_name'], '')

    def test_invalid_names_and_corrupt_preferences(self):
        for value in (None, 5, 'a'*65, 'PC\nlog', 'PC\x00', '\u202ePC'):
            with self.assertRaises(ValueError):
                preferences.validate_pc_name(value)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'prefs.json'
            with patch('utils.resolve_project_path', return_value=path):
                for value in ([], {'language':'en', 'pc_name':'bad\nname'}):
                    path.write_text(json.dumps(value), encoding='utf-8')
                    self.assertEqual(preferences.read()['pc_name'], '')

    def test_error_report_carries_explicit_name_only(self):
        from error_telemetry import ErrorTelemetry
        with tempfile.TemporaryDirectory() as directory:
            reporter = ErrorTelemetry(Path(directory), 'https://receiver.example')
            with patch('presentation_preferences.read', return_value={'language':'ru','pc_name':'Office PC'}):
                self.assertTrue(reporter.report('runtime_crash'))
            reporter.drain()
            self.assertEqual(reporter.export()['events'][0]['pc_name'], 'Office PC')
