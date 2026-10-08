"""Positive side-menu evidence from three language-independent control glyphs."""
import base64
from functools import lru_cache
import cv2
import numpy as np

_GLYPHS = ('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')

@lru_cache(maxsize=12)
def _templates(height):
    scale=height/577
    values=[]
    for raw in _GLYPHS:
        original=cv2.imdecode(np.frombuffer(base64.b64decode(raw),np.uint8),cv2.IMREAD_GRAYSCALE)
        values.append(cv2.resize(original,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA))
    return values

def side_menu_close_position(frame):
    if frame is None or frame.ndim!=3:
        return None
    h,w=frame.shape[:2]
    if h<200 or w<h*1.1:
        return None
    gray=cv2.cvtColor(frame,cv2.COLOR_RGB2GRAY)
    x0=int(w*.55)
    roi=gray[:int(h*.7),x0:]
    hits=[]
    templates=_templates(h)
    for glyph in templates[:3]:
        if roi.shape[0]<glyph.shape[0] or roi.shape[1]<glyph.shape[1]:
            return None
        _,score,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(roi,glyph,cv2.TM_CCOEFF_NORMED))
        if score>=.86:
            hits.append((x+x0,y))
    if len(hits)<2 or max(x for x,y in hits)-min(x for x,y in hits)>w*.09:
        return None
    glyph=templates[3];roi=gray[:int(h*.085),int(w*.80):]
    if roi.shape[0]<glyph.shape[0] or roi.shape[1]<glyph.shape[1]:
        return None
    _,score,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(roi,glyph,cv2.TM_CCOEFF_NORMED))
    if score<.88:
        return None
    return (int(w*.80)+x+glyph.shape[1]/2,y+glyph.shape[0]/2)
