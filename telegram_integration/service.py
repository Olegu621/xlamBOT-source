"""Independent polling, observation and notification workers."""
import threading
import time

from .bridge import BridgeError
from .controller import Controller
from .store import redact
from .transport import APIError


class Service:
    def __init__(self, store, api, bridge, clock=time.time):
        self.store, self.api, self.bridge, self.clock = store, api, bridge, clock
        self.stop = threading.Event()
        self.controller = Controller(store, api, bridge, self.stop, clock)
        self.previous = {}
        self.update_previous = None
        self.panel_online = None
        self.last_summary = clock()

    def emit(self, category, key, detail, critical=False):
        controller = self.controller
        text = f"xlamBOT · {controller.t(category)}\n{key or 'xlamBOT'}\n{redact(detail)}"
        controller.notifications.enqueue(category, key, text, critical)

    def observe_once(self):
        now = self.clock()
        devices = self.bridge.devices()
        if self.panel_online is False:
            self.emit("error", None, self.controller.t("panel_restored"))
        self.panel_online = True
        for key, device in devices.items():
            runtime = device.get("runtime", {})
            try:
                telemetry = self.bridge.telemetry(key)
            except BridgeError:
                telemetry = {}
            current = {**runtime, **telemetry, "adb": device.get("state", "offline")}
            previous = self.previous.get(key)
            if previous is not None:
                for field, category in (("state", "lifecycle"), ("adb", "adb"),
                                        ("brawler", "brawler"), ("account_total", "trophies")):
                    value, old = current.get(field), previous.get(field)
                    if value is not None and value != old and (old is not None or field == "adb"):
                        self.emit(category, key, f"{old if old is not None else '—'} → {value}",
                                  field == "adb" and value != "device")
                error = current.get("last_error")
                if error and error != previous.get("last_error"):
                    self.emit("error", key, error, True)
                game = current.get("detected_state")
                if game != previous.get("detected_state") and game in {"login_failure", "idle_disconnect", "network_error"}:
                    self.emit("game", key, game, True)
                if current.get("queue_length") == 0 and (previous.get("queue_length") or 0) > 0:
                    self.emit("queue", key, self.controller.t("queue"))
                counter, old = current.get("completed_matches"), previous.get("completed_matches")
                if (type(counter) is int and type(old) is int
                        and current.get("started_at") == previous.get("started_at")):
                    delta = max(0, counter - old)
                    if delta:
                        self.controller.observed[key] = self.controller.observed.get(key, 0) + delta
                        self.emit("match", key, f"+{delta} · {current.get('last_match_result') or '—'}")
            if type(current.get("completed_matches")) is int:
                self.controller.observed.setdefault(key, 0)
            self.previous[key] = current
            self.check_limit(key, current, now)
        try:
            update = self.bridge.request("/api/updates/status")
            signature = (update.get("state"), update.get("revision"), update.get("available"))
            if self.update_previous is not None and signature != self.update_previous:
                self.emit("update", None, update.get("message") or str(signature), update.get("state") == "error")
            self.update_previous = signature
        except BridgeError:
            pass
        config = self.store.snapshot()
        if now - self.last_summary >= config["summary_minutes"] * 60:
            key = None if config["device_filter"] == "all" else config["device_filter"]
            # Convert generated HTML to readable text before sendMessage without parse_mode.
            import html
            import re
            text = html.unescape(re.sub(r"</?b>", "", self.controller.summary(key)))
            self.controller.notifications.enqueue("summary", key, text)
            self.last_summary = now

    def check_limit(self, key, current, now):
        with self.controller.control_lock:
            self._check_limit(key, current, now)

    def _check_limit(self, key, current, now):
        limits = self.store.snapshot()["limits"]
        limit = limits.get(key)
        if not limit:
            return
        if not current.get("is_running") and current.get("state") not in {"starting", "stopping"}:
            limits.pop(key)
            self.store.update(limits=limits)
            return
        due = bool(limit.get("deadline") and now >= limit["deadline"])
        counter = current.get("completed_matches")
        if "remaining" in limit and type(counter) is int:
            old = limit["counter"]
            delta = max(0, counter - old) if current.get("started_at") == limit["session"] else 0
            if delta or counter != old or current.get("started_at") != limit["session"]:
                limit.update(remaining=max(0, limit["remaining"] - delta), counter=counter, session=current.get("started_at"))
                self.store.update(limits=limits)
            due = limit["remaining"] == 0
        if due:
            self.bridge.control(key, "stop")
            limits.pop(key)
            self.store.update(limits=limits)
            self.emit("lifecycle", key, self.controller.t("limit_reached"))

    def monitor(self):
        while not self.stop.is_set() and self.store.snapshot()["enabled"]:
            try:
                self.observe_once()
            except BridgeError:
                if self.panel_online is not False:
                    self.emit("error", None, self.controller.t("panel_lost"), True)
                self.panel_online = False
            except Exception:
                # Do not log exception text: downstream responses may contain secrets.
                self.emit("error", None, "Observer failure", True)
            self.stop.wait(5)

    def poll_once(self):
        config = self.store.snapshot()
        if not config["enabled"]:
            return
        updates = self.api.call("getUpdates", offset=config["offset"], timeout=20,
                                allowed_updates=["message", "callback_query"])
        for update in updates:
            if update.get("update_id", -1) < self.store.snapshot()["offset"]:
                continue
            # At-most-once controls across restarts: persist acknowledgement before execution.
            self.store.update(offset=update["update_id"] + 1)
            self.controller.handle(update)

    def run(self):
        if not self.store.snapshot()["enabled"]:
            return
        threads = [threading.Thread(target=target, daemon=True, name="telegram-" + name)
                   for target, name in ((self.monitor, "monitor"), (self.controller.notifications.run, "sender"))]
        for thread in threads:
            thread.start()
        delay = 1
        try:
            while not self.stop.is_set() and self.store.snapshot()["enabled"]:
                try:
                    self.poll_once()
                    delay = 1
                except APIError as error:
                    if error.code in (401, 409):
                        self.store.update(enabled=False)
                        break
                    delay = min(delay * 2, 60)
                    self.stop.wait(max(delay, error.retry_after))
                except (BridgeError, ValueError, KeyError):
                    self.stop.wait(1)
        finally:
            self.stop.set()
            for thread in threads:
                thread.join(timeout=1)
