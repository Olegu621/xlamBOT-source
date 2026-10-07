"""Persistent cover selection; proximity/approach are observable exposure signals."""
import math
from combat_behavior import position, unit, unique

class BushCover:
    def __init__(self):
        self.last_pulse=None;self.pulse_until=0.;self.side=1;self.excluded=None;self.exclude_until=0.;self.last_enemy_distance=None;self.goal=None
    def plan(self,player,bushes,enemies,tile,radius,now,attack_range,visible,safe,attacked=False,refuge=None,offset=(0.,0.)):
        world=lambda point:(point[0]+offset[0],point[1]+offset[1])
        enemies=unique(enemies)
        target=min(enemies,key=lambda b:math.dist(position(b),player)) if enemies else None
        distance=math.dist(position(target),player) if target else float('inf')
        approaching=self.last_enemy_distance is not None and distance<self.last_enemy_distance-tile*.08
        self.last_enemy_distance=distance if target else None
        fire=target is not None and distance<=attack_range and visible(target)
        inside=[b for b in bushes if b[0]<=player[0]<=b[2] and b[1]<=player[1]<=b[3]]
        exposed=attacked or distance<tile*3 or (approaching and distance<tile*6)
        excluded_here=now<self.exclude_until and self.excluded is not None and any(math.dist(world(position(b)),self.excluded)<tile for b in inside)
        threatened=exposed or not safe(player,tile*1.5) or excluded_here
        if (exposed or not safe(player,tile*1.5)) and inside:
            self.excluded=world(position(inside[0]));self.exclude_until=now+5
        report={'mode':1,'intent':'hide','reason':'covered','fire_allowed':fire,'target':list(position(target)) if target else None,'preferred_distance':attack_range*1.12}
        if inside and not threatened:
            if self.last_pulse is None:self.last_pulse=now
            if now-self.last_pulse>=3:
                self.last_pulse=now;self.pulse_until=now+.12;self.side*=-1
            movement=(0.,0.)
            if now<self.pulse_until:
                b=inside[0];aim=(player[0]+self.side*tile*.15,player[1])
                if b[0]<aim[0]<b[2] and safe(aim,tile*.2):movement=(self.side*radius,0.)
                else:
                    v=unit((position(b)[0]-player[0],position(b)[1]-player[1]));movement=tuple(x*radius for x in v)
            return {'movement':movement,'target':target,'report':report}
        self.last_pulse=now;self.pulse_until=0
        candidates=[]
        for b in bushes:
            aim=position(b)
            if not safe(aim,tile):continue
            if now<self.exclude_until and self.excluded and math.dist(world(aim),self.excluded)<tile:continue
            if target and math.dist(aim,position(target))<tile*2:continue
            candidates.append(aim)
        if candidates:
            aim=min(candidates,key=lambda a:math.dist(a,player)-(tile*2 if self.goal is not None and math.dist(world(a),self.goal)<tile else 0));self.goal=world(aim);v=unit((aim[0]-player[0],aim[1]-player[1]));report.update(intent='seek_cover',reason='under_attack' if attacked else 'exposed' if threatened else 'find_bush')
        else:
            # Explore clear ground outside the threatened bush, without following allies.
            options=[]
            for n in range(16):
                angle=n*math.pi/8;aim=(player[0]+math.cos(angle)*tile*3,player[1]+math.sin(angle)*tile*3)
                if not safe(aim,tile):continue
                score=math.dist(aim,refuge) if refuge is not None else 0.
                if target:score-=math.dist(aim,position(target))*2
                options.append((score,aim))
            aim=min(options,key=lambda o:o[0])[1] if options else player
            v=unit((aim[0]-player[0],aim[1]-player[1]))
            report.update(intent='retreat' if threatened else 'explore',reason='no_safe_bush' if threatened else 'no_visible_bush')
        return {'movement':None if v is None else tuple(x*radius for x in v),'target':target,'report':report}
