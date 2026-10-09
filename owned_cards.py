"""Locate the owned-card trophy badge when the unlock tile shifts the grid."""
import base64
from functools import lru_cache
import cv2
import numpy as np

BADGE = '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'

@lru_cache(maxsize=12)
def _badge(height):
    raw = cv2.imdecode(np.frombuffer(base64.b64decode(BADGE), np.uint8), 0)
    return cv2.resize(raw, (max(2, round(raw.shape[1]*height/720)),
                            max(2, round(raw.shape[0]*height/720))))


def _rank_card_anchors(frame):
    h,w = frame.shape[:2]
    scale = h/720
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
    purple = cv2.inRange(hsv, (130,90,85), (172,255,255))
    purple[:round(h*.14)] = 0
    count,_,stats,centers = cv2.connectedComponentsWithStats(purple)
    anchors = []
    for i in range(1,count):
        x,y,bw,bh,area = stats[i]
        if not (35*scale <= bw <= 65*scale and 35*scale <= bh <= 65*scale
                and .75 <= bw/bh <= 1.3 and area >= bw*bh*.35):
            continue
        if np.mean(np.all(frame[y:y+bh,x:x+bw] > 180,axis=2)) < .015:
            continue
        cx,cy = centers[i]
        ax,ay = round(cx-245*scale),round(cy+135*scale)
        radius = max(2,round(18*scale))
        if ax-radius < 0 or ay-radius < 0 or ax+radius >= w or ay+radius >= h:
            continue
        shield = hsv[ay-radius:ay+radius,ax-radius:ax+radius]
        bronze = cv2.inRange(shield,(8,90,100),(38,255,255))
        if np.mean(bronze > 0) >= .12:
            anchors.append((ax,ay))
    return anchors


def first_owned_card(frame):
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
        return None
    h,w = frame.shape[:2]
    top = round(h*.18)
    crop = cv2.cvtColor(frame[top:round(h*.94)], cv2.COLOR_RGB2GRAY)
    glyph = _badge(h)
    if any(crop.shape[i] < glyph.shape[i] for i in (0,1)):
        return None
    scores = cv2.matchTemplate(crop, glyph, cv2.TM_CCOEFF_NORMED)
    ys,xs = np.where(scores >= .91)
    candidates = [(int(x)+glyph.shape[1]//2,top+int(y)+glyph.shape[0]//2)
                  for x,y in zip(xs,ys)]
    # Zero-trophy owned cards use a bronze rank shield instead of the cup.
    # Require both the numbered power badge and its separate rank shield.
    candidates.extend(_rank_card_anchors(frame))
    if not candidates:
        return None
    row = min(y for x,y in candidates)
    return min((x,y) for x,y in candidates if y <= row+round(h*.025))


def resolved_card(frame, configured):
    anchor = first_owned_card(frame)
    if anchor is None:
        return configured, None
    h,w = frame.shape[:2]
    scale = h/720
    px,py = configured[0]*w/1920,configured[1]*h/1080
    # Keep a user's calibrated point if it lies on the confirmed first card.
    if anchor[0]-20*scale <= px <= anchor[0]+270*scale and anchor[1]-155*scale <= py <= anchor[1]+15*scale:
        return configured, None
    return (anchor[0]*1920/w,anchor[1]*1080/h), anchor


def reading_regions(frame, anchor):
    h,w = frame.shape[:2];s=h/720;x,y=anchor
    def region(dx,dy,width,height):
        return ((x+dx*s)*1920/w,(y+dy*s)*1080/h,width*s*1920/w,height*s*1080/h)
    return region(35,-40,190,34),region(12,-16,90,32)
