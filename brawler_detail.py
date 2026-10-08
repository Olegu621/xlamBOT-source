"""Language-independent controls on a brawler detail screen.

Only anonymous game glyphs are embedded; account frames are never packaged.
Coordinates come from matching the current frame, not a cached classification.
"""
import base64
from functools import lru_cache
import cv2
import numpy as np

HEALTH = 'iVBORw0KGgoAAAANSUhEUgAAACEAAAAfCAIAAADm9jPlAAADcUlEQVRIDbXBXUhbZxwH4N//fDUzJDF7bTFRujJqaWiRWjIZ22R44ejCijUo7sJ1GcLA1K4KpYo3bZGVyaBzvZFdjNFJEbLUzsF0BTcGXgjd20ht2XZRxZmZSG2yaK35MDmZDWSk01i3njwPgaPQCByFRuAoNAJHoRE4NpNIqlAqdsu7RRKXU8tziblwMoynvZmo++aVayVSiaqqAERBBOD9y3vGfyawHkAOAse/nLecP1d6rkgoQlYynZx8PHn2z7O3Ht8CYJWtNytuHn7hMPJwzbmuhq4ii8DxD4tkuW27bVEsyGNseey0/7TP5jOKRmzr5NzJwdAgMggcT6hAAiuvrhhEA7alQhUg4FnW1DX9lB4ZBI4nVFx/+bqTOaGdC4ELF4MXARA4NpTKpcHKIDR1N3q38tdKAASODScMJ24cuAFNJdNJ2ScDIHAgjcH5wRZnC7Rm+MEgR2UCByVoaH6oubkZmlqKL9m+swEgcOz7el+LsaW3txeamlyaPP7zcQAEjiMfHdlbsndkZASauvzb5Uv3LgEgcBz98KgkSRMTE4qiQDvV31fPrs0CIHDs/2y/6XdTW1tba2srNDK7Ols9Vo0MAof+vv7gpwfNZvPo6Kgsy9DCsS+O8Rc5MggcUGFvt0OFy+Vyu91EhOczNTVVd78OWQQOpGH7xKb/Qw9gYGDAbrfjOfj9fkebI/h+EFkEDlJJt6A79PEhAEQ0PDxcXl6O/2VxcbGhoWGmfUZVVGRR8bfFYkIEYP7RbPKZoEIQhL6+vtraWvxH8/PzTqcz8lokUhNBDmIehgxSqezLMiksIcPhcPT09Oh0OuzM+Ph4d3d3qiLld/rxNGIehiwhKli/soorIgAi0ul0HR0djY2N2FYoFOrq6rozfSdeEg98EMAmxDwMOYSEYL1mFRaFDchgjLnd7vr6emzF6/X29/fHYrH1l9YX3l3AVoh5GDYx/WIy/2RGDkVRmpqaOjs7kZVOp2tqamKxGICHbzxcfX0VeRDzMGxFSAh7hvYoAUUQBOSoqqo61X7qyudXpqenQUjpUsH3gklzEvkR8zDkp0SU4vHiopkiZImiiIxUKvWo6lHorRCehZiHYXsqpIhk9BkNPgOlSRRFANHy6IO3HyRNSewAMQ/DztA67QrsMo+Zw++E42VxEHaImIehwP4GhwAyMxXgKZwAAAAASUVORK5CYII='
HANGER = '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'
HOME = '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'

@lru_cache(maxsize=16)
def _glyph(encoded, height):
    raw = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), np.uint8), 1)
    raw = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
    return cv2.resize(raw, (max(1, round(raw.shape[1]*height/720)),
                            max(1, round(raw.shape[0]*height/720))))


def _locate(frame, encoded, bounds):
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = bounds
    left, top = round(width*x1), round(height*y1)
    crop = frame[top:round(height*y2), left:round(width*x2)]
    template = _glyph(encoded, height)
    if not crop.size or any(crop.shape[i] < template.shape[i] for i in (0, 1)):
        return None
    _, score, _, loc = cv2.minMaxLoc(cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED))
    if score < .89:
        return None
    return (left+loc[0]+template.shape[1]//2, top+loc[1]+template.shape[0]//2)


def detail_home_position(frame):
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
        return None
    if not (_locate(frame, HEALTH, (.68, .40, 1, .78))
            and _locate(frame, HANGER, (.10, .70, .30, .86))):
        return None
    return _locate(frame, HOME, (.86, 0, 1, .13))


def detail_select_position(frame):
    if detail_home_position(frame) is None:
        return None
    height, width = frame.shape[:2]
    left, top = 0, round(height*.84)
    crop = frame[top:round(height*.98), :round(width*.30)]
    # The Select control is yellow in both supported languages. Try and
    # Upgrade controls are outside this region and cannot authorize this tap.
    r, g, b = cv2.split(crop)
    mask = ((r > 190) & (g > 135) & (b < 65)).astype(np.uint8)
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    for x, y, w, h, area in sorted(stats[1:], key=lambda row: row[4], reverse=True):
        if w > width*.16 and h > height*.045 and area > width*height*.008:
            return (left+int(x+w//2), top+int(y+h//2))
    return None
