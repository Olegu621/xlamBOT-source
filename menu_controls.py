"""Positive Back-arrow evidence excluding the emulator FPS overlay."""
import base64
from functools import lru_cache
import cv2
import numpy as np
ARROW = 'iVBORw0KGgoAAAANSUhEUgAAACgAAAAeCAAAAAB7tgMBAAAAg0lEQVQ4EY3BCQ6DMBAEwe7/P3oi4wMDG8lV0oSS3OQSKnKTLlRkkSFUZJIpVGSQJRRkkFsoSCebUJCL7EJBGnkIX9LIU/iQRl7CmzTyFp7kIh9hJ518hY10UgiLDFIJg0xSCp1MUgoXWaQWGlnkjwByk3+CbOSQHJJDckgOySE5JId+n94WH95AK6wAAAAASUVORK5CYII='
@lru_cache(maxsize=16)
def _arrow(height):
    raw=cv2.imdecode(np.frombuffer(base64.b64decode(ARROW),np.uint8),0)
    return cv2.resize(raw,(max(2,round(raw.shape[1]*height/720)),max(2,round(raw.shape[0]*height/720))),interpolation=cv2.INTER_NEAREST)

def back_arrow_position(frame):
    if frame is None or frame.ndim!=3 or frame.shape[2]!=3:return None
    h,w=frame.shape[:2];crop=frame[:round(h*.13),:round(w*.13)]
    glyph=_arrow(h)
    if not crop.size or any(crop.shape[i]<glyph.shape[i] for i in (0,1)):return None
    white=np.all(crop>205,axis=2).astype(np.uint8)*255
    _,score,_,location=cv2.minMaxLoc(cv2.matchTemplate(white,glyph,cv2.TM_CCOEFF_NORMED))
    if score<.94:return None
    return location[0]+glyph.shape[1]//2,location[1]+glyph.shape[0]//2
