"""Ordered per-device observations and immutable command preconditions."""
from dataclasses import dataclass
import threading
import time
import math


@dataclass(frozen=True)
class Observation:
    state: str
    frame_time: float
    epoch: int


class Observations:
    def __init__(self, max_age=1.0):
        self.lock = threading.RLock()
        self.max_age = max_age
        self.current = Observation('unknown', 0.0, 0)

    def publish(self, state, frame_time):
        with self.lock:
            if not isinstance(state, str) or not state or not math.isfinite(frame_time):
                return False
            old = self.current
            if frame_time <= old.frame_time:
                return False
            self.current = Observation(state, frame_time, old.epoch + (state != old.state))
            return True

    def snapshot(self):
        with self.lock:
            return self.current

    def permits(self, expected, now=None):
        with self.lock:
            current = self.current
            age = (time.time() if now is None else now) - current.frame_time
            return current.epoch == expected.epoch and current.state == expected.state and 0 <= age <= self.max_age
