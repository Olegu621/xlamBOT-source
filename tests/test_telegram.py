import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import urllib.error

from flask import Flask, jsonify, request

from telegram_integration.bridge import BridgeError, LocalBridge
from telegram_integration.cli import configure_console, SingleInstance
from telegram_integration.client import ManagerClient, SessionError as ClientSessionError
from telegram_integration.controller import Controller
from telegram_integration.counter import MatchCounter
from telegram_integration.lifecycle import AppBridge, start_optional
from telegram_integration.manager import Sessions, SessionError, Management, handler_for
from telegram_integration.notifications import Notifications, quiet_now
from telegram_integration.service import Service
from telegram_integration.store import Store, redact
from telegram_integration.transport import APIError, TelegramAPI

TOKEN = "123456789:" + "a" * 32  # Fixture only; no real Telegram API is called.


class API:
    def __init__(self, token=TOKEN):
        self.calls = []
        self.updates = []

    def validate(self):
        return {"id": 123456789, "username": "FixtureBot", "is_bot": True}

    def call(self, method, **payload):
        self.calls.append((method, payload))
        if method == "getUpdates":
            return self.updates
        if method == "getManagedBotToken":
            return TOKEN
        return {"message_id": 1}

    def photo(self, chat_id, image, caption):
        self.calls.append(("photo", {"chat_id": chat_id, "image": image, "caption": caption}))


class Bridge:
    language = "en"

    def __init__(self):
        self.items = {key: {"key": key, "serial": key + ":16384", "state": "device",
                           "runtime": {"state": "idle", "is_running": False, "started_at": 1}}
                      for key in ("a", "b")}
        self.data = {key: {"completed_matches": 0, "brawler": "Shelly", "account_total": 100, "queue_length": 1}
                     for key in self.items}
        self.controls = []

    def devices(self):
        return self.items

    def telemetry(self, key):
        return self.data[key].copy()

    def control(self, key, action, serial=None):
        self.controls.append((key, action, serial))
        self.items[key]["runtime"].update(state={"start": "running", "resume": "running", "pause": "paused", "stop": "idle"}[action],
                                           is_running=action != "stop")
        return {"ok": True}

    def stop_all(self):
        self.controls.append(("all", "stop", None))

    def screenshot(self, key):
        return b"jpeg"

    def request(self, path):
        return {"state": "current", "revision": 24}


class Base(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = Store(self.temporary.name)
        self.api, self.bridge, self.stop = API(), Bridge(), threading.Event()
        self.now = 1000

    def clock(self):
        return self.now

    def owner(self):
        self.store.update(configured=True, enabled=True, owner_id=11, chat_id=11, selected="a")

    def controller(self):
        return Controller(self.store, self.api, self.bridge, self.stop, self.clock)

    def callback(self, data, user=11, chat=11, identifier="press"):
        return {"callback_query": {"id": identifier, "from": {"id": user}, "data": data,
                                  "message": {"message_id": 1, "chat": {"id": chat, "type": "private"}}}}

    def button(self, action):
        markup = self.api.calls[-1][1]["reply_markup"]
        return next(button["callback_data"] for row in markup["inline_keyboard"] for button in row
                    if button["callback_data"].split(":")[1] == action)


class SetupTests(Base):
    def test_decline_never_connects(self):
        factory = Mock()
        config = configure_console(self.store, interactive=True, input_fn=lambda _: "2", output=lambda _: None, api_factory=factory)
        self.assertFalse(config["enabled"])
        self.assertTrue(Store(self.temporary.name).snapshot()["configured"])
        factory.assert_not_called()

    def test_headless_setup_never_prompts_even_with_flag(self):
        prompt = Mock(side_effect=AssertionError("must not prompt"))
        config = configure_console(self.store, force=True, interactive=False, input_fn=prompt)
        self.assertFalse(config["enabled"])
        prompt.assert_not_called()

    def test_manual_setup_hides_token_and_keeps_secrets_separate(self):
        choices = iter(["1", "2"])
        output = []
        config = configure_console(self.store, interactive=True, input_fn=lambda _: next(choices),
                                   secret_fn=lambda _: TOKEN, output=output.append, open_url=lambda _: None, api_factory=API)
        self.assertTrue(config["enabled"])
        self.assertEqual(self.store.secret()["token"], TOKEN)
        self.assertNotIn(TOKEN, "\n".join(output))
        self.assertNotIn(TOKEN, (Path(self.temporary.name) / "preferences.json").read_text())
        import os
        if os.name == "nt":
            self.assertNotIn(TOKEN.encode(), (Path(self.temporary.name) / "secrets.bin").read_bytes())
        else:
            self.assertEqual((Path(self.temporary.name) / "secrets.bin").stat().st_mode & 0o777, 0o600)

    def test_bad_token_does_not_abort_game_start(self):
        output = []
        choices = iter(["1", "2"])
        factory = Mock(side_effect=APIError("invalid_token"))
        config = configure_console(self.store, interactive=True, input_fn=lambda _: next(choices), secret_fn=lambda _: TOKEN,
                                   output=output.append, api_factory=factory)
        self.assertFalse(config["enabled"])
        self.assertNotIn(TOKEN, str(output))

    def test_os_secret_round_trip(self):
        self.store.put_secret(token=TOKEN)
        self.assertEqual(Store(self.temporary.name).secret(), {"token": TOKEN})

    def test_redacts_tokens_in_diagnostics(self):
        self.assertNotIn(TOKEN, redact("Failure requesting /bot" + TOKEN + "/getMe"))

    def test_single_instance_rejects_second_poller(self):
        first = SingleInstance(Path(self.temporary.name) / "client.lock")
        second = SingleInstance(Path(self.temporary.name) / "client.lock")
        first.acquire()
        self.addCleanup(first.close)
        with self.assertRaises(RuntimeError):
            second.acquire()

    def test_managed_console_setup_uses_handoff_without_a_manager_token(self):
        output = []
        choices = iter(["1", "1"])
        client = Mock()
        client.request.side_effect = [{"session": "s", "claim_secret": "capability", "url": "https://t.me/ManagerBot?start=connect_s"},
                                     {"ready": True, "token": TOKEN, "owner_id": 11}]
        with patch("telegram_integration.cli.ManagerClient", return_value=client):
            configure_console(self.store, interactive=True, input_fn=lambda _: next(choices), output=output.append,
                              manager_url="https://manager.example", open_url=lambda _: None, api_factory=API)
        self.assertEqual(self.store.snapshot()["owner_id"], 11)
        self.assertNotIn("capability", str(output))
        self.assertNotIn(TOKEN, str(output))

    def test_pair_code_is_expiring_and_single_use(self):
        code = self.store.pairing_code(now=100)
        self.assertFalse(self.store.bind("wrong", 11, 11, now=101))
        self.assertTrue(self.store.bind(code, 11, 11, now=102))
        self.assertFalse(self.store.bind(code, 22, 22, now=103))
        self.assertEqual(self.store.snapshot()["owner_id"], 11)

    def test_expired_code_cannot_bind(self):
        code = self.store.pairing_code(now=100)
        self.assertFalse(self.store.bind(code, 11, 11, now=400))

    def test_managed_owner_cannot_be_replaced(self):
        self.store.update(owner_id=11)
        code = self.store.pairing_code(now=100)
        self.assertFalse(self.store.bind(code, 22, 22, now=101))
        self.assertTrue(self.store.bind(code, 11, 11, now=102))


class ControlTests(Base):
    def setUp(self):
        super().setUp()
        self.owner()

    def test_foreign_user_and_chat_cannot_control(self):
        controller = self.controller()
        controller.menu()
        button = self.button("start")
        controller.handle(self.callback(button, user=22, chat=22))
        controller.handle(self.callback(button, user=11, chat=22))
        self.assertEqual(self.bridge.controls, [])

    def test_repeated_press_only_executes_once(self):
        controller = self.controller()
        controller.menu()
        button = self.button("start")
        controller.handle(self.callback(button))
        controller.handle(self.callback(button))
        controller.handle(self.callback(button, identifier="another-id"))
        self.assertEqual(self.bridge.controls, [("a", "start", "a:16384")])

    def test_expired_and_changed_device_buttons_are_rejected(self):
        for changed in (False, True):
            with self.subTest(changed=changed):
                controller = self.controller()
                controller.menu()
                button = self.button("start")
                if changed:
                    self.store.update(selected="b")
                else:
                    self.now += 601
                controller.handle(self.callback(button))
        self.assertEqual(self.bridge.controls, [])

    def test_real_button_styles(self):
        self.controller().menu()
        buttons = [button for row in self.api.calls[-1][1]["reply_markup"]["inline_keyboard"] for button in row]
        self.assertEqual(next(b for b in buttons if ":start:" in b["callback_data"])["style"], "success")
        self.assertEqual(next(b for b in buttons if ":stop:" in b["callback_data"])["style"], "danger")

    def test_forged_stop_all_confirmation_does_not_execute(self):
        controller = self.controller()
        controller.menu()
        nonce = self.button("start").split(":")[0]
        controller.handle(self.callback(nonce + ":confirmed:stop_all"))
        self.assertEqual(self.bridge.controls, [])

    def test_stop_all_requires_confirmation(self):
        controller = self.controller()
        controller.menu()
        controller.handle(self.callback(self.button("confirm")))
        self.assertEqual(self.bridge.controls, [])
        controller.handle(self.callback(self.button("confirmed"), identifier="confirm"))
        self.assertEqual(self.bridge.controls, [("all", "stop", None)])

    def test_selecting_one_device_does_not_control_another(self):
        controller = self.controller()
        controller.menu("devices")
        markup = self.api.calls[-1][1]["reply_markup"]["inline_keyboard"]
        controller.handle(self.callback(markup[1][0]["callback_data"]))
        controller.handle(self.callback(self.button("start"), identifier="start-b"))
        self.assertEqual(self.bridge.controls, [("b", "start", "b:16384")])

    def test_start_is_account_linking_not_autoplay(self):
        self.controller().handle({"message": {"from": {"id": 11}, "chat": {"id": 11, "type": "private"}, "text": "/start"}})
        self.assertEqual(self.bridge.controls, [])

    def test_photo_only_uses_selected_device(self):
        controller = self.controller()
        controller.menu()
        controller.handle(self.callback(self.button("photo")))
        self.assertEqual(next(payload for method, payload in self.api.calls if method == "photo")["caption"], "a")

    def test_preferences_survive_restart(self):
        controller = self.controller()
        controller.menu("notifications")
        controller.handle(self.callback(self.button("toggle")))
        self.assertNotIn("lifecycle", Store(self.temporary.name).snapshot()["categories"])

    def test_at_most_once_after_restart(self):
        service = Service(self.store, self.api, self.bridge, self.clock)
        service.controller.menu()
        update = {"update_id": 100, **self.callback(self.button("start"))}
        self.api.updates = [update, update]
        service.poll_once()
        restarted = Service(Store(self.temporary.name), self.api, self.bridge, self.clock)
        restarted.poll_once()
        self.assertEqual(len(self.bridge.controls), 1)


class EventTests(Base):
    def setUp(self):
        super().setUp()
        self.owner()
        self.store.update(categories=list(("error", "adb", "match", "lifecycle", "summary")))

    def test_filter_and_duplicate_suppression(self):
        notifications = Notifications(self.store, self.api, self.stop, self.clock)
        self.store.update(device_filter="a")
        notifications.enqueue("error", "b", "wrong device")
        notifications.enqueue("error", "a", "same error")
        notifications.enqueue("error", "a", "same error")
        self.assertEqual(len(notifications.queue), 1)

    def test_quiet_hours_cross_midnight_and_critical_override(self):
        from datetime import datetime
        notifications = Notifications(self.store, self.api, self.stop, self.clock)
        self.store.update(quiet_enabled=True)
        event = {"category": "error", "device": "a", "critical": False}
        self.assertFalse(notifications.allowed(event, datetime(2026, 1, 1, 1, 0)))
        event["critical"] = True
        self.assertTrue(notifications.allowed(event, datetime(2026, 1, 1, 1, 0)))
        self.store.update(critical_at_night=False)
        self.assertFalse(notifications.allowed(event, datetime(2026, 1, 1, 1, 0)))
        self.assertFalse(quiet_now(self.store.snapshot(), datetime(2026, 1, 1, 12, 0)))

    def test_queue_is_bounded_and_stale_alerts_expire(self):
        notifications = Notifications(self.store, self.api, self.stop, self.clock)
        for index in range(100):
            notifications.enqueue("error", "a", str(index))
        self.assertEqual(len(notifications.queue), 50)
        self.now += 121
        self.assertIsNone(notifications.next_event())

    def test_disable_cancels_pending_alerts(self):
        notifications = Notifications(self.store, self.api, self.stop, self.clock)
        notifications.enqueue("error", "a", "pending")
        self.store.update(enabled=False)
        self.assertIsNone(notifications.next_event())

    def test_retry_after_respected_without_replaying_send(self):
        stop = Mock()
        stop.is_set.side_effect = [False, True]
        api = Mock()
        api.call.side_effect = APIError(429, retry_after=30)
        notifications = Notifications(self.store, api, stop, self.clock)
        notifications.enqueue("error", "a", "test")
        notifications.run()
        stop.wait.assert_called_with(30)
        self.assertEqual(api.call.call_count, 1)

    def test_observer_emits_adb_loss_and_recovery(self):
        service = Service(self.store, self.api, self.bridge, self.clock)
        service.observe_once()
        self.bridge.items["a"]["state"] = "offline"
        service.observe_once()
        self.bridge.items["a"]["state"] = "device"
        service.observe_once()
        self.assertEqual([event["category"] for event in service.controller.notifications.queue], ["adb", "adb"])

    def test_time_limit_uses_existing_stop_and_only_selected_device(self):
        self.bridge.items["a"]["runtime"].update(is_running=True, state="running")
        service = Service(self.store, self.api, self.bridge, self.clock)
        service.controller.limit("a", "minutes", "30")
        self.now += 1801
        service.observe_once()
        self.assertEqual(self.bridge.controls, [("a", "stop", None)])
        self.assertEqual(self.store.snapshot()["limits"], {})

    def test_match_limit_survives_brawler_rotation(self):
        self.bridge.items["a"]["runtime"].update(is_running=True, state="running")
        service = Service(self.store, self.api, self.bridge, self.clock)
        service.controller.limit("a", "matches", "5")
        self.bridge.data["a"].update(completed_matches=3, brawler="Colt")
        service.observe_once()
        self.assertEqual(self.store.snapshot()["limits"]["a"]["remaining"], 2)
        self.bridge.data["a"].update(completed_matches=5)
        service.observe_once()
        self.assertEqual(self.bridge.controls, [("a", "stop", None)])

    def test_disabled_poll_never_contacts_telegram(self):
        self.store.update(enabled=False)
        Service(self.store, self.api, self.bridge, self.clock).poll_once()
        self.assertEqual(self.api.calls, [])


class ManagerTests(Base):
    def sessions(self):
        result = Sessions(":memory:", "ManagerBot", self.clock, allowed_users={11})
        self.addCleanup(result.db.close)
        return result

    def test_creation_authenticates_owner_before_token_handoff(self):
        sessions = self.sessions()
        session = sessions.create()
        url = sessions.link(session["session"], 11)
        self.assertIn("https://t.me/newbot/ManagerBot/xlam_", url)
        with self.assertRaises(SessionError):
            sessions.link(session["session"], 22)
        sessions.attach(11, 123456789, TOKEN)
        with self.assertRaises(SessionError):
            sessions.claim(session["session"], "wrong secret")
        claimed = sessions.claim(session["session"], session["claim_secret"])
        self.assertEqual(claimed["token"], TOKEN)
        self.assertEqual(claimed["owner_id"], 11)
        with self.assertRaises(SessionError):
            sessions.claim(session["session"], session["claim_secret"])

    def test_expired_creation_cannot_be_claimed(self):
        sessions = self.sessions()
        session = sessions.create()
        self.now += 601
        with self.assertRaises(SessionError):
            sessions.claim(session["session"], session["claim_secret"])

    def test_managed_bot_update_uses_official_token_method(self):
        sessions = self.sessions()
        session = sessions.create()
        sessions.link(session["session"], 11)
        Management(sessions, self.api, self.store, self.stop).handle(
            {"managed_bot": {"user": {"id": 11}, "bot": {"id": 987}}})
        self.assertEqual(self.api.calls, [("getManagedBotToken", {"user_id": 987})])
        self.assertTrue(sessions.claim(session["session"], session["claim_secret"])["ready"])

    def test_unrelated_bot_never_requests_token(self):
        Management(self.sessions(), self.api, self.store, self.stop).handle(
            {"managed_bot": {"user": {"id": 22}, "bot": {"id": 987}}})
        self.assertEqual(self.api.calls, [])

    def test_real_local_http_handoff_is_single_use(self):
        from http.server import ThreadingHTTPServer
        sessions = self.sessions()
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(sessions))
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        client = ManagerClient(f"http://127.0.0.1:{server.server_port}")
        created = client.request("/v1/sessions", {})
        sessions.link(created["session"], 11)
        sessions.attach(11, 123456789, TOKEN)
        payload = {key: created[key] for key in ("session", "claim_secret")}
        self.assertEqual(client.request("/v1/claim", payload)["token"], TOKEN)
        with self.assertRaises(ClientSessionError):
            client.request("/v1/claim", payload)

    def test_manager_rejects_unencrypted_remote_handoff(self):
        with self.assertRaises(ClientSessionError):
            ManagerClient("http://manager.example")


class BridgeTests(Base):
    def test_authenticated_handlers_are_used_without_a_live_server(self):
        app = Flask(__name__)
        app.config["UI_API_TOKEN"] = "local-session"
        calls = []
        @app.post("/api/devices/<key>/start")
        def start(key):
            if request.headers.get("X-Xlam-UI-Token") != "local-session":
                return {}, 403
            calls.append((key, request.json))
            return jsonify(ok=True)
        bridge = AppBridge(app)
        bridge.control("a", "start", "127.0.0.1:16384")
        self.assertEqual(calls, [("a", {"serial": "127.0.0.1:16384"})])

    def test_remote_panel_and_credentials_are_rejected(self):
        for url in ("http://example.com", "http://user:secret@127.0.0.1", "http://127.0.0.1/redirect", "http://127.0.0.1?t=secret"):
            with self.subTest(url=url), self.assertRaises(BridgeError):
                LocalBridge(url)

    def test_control_timeout_is_not_replayed(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.URLError("secret details")
        bridge = LocalBridge(opener=opener)
        bridge.token = "ui-session"
        with self.assertRaises(BridgeError) as error:
            bridge.control("a", "start")
        self.assertEqual(opener.open.call_count, 1)
        self.assertNotIn("secret", str(error.exception))

    def test_telegram_network_errors_do_not_expose_token(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.URLError("https://api.telegram.org/bot" + TOKEN)
        api = TelegramAPI(TOKEN, opener)
        with self.assertRaises(APIError) as error:
            api.validate()
        self.assertNotIn(TOKEN, str(error.exception))

    def test_expired_local_ui_token_renews_once(self):
        opener = Mock()
        opener.open.side_effect = [urllib.error.HTTPError("local", 403, "expired", {}, None),
                                  io.BytesIO(b'<html lang="en"><meta name="xlam-ui-token" content="new-token">'),
                                  io.BytesIO(b'{"ok":true}')]
        bridge = LocalBridge(opener=opener)
        bridge.token = "old-token"
        self.assertTrue(bridge.control("a", "start")["ok"])
        self.assertEqual(opener.open.call_count, 3)
        self.assertEqual(bridge.token, "new-token")
        self.assertEqual(bridge.language, "en")

    def test_invalid_telegram_payload_is_a_safe_error(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'[]')
        with self.assertRaises(APIError):
            TelegramAPI(TOKEN, opener).validate()

    def test_regular_startup_registers_service_and_shutdown(self):
        self.owner()
        self.store.put_secret(token=TOKEN)
        app = Flask(__name__)
        with patch("telegram_integration.lifecycle.Service") as factory:
            service = start_optional(app, self.store, configure=lambda store, **kw: store.snapshot(), api_factory=API)
            self.assertIs(service, app.extensions["telegram"])
            app.extensions["telegram_stop"]()
            factory.return_value.stop.set.assert_called_once()

    def test_startup_disabled_has_no_api_or_thread(self):
        app = Flask(__name__)
        factory = Mock()
        result = start_optional(app, self.store, configure=lambda store, **kw: store.snapshot(), api_factory=factory)
        self.assertIsNone(result)
        factory.assert_not_called()
        self.assertNotIn("telegram", app.extensions)

    def test_self_test_skips_console_and_telegram(self):
        app = Flask(__name__)
        configure = Mock(side_effect=AssertionError("must not configure"))
        with patch("sys.argv", ["xlamBOT", "--update-self-test"]):
            self.assertIsNone(start_optional(app, self.store, configure=configure))


class CounterTests(unittest.TestCase):
    def test_result_screen_counted_once_and_play_again_rearms(self):
        now = [0]
        counter = MatchCounter(lambda: now[0])
        counter.observe("match")
        now[0] = 2
        counter.observe("match")
        counter.observe("end_victory")
        counter.observe("end_victory")
        self.assertEqual(counter.completed, 1)
        now[0] = 3
        counter.observe("match")
        now[0] = 5
        counter.observe("match")
        counter.observe("end_trio_showdown_1")
        self.assertEqual(counter.completed, 2)

    def test_result_without_observed_match_and_single_frame_noise_not_counted(self):
        counter = MatchCounter(lambda: 1)
        counter.observe("end_victory")
        counter.observe("match")
        counter.observe("end_victory")
        self.assertEqual(counter.completed, 0)

    def test_returning_to_lobby_does_not_count_an_unrelated_result(self):
        now = [0]
        counter = MatchCounter(lambda: now[0])
        counter.observe("match")
        now[0] = 2
        counter.observe("match")
        counter.observe("lobby")
        counter.observe("end_victory")
        self.assertEqual(counter.completed, 0)


if __name__ == "__main__":
    unittest.main()
