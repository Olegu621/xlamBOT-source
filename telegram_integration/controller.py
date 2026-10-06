"""Owner-only commands and expiring single-use buttons."""
from __future__ import annotations

import collections
import html
import secrets
import threading
import time

from .bridge import BridgeError
from .i18n import tr
from .notifications import Notifications
from .store import CATEGORIES, PRESETS, redact
from .transport import APIError


class Controller:
    def __init__(self, store, api, bridge, stop, clock=time.time):
        self.store, self.api, self.bridge, self.stop, self.clock = store, api, bridge, stop, clock
        self.notifications = Notifications(store, api, stop, clock)
        self.menus = collections.OrderedDict()
        self.actions = collections.deque(maxlen=256)
        self.attempts = {}
        self.observed = {}
        self.control_lock = threading.RLock()

    def language(self):
        value = self.store.snapshot()["language"]
        return getattr(self.bridge, "language", "ru") if value == "auto" else value

    def t(self, key):
        return tr(key, self.language())

    def send(self, text, markup=None):
        payload = {"chat_id": self.store.snapshot()["chat_id"], "text": text[:4000], "parse_mode": "HTML"}
        if markup:
            payload["reply_markup"] = markup
        return self.api.call("sendMessage", **payload)

    def menu(self, screen="main", message_id=None):
        config = self.store.snapshot()
        devices = self.bridge.devices()
        nonce = secrets.token_hex(4)
        self.menus[nonce] = {"until": self.clock() + 600, "device": config["selected"], "choices": {}}
        while len(self.menus) > 64:
            self.menus.popitem(last=False)
        rows = []
        def button(key, action, value="", style=None, label=None):
            result = {"text": label or self.t(key), "callback_data": f"{nonce}:{action}:{value}"}
            if style:
                result["style"] = style
            return result
        chosen = html.escape(config["selected"] or self.t("none"))
        text = f"<b>xlamBOT · Telegram</b>\n📱 {chosen}"
        if screen in ("devices", "filter"):
            for index, (key, device) in enumerate(devices.items()):
                self.menus[nonce]["choices"][str(index)] = key
                label = f"{'🟢' if device.get('state') == 'device' else '🔴'} {key}"
                rows.append([button("devices", "select" if screen == "devices" else "filter", str(index), label=label)])
            if screen == "filter":
                rows.append([button("all", "filter", "all")])
            if not devices:
                text += "\n" + self.t("empty")
        elif screen == "notifications":
            text += "\n<b>" + self.t("notifications") + "</b>"
            for category in CATEGORIES:
                label = ("✅ " if category in config["categories"] else "⬜ ") + self.t(category)
                rows.append([button(category, "toggle", category, label=label)])
            rows += [[button("errors", "preset", "errors"), button("important", "preset", "important")],
                     [button("every", "preset", "all"), button("off", "preset", "off")],
                     [button("filter", "screen", "filter")]]
        elif screen == "settings":
            rows = [[button("language", "lang", "ru", label="🇷🇺 Русский"), button("language", "lang", "en", label="🇬🇧 English")],
                    [button("auto", "lang", "auto")],
                    [button("quiet", "quiet", label=f"{'✅' if config['quiet_enabled'] else '⬜'} {self.t('quiet')} {config['quiet_start']}–{config['quiet_end']}")],
                    [button("critical", "critical", label=f"{'✅' if config['critical_at_night'] else '⬜'} {self.t('critical')}")],
                    [button("summary_interval", "interval", str(n), label=f"{n} min") for n in (15, 30, 60)],
                    [button("limit_time", "minutes", str(n), label=f"⏱ {n} min") for n in (30, 60, 120)],
                    [button("limit_match", "matches", str(n), label=f"🎮 {n}") for n in (5, 10, 20)],
                    [button("clear_limit", "clear")], [button("diagnostics", "diagnostics"), button("test", "test")],
                    [button("disable", "confirm", "disable", "danger"), button("unlink", "confirm", "unlink", "danger")]]
            text += f"\n{self.t('summary_interval')}: {config['summary_minutes']}\n{self.t('limit_time')} / {self.t('limit_match')}"
        elif screen.startswith("confirm-"):
            action = screen.removeprefix("confirm-")
            text += "\n" + (self.t("confirm") if action == "stop_all" else self.t(action))
            rows = [[button("yes", "confirmed", action, "danger"), button("cancel", "screen", "main")]]
        else:
            rows = [[button("play", "start", style="success"), button("resume", "resume", style="success")],
                    [button("pause", "pause"), button("stop", "stop", style="danger")],
                    [button("status", "status"), button("devices", "screen", "devices")],
                    [button("photo", "photo"), button("notifications", "screen", "notifications")],
                    [button("settings", "screen", "settings"), button("help", "help")],
                    [button("stop_all", "confirm", "stop_all", "danger")]]
        if screen != "main":
            rows.append([button("back", "screen", "main")])
        markup = {"inline_keyboard": rows}
        if message_id:
            return self.api.call("editMessageText", chat_id=config["chat_id"], message_id=message_id,
                                 text=text[:4000], parse_mode="HTML", reply_markup=markup)
        return self.send(text, markup)

    def handle(self, update):
        with self.control_lock:
            self._handle(update)

    def _handle(self, update):
        config = self.store.snapshot()
        if not config["enabled"]:
            return
        callback = update.get("callback_query")
        message = callback.get("message", {}) if callback else update.get("message", {})
        sender = callback.get("from", {}) if callback else message.get("from", {})
        user_id, chat_id = sender.get("id"), message.get("chat", {}).get("id")
        if not user_id or message.get("chat", {}).get("type") != "private":
            return
        text = message.get("text", "")
        if not callback and text.startswith("/start ") and config["chat_id"] is None:
            now = self.clock()
            attempts = [at for at in self.attempts.get(user_id, []) if now - at < 300]
            if len(attempts) >= 5:
                return
            attempts.append(now)
            self.attempts[user_id] = attempts
            if len(self.attempts) > 256:
                self.attempts.clear()
            if self.store.bind(text.split(maxsplit=1)[1], user_id, chat_id, now):
                self.send(self.t("bound"))
                self.menu()
            return
        if user_id != config["owner_id"] or chat_id != config["chat_id"]:
            return
        try:
            if callback:
                self.api.call("answerCallbackQuery", callback_query_id=callback["id"])
                if callback["id"] in self.actions:
                    return
                self.actions.append(callback["id"])
                self.callback(callback)
            else:
                command = text.split(maxsplit=1)[0].split("@")[0] if text else ""
                if command in ("/start", "/menu"):
                    self.menu()
                elif command == "/play":
                    self.perform("start", config["selected"])
                    self.menu()
                elif command == "/status":
                    self.send(self.summary(config["selected"]))
                elif command in ("/devices", "/settings"):
                    self.menu(command[1:])
                elif command == "/help":
                    self.send(self.t("help_text"))
        except BridgeError:
            self.send(self.t("unavailable"))

    def callback(self, callback):
        parts = callback.get("data", "").split(":", 2)
        if len(parts) != 3:
            return
        nonce, action, value = parts
        menu = self.menus.get(nonce)
        config = self.store.snapshot()
        if not menu or self.clock() >= menu["until"] or menu["device"] != config["selected"]:
            self.send(self.t("stale"))
            return
        # Every button is single-use, including controls and confirmation buttons.
        del self.menus[nonce]
        screen, key = "main", menu["device"]
        if action == "screen" and value in ("main", "devices", "notifications", "settings", "filter"):
            screen = value
        elif action in ("select", "filter"):
            selected = menu["choices"].get(value)
            if action == "select" and selected in self.bridge.devices():
                self.store.update(selected=selected)
            elif action == "filter" and (selected is not None or value == "all"):
                self.store.update(device_filter=selected if selected is not None else "all")
            screen = "main" if action == "select" else "notifications"
        elif action in ("start", "pause", "resume", "stop"):
            self.perform(action, key)
        elif action == "confirm" and value in ("stop_all", "disable", "unlink"):
            screen = "confirm-" + value
        elif action == "confirmed":
            # Require a confirmation menu, not a forged 'confirmed' action on a main menu.
            if menu.get("confirmation") != value:
                self.send(self.t("stale"))
                return
            if value == "stop_all":
                self.bridge.stop_all()
                self.send(self.t("done"))
            elif value in ("disable", "unlink"):
                self.send(self.t("disabled"))
                self.store.unlink() if value == "unlink" else self.store.update(enabled=False)
                self.stop.set()
                return
        elif action == "toggle" and value in CATEGORIES:
            categories = set(config["categories"])
            categories.symmetric_difference_update({value})
            self.store.update(categories=sorted(categories))
            screen = "notifications"
        elif action == "preset" and value in PRESETS:
            self.store.update(categories=sorted(PRESETS[value]))
            screen = "notifications"
        elif action == "lang" and value in ("ru", "en", "auto"):
            self.store.update(language=value)
            screen = "settings"
        elif action in ("quiet", "critical", "interval"):
            if action == "quiet":
                self.store.update(quiet_enabled=not config["quiet_enabled"])
            elif action == "critical":
                self.store.update(critical_at_night=not config["critical_at_night"])
            elif value in ("15", "30", "60"):
                self.store.update(summary_minutes=int(value))
            screen = "settings"
        elif action in ("minutes", "matches", "clear"):
            self.limit(key, action, value)
            screen = "settings"
        elif action == "status":
            self.send(self.summary(key))
        elif action == "photo":
            if key not in self.bridge.devices():
                raise BridgeError("Device unavailable")
            self.api.photo(config["chat_id"], self.bridge.screenshot(key), key)
        elif action == "test":
            self.send(self.t("test_ok"))
        elif action == "help":
            self.send(self.t("help_text"))
        elif action == "diagnostics":
            device = self.bridge.devices().get(key, {})
            runtime = device.get("runtime", {})
            self.send(html.escape(f"{key or '—'}\nADB: {device.get('state', '—')}\n{self.t('state')}: {runtime.get('state', '—')}\n{self.t('last_error')}: {redact(runtime.get('last_error') or '—')}"))
        self.menu(screen, callback["message"].get("message_id"))
        if screen.startswith("confirm-"):
            last = next(reversed(self.menus))
            self.menus[last]["confirmation"] = screen.removeprefix("confirm-")

    def perform(self, action, key):
        devices = self.bridge.devices()
        if key not in devices:
            raise BridgeError("Selected device unavailable")
        state = devices[key].get("runtime", {}).get("state", "idle")
        valid = {"start": {"idle", "error"}, "resume": {"paused", "pausing"},
                 "pause": {"running"}, "stop": {"running", "paused", "pausing", "starting"}}
        if state not in valid[action] or (action in ("start", "resume") and devices[key].get("state") != "device"):
            raise BridgeError("Control no longer valid for this state")
        self.bridge.control(key, action, devices[key].get("serial"))
        self.send(self.t("done") + " · " + html.escape(key))

    def summary(self, key):
        devices = self.bridge.devices()
        lines = ["<b>xlamBOT</b>"]
        for name, device in devices.items():
            if key and name != key:
                continue
            runtime = device.get("runtime", {})
            try:
                telemetry = self.bridge.telemetry(name)
            except BridgeError:
                telemetry = {}
            lines.append("\n📱 " + html.escape(name))
            values = [("state", runtime.get("state")), ("uptime", runtime.get("uptime_seconds")),
                      ("brawler_name", telemetry.get("brawler")), ("trophies_value", telemetry.get("trophies")),
                      ("account", telemetry.get("account_total")), ("counter", telemetry.get("games_on_brawler")),
                      ("matches_value", telemetry.get("completed_matches")), ("last_error", runtime.get("last_error") or None)]
            lines.append("ADB: " + html.escape(device.get("state", "—")))
            for label, value in values:
                value = round(value) if isinstance(value, float) else value
                lines.append(self.t(label) + ": " + html.escape(redact(value if value is not None else "—")))
        return "\n".join(lines)[:4000]

    def limit(self, key, action, value):
        device = self.bridge.devices().get(key)
        if not device:
            raise BridgeError("Device unavailable")
        if action != "clear" and not device.get("runtime", {}).get("is_running"):
            raise BridgeError("Start this device before setting a limit")
        limits = self.store.snapshot()["limits"]
        if action == "clear":
            limits.pop(key, None)
        elif action == "minutes" and value in ("30", "60", "120"):
            limits[key] = {"deadline": self.clock() + int(value) * 60}
        elif action == "matches" and value in ("5", "10", "20"):
            telemetry = self.bridge.telemetry(key)
            counter = telemetry.get("completed_matches")
            if type(counter) is not int:
                self.send(self.t("limit_missing"))
                return
            limits[key] = {"remaining": int(value), "counter": counter,
                           "session": device.get("runtime", {}).get("started_at")}
        else:
            return
        self.store.update(limits=limits)
        self.send(self.t("limit_saved"))
