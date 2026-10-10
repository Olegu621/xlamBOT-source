"""Loose power cubes from the current battle frame, excluding player badges."""
import math
import cv2
import numpy as np

def visible_cubes(frame):
    if frame is None:return []
    h,w=frame.shape[:2];r,g,b=cv2.split(frame)
    mask=((g>155)&(r<185)&(b<185)&(g.astype(np.int16)>r.astype(np.int16)+30)).astype(np.uint8)*255
    cubes=[]
    for contour in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,bw,bh=cv2.boundingRect(contour)
        if not(.035*h<bw<.10*h and .035*h<bh<.10*h and .5<bw/bh<1.8):continue
        if not(.08*w<x<.90*w and .15*h<y<.82*h):continue
        if cv2.contourArea(contour)<bw*bh*.25:continue
        patch=frame[max(0,y-4):min(h,y+bh+4),max(0,x-4):min(w,x+bw+4)]
        gold=(patch[:,:,0]>170)&(patch[:,:,1]>145)&(patch[:,:,2]<130)
        if gold.mean()>.025:cubes.append((x+bw/2,y+bh/2))
    return cubes

def choose_cube(cubes,player,enemies,entities,tile,gas_mask):
    if any(math.dist(player,e)<tile*3 for e in enemies):return None
    safe=[]
    for point in cubes:
        distance=math.dist(player,point)
        if distance>tile*6 or distance<tile*.25:continue
        if any(math.dist(point,e)<tile*.8 for e in entities):continue
        if any(math.dist(point,e)<distance+tile for e in enemies):continue
        if gas_mask is not None:
            h,w=gas_mask.shape[:2];x,y=map(round,point);margin=max(3,round(tile*.5))
            patch=gas_mask[max(0,y-margin):min(h,y+margin+1),max(0,x-margin):min(w,x+margin+1)]
            if not patch.size or (patch>0).mean()>.05:continue
        safe.append(point)
    return min(safe,key=lambda p:math.dist(player,p)) if safe else None
