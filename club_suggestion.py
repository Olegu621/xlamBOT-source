"""Confirm the club recommendation modal and its own visible Close control."""
import base64
from functools import lru_cache
import cv2
import numpy as np
CROSS = 'iVBORw0KGgoAAAANSUhEUgAAAD4AAAAuCAAAAABVfPUDAAAAx0lEQVRIDaXBCVIDQQwEwar/P7qx1xdIGiBCmbIiK7IiK7IiK7IiB0H+JqNwIx9BBjIKd/ISQDoZhCe5hIs00oU3uQlPUkkTvhHCi1RShTMppAq/kJ+kCUdSSBcOpJJBGEkjkzCQTkahkYHMQiETmYVCJjIJnQxkECbSSRdm0kgVjqSSKhxJJVU4k0KacCY/SRfeJHxIJYPwJIQ3aWQS7uQSHqSTUQB5CBcZyCzIS7iRifxDkJmsyIqsyIqsyIqsyIqsyIqsfAHWBSYvb/+FIwAAAABJRU5ErkJggg=='
@lru_cache(maxsize=16)
def _cross(height):
    raw=cv2.imdecode(np.frombuffer(base64.b64decode(CROSS),np.uint8),0)
    return cv2.resize(raw,(max(2,round(raw.shape[1]*height/720)),max(2,round(raw.shape[0]*height/720))),interpolation=cv2.INTER_NEAREST)

def club_suggestion_close_position(frame):
    if frame is None or frame.ndim!=3 or frame.shape[2]!=3:return None
    h,w=frame.shape[:2];s=h/720;glyph=_cross(h)
    left=round(w*.5);roi=frame[:round(h*.25),left:]
    if any(roi.shape[i]<glyph.shape[i] for i in (0,1)):return None
    white=np.all(roi>205,axis=2).astype(np.uint8)*255
    _,score,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(white,glyph,cv2.TM_CCOEFF_NORMED))
    if score<.92:return None
    x+=left;cx=x+glyph.shape[1]/2;cy=y+glyph.shape[0]/2
    def region(dx1,dy1,dx2,dy2):
        a,b,c,d=round(cx+dx1*s),round(cy+dy1*s),round(cx+dx2*s),round(cy+dy2*s)
        if a<0 or b<0 or c>w or d>h or c<=a or d<=b:return None
        return frame[b:d,a:c].astype(np.int16)
    button=region(-30,-21,30,21)
    if button is None or ((button[:,:,0]>165)&(button[:,:,1]<90)&(button[:,:,2]<90)).mean()<.3:return None
    # Header/body plus all five alternating list rows are independent evidence.
    # They do not depend on the translated heading or account/club names.
    for bounds in [(-730,-25,-60,-16),(-730,50,-60,105)]:
        p=region(*bounds)
        if p is None or ((p[:,:,0]<80)&(p[:,:,1]>65)&(p[:,:,2]>190)).mean()<.6:return None
    for i in range(5):
        p=region(-710,160+75*i,-670,184+75*i)
        separator=region(-710,194+75*i,-670,210+75*i)
        if p is None or separator is None:return None
        grey=(np.ptp(p,axis=2)<35)&(p.mean(axis=2)>70)&(p.mean(axis=2)<165)
        if grey.mean()<.7 or (separator.mean(axis=2)<40).mean()<.2:return None
    return round(cx),round(cy)
