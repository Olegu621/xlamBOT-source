"""Discovery and capture recovery when an online device stops answering."""
import importlib
import sys
import time
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, PropertyMock, patch

from adbutils.errors import AdbError
from test_runtime_consistency import BotInstance, scrcpy
BotHalt = BotInstance.check_transport_recovery.__globals__['BotHalt']


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        package = ModuleType('webui')
        package.__path__ = [str(Path('webui').resolve())]
        modules = patch.dict(sys.modules, {'webui': package, 'capture_transport': scrcpy})
        modules.start()
        self.addCleanup(modules.stop)
        self.module = importlib.import_module('webui.device_manager')
        for name, options in [
            ('load_toml_as_dict', {'return_value': {}}),
            ('AUTO_CONNECTOR.refresh', {'side_effect': lambda client, devices, preferred: devices}),
            ('device_profiles.read_profile_meta', {'return_value': {}}),
            ('foreground_package', {'return_value': 'com.supercell.brawlstars'}),
        ]:
            mocked = patch.object(self.module, name, **options) if '.' not in name else patch('webui.device_manager.' + name, **options)
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_discovery_timeout_returns_unavailable_without_ui_exception(self):
        from adbutils.errors import AdbTimeout
        with patch.object(self.module.adb, 'device_list', side_effect=AdbTimeout('timeout')):
            result = self.module.DeviceRuntimeManager.list_adb_devices()
        self.assertFalse(result[0]['ok'])

    def device(self, serial, metadata_failure=False):
        device = Mock(serial=serial)
        device.get_state.return_value = 'device'
        def shell(args, timeout):
            self.assertEqual(timeout, 3.0)
            if args == ['getprop', 'ro.product.model']:
                if metadata_failure:
                    raise AdbError('device disconnected during metadata query')
                return 'LDPlayer'
            if args == ['getprop', 'ro.build.version.release']:
                return '9'
            return 'Physical size: 1280x720'
        device.shell.side_effect = shell
        type(device).prop = PropertyMock(side_effect=AdbError('unguarded property request'))
        return device

    def test_metadata_disconnect_does_not_hide_other_devices_or_raise(self):
        failed = self.device('emulator-5554', True)
        healthy = self.device('emulator-5556')
        with patch.object(self.module.adb, 'device_list', return_value=[failed, healthy]):
            result = self.module.DeviceRuntimeManager.list_adb_devices()
        self.assertEqual([item['serial'] for item in result], ['emulator-5554', 'emulator-5556'])
        self.assertEqual(result[0]['model'], '')
        self.assertEqual(result[1]['model'], 'LDPlayer')
        self.assertTrue(result[1]['brawl_stars_running'])
        for device in (failed, healthy):
            self.assertEqual(sum(call.args[0] == ['getprop', 'ro.product.model'] for call in device.shell.call_args_list), 1)

    def test_discovery_failure_keeps_structured_unavailable_response(self):
        with patch.object(self.module.adb, 'device_list', side_effect=AdbError('ADB server unavailable')):
            result = self.module.DeviceRuntimeManager.list_adb_devices()
        self.assertFalse(result[0]['ok'])


class VideoRecoveryTests(unittest.TestCase):
    def bot(self):
        bot = BotInstance.__new__(BotInstance)
        bot.window_controller = Mock()
        bot.device_label = 'test-device'
        bot.should_stop = Mock(return_value=False)
        return bot

    def test_live_static_video_retries_before_the_halt_deadline(self):
        bot = self.bot()
        bot.window_controller.is_stream_alive.return_value = True
        with patch.object(time, 'time', return_value=100):
            bot.recover_video_stream(90, now=10)
        bot.window_controller.release_all_inputs.assert_called_once()
        bot.window_controller.reconnect_scrcpy.assert_called_once_with(max_retries=1)
        self.assertEqual(bot._transport_lost_since, 10)
        bot.window_controller.restart_brawl_stars.assert_not_called()

    def test_short_encoder_pause_has_no_reconnect_or_input(self):
        bot = self.bot()
        with patch.object(time, 'time', return_value=100):
            bot.recover_video_stream(99, now=10)
        bot.window_controller.reconnect_scrcpy.assert_not_called()
        bot.window_controller.release_all_inputs.assert_called_once()

    def test_missing_frame_retries_are_bounded_and_do_not_reset_loss_timer(self):
        bot = self.bot()
        bot.window_controller.reconnect_scrcpy.return_value = True
        bot.recover_video_stream(0, now=10)
        bot.recover_video_stream(0, now=11)
        bot.recover_video_stream(0, now=25)
        self.assertEqual(bot.window_controller.reconnect_scrcpy.call_count, 2)
        self.assertEqual(bot._transport_lost_since, 10)
        with self.assertRaises(BotHalt):
            bot.recover_video_stream(0, now=70)
        self.assertEqual(bot.window_controller.reconnect_scrcpy.call_count, 2)

    def test_fresh_video_clears_deadline_and_stop_never_reconnects(self):
        bot = self.bot()
        bot.recover_video_stream(0, now=10)
        bot.check_transport_recovery(True, now=50)
        self.assertIsNone(bot._transport_lost_since)
        bot.should_stop.return_value = True
        bot.window_controller.reconnect_scrcpy.reset_mock()
        bot.recover_video_stream(0, now=51)
        bot.window_controller.reconnect_scrcpy.assert_not_called()

    def test_worker_recovers_missing_or_static_frame_without_waiting_or_clicking(self):
        for frame, stamp in [(None, 0), (object(), 90)]:
            with self.subTest(stamp=stamp), patch.object(time, 'time', return_value=100):
                bot = self.bot()
                bot.picked_first_brawler = True
                bot._thinking_config_checked = time.perf_counter()
                bot.run_for_minutes = 0
                bot.in_cooldown = False
                bot.get_latest_state = Mock(return_value='frame_stale')
                bot.check_and_handle_brawl_stars_crash = Mock(return_value=True)
                bot.window_controller.FRAME_STALE_TIMEOUT = .75
                bot.window_controller.get_latest_frame.return_value = (frame, stamp)
                bot.window_controller.is_stream_alive.return_value = True
                bot.sleep_interruptible = Mock(return_value='stop')
                bot.stop_gracefully = Mock()
                bot.Play = Mock()
                bot.handle_detected_state = Mock()
                bot._main_loop()
                bot.window_controller.reconnect_scrcpy.assert_called_once_with(max_retries=1)
                bot.window_controller.screenshot.assert_not_called()
                bot.handle_detected_state.assert_not_called()
                bot.Play.main.assert_not_called()
                bot.stop_gracefully.assert_called_once()


if __name__ == '__main__':
    unittest.main()
