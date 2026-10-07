"""Exact circular collision, including rounded rectangle corners."""
import math

def point_rectangle(point,rect):
    x,y=point;x1,y1,x2,y2=rect
    return max(x1-x,0,x-x2)**2+max(y1-y,0,y-y2)**2

def point_segment(point,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];length=dx*dx+dy*dy
    t=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length)) if length else 0
    return (point[0]-a[0]-t*dx)**2+(point[1]-a[1]-t*dy)**2

def crosses(a,b,rect):
    lo,hi=0.,1.
    for axis in (0,1):
        delta=b[axis]-a[axis]
        if abs(delta)<1e-9:
            if a[axis]<rect[axis] or a[axis]>rect[axis+2]:return False
        else:
            x,y=(rect[axis]-a[axis])/delta,(rect[axis+2]-a[axis])/delta
            lo=max(lo,min(x,y));hi=min(hi,max(x,y))
            if lo>hi:return False
    return True

def blocked(a,b,radius,walls):
    r2=radius*radius
    for wall in walls:
        x1,y1,x2,y2=wall[:4]
        if max(a[0],b[0])<x1-radius or min(a[0],b[0])>x2+radius or max(a[1],b[1])<y1-radius or min(a[1],b[1])>y2+radius:continue
        start=point_rectangle(a,wall);end=point_rectangle(b,wall)
        if start<=r2 and end>start+1e-6:continue
        if start<=r2 or end<=r2 or crosses(a,b,wall):return True
        if min(point_segment(c,a,b) for c in ((x1,y1),(x1,y2),(x2,y1),(x2,y2)))<=r2:return True
    return False

def detour(player,desired,radius,tile,walls,directions=16):
    """Find a short route toward the destination, rather than chasing a blocked ray."""
    if not desired or math.hypot(*desired)<1:return None
    length=math.hypot(*desired);unit=(desired[0]/length,desired[1]/length)
    if not blocked(player,(player[0]+unit[0]*tile,player[1]+unit[1]*tile),radius,walls):return None
    goal=(player[0]+unit[0]*tile*3,player[1]+unit[1]*tile*3)
    options=[]
    for n in range(directions):
        angle=2*math.pi*n/directions;direction=(math.cos(angle),math.sin(angle));first=(player[0]+direction[0]*tile,player[1]+direction[1]*tile)
        if blocked(player,first,radius,walls):continue
        costs=[math.dist(first,goal)+tile*.8]
        for offset in (-math.pi/2,-math.pi/4,0,math.pi/4,math.pi/2):
            a=angle+offset;second=(first[0]+math.cos(a)*tile,first[1]+math.sin(a)*tile)
            if not blocked(first,second,radius,walls):costs.append(math.dist(second,goal))
        options.append((min(costs)+tile*.05*(1-direction[0]*unit[0]-direction[1]*unit[1]),direction))
    return min(options,key=lambda x:x[0])[1] if options else None
