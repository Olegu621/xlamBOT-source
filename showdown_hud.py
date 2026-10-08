"""Recognize the stable Showdown caption without its animated map background."""
import base64
from functools import lru_cache
import cv2
import numpy as np

# Anonymous lower glyphs of "Teams left:"; FPS overlay and changing count excluded.
CAPTION = 'iVBORw0KGgoAAAANSUhEUgAAAHwAAAAdCAAAAABN3VedAAABy0lEQVRIDcXBQXLjSAADMPD/j+aK7Y2luJLLXALEv6qJn9WXUBOf4l/VxI/qCA018Sn+VU38qCZeauJT/Kua+FFNvNTEp1AENaEm3uqIp5p4qZe41C11C3XEJWpSn+Kl3uJWE0d9CeqWeog64hL1m5i6xa0mpm6hbqmHqCMuUb8K6iFuNXGpp6hb6iHqiEvUr4J6SYmHmqC+ibqlbqGOuET9KqgjPtUEdURNUEccNTF1xCWoCXWEmqBe4kNNUBNqgjriqImpIy5BTVATaoL6Et/UhDpCTVBHHDXxKagJakJNXOpLPNWE+i6oI46a+BTUBDWhJqbe4lYT6rugjjhq4lNQE9SEmjjqS9xqQn0TlzriqIlPQU1QE2rif/W/eKsJ9RRTRxw18SmoCWpCTXypl3irCWrioY44auKoiUtQE9SEmqAEdcRbTVATD3XEURNTR1yCmqAm1IT6Jt5qgjpCEZc64qiJqSMuQU1QE2pCPcWtJi71EJc64qiJqSMuQU1QE2pCPcWtJqYegjriqImpIy5BTVATaoK6xUNNHPUWlzriqImpIy5BTVATamLqJb6piZd6iZeaOGpi6ohL/KH4Q/FnmvgzTfyh+EP/AeZpsh7frbxYAAAAAElFTkSuQmCC'

@lru_cache(maxsize=24)
def _caption(height, factor=1.):
    raw = cv2.imdecode(np.frombuffer(base64.b64decode(CAPTION), np.uint8), 0)
    return cv2.resize(raw, (max(2, round(raw.shape[1]*height/720*factor)),
                            max(2, round(raw.shape[0]*height/720*factor))),
                      interpolation=cv2.INTER_NEAREST)


def visible_showdown_caption(frame):
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
        return False
    height, width = frame.shape[:2]
    crop = frame[:round(height*.12), :round(width*.30)]
    if not crop.size:
        return False
    # Threshold the current pixels, not cached state. Dimmed modal HUDs cannot
    # pass; moving scenery no longer distorts the letters' template score.
    white = (np.all(crop > 205, axis=2).astype(np.uint8)*255)
    for factor in (1., .96, 1.04):
        glyph = _caption(height, factor)
        if any(white.shape[i] < glyph.shape[i] for i in (0, 1)):
            continue
        _, score, _, _ = cv2.minMaxLoc(cv2.matchTemplate(white, glyph, cv2.TM_CCOEFF_NORMED))
        if score >= .90:
            return True
    return False
