"""Regression scenarios from the revision 54 architecture audit."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch

import numpy as np
import device_profiles as profiles
import settings_schema
import utils
import update_client
from runtime_observation import Observations
# Device transport is provided by the installed runtime, not the source repo.
# Use a control-boundary double; import and exercise the real worker/controller.
scrcpy = SimpleNamespace(ACTION_UP=1, ACTION_DOWN=0, ACTION_MOVE=2)
with patch.dict(sys.modules, {'capture_transport': scrcpy}):
    from bot_instance import BotInstance
    from window_controller import WindowController, StaleFrameError
from play import Play
from stage_manager import StageManager
from trophy_observer import TrophyObserver, MatchResult
from side_menu import _templates, side_menu_close_position


class RuntimeConsistencyTests(unittest.TestCase):
    def bot(self):
        bot = BotInstance.__new__(BotInstance)
        bot.observations = Observations()
        bot.state_lock = bot.observations.lock
        bot.state = None
        bot.latest_state_frame_time = 0
        bot.max_cached_state_age = 1
        bot.window_controller = MagicMock()
        bot.Play = SimpleNamespace(world_state={'player_present': True, 'timestamp': time.time()})
        bot.Stage_manager = Mock()
        return bot

    def test_old_frame_cannot_overwrite_new_screen_or_release_input(self):
        bot = self.bot()
        self.assertTrue(bot.set_latest_state('lobby', 100.15))
        self.assertFalse(bot.set_latest_state('match', 100.10))
        self.assertFalse(bot.set_latest_state('match', 100.15))
        self.assertEqual(bot.state, 'lobby')
        bot.window_controller.release_all_inputs.assert_not_called()

    def test_unknown_is_not_promoted_by_cached_player_detection(self):
        bot = self.bot()
        bot.set_latest_state('unknown', time.time())
        self.assertEqual(bot.get_latest_state(), 'unknown')

    def test_expired_cache_has_no_unknown_recovery_authority(self):
        bot = self.bot()
        bot.set_latest_state('unknown', time.time() - 5)
        self.assertEqual(bot.get_latest_state(), 'frame_stale')

    def test_cached_handler_neither_republishes_nor_handles_obsolete_state(self):
        bot = self.bot()
        bot.set_latest_state('lobby', time.time())
        snapshot = bot.observations.snapshot()
        bot._handle_detected_state = Mock()
        bot.handle_detected_state('match')
        bot._handle_detected_state.assert_not_called()
        bot.handle_detected_state('lobby')
        bot._handle_detected_state.assert_called_once_with('lobby')
        self.assertEqual(bot.observations.snapshot(), snapshot)

    def controller(self):
        controller = WindowController.__new__(WindowController)
        controller.observations = Observations()
        controller.observations.publish('match', time.time())
        controller.input_owner = threading.get_ident()
        controller.input_lock = threading.RLock()
        controller.active_touches = {}
        controller.input_enabled = True
        controller.gameplay_frame_time = None
        controller.FRAME_STALE_TIMEOUT = .75
        controller.frame_is_fresh = lambda *a: True
        controller.is_stream_alive = lambda: True
        controller.scrcpy_client = SimpleNamespace(control=Mock())
        return controller

    def test_menu_transition_during_inference_rejects_attack(self):
        controller = self.controller()
        with controller.decision_scope(controller.observations.snapshot()):
            controller.observations.publish('lobby', time.time())
            with self.assertRaises(StaleFrameError):
                controller._send_touch(900, 600, scrcpy.ACTION_DOWN, 2)
        controller.scrcpy_client.control.touch.assert_not_called()

    def test_new_frames_of_same_screen_do_not_starve_input(self):
        controller = self.controller()
        with controller.decision_scope(controller.observations.snapshot()):
            controller.observations.publish('match', time.time())
            controller._send_touch(900, 600, scrcpy.ACTION_DOWN, 2)
            controller._send_touch(900, 600, scrcpy.ACTION_UP, 2)
        self.assertEqual(controller.scrcpy_client.control.touch.call_count, 2)

    def test_fresh_menu_screenshot_can_advance_a_confirmed_selection_flow(self):
        controller=self.controller()
        controller.width=1280;controller.height=720
        controller.get_latest_frame=lambda:(np.zeros((720,1280,3),np.uint8),time.time())
        def observe(frame,stamp):
            controller.observations.publish('brawler_selection',stamp)
            return controller.observations.snapshot()
        controller.observe_action_frame=observe
        with controller.decision_scope(controller.observations.snapshot(),allow_menu_transitions=True):
            controller.screenshot()
            controller._send_touch(20,20,scrcpy.ACTION_DOWN,2)
        controller.scrcpy_client.control.touch.assert_called_once()

    def test_battle_screenshot_does_not_reauthorize_attack_after_menu_transition(self):
        controller=self.controller()
        controller.width=1280;controller.height=720
        controller.get_latest_frame=lambda:(np.zeros((720,1280,3),np.uint8),time.time())
        controller.observe_action_frame=Mock()
        with controller.decision_scope(controller.observations.snapshot()):
            controller.observations.publish('lobby',time.time())
            controller.screenshot()
            with self.assertRaises(StaleFrameError):controller._send_touch(20,20,scrcpy.ACTION_DOWN,2)
        controller.observe_action_frame.assert_not_called()

    def test_watchdog_releases_held_input_after_screen_transition(self):
        controller=self.controller()
        with controller.decision_scope(controller.observations.snapshot()):
            controller._send_touch(20,20,scrcpy.ACTION_DOWN,1)
        controller.observations.publish('lobby',time.time())
        controller._watchdog_stop=SimpleNamespace(wait=Mock(side_effect=[False,True]))
        controller._input_watchdog()
        self.assertEqual(controller.active_touches,{})
        self.assertEqual(controller.scrcpy_client.control.touch.call_args.args[2],scrcpy.ACTION_UP)

    def test_stop_and_other_thread_cannot_send_down(self):
        controller = self.controller()
        controller.stop_requested = lambda: True
        with self.assertRaises(StaleFrameError):
            controller._send_touch(10, 10, scrcpy.ACTION_DOWN, 2)
        controller.stop_requested = lambda: False
        errors = []
        def worker():
            try:
                controller._send_touch(10, 10, scrcpy.ACTION_DOWN, 2)
            except StaleFrameError:
                errors.append(True)
        thread = threading.Thread(target=worker)
        thread.start(); thread.join(2)
        self.assertEqual(errors, [True])
        controller.scrcpy_client.control.touch.assert_not_called()

    def test_observations_from_racing_classifiers_remain_ordered(self):
        observations = Observations()
        threads = [threading.Thread(target=observations.publish, args=(str(index), float(index))) for index in range(1, 40)]
        for thread in reversed(threads): thread.start()
        for thread in threads: thread.join(2)
        self.assertEqual(observations.snapshot().state, '39')

    def test_reward_ignores_stale_state_and_honors_stop(self):
        manager = StageManager.__new__(StageManager)
        manager.window_controller = Mock()
        manager.runtime_control = SimpleNamespace(should_stop=lambda: True, should_pause=lambda: False)
        manager.click_star_drop('angelic')
        manager.window_controller.press.assert_not_called()
        manager.runtime_control = None
        with patch('stage_manager.get_state', return_value='lobby'):
            manager.click_star_drop('regular')
        manager.window_controller.press.assert_not_called()
        with patch('stage_manager.get_state', return_value='star_drop_regular'):
            manager.click_star_drop('regular')
        manager.window_controller.press.assert_called_once_with('proceed', .05)
        self.assertFalse(hasattr(manager, '_star_drop_thread'))

    def test_fast_results_count_once_and_next_battle_counts(self):
        manager = StageManager.__new__(StageManager)
        manager.window_controller = Mock()
        manager.runtime_control = None
        manager.play_again_on_win = False
        manager.time_since_last_stat_change = time.time() - 2
        manager.playstyle_info = {}
        manager.current_brawler = lambda: 'shelly'
        manager.brawlers_pick_data = [{'brawler':'shelly', 'type':'trophies'}]
        manager.Trophy_observer = Mock(current_trophies=5, current_wins=0, win_streak=0)
        manager.Trophy_observer.parse_game_result.return_value = SimpleNamespace(result=MatchResult.DEFEAT)
        manager._sleep_interruptible = lambda *a: False
        def result():
            with patch('stage_manager.get_state', side_effect=['end_defeat','lobby']), patch('stage_manager.is_underdog',return_value=False), patch('stage_manager.save_brawler_data'):
                manager.end_game()
        result(); result()
        self.assertEqual(manager.Trophy_observer.add_trophies.call_count, 1)
        manager.observe_match(); manager.observe_match()
        result()
        self.assertEqual(manager.Trophy_observer.add_trophies.call_count, 2)

    def test_gas_failure_preserves_danger_and_marks_unavailable(self):
        play = Play.__new__(Play)
        play.Detect_gas = SimpleNamespace(detect_objects=Mock(side_effect=RuntimeError('offline')))
        play.gas_boxes = [[1,1,20,20]]
        play.gas_mask = np.ones((30,30),np.uint8)
        play.gas_mask_time = 0; play.gas_detect_interval = .1; play.gas_confidence = .25
        play.gas_in_danger = True; play.gas_detection_ok = True
        play.gas_player_box = [2,2,10,10]; play.verbose_debug = False
        play.refresh_gas(np.zeros((30,30,3),np.uint8))
        self.assertFalse(play.gas_detection_ok)
        self.assertTrue(play.gas_in_danger)
        self.assertEqual(play.gas_state, 'UNAVAILABLE')

    def test_profile_paths_reject_traversal_reserved_names_and_aliases(self):
        for key in ['.', '..', 'CON', 'nul.txt', 'LPT1', 'phone/1', 'phone\\1', 'bad.']:
            with self.assertRaises(ValueError, msg=key): profiles.profile_dir(key)
        self.assertNotEqual(profiles.sanitize_key('phone:1'), profiles.sanitize_key('phone-1'))
        self.assertEqual(profiles.sanitize_key('127.0.0.1:5555'), '127.0.0.1-5555')
        self.assertEqual(profiles.sanitize_key('emulator-5554'), 'emulator-5554')

    def test_parallel_settings_preserve_both_edits(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(utils,'PROJECT_ROOT',Path(temporary)), patch.object(utils,'DATA_ROOT',Path(temporary)):
            cfg=Path(temporary)/'cfg'; cfg.mkdir()
            (cfg/'audit.toml').write_text('a = 0\nb = 0\n',encoding='utf8')
            profiles.ensure_profile('audit-device')
            barrier=threading.Barrier(2); errors=[]
            original=utils.save_dict_as_toml
            def delayed(values,path):
                time.sleep(.03)
                original(values,path)
            def worker(values):
                try:
                    barrier.wait(2); profiles.update_settings('audit-device','audit',values)
                except Exception as error: errors.append(error)
            with patch.object(utils,'save_dict_as_toml',side_effect=delayed):
                threads=[threading.Thread(target=worker,args=(v,)) for v in [{'a':1},{'b':2}]]
                for thread in threads: thread.start()
                for thread in threads: thread.join(3)
            self.assertFalse(errors)
            self.assertEqual(profiles.read_settings('audit-device')['audit'],{'a':1,'b':2})

    def test_variable_lists_validate_tail_and_auto_union_both_ways(self):
        for value in [['gas',17], ['gas','gas'], ['gas','']]:
            with self.assertRaises(ValueError): settings_schema.validate('gas_classes',value,['gas'])
        settings_schema.validate('wall_model_classes',['wall','bush'],['wall'])
        for name in ['max_fps','used_threads']:
            settings_schema.validate(name,'auto',4)
            settings_schema.validate(name,4,'auto')
            for value in [True,0,'bad',[],1000]:
                with self.assertRaises(ValueError): settings_schema.validate(name,value,'auto')

    def test_verified_current_survives_broken_pending(self):
        previous_meta=list(sys.meta_path)
        try:
            with tempfile.TemporaryDirectory() as temporary, patch.dict('os.environ',{'XLAMBOT_UPDATE_HOME':temporary}), patch.object(update_client,'BUNDLED_REVISION',0):
                folder=Path(temporary)/'releases'/'54'; (folder/'content').mkdir(parents=True)
                (folder/'manifest.json').write_text(json.dumps({'revision':54}))
                update_client.write_state({'enabled':True,'revision':54,'pending':55})
                with patch.object(update_client,'verify',side_effect=lambda value:value),patch.object(update_client,'validate_content'):
                    self.assertEqual(update_client.activate(), folder/'content')
                state=update_client.read_state()
                self.assertEqual(state['revision'],54)
                self.assertNotIn('pending',state)
                self.assertIn('restored verified',state['last_error'])
        finally:
            sys.meta_path[:]=previous_meta
            update_client.ACTIVE_OVERLAY=None

    def test_previous_survives_broken_current_and_pending(self):
        previous_meta=list(sys.meta_path)
        try:
            with tempfile.TemporaryDirectory() as temporary, patch.dict('os.environ',{'XLAMBOT_UPDATE_HOME':temporary}), patch.object(update_client,'BUNDLED_REVISION',0):
                folder=Path(temporary)/'releases'/'53'; (folder/'content').mkdir(parents=True)
                (folder/'manifest.json').write_text(json.dumps({'revision':53}))
                update_client.write_state({'enabled':True,'revision':54,'previous':53,'pending':55})
                with patch.object(update_client,'verify',side_effect=lambda value:value),patch.object(update_client,'validate_content'):
                    self.assertEqual(update_client.activate(),folder/'content')
                self.assertEqual(update_client.read_state()['revision'],53)
        finally:
            sys.meta_path[:]=previous_meta
            update_client.ACTIVE_OVERLAY=None

    def test_locked_history_fails_in_bounded_time(self):
        with patch('trophy_observer.os.replace',side_effect=PermissionError('locked')),patch('trophy_observer.time.monotonic',side_effect=[1.,2.,5.]),patch('trophy_observer.time.sleep'):
            with self.assertRaises(PermissionError): TrophyObserver._replace_when_available(Path('source'),Path('history'))

    def test_new_installer_never_reactivates_older_overlay_when_updates_disabled(self):
        with tempfile.TemporaryDirectory() as temporary,patch.dict('os.environ',{'XLAMBOT_UPDATE_HOME':temporary}):
            update_client.write_state({'enabled':False,'revision':54,'pending':53})
            self.assertIsNone(update_client.activate())
            state=update_client.read_state()
            self.assertEqual(state['revision'],55)
            self.assertNotIn('pending',state)
            self.assertFalse(state['enabled'])

    def test_side_menu_requires_multiple_controls_and_scales(self):
        for height,width in [(577,837),(720,1280),(1080,1920)]:
            frame=np.full((height,width,3),30,np.uint8)
            icons=_templates(height)
            for glyph,y in zip(icons[:3],[.08,.20,.55]):
                x=int(width*.76); top=int(height*y)
                frame[top:top+glyph.shape[0],x:x+glyph.shape[1]]=glyph[:,:,None]
            glyph=icons[3]; x=int(width*.93); top=2
            frame[top:top+glyph.shape[0],x:x+glyph.shape[1]]=glyph[:,:,None]
            self.assertIsNotNone(side_menu_close_position(frame))
            frame[int(height*.08):int(height*.70)]=30
            self.assertIsNone(side_menu_close_position(frame))

    def test_unknown_without_confirmed_control_does_not_open_menu(self):
        manager=StageManager.__new__(StageManager)
        manager.runtime_control=None; manager._unknown_since=0; manager._last_unknown_tap=-100
        manager.window_controller=Mock()
        manager.window_controller.screenshot.return_value=np.zeros((720,1280,3),np.uint8)
        with patch('stage_manager.get_state',return_value='unknown'):
            manager.recover_unknown()
        manager.window_controller.click.assert_not_called()

    def test_account_change_cannot_be_reported_as_earnings(self):
        observer=TrophyObserver.__new__(TrophyObserver)
        observer._account_tag='#AAA'; observer._pending_account=None
        observer.account_total=10000; observer.account_samples=[(time.time()-400,10000)]
        observer.account_verified=True; observer.save_account_state=Mock()
        with patch.object(observer,'_account_identity',return_value='#BBB'):
            observer.record_account_total(10100); observer.record_account_total(10100)
        self.assertEqual(len(observer.account_samples),1)
        self.assertEqual(observer.account_samples[0][1],10100)

    def test_model_catalog_accepts_both_raw_yolo_axis_orders(self):
        import training_models, onnxruntime
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'test.onnx'; path.write_bytes(b'model')
            for shape in [[1,7,8400],[1,8400,7]]:
                session=SimpleNamespace(get_modelmeta=lambda:SimpleNamespace(custom_metadata_map={'names':"['player','enemy','teammate']"}),get_outputs=lambda:[SimpleNamespace(shape=shape)])
                training_models._read_catalog.cache_clear()
                with patch.object(onnxruntime,'InferenceSession',return_value=session):
                    self.assertEqual(training_models._read_catalog(((str(path),0,5),))['classes'],['enemy','teammate','player'])


if __name__=='__main__': unittest.main()
