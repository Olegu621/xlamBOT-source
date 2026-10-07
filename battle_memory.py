"""Small, per-match memory. Camera motion must not look like ally movement."""
import math
from collections import deque
from statistics import median


def position(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class BattleMemory:
    def __init__(self):
        self.reset()

    def reset(self):
        self.offset = (0., 0.)
        self.walls = []
        self.tracks = []
        self.dangers = deque(maxlen=32)
        self.paths = deque(maxlen=64)
        self.updated = None
        self.camera_valid = False
        self.progress_anchor = None
        self.progress_time = None
        self.idle_count = 0

    def world(self, point):
        return (point[0] + self.offset[0], point[1] + self.offset[1])

    def update(self, data, now, tile, fresh_walls=True):
        if self.updated is not None and now - self.updated > 1.5:
            self.reset()  # pause, respawn, missing player or a new map
        if not fresh_walls:
            return
        walls = data.get('wall', [])[:60]
        shifts = []
        for old in self.walls:
            candidates = [b for b in walls
                          if abs((b[2]-b[0])-(old[2]-old[0])) < tile*.3
                          and abs((b[3]-b[1])-(old[3]-old[1])) < tile*.3]
            if candidates:
                a = position(old)
                b = position(min(candidates, key=lambda b: distance(a, position(b))))
                if distance(a, b) < tile*.55:
                    shifts.append((b[0]-a[0], b[1]-a[1]))
        valid = False
        if len(shifts) >= 4:
            dx, dy = median(s[0] for s in shifts), median(s[1] for s in shifts)
            support = sum(distance(s, (dx, dy)) < tile*.16 for s in shifts)
            valid = support >= 4 and support >= len(shifts)*.7
            if valid:
                self.offset = (self.offset[0]-dx, self.offset[1]-dy)
        if self.updated is not None and not valid:
            self.tracks.clear()
            self.dangers.clear()
            self.paths.clear()
            self.progress_anchor = None
            self.progress_time = now
        self.walls = [list(b[:4]) for b in walls]
        self.camera_valid = valid
        self.updated = now
        player = self.world(position(data['player'][0]))
        if self.progress_anchor is None or distance(player, self.progress_anchor) > tile*.3:
            self.progress_anchor, self.progress_time = player, now
        enemies = [self.world(position(b)) for b in data.get('enemy', [])]
        self.tracks = [t for t in self.tracks if now-t['seen'] < 1.5]
        used = set()
        for box in data.get('teammate', []):
            p = self.world(position(box))
            choices = [(distance(p, t['pos']), i) for i, t in enumerate(self.tracks) if i not in used]
            best = min(choices, default=(float('inf'), -1))
            if best[0] < tile*1.8:
                i = best[1]
                track = self.tracks[i]
                old = track['pos']
                if valid and distance(p, track['anchor']) > tile*.6:
                    track['anchor'], track['moved'], track['idle'] = p, now, False
                    if distance(p, old) > tile*.12:
                        self.paths.append((old, p, now))
                # A stationary defender in an active fight is not an autoclicker.
                if any(distance(p, enemy) < tile*5 for enemy in enemies):
                    track['moved'] = now
                if valid and now-track['moved'] >= 10:
                    track['idle'] = True
                track.update(pos=p, seen=now)
            else:
                self.tracks.append(dict(pos=p, anchor=p, moved=now, seen=now, idle=False))
                i = len(self.tracks)-1
            used.add(i)
        self.idle_count = sum(t['idle'] for t in self.tracks)
        self.paths = deque((p for p in self.paths if now-p[2] < 8), maxlen=64)
        self.dangers = deque((d for d in self.dangers if now-d[1] < 12), maxlen=32)
        for enemy in enemies:
            count = sum(distance(enemy, e) < tile*3 for e in enemies)
            if count >= 2:
                nearby = next((i for i,d in enumerate(self.dangers) if distance(d[0], enemy)<tile), None)
                if nearby is None:
                    self.dangers.append((enemy, now, count))
                else:
                    self.dangers[nearby] = (enemy, now, count)

    def active_allies(self, boxes, now, tile):
        if not self.camera_valid or self.updated is None or now-self.updated > .6:
            return boxes
        return [b for b in boxes if not any(t['idle'] and now-t['seen']<1.5
                    and distance(self.world(position(b)), t['pos'])<tile*.8 for t in self.tracks)]

    def stalled(self, now, delay):
        return self.camera_valid and self.updated is not None and now-self.updated < .6 \
            and self.progress_time is not None and now-self.progress_time > delay

    def score(self, start, step, allies, now, tile):
        if not self.camera_valid or self.updated is None or now-self.updated > .6:
            return 0.
        a = self.world(start)
        target = (a[0]+step[0]*tile*2, a[1]+step[1]*tile*2)
        support = sum(distance(a, self.world(position(b))) < tile*5 for b in allies)
        risk = 0.
        for p, stamp, count in self.dangers:
            if distance(target,p) < distance(a,p) and distance(target,p) < tile*5:
                risk += max(0., 1-(now-stamp)/12)*min(count,4)*(1. if support<2 else .15)
        # Recently traversed ground is only a preference, never permission to
        # ignore a current wall or walk into gas.
        walked = any(distance(target,p[1])<tile for p in self.paths)
        return risk - (.15 if walked else 0.)


class Steering:
    def __init__(self):
        self.previous = None
        self.changed = 0.

    def choose(self, vector, now, safe):
        if vector is None or math.hypot(*vector) < 1e-6:
            self.previous = None
            return vector
        previous = self.previous
        if previous and safe(previous):
            dot = sum(a*b for a,b in zip(previous,vector))/(math.hypot(*previous)*math.hypot(*vector))
            # Ignore small detection jitter; hold reversals briefly, not forever.
            if dot > math.cos(math.radians(16)) or now-self.changed < .22:
                return previous
        self.previous, self.changed = vector, now
        return vector
