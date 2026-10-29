"""Explicit brawler choice must survive initial startup and selection retries."""
import unittest
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_runtime_consistency import BotInstance


class InitialBrawlerChoiceTests(unittest.TestCase):
    def bot(self, locked='', sorted_pick=True, automatically_pick=True, confirmed=True):
        manager=SimpleNamespace(
            onboarding=SimpleNamespace(pending_transition=lambda state:False),
            locked_brawler=lambda:locked, _lock_queue_to=Mock(),
            _select_locked_brawler=Mock(), _lock_ok=confirmed,
            brawlers_pick_data=[{'brawler':'cosmo','automatically_pick':automatically_pick}],
            _pick_lowest_trophies=lambda:sorted_pick,
            brawler_sort_point=lambda:(850,432),
            _adopt_picked_brawler=Mock(), current_brawler=lambda:None)
        return SimpleNamespace(
            window_controller=SimpleNamespace(screenshot=lambda:'lobby',screen_state=lambda f:f),
            Stage_manager=manager, lobby_automator=Mock(), runtime_control=None,
            get_latest_state=lambda:'lobby', sleep_interruptible=Mock(return_value=None),
            stop_gracefully=Mock(), ping_when_stuck=False, device_label='test',
            update_trophy_observer=Mock(), picked_first_brawler=False)

    def test_explicit_choice_wins_over_sort_and_old_queue(self):
        for automatically_pick in (True,False):
            with self.subTest(automatically_pick=automatically_pick):
                bot=self.bot(locked='vince',automatically_pick=automatically_pick)
                self.assertTrue(BotInstance._pick_initial_brawler_step(bot))
                bot.Stage_manager._lock_queue_to.assert_called_once_with('vince')
                bot.Stage_manager._select_locked_brawler.assert_called_once_with('vince')
                bot.lobby_automator.select_brawler_by_sort.assert_not_called()
                bot.lobby_automator.select_brawler.assert_not_called()
                self.assertTrue(bot.picked_first_brawler)

    def test_unconfirmed_explicit_choice_never_falls_back_to_sort(self):
        bot=self.bot(locked='vince',confirmed=False)
        self.assertFalse(BotInstance._pick_initial_brawler_step(bot))
        self.assertFalse(bot.picked_first_brawler)
        bot.lobby_automator.select_brawler_by_sort.assert_not_called()
        bot.update_trophy_observer.assert_not_called()

    def test_named_retry_keeps_the_same_requested_brawler(self):
        bot=self.bot(sorted_pick=False)
        bot.lobby_automator.select_brawler.side_effect=['failed','success']
        self.assertTrue(BotInstance._pick_initial_brawler_step(bot))
        self.assertEqual([call.args[0] for call in bot.lobby_automator.select_brawler.call_args_list],
                         ['cosmo','cosmo'])
        bot.lobby_automator.select_brawler_by_sort.assert_not_called()

    def test_sorted_retry_preserves_configured_sort(self):
        bot=self.bot()
        bot.lobby_automator.select_brawler_by_sort.side_effect=['error','success']
        self.assertTrue(BotInstance._pick_initial_brawler_step(bot))
        self.assertEqual(bot.lobby_automator.select_brawler_by_sort.call_count,2)
        bot.lobby_automator.select_brawler.assert_not_called()
        for call in bot.lobby_automator.select_brawler_by_sort.call_args_list:
            self.assertEqual(call.kwargs['sort_point'],(850,432))

    def test_failed_named_retries_do_not_adopt_or_start_another_brawler(self):
        bot=self.bot(sorted_pick=False)
        bot.lobby_automator.select_brawler.return_value='failed'
        with patch.object(time,'sleep'):
            self.assertFalse(BotInstance._pick_initial_brawler_step(bot))
        bot.Stage_manager._adopt_picked_brawler.assert_not_called()
        bot.lobby_automator.select_brawler_by_sort.assert_not_called()
        self.assertFalse(bot.picked_first_brawler)

    def test_cancel_during_retry_does_not_issue_another_selection(self):
        bot=self.bot(sorted_pick=False)
        bot.lobby_automator.select_brawler.return_value='failed'
        bot.sleep_interruptible.return_value='stop'
        with patch.object(time,'sleep'):
            self.assertFalse(BotInstance._pick_initial_brawler_step(bot))
        self.assertEqual(bot.lobby_automator.select_brawler.call_count,1)
        bot.stop_gracefully.assert_called_once()
        bot.lobby_automator.select_brawler_by_sort.assert_not_called()
