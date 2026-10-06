"""Count recognized result screens once, including play-again without a lobby."""
import time


class MatchCounter:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.match_since = None
        self.armed = False
        self.completed = 0
        self.last_result = None

    def observe(self, state):
        now = self.clock()
        if state == "match":
            if self.match_since is None:
                self.match_since = now
            if now - self.match_since >= 1:
                self.armed = True
        elif state and state.startswith("end_"):
            if self.armed:
                self.completed += 1
                self.last_result = state.removeprefix("end_")
                self.armed = False
            self.match_since = None
        elif state in {"lobby", "match_making"}:
            self.match_since = None
            self.armed = False

    def snapshot(self):
        return {"completed_matches": self.completed, "last_match_result": self.last_result}
