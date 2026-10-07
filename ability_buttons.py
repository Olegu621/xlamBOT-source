"""Locate a charged circular ability button near its configured position."""
import math
import cv2
import numpy as np

# Small control crops are slower with dozens of OpenCV worker threads. This
# process hosts several devices; detector GPU execution uses its own runtime.
cv2.setNumThreads(1)

BOUNDS = {'super': ((17, 170, 190), (35, 255, 255)),
          'gadget': ((38, 170, 160), (85, 255, 255)),
          'hypercharge': ((130, 150, 160), (175, 255, 255))}


def ready_button(frame, ability, configured):
    if frame is None or ability not in BOUNDS:
        return None
    h, w = frame.shape[:2]
    x, y = configured[0]*w/1920, configured[1]*h/1080
    radius = min(w/1920, h/1080)*100
    left, top = max(int(x-radius), int(w*.6)), max(int(y-radius), int(h*.62))
    right, bottom = min(w, int(x+radius)), min(h, int(y+radius))
    crop = frame[top:bottom, left:right]
    if not crop.size:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, *BOUNDS[ability])
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    scale = min(w/1920, h/1080)
    circles = cv2.HoughCircles(cv2.GaussianBlur(gray,(5,5),0), cv2.HOUGH_GRADIENT,
        1, max(15,45*scale), param1=100,param2=28,
        minRadius=max(8,int(30*scale)),maxRadius=max(12,int(78*scale)))
    if circles is None:
        return None
    yy,xx = np.ogrid[:crop.shape[0],:crop.shape[1]]
    candidates = []
    for cx,cy,radius in circles[0]:
        inner = (xx-cx)**2+(yy-cy)**2 < (radius*.82)**2
        ring = ((xx-cx)**2+(yy-cy)**2 > (radius*.94)**2) & \
               ((xx-cx)**2+(yy-cy)**2 < (radius*1.1)**2)
        if not inner.any() or not ring.any():
            continue
        # A saturated patch of map terrain is not a charged round control.
        if np.mean(mask[inner]>0)<.27 or np.mean(hsv[:,:,2][ring]<105)<.3:
            continue
        px,py = left+float(cx),top+float(cy)
        candidates.append((math.hypot(px-x,py-y),(px,py)))
    return min(candidates)[1] if candidates else None



class AbilityButtons:
    def __init__(self):
        self.last_used = {}
        self.observed = {}
        self.confirmed = {}
        self.ready = {}
        self.last_observed = -100.

    def observe(self, frame, points, now):
        if now-self.last_observed < .12:
            return
        self.last_observed = now
        for ability in BOUNDS:
            point = ready_button(frame, ability, points[ability])
            previous = self.observed.get(ability)
            # Two different fresh frames, and a short confirmation interval.
            stable = point is not None and previous is not None \
                and math.hypot(point[0]-previous[0][0], point[1]-previous[0][1]) < 12
            if not stable:
                self.confirmed[ability] = now
            self.observed[ability] = (point,now) if point else None
            self.ready[ability] = point if stable and now-self.confirmed.get(ability,now)>=.08 \
                and now-self.last_used.get(ability,-100)>=1.2 else None

    def consume(self, ability, now):
        point = self.ready.get(ability)
        if point is None or now-self.last_observed > .3:
            return None
        self.ready[ability] = None
        self.last_used[ability] = now
        return point
