"""Filtered, coalesced, expiring alerts. Monitoring never runs in the game loop."""
from collections import deque
from datetime import datetime
import threading
import time

from .store import redact
from .transport import APIError


def quiet_now(config, when=None):
    if not config.get("quiet_enabled"):
        return False
    when = when or datetime.now().astimezone()
    current = when.hour * 60 + when.minute
    def minutes(value):
        hour, minute = map(int, value.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError("Invalid quiet hours")
        return hour * 60 + minute
    start, end = minutes(config["quiet_start"]), minutes(config["quiet_end"])
    return start <= current < end if start < end else (current >= start or current < end) if start != end else False


class Notifications:
    def __init__(self, store, api, stop, clock=time.time):
        self.store, self.api, self.stop, self.clock = store, api, stop, clock
        self.queue = deque(maxlen=50)
        self.lock = threading.Lock()
        self.seen = {}

    def allowed(self, event, when=None):
        config = self.store.snapshot()
        if not config["enabled"] or config["chat_id"] is None or event["category"] not in config["categories"]:
            return False
        if config["device_filter"] != "all" and event["device"] not in (None, config["device_filter"]):
            return False
        return not quiet_now(config, when) or (event["critical"] and config["critical_at_night"])

    def enqueue(self, category, device, text, critical=False):
        now = self.clock()
        event = {"category": category, "device": device, "text": redact(text), "critical": critical, "at": now}
        if not self.allowed(event):
            return
        identity = (category, device, event["text"])
        with self.lock:
            self.seen = {key: at for key, at in self.seen.items() if now - at < 60}
            if identity in self.seen:
                return
            self.seen[identity] = now
            self.queue.append(event)

    def next_event(self):
        with self.lock:
            while self.queue:
                event = self.queue.popleft()
                if self.clock() - event["at"] <= 120 and self.allowed(event):
                    return event
        return None

    def run(self):
        delay = 1
        while not self.stop.is_set():
            event = self.next_event()
            if event is None:
                self.stop.wait(0.5)
                continue
            try:
                self.api.call("sendMessage", chat_id=self.store.snapshot()["chat_id"], text=event["text"])
                delay = 1
                self.stop.wait(1)
            except APIError as error:
                if error.code in (401, 403):
                    self.store.update(enabled=False)
                    return
                # A failed send may have reached Telegram. Do not replay it blindly.
                delay = min(delay * 2, 60)
                self.stop.wait(max(delay, error.retry_after))
