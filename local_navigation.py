"""Exact circular collision, including rounded rectangle corners."""
import math
import heapq
from functools import lru_cache

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
    radius=passage_radius(a,b,radius,walls)
    r2=radius*radius
    for wall in walls:
        x1,y1,x2,y2=wall[:4]
        if max(a[0],b[0])<x1-radius or min(a[0],b[0])>x2+radius or max(a[1],b[1])<y1-radius or min(a[1],b[1])>y2+radius:continue
        start=point_rectangle(a,wall);end=point_rectangle(b,wall)
        if start<=r2 and end>start+1e-6:continue
        if start<=r2 or end<=r2 or crosses(a,b,wall):return True
        if min(point_segment(c,a,b) for c in ((x1,y1),(x1,y2),(x2,y1),(x2,y2)))<=r2:return True
    return False

def passages(walls,radius):
    return _passages(tuple(tuple(w[:4]) for w in walls),radius)

@lru_cache(maxsize=64)
def _passages(walls,radius):
    """Separate solid boxes may delimit a traversable opening, never a solid wall."""
    result=[]
    for i,a in enumerate(walls):
        for b in walls[i+1:]:
            for axis in (0,1):
                other=1-axis
                lo=max(a[other],b[other]);hi=min(a[other+2],b[other+2])
                left,right=(a,b) if a[axis+2]<=b[axis] else (b,a)
                gap=right[axis]-left[axis+2]
                if hi>lo and 0<gap<radius*2.2:
                    result.append((axis,(left[axis+2]+right[axis])/2,lo,hi,gap))
    return result

def passage_radius(a,b,radius,walls):
    for axis,center,lo,hi,gap in passages(walls,radius):
        other=1-axis
        # Shrink only for a segment aligned within a detected real opening.
        delta=b[other]-a[other]
        if abs(delta)<1e-9:
            interval=(0.,1.) if lo<=a[other]<=hi else None
        else:
            u,v=sorted(((lo-a[other])/delta,(hi-a[other])/delta))
            interval=(max(0,u),min(1,v)) if max(0,u)<=min(1,v) else None
        if interval and all(abs(a[axis]+t*(b[axis]-a[axis])-center)<gap*.45 for t in interval):
            radius=min(radius,gap*.40)
    return radius

def detour(player,desired,radius,tile,walls,directions=16,risk=None):
    """Bounded visibility graph follows wall corners and aligns with small gaps."""
    if not desired or math.hypot(*desired)<1:return None
    length=math.hypot(*desired);unit=(desired[0]/length,desired[1]/length)
    if not blocked(player,(player[0]+unit[0]*tile,player[1]+unit[1]*tile),radius,walls):return None
    near=sorted(walls,key=lambda w:point_rectangle(player,w))[:8]
    reach=max(tile*4,min(tile*8,max((math.sqrt(point_rectangle(player,w)) for w in near),default=0)+tile*3))
    goal=(player[0]+unit[0]*reach,player[1]+unit[1]*reach)
    nodes=[player,goal]
    margin=radius+max(1,tile*.03)
    for x1,y1,x2,y2,*_ in near:
        nodes.extend([(x1-margin,y1-margin),(x1-margin,y2+margin),(x2+margin,y1-margin),(x2+margin,y2+margin)])
    for axis,center,lo,hi,gap in passages(near,radius):
        for extent in (lo-margin,hi+margin):
            nodes.append((center,extent) if axis==0 else (extent,center))
    # Free endpoints around the desired destination when that destination is solid.
    for n in range(8):
        angle=n*math.pi/4
        nodes.append((player[0]+math.cos(angle)*reach,player[1]+math.sin(angle)*reach))
    costs={0:0.};first={};queue=[(0.,0)];visited=set();best=None
    while queue:
        priority,i=heapq.heappop(queue)
        cost=costs[i]
        if i in visited:continue
        if len(visited)>=16:break
        visited.add(i)
        if i==1:
            best=(cost,first[i]);break
        if i:
            score=cost+math.dist(nodes[i],goal)*1.3
            if best is None or score<best[0]:best=(score,first[i])
        neighbors=sorted((j for j in range(len(nodes)) if j!=i and j not in visited),key=lambda j:math.dist(nodes[i],nodes[j]))[:10]
        if 1 not in visited and 1 not in neighbors:neighbors.append(1)
        for j in neighbors:
            point=nodes[j]
            if j==i or j in visited or blocked(nodes[i],point,radius,near):continue
            distance=math.dist(nodes[i],point);value=cost+distance
            if risk:
                value += distance*sum(risk((nodes[i][0]+t*(point[0]-nodes[i][0]),nodes[i][1]+t*(point[1]-nodes[i][1]))) for t in (.25,.5,.75))/3
            if value<costs.get(j,float('inf')):
                costs[j]=value;first[j]=j if i==0 else first[i];heapq.heappush(queue,(value+math.dist(point,goal),j))
    if best is None:return None
    target=nodes[best[1]];dx,dy=target[0]-player[0],target[1]-player[1];length=math.hypot(dx,dy)
    return (dx/length,dy/length) if length else None
