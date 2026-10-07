"""Local own-health-bar drop detector; missing bars never mean zero health."""
import cv2
import numpy as np

def health_bar(frame,box):
    if frame is None or not box:return None
    h,w=frame.shape[:2];x1,y1,x2,y2=map(int,box[:4]);bw=x2-x1;bh=y2-y1
    left,right=max(0,x1),min(w,x2)
    top,bottom=max(0,y1),min(h,int(y1+bh*.55))
    crop=frame[top:bottom,left:right]
    if crop.size==0:return None
    r,g,b=[crop[:,:,i].astype(np.int16) for i in range(3)]
    mask=((g>150)&(g>r*1.2)&(g>b*1.25)&(r<210)).astype(np.uint8)*255
    kernel=np.ones((1,max(3,int(h/720*5))),np.uint8)
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,kernel)
    count,labels,stats,centers=cv2.connectedComponentsWithStats(mask)
    bars=[(width,y) for x,y,width,height,area in stats[1:] if width>=max(5,bw*.25) and width>=height*3 and height<=max(3,bh*.12) and abs(x+width/2-bw/2)<bw*.3]
    return max(bars)[0]/h if bars else None

class IncomingDamage:
    def __init__(self):self.previous=None;self.observed=0.;self.low_count=0;self.until=0.
    def observe(self,frame,box,now):
        value=health_bar(frame,box)
        if value is not None:
            if self.previous is not None and now-self.observed<.8 and value<self.previous*.88 and self.previous-value>.006:
                self.low_count+=1
                if self.low_count>=2:self.until=now+3;self.previous=value;self.low_count=0
            else:self.previous=value;self.low_count=0
            self.observed=now
        elif now-self.observed>.8:self.previous=None;self.low_count=0
        return now<self.until
