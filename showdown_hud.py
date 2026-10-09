"""Recognize the stable Showdown caption without its animated map background."""
import base64
from functools import lru_cache
import cv2
import numpy as np

# Anonymous lower glyphs of "Teams left:"; FPS overlay and changing count excluded.
CAPTION = 'iVBORw0KGgoAAAANSUhEUgAAAHwAAAAdCAAAAABN3VedAAABy0lEQVRIDcXBQXLjSAADMPD/j+aK7Y2luJLLXALEv6qJn9WXUBOf4l/VxI/qCA018Sn+VU38qCZeauJT/Kua+FFNvNTEp1AENaEm3uqIp5p4qZe41C11C3XEJWpSn+Kl3uJWE0d9CeqWeog64hL1m5i6xa0mpm6hbqmHqCMuUb8K6iFuNXGpp6hb6iHqiEvUr4J6SYmHmqC+ibqlbqGOuET9KqgjPtUEdURNUEccNTF1xCWoCXWEmqBe4kNNUBNqgjriqImpIy5BTVATaoL6Et/UhDpCTVBHHDXxKagJakJNXOpLPNWE+i6oI46a+BTUBDWhJqbe4lYT6rugjjhq4lNQE9SEmjjqS9xqQn0TlzriqIlPQU1QE2rif/W/eKsJ9RRTRxw18SmoCWpCTXypl3irCWrioY44auKoiUtQE9SEmqAEdcRbTVATD3XEURNTR1yCmqAm1IT6Jt5qgjpCEZc64qiJqSMuQU1QE2pCPcWtJi71EJc64qiJqSMuQU1QE2pCPcWtJqYegjriqImpIy5BTVATaoK6xUNNHPUWlzriqImpIy5BTVATamLqJb6piZd6iZeaOGpi6ohL/KH4Q/FnmvgzTfyh+EP/AeZpsh7frbxYAAAAAElFTkSuQmCC'

# Alternate current HUD lettering; only constant caption pixels are retained.
CAPTION_CURRENT = 'iVBORw0KGgoAAAANSUhEUgAAADYAAAAKCAAAAADalvLXAAAAaUlEQVQoFZ3BsQHCMAAEMd3+Qz820EIRKY/kkRwjvy0fy1eu5Y/lbTI5ci1GRuYtIyxDc2XKtUwLizUtk2NZk2Vy5FpGpsWaFhPWEMvkyLVYTNNkLSYsy7FYjlyLkWlZ1jLCYmSxTHnkBVCdQgsiIonvAAAAAElFTkSuQmCC'

# Russian caption without the changing team count or account information.
CAPTION_RUSSIAN = 'iVBORw0KGgoAAAANSUhEUgAAAF0AAAAMCAAAAAAlyO5NAAAAkUlEQVQ4EbXBgU0AMQADMd/+Q4f2BWKC2nkpx/JGTJMXYrG8kIVlwuTPkGWxsHyWZVkslmOZLJYln2W5lmNiWZZlOYYwYplMIyxzxLLksyzXYk0sy7Isx7IwZJmWNU3LNLEsMU0mx2JZFsuyTFgWlmVZjmUty2KZLGFyLb8mls/kmFiu5Zr8G/k1V3ln5aW89ANzdWkNKtE3EwAAAABJRU5ErkJggg=='

@lru_cache(maxsize=24)
def _caption(height, factor=1., encoded=CAPTION, reference_height=720):
    raw = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), np.uint8), 0)
    return cv2.resize(raw, (max(2, round(raw.shape[1]*height/reference_height*factor)),
                            max(2, round(raw.shape[0]*height/reference_height*factor))),
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
    for encoded, reference_height in ((CAPTION, 720), (CAPTION_CURRENT, 212), (CAPTION_RUSSIAN, 219)):
        candidates = [(white,height)]
        if encoded == CAPTION_RUSSIAN and height > reference_height:
            scale = reference_height/height
            transform = np.array([[scale,0,(scale-1)/2],
                                  [0,scale,(scale-1)/2]],np.float32)
            normalized = cv2.warpAffine(crop,transform,
                                        (round(crop.shape[1]*scale),round(crop.shape[0]*scale)),
                                        flags=cv2.INTER_LINEAR)
            candidates.append((np.all(normalized > 200,axis=2).astype(np.uint8)*255,
                               reference_height))
        for candidate,candidate_height in candidates:
            for factor in (1., .96, 1.04):
                glyph = _caption(candidate_height, factor, encoded, reference_height)
                if any(candidate.shape[i] < glyph.shape[i] for i in (0, 1)):
                    continue
                _, score, _, _ = cv2.minMaxLoc(cv2.matchTemplate(candidate, glyph, cv2.TM_CCOEFF_NORMED))
                if score >= .90:
                    return True
    return False
