"""Peak cloud coverage along a short swept body path; never average away an edge."""
import math
import numpy as np
import cv2

def coverage_integral(mask):
    return cv2.integral((mask>0).astype(np.uint8))


def corridor_peak(mask, box, vector, reach=3., integral=None):
    if mask is None or box is None:return 0.
    dx,dy=vector;length=math.hypot(dx,dy)
    if length<1e-6:return 0.
    dx,dy=dx/length,dy/length
    x1,y1,x2,y2=box;cx,cy=(x1+x2)/2,(y1+y2)/2
    radius=max(1.,min(x2-x1,y2-y1)/2)
    h,w=mask.shape[:2];peak=0.
    for distance in np.linspace(radius*.5,radius*2*reach,16):
        x,y=cx+dx*distance,cy+dy*distance
        # Unobserved ground past the screen is not a proven safe route.
        if x-radius<0 or y-radius<0 or x+radius>=w or y+radius>=h:return 1.
        left,top,right,bottom=round(x-radius),round(y-radius),min(w,round(x+radius)+1),min(h,round(y+radius)+1)
        if integral is None:
            share=float(np.mean(mask[top:bottom,left:right]>0))
        else:
            count=int(integral[bottom,right])-int(integral[top,right])-int(integral[bottom,left])+int(integral[top,left])
            share=count/((bottom-top)*(right-left))
        peak=max(peak,share)
    return peak
