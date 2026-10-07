"""Positive battle identity and a cheap guard against spectator/respawn input."""
import base64
import cv2
import numpy as np
from functools import lru_cache

_CAPTION = "iVBORw0KGgoAAAANSUhEUgAAAH8AAAAlCAAAAABOw2leAAACAUlEQVRYCcXBUW7bUBAEMM79Dz3dfWlkqS0QA/0wGZ8VnxWfFUd9i/cV8Q+14mex6i7eVCP+Vit+1Fj1FG+pEX+rFT+LVU/xlhrxt1rxs1j1h3hHjfiHIt4Qq45QR7yjRvyPWHUEteIdNeJ/xKojqBVfingqcdSIUcS/VKwivtSIFauOoEas+hbf6regRlAjLrWCGlFfYtSKFauOoEasusRRl6BGqBWXWkE9BbVixaojasVRL7HqEtQINeKlVlBPQa1Yseou7mrFqJegRtSIm1pBPQW1YsWqu7irFaNWKEGNqBE3tWLUEWoEtWLFqqd4qRXUETRGXeKuVqwaQY14ilVHqCNGvQS14lKXuKsVq0ZQI55i1RHUCuomqBWXusRdrVg1ghrxFKuOoFaolTqCWnGpl7ipFatGUCOeYtUR1BE1Qq2gVlzqJW5qxaoR1IinWHUEdUSNUCtGrfhWI2rETa1YNYIa8RSrjqgvoUaoL6GO0Bg1ola81IpVI6gR1IoVq/4QaqV+C3WJUSPUikutWDWCGkGtWLHqD6GegroENUKtuNSKVSOoEdSKFaueYtRDUJegRlArvtWKVSOoEdSKFUfdxVFH1IhVvwU1glrxrVasGkGNoFasOOoSlxpBiS+1YtWIUSu+1YijCGoEtWLFZ8VnxWfFZ8VnxWfFZ8VnxWf9Aq/zvSU5vr3XAAAAAElFTkSuQmCC"

@lru_cache(maxsize=12)
def _caption(height):
    template=cv2.imdecode(np.frombuffer(base64.b64decode(_CAPTION),np.uint8),0)
    scale=height/720
    return cv2.resize(template,None,fx=scale,fy=scale,interpolation=cv2.INTER_NEAREST)

def respawning(frame):
    h,w=frame.shape[:2]
    patch=frame[int(h*.22):int(h*.53),int(w*.28):int(w*.72)]
    white=cv2.inRange(patch,np.array([220,220,220],np.uint8),np.array([255,255,255],np.uint8))
    template=_caption(h)
    if white.shape[0]<template.shape[0] or white.shape[1]<template.shape[1]:return False
    return cv2.minMaxLoc(cv2.matchTemplate(white,template,cv2.TM_CCOEFF_NORMED))[1]>.78

def overlap(a,b):
    area=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return area/max(1,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-area)

def own_player(data):
    """An enemy or ally cannot simultaneously be the controlled player."""
    others=(data.get('enemy') or [])+(data.get('teammate') or [])
    players=[b for b in data.get('player',[]) if not any(overlap(b,e)>.6 for e in others)]
    data['player']=players[:1]
    return data
