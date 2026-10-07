"""Bounded per-device tactics. Physical gas/wall checks remain authoritative."""
import math

PREFERENCES={1:1.12,2:.88,3:.74,4:.63,5:.50}
TOLERANCE={1:0,2:0,3:0,4:1,5:2}

def position(box):return ((box[0]+box[2])/2,(box[1]+box[3])/2)
def unit(vector):
    length=math.hypot(*vector)
    return (vector[0]/length,vector[1]/length) if length>1e-6 else (0.,0.)
def overlap(a,b):
    shared=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return shared/max(1,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-shared)
def unique(boxes):
    result=[]
    for b in boxes:
        if len(b)>=4 and all(math.isfinite(float(x)) for x in b[:4]) and not any(overlap(b,a)>.45 for a in result):result.append(b)
    return result

class CombatBehavior:
    def __init__(self):self.reset()
    def reset(self):
        self.target=None;self.seen=0.;self.side=1.;self.mode=None

    def plan(self,level,player,enemies,allies,attack_range,safe_range,tile,radius,now,visible=None):
        if self.mode!=level:self.reset();self.mode=level
        enemies=unique(enemies);allies=unique(allies);attack_range=max(attack_range,tile*1.5)
        visible=visible or (lambda box:True)
        ally_points=[position(b) for b in allies]
        report={'mode':level,'target':None,'intent':'explore','reason':'no_target','fire_allowed':False,'near_enemies':0,'support':0,'preferred_distance':None}
        if not enemies:
            self.target=None
            if ally_points:
                anchor=min(ally_points,key=lambda a:math.dist(a,player));distance=math.dist(anchor,player)
                limit=tile*(3 if level<3 else 5 if level<5 else 7)
                if distance>limit:
                    direction=unit((anchor[0]-player[0],anchor[1]-player[1]));report.update(intent='regroup',reason='team_separated')
                    return {'movement':tuple(v*radius for v in direction),'target':None,'report':report}
            return {'movement':None,'target':None,'report':report}
        support_radius=max(tile*5,min(attack_range,tile*7))
        nearby_allies=[a for a in ally_points if math.dist(a,player)<support_radius]
        near=[b for b in enemies if math.dist(position(b),player)<max(tile*5,attack_range*.75)]
        def score(box):
            pos=position(box);distance=math.dist(pos,player)
            help_distance=min((math.dist(pos,a) for a in nearby_allies),default=attack_range*2)
            return distance+(0 if visible(box) else attack_range*.75)+min(help_distance,attack_range)*.15
        candidate=min(enemies,key=score)
        if self.target is not None and now-self.seen<.7:
            previous=min(enemies,key=lambda b:math.dist(position(b),self.target))
            if math.dist(position(previous),self.target)<max(tile*2,attack_range*.18) and score(previous)<=score(candidate)+max(tile,attack_range*.12):candidate=previous
        point=position(candidate)
        if self.target is None or math.dist(point,self.target)>tile*2:self.side=1 if point[1]>=player[1] else -1
        self.target=point;self.seen=now
        distance=math.dist(point,player);toward=unit((point[0]-player[0],point[1]-player[1]));can_see=visible(candidate)
        melee=attack_range<=tile*3.8 or safe_range<=0
        desired=attack_range*(PREFERENCES[level] if not melee else {1:1.3,2:1.05,3:.8,4:.6,5:.4}[level])
        desired=max(tile*.8,desired)
        band=max(tile*.25,attack_range*.08)
        outnumbered=len(near)>len(nearby_allies)+1+TOLERANCE[level]
        retreat=(level==1 and distance<max(desired,tile*7)) or (outnumbered and distance<max(tile*6,attack_range))
        if retreat:
            # Flee the combined pressure, not whichever enemy won one frame's rank.
            threat=(0.,0.)
            for enemy in near or [candidate]:
                pos=position(enemy);d=max(math.dist(pos,player),tile*.5);away=unit((player[0]-pos[0],player[1]-pos[1]));weight=1/(d*d)
                threat=(threat[0]+away[0]*weight,threat[1]+away[1]*weight)
            direction=unit(threat)
            if direction==(0.,0.):direction=(-toward[0],-toward[1])
            if nearby_allies:
                anchor=min(nearby_allies,key=lambda a:math.dist(a,player));back=unit((anchor[0]-player[0],anchor[1]-player[1]))
                # Never regroup through the target we are retreating from.
                if sum(a*b for a,b in zip(back,toward))<.35:direction=unit((direction[0]+back[0]*.6,direction[1]+back[1]*.6))
            intent='retreat';reason='avoid_contact' if level==1 else 'outnumbered'
        elif level==1:
            direction=(-toward[1]*self.side,toward[0]*self.side);intent='evade';reason='safe_distance'
        elif distance<desired-band:
            direction=(-toward[0],-toward[1]);intent='kite';reason='too_close'
        elif distance>desired+band:
            direction=toward;intent='approach';reason='effective_range'
        else:
            direction=(-toward[1]*self.side,toward[0]*self.side);intent='strafe';reason='hold_range'
        if not can_see and not retreat and distance<=desired+band:
            direction=(-toward[1]*self.side,toward[0]*self.side);intent='flank';reason='target_behind_wall'
        # Distance dead zone and target persistence prevent approach/retreat jitter.
        fire=can_see and distance<=attack_range and (level!=1 or distance<=attack_range*.7)
        report.update(target=list(point),intent=intent,reason=reason,fire_allowed=fire,near_enemies=len(near),support=len(nearby_allies),preferred_distance=round(desired,1),target_distance=round(distance,1))
        return {'movement':tuple(v*radius for v in direction),'target':candidate,'report':report}
