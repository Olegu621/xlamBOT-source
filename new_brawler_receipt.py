"""Confirmed Continue action on the new-brawler unlock receipt."""
import base64
from functools import lru_cache
import cv2
import numpy as np

TITLE = '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'
CONTINUE = 'iVBORw0KGgoAAAANSUhEUgAAAKEAAAAkCAAAAADERwUBAAACiElEQVRYCc3BiWHDQAwDMHD/oVnpbOfpBAHi18Wvi18Xvy5e6hIvdYlbrVg1Qn2Jegu1YtUIdcSoFdRb3OJRL3HUWxx1xKgR6kvUW6gjRo1QR4xaQX2IS1zqQ4z6EquOGDVCfYl6C3XEqBHqiFErqA9xiUu9xah/YtQlqBHqS9RbqEtQI9QRo1ZQH+ISR32IUf/EqEtQI9SXqLdQl6BGqCNGraDe4harLkFj1CXUJahbqBFHHXGrFatuoUaoI0atoFZ8iVVHvNQRo46gbqFGHLXiUStW3UKNUEeMWkGt+BKrVrzViqNWUI+oEUeteNSKVY+oEeqIUSuoFV9i1YqXOuKoI9QjasRRKx61YtUjaoQ6YtQKasWXGHXESx1x1BHqJTXiqBWPWrHqJTVCHTFqBfUSjxh1xEsdcdQR6p84asWjVqz6J9QRo1ZQL/GIUUe81IpLHaH+iaNWPGrFqn9CHTFqBfUSjxh1xEsdcdQR6p84asWjVqz6J9QRo1ZQL/GIUUe81BFHHaFG1COOWvGoFatG1CPUEaNWUCu+xKoVb7XiqBXUCHWLo1Y8asWqEeoW6ohRK6gVX2LVES91xKgjqBHqFketeNSKVSPULdQRo1ZQK77EqkuMBnUJdQlqBHWJo1Y8asWqEdQl1CXUEdSKL3HUhxj1T4waQV3iqBW3usSoEdQlqH+CeotbHPUpqH9i1IhRRxy14qi3UCNGHUH9E9SHuMSlPsSoL7FqxKgjjlpx1FuoEaOOGPUlRn2IS9zqLVZ9iKNGrFpx1Iqj3kKNWLVi1YdY9SEu8VK3uNUtbjVi1YqjVhz1FmrEqhWXusWlPsQlfl38uvh18evi18Wvi18Xvy5+Xfy6P4079SU1Zf+4AAAAAElFTkSuQmCC'

@lru_cache(maxsize=24)
def _glyph(encoded, height):
    raw=cv2.imdecode(np.frombuffer(base64.b64decode(encoded),np.uint8),0)
    return cv2.resize(raw,(max(2,round(raw.shape[1]*height/720)),
                           max(2,round(raw.shape[0]*height/720))),interpolation=cv2.INTER_NEAREST)


def _locate(frame, encoded, bounds, yellow=False):
    h,w=frame.shape[:2];x1,y1,x2,y2=bounds
    left,top=round(w*x1),round(h*y1)
    crop=frame[top:round(h*y2),left:round(w*x2)]
    if not crop.size:return None
    if yellow:
        mask=(crop[:,:,0]>220)&(crop[:,:,1]>190)&(crop[:,:,2]<190)
    else:
        mask=np.all(crop>205,axis=2)
    glyph=_glyph(encoded,h)
    if any(crop.shape[i]<glyph.shape[i] for i in (0,1)):return None
    _,score,_,loc=cv2.minMaxLoc(cv2.matchTemplate(mask.astype(np.uint8)*255,glyph,cv2.TM_CCOEFF_NORMED))
    if score<.90:return None
    return (left+loc[0]+glyph.shape[1]//2,top+loc[1]+glyph.shape[0]//2)


def new_brawler_continue_position(frame):
    if frame is None or frame.ndim!=3 or frame.shape[2]!=3:return None
    if _locate(frame,TITLE,(.43,.10,.96,.34),yellow=True) is None:return None
    position=_locate(frame,CONTINUE,(.46,.78,.70,.94))
    if position is None:return None
    # Confirm the blue action behind its lettering. The green Select control
    # changes the equipped brawler and must never be used for dismissal.
    h,w=frame.shape[:2];x,y=position
    patch=frame[max(0,y-round(h*.025)):min(h,y+round(h*.025)),
                max(0,x-round(w*.08)):min(w,x+round(w*.08))]
    hsv=cv2.cvtColor(patch,cv2.COLOR_RGB2HSV)
    blue=cv2.inRange(hsv,np.array([100,120,140]),np.array([125,255,255]))
    return position if np.mean(blue>0)>.30 else None
