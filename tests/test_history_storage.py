import csv
import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import utils
from trophy_observer import TrophyObserver,ParsedGameResult,GameMode,MatchResult


class HistoryStorageTests(unittest.TestCase):
    def test_full_disk_does_not_halt_accounting_and_pending_results_retry_once(self):
        with tempfile.TemporaryDirectory() as folder,utils.config_scope(Path(folder)):
            observer=TrophyObserver();observer.current_trophies=100;observer.current_wins=0
            original=observer.history_file.read_bytes()
            result=ParsedGameResult(GameMode.TRIO_SHOWDOWN,MatchResult.VICTORY,place=0)
            with patch('trophy_observer.os.fsync',side_effect=OSError(errno.ENOSPC,'disk full')),patch('trophy_observer.time.monotonic',return_value=10),patch('error_telemetry.report') as report:
                observer.add_trophies(result,'shelly',False,{})
                observer.add_trophies(result,'shelly',False,{})
                observer.retry_history_save()
                self.assertEqual(report.call_count,1)
                self.assertEqual(report.call_args.args[:2],('application_exception','error'))
            self.assertEqual(observer.history_file.read_bytes(),original)
            self.assertEqual(len(observer.match_history),2)
            self.assertEqual(observer.match_counter,2)
            with patch('trophy_observer.time.monotonic',return_value=41):
                self.assertTrue(observer.retry_history_save())
                self.assertTrue(observer.retry_history_save())
            with observer.history_file.open(encoding='utf-8',newline='') as handle:
                self.assertEqual(len(list(csv.DictReader(handle))),2)
            self.assertFalse(observer._history_dirty)
            self.assertFalse(list(Path(folder).glob('.*.tmp')))

    def test_cleanup_failure_does_not_mask_original_storage_error(self):
        with tempfile.TemporaryDirectory() as folder,utils.config_scope(Path(folder)):
            observer=TrophyObserver()
            with patch('trophy_observer.os.fsync',side_effect=OSError(errno.ENOSPC,'disk full')),patch.object(Path,'unlink',side_effect=PermissionError('locked')):
                with self.assertRaises(OSError) as failure:observer._atomic_save_history([])
            self.assertEqual(failure.exception.errno,errno.ENOSPC)

    def test_programming_errors_are_not_hidden_as_storage_failure(self):
        observer=TrophyObserver.__new__(TrophyObserver);observer.match_history=[]
        with patch.object(observer,'_atomic_save_history',side_effect=ValueError('bad row')):
            with self.assertRaises(ValueError):observer.save_history()
