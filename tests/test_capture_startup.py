import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from test_runtime_consistency import BotInstance
worker = BotInstance._connect_controller.__globals__
CaptureConnectionError = worker['CaptureConnectionError']
StartupCancelled = worker['StartupCancelled']


class StartupTests(unittest.TestCase):
    def instance(self, serial='emulator-5554'):
        b = BotInstance.__new__(BotInstance)
        b.serial = serial
        b.device_label = 'test'
        b.max_fps = 30
        b.stop_event = None
        b.runtime_control = None
        b.sleep_interruptible = Mock(return_value=None)
        return b

    def test_transient_connection_retry_stays_on_same_device(self):
        b = self.instance()
        controller = Mock()
        create = Mock(side_effect=[CaptureConnectionError(), controller])
        with patch.dict(worker, WindowController=create):
            self.assertIs(b._connect_controller(), controller)
        self.assertEqual(create.call_args_list[0], create.call_args_list[1])
        self.assertEqual(create.call_args.kwargs['serial'], b.serial)

    def test_exhaustion_is_bounded_and_unpinned_discovery_is_not_repeated(self):
        for serial, count in [('emulator-5554', 6), (None, 1)]:
            b = self.instance(serial)
            create = Mock(side_effect=CaptureConnectionError())
            with patch.dict(worker, WindowController=create):
                with self.assertRaises(CaptureConnectionError):
                    b._connect_controller()
            self.assertEqual(create.call_count, count)

    def test_capture_available_after_longer_startup_recovers_without_switching_device(self):
        b = self.instance()
        controller = Mock()
        create = Mock(side_effect=[CaptureConnectionError()] * 5 + [controller])
        with patch.dict(worker, WindowController=create):
            self.assertIs(b._connect_controller(), controller)
        self.assertEqual([call.args[0] for call in b.sleep_interruptible.call_args_list], [1,2,4,8,15])
        self.assertTrue(all(call.kwargs['serial'] == b.serial for call in create.call_args_list))

    def test_programming_error_is_not_retried(self):
        b = self.instance()
        create = Mock(side_effect=ValueError('invalid settings'))
        with patch.dict(worker, WindowController=create):
            with self.assertRaises(ValueError):
                b._connect_controller()
        self.assertEqual(create.call_count, 1)

    def test_pause_and_stop_cancel_retry_and_close_successful_late_connection(self):
        for action in ['stop', 'pause']:
            b = self.instance()
            b.sleep_interruptible.return_value = action
            create = Mock(side_effect=CaptureConnectionError())
            with patch.dict(worker, WindowController=create):
                with self.assertRaises(StartupCancelled):
                    b._connect_controller()
            self.assertEqual(create.call_count, 1)
        b = self.instance()
        stopped = [False]
        b.runtime_control = SimpleNamespace(should_stop=lambda: stopped[0], should_pause=lambda: False)
        controller = Mock()
        def connected(*args, **kwargs):
            stopped[0] = True
            return controller
        with patch.dict(worker, WindowController=Mock(side_effect=connected)):
            with self.assertRaises(StartupCancelled):
                b._connect_controller()
        controller.close.assert_called_once()


class StreamTests(unittest.TestCase):
    def load_adapter(self, failure):
        package = ModuleType('scrcpy')
        core = ModuleType('scrcpy.core')
        class BaseClient:
            def _Client__stream_loop(self):
                raise failure
            def stop(self):
                self.stopped = True
        package.Client = BaseClient
        for name in ['EVENT_FRAME', 'EVENT_DISCONNECT', 'ACTION_UP', 'ACTION_DOWN', 'ACTION_MOVE']:
            setattr(package, name, 0)
        core.AdbConnection = object
        core.SCRCPY_SERVER_VERSION = '2.7'
        package.core = core
        path = Path(worker['__file__']).resolve().parent / 'capture_transport.py'
        if not path.exists():
            path = path.with_suffix('.pyc')
        spec = importlib.util.spec_from_file_location('isolated_transport_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'scrcpy': package, 'scrcpy.core': core}):
            spec.loader.exec_module(module)
        return module.Client.__new__(module.Client)

    def test_socket_loss_stops_stream_without_unhandled_thread_crash(self):
        for error in [ConnectionError('closed'), OSError('reset')]:
            client = self.load_adapter(error)
            client._Client__stream_loop()
            self.assertTrue(client.stopped)

    def test_unexpected_decoder_failure_still_propagates(self):
        client = self.load_adapter(RuntimeError('decoder failed'))
        with self.assertRaises(RuntimeError):
            client._Client__stream_loop()
