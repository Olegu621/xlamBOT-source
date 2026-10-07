"""Peak cloud coverage along a short swept body path; never average away an edge."""
import math
import numpy as np

def corridor_peak(mask, box, vector, reach=3.):
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
        patch=mask[round(y-radius):round(y+radius)+1,round(x-radius):round(x+radius)+1]
        peak=max(peak,float(np.mean(patch>0)))
    return peak
