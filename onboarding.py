"""First-run training actions require the original onboarding controls."""
from __future__ import annotations
import base64
from functools import lru_cache
import heapq
import math
import random
import time
import cv2
import numpy as np
from onboarding_assets import SID,CUBE,COOKIES,FIRST_WIN,FIRST_EXIT,NICK_TITLE,NICK_OK,REWARD_HINT,GUIDE_CLAIM,UPGRADE_INFO,INFO_CONFIRM
from onboarding_assets import POWER_TITLE,POWER_ICON
from onboarding_assets import CLAIM_SMALL,ROAD_HEADER,ROAD_HOME
from onboarding_assets import COIN_TITLE,COIN_ICON
from onboarding_assets import UPGRADE_LOBBY_HINT,GUIDE_BRAWLERS
from onboarding_assets import ONE_OWNED,SHELLY_NAME,SHELLY_LEVEL_ONE
from onboarding_assets import SHELLY_DETAIL_NAME,UPGRADE_PRICE,DETAIL_LEVEL_ONE
from onboarding_assets import UPGRADE_TWO_TITLE,UPGRADE_CONFIRM_PRICE

@lru_cache(maxsize=32)
def template(encoded,height):
    raw=cv2.imdecode(np.frombuffer(base64.b64decode(encoded),np.uint8),cv2.IMREAD_COLOR)
    factor=height/720
    return cv2.cvtColor(cv2.resize(raw,(max(2,round(raw.shape[1]*factor)),max(2,round(raw.shape[0]*factor)))),cv2.COLOR_BGR2RGB)

def locate(frame,encoded,region,threshold=.85):
    if not isinstance(frame,np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3 or not frame.size:return None
    h,w=frame.shape[:2];x1,y1,x2,y2=region
    left,top=round(x1*w),round(y1*h);crop=frame[top:round(y2*h),left:round(x2*w)]
    glyph=template(encoded,h)
    if crop.shape[0]<glyph.shape[0] or crop.shape[1]<glyph.shape[1]:return None
    _,score,_,point=cv2.minMaxLoc(cv2.matchTemplate(crop,glyph,cv2.TM_CCOEFF_NORMED))
    if score<threshold:return None
    return left+point[0]+glyph.shape[1]/2,top+point[1]+glyph.shape[0]/2

def tutorial_screen(frame):
    return frame is not None and locate(frame,SID,(0,.055,.26,.17),.93) is not None

def cookie_decline(frame):
    if frame is None or locate(frame,COOKIES,(.35,.85,.67,.92),.94) is None:return None
    h,w=frame.shape[:2]
    left=frame[round(.75*h):round(.84*h),round(.05*w):round(.47*w)].mean(axis=(0,1))
    right=frame[round(.75*h):round(.84*h),round(.53*w):round(.94*w)].mean(axis=(0,1))
    if left.max()<110 and right[0]>200 and right[1]>120 and right[2]<130:
        return w*.26,h*.795
    return None

def onboarding_screen(frame):
    return tutorial_screen(frame) or cookie_decline(frame) is not None or first_result_exit(frame) is not None or first_reward_guide(frame) is not None or instruction_confirm(frame) is not None or power_receipt(frame) or reward_road_home(frame) is not None or guided_upgrade(frame) is not None

def guided_upgrade(frame):
    if frame is None:return None
    if locate(frame,UPGRADE_TWO_TITLE,(.20,.05,.80,.18),.95) is not None:
        price=locate(frame,UPGRADE_CONFIRM_PRICE,(.60,.84,.88,.97),.95)
        h,w=frame.shape[:2];r,g,b=cv2.split(frame[round(.66*h):round(.86*h),round(.65*w):round(.78*w)])
        if price and ((r>210)&(g>130)&(g<230)&(b<185)).mean()>.12:return price
    if locate(frame,SHELLY_DETAIL_NAME,(.04,.17,.28,.30),.95) is not None and locate(frame,DETAIL_LEVEL_ONE,(.69,.38,.78,.50),.95) is not None:
        price=locate(frame,UPGRADE_PRICE,(.72,.75,.97,.90),.95)
        h,w=frame.shape[:2];r,g,b=cv2.split(frame[round(.46*h):round(.63*h),round(.76*w):round(.86*w)])
        if price and ((r>210)&(g>130)&(g<230)&(b<185)).mean()>.20:return price
    if locate(frame,UPGRADE_LOBBY_HINT,(.15,.43,.43,.63),.94) is not None:
        position=locate(frame,GUIDE_BRAWLERS,(0,.35,.12,.50),.94)
        if position:return position
    if locate(frame,ONE_OWNED,(.46,.10,.56,.17),.95) is not None and locate(frame,SHELLY_LEVEL_ONE,(.65,.13,.74,.25),.88) is not None:
        name=locate(frame,SHELLY_NAME,(.56,.29,.70,.40),.72)
        if name:
            h,w=frame.shape[:2]
            return name[0]-w*.06,name[1]-h*.06
    return None

def reward_road_home(frame):
    if frame is None or locate(frame,ROAD_HEADER,(.07,0,.35,.10),.94) is None:return None
    return locate(frame,ROAD_HOME,(.90,0,.99,.12),.94)

def power_receipt(frame):
    if frame is None:return False
    return (locate(frame,POWER_TITLE,(.30,.17,.70,.32),.94) is not None and locate(frame,POWER_ICON,(.40,.45,.60,.65),.92) is not None) or (locate(frame,COIN_TITLE,(.30,.10,.70,.26),.94) is not None and locate(frame,COIN_ICON,(.30,.55,.50,.78),.92) is not None)

def instruction_confirm(frame):
    if frame is None or locate(frame,UPGRADE_INFO,(.20,.04,.80,.20),.94) is None:return None
    return locate(frame,INFO_CONFIRM,(.32,.80,.65,.95),.94)

def first_reward_guide(frame):
    if frame is None:return None
    claim=locate(frame,GUIDE_CLAIM,(.20,.4,.8,.74),.94) or locate(frame,CLAIM_SMALL,(.20,.4,.8,.74),.94)
    if claim and locate(frame,ROAD_HEADER,(.07,0,.35,.10),.94) is not None:
        h,w=frame.shape[:2];r,g,b=cv2.split(frame[round(.23*h):round(.45*h),round(.40*w):round(.65*w)])
        if ((r>210)&(g>130)&(g<230)&(b<185)).mean()>.12:return claim
    if frame is None or locate(frame,REWARD_HINT,(.08,.26,.38,.44),.94) is None:return None
    h,w=frame.shape[:2];crop=frame[round(.08*h):round(.26*h),round(.16*w):round(.28*w)]
    r,g,b=cv2.split(crop)
    if ((r>210)&(g>130)&(g<225)&(b<185)).mean()<.18:return None
    return w*.218,h*.112

def first_result_exit(frame):
    if frame is None or locate(frame,FIRST_WIN,(0,0,.50,.20),.94) is None:return None
    return locate(frame,FIRST_EXIT,(.77,.86,.99,.99),.94)

def generated_name_confirm(frame):
    if not tutorial_screen(frame) or locate(frame,NICK_TITLE,(.28,.09,.72,.18),.94) is None:return None
    h,w=frame.shape[:2];field=frame[round(.27*h):round(.34*h),round(.27*w):round(.56*w)]
    if np.all(field>215,axis=2).mean()<.55 or np.all(field<60,axis=2).mean()<.03:return None
    return locate(frame,NICK_OK,(.59,.25,.78,.36),.94)

def age_controls(frame):
    if not tutorial_screen(frame):return None
    h,w=frame.shape[:2];r,g,b=cv2.split(frame)
    green=((g>185)&(r<110)&(b<110)).astype(np.uint8)*255
    knob=confirm=None
    for x,y,bw,bh in blobs(green):
        if .035*w<bw<.12*w and .065*h<bh<.16*h and .43*h<y<.52*h:
            knob=(x+bw/2,y+bh/2)
        if .14*w<bw<.23*w and .055*h<bh<.16*h and .65*h<y<.74*h:
            confirm=(x+bw/2,y+bh/2)
    if knob and confirm is None:
        patch=frame[round(.675*h):round(.77*h),round(.415*w):round(.59*w)].astype(np.int16)
        neutral=(patch.max(axis=2)-patch.min(axis=2)<12)&(patch.mean(axis=2)>100)&(patch.mean(axis=2)<205)
        if neutral.mean()>.45:confirm=(w*.5,h*.725)
    # Age page has a long grey slider and a separate green confirmation.
    grey=frame[round(.47*h):round(.53*h),round(.29*w):round(.70*w)]
    grey_pixels=(grey[:,:,2]>grey[:,:,0])&(grey[:,:,0]<90)&(grey[:,:,1]<120)
    return (knob,confirm) if knob and confirm and grey_pixels.mean()>.55 else None

def blobs(mask):
    return [cv2.boundingRect(c) for c in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]]

def player_position(frame):
    h,w=frame.shape[:2];r,g,b=cv2.split(frame)
    mask=((g>175)&(r<175)&(b<145)).astype(np.uint8)*255
    candidates=[]
    for x,y,bw,bh in blobs(mask):
        if .03*w<bw<.10*w and .006*h<bh<.03*h and bw>3*bh and .25*w<x<.75*w and .25*h<y<.75*h:
            candidates.append((math.hypot(x+bw/2-w/2,y-h*.58),(x+bw/2,y+bh+h*.095)))
    return min(candidates)[1] if candidates else None

def cube_position(frame,player):
    h,w=frame.shape[:2];r,g,b=cv2.split(frame)
    mask=((g>155)&(r<185)&(b<185)&(g.astype(np.int16)>r.astype(np.int16)+30)).astype(np.uint8)*255
    targets=[]
    for x,y,bw,bh in blobs(mask):
        if not(.021*w<bw<.065*w and .030*h<bh<.095*h and .4<bw/bh<1.6 and .3*w<x<.7*w and .1*h<y<.8*h):continue
        crop=frame[max(0,y-4):min(h,y+bh+4),max(0,x-4):min(w,x+bw+4)]
        gold=(crop[:,:,0]>170)&(crop[:,:,1]>155)&(crop[:,:,2]<130)
        if gold.mean()>.04:targets.append((x+bw/2,y+bh/2))
    return min(targets,key=lambda p:math.dist(p,player)) if targets else None

def path_direction(frame,player,target):
    h,w=frame.shape[:2];cell=max(8,round(h/36));r,g,b=cv2.split(frame)
    obstacles=(r>190)&(g>70)&(g<190)&(b<175)
    mask=obstacles.astype(np.uint8)*255
    obstacles=np.zeros_like(mask)
    for contour in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,bw,bh=cv2.boundingRect(contour)
        if bh>h*.045 and cv2.contourArea(contour)>h*h*.001:
            cv2.drawContours(obstacles,[contour],-1,1,-1)
    obstacles=cv2.dilate(obstacles,np.ones((max(3,round(h*.05)),)*2,np.uint8))
    rows,cols=math.ceil(h/cell),math.ceil(w/cell)
    blocked=set()
    for y in range(rows):
        for x in range(cols):
            cx,cy=(x+.5)*cell,(y+.5)*cell
            if not (.20*w<cx<.82*w and .19*h<cy<.85*h) or np.mean(obstacles[y*cell:(y+1)*cell,x*cell:(x+1)*cell])>.12:blocked.add((x,y))
    start=(int(player[0]/cell),int(player[1]/cell));goal=(int(target[0]/cell),int(target[1]/cell))
    blocked.discard(start);blocked.discard(goal)
    queue=[(0,0,start)];parent={start:None};cost={start:0}
    while queue:
        _,distance,node=heapq.heappop(queue)
        if distance!=cost[node]:continue
        if node==goal:break
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)):
            nxt=node[0]+dx,node[1]+dy
            if not(0<=nxt[0]<cols and 0<=nxt[1]<rows) or nxt in blocked:continue
            if dx and dy and ((node[0]+dx,node[1]) in blocked or (node[0],node[1]+dy) in blocked):continue
            candidate=distance+math.hypot(dx,dy)
            if candidate>=cost.get(nxt,float('inf')):continue
            cost[nxt]=candidate;parent[nxt]=node
            heapq.heappush(queue,(candidate+math.dist(nxt,goal),candidate,nxt))
    if goal not in parent:return None
    path=[];node=goal
    while node!=start:path.append(node);node=parent[node]
    path.reverse()
    waypoint=((path[min(2,len(path)-1)][0]+.5)*cell,(path[min(2,len(path)-1)][1]+.5)*cell) if path else target
    return waypoint[0]-player[0],waypoint[1]-player[1]

def attack_button(frame):
    h,w=frame.shape[:2];hsv=cv2.cvtColor(frame,cv2.COLOR_RGB2HSV)
    mask=(((hsv[:,:,0]<25)|(hsv[:,:,0]>174))&(hsv[:,:,1]>140)&(hsv[:,:,2]>140)).astype(np.uint8)*255
    for x,y,bw,bh in blobs(mask):
        if x>.70*w and y>.57*h and .065*h<bw<.16*h and .065*h<bh<.16*h and .6<bw/bh<1.5:
            return x+bw/2,y+bh/2
    return None

def attack_target(frame,player):
    h,w=frame.shape[:2];r,g,b=cv2.split(frame)
    red=((r>185)&(g<100)&(b<125)).astype(np.uint8)*255
    targets=[]
    for x,y,bw,bh in blobs(red):
        if .025*w<bw<.13*w and .004*h<bh<.025*h and bw>3*bh and .2*w<x<.8*w and .2*h<y<.7*h:
            targets.append((x+bw/2,y+bh+h*.075))
    if targets:return min(targets,key=lambda p:math.dist(p,player))
    orange=((r>215)&(g>120)&(g<205)&(b<115)).astype(np.uint8)*255
    for x,y,bw,bh in blobs(cv2.morphologyEx(orange,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))):
        if .02*w<bw<.2*w and .035*h<bh<.16*h and .2*w<x<.8*w and .2*h<y<.7*h:targets.append((x+bw/2,y+bh/2))
    return min(targets,key=lambda p:math.dist(p,player)) if targets else None

class Onboarding:
    def __init__(self):
        self.last_action=0.;self.phase=None;self.room_started=None
        self.age_position=None

    def pending_transition(self,state):
        return (self.phase in ('guided_upgrade','first_reward','power_receipt','instruction','return_home','nickname')
                and state in ('lobby','brawler_selection','brawler_detail')
                and time.monotonic()-self.last_action < 3)

    def step(self,stage,frame):
        if not onboarding_screen(frame):return False
        now=time.monotonic()
        interval = .25 if self.phase in ('move','attack','super') else 1.5
        if now-self.last_action<interval:return True
        self.last_action=now
        if stage._should_stop() or stage._should_pause():return True
        controller=stage.window_controller;h,w=frame.shape[:2]
        upgrade=guided_upgrade(frame)
        if upgrade:
            self.phase='guided_upgrade';controller.click(*upgrade);return True
        if power_receipt(frame):
            self.phase='power_receipt';controller.click(w*.5,h*.88);return True
        info=instruction_confirm(frame)
        if info:
            self.phase='instruction';controller.click(*info);return True
        reward_guide=first_reward_guide(frame)
        if reward_guide:
            self.phase='first_reward';controller.click(*reward_guide);return True
        home=reward_road_home(frame)
        if home:
            self.phase='return_home';controller.click(*home);return True
        exit_position=first_result_exit(frame)
        if exit_position:
            self.phase='first_result';controller.click(*exit_position);return True
        name_confirm=generated_name_confirm(frame)
        if name_confirm:
            # Keep the nickname generated by the game; never type personal data.
            self.phase='nickname';controller.click(*name_confirm);return True
        decline=cookie_decline(frame)
        if decline:
            self.phase='cookies';controller.click(*decline);return True
        age=age_controls(frame)
        if age:
            knob,confirm=age
            self.phase='age'
            # Original 69.414 slider: centre is 31; this interval selects an adult age.
            if self.age_position is None:self.age_position=random.uniform(.50,.58)
            desired=self.age_position*w
            if abs(knob[0]-desired)<w*.015:
                controller.click(*confirm)
            else:
                controller.touch_down(*knob,pointer_id=controller.PID_JOYSTICK)
                try:
                    controller.touch_move(desired,knob[1],pointer_id=controller.PID_JOYSTICK)
                    stage._sleep_interruptible(.15)
                finally:controller.touch_up(desired,knob[1],pointer_id=controller.PID_JOYSTICK)
            return True
        player=player_position(frame)
        if player is None:return True
        if self.room_started is None:self.room_started=now
        if now-self.room_started>900:
            controller.release_all_inputs();return True
        controller.release_all_inputs();controller.gameplay_frame_time=None
        button=attack_button(frame);enemy=attack_target(frame,player) if button else None
        if enemy:
            from ability_buttons import ready_button
            super_button=ready_button(frame,'super',(1460,820))
            self.phase='super' if super_button else 'attack';origin=super_button or button
            vector=(enemy[0]-player[0],enemy[1]-player[1]);length=math.hypot(*vector)
            if length<1:return True
            target=(origin[0]+vector[0]/length*h*.1,origin[1]+vector[1]/length*h*.1)
            pointer=controller.PID_ATTACK
        else:
            cube=cube_position(frame,player) or locate(frame,CUBE,(.20,.19,.82,.78),.74)
            if cube is None:
                if not button:return True
                cube=(w*.5,h*.27)
            vector=path_direction(frame,player,cube)
            if vector is None:return True
            length=math.hypot(*vector)
            if length<1:return True
            self.phase='move';origin=(w*.115,h*.81);target=(origin[0]+vector[0]/length*h*.12,origin[1]+vector[1]/length*h*.12);pointer=controller.PID_JOYSTICK
        controller.touch_down(*origin,pointer_id=pointer)
        try:
            controller.touch_move(*target,pointer_id=pointer)
            stage._sleep_interruptible(.16 if self.phase=='move' else .07)
        finally:
            controller.touch_up(*origin,pointer_id=pointer)
            controller.release_all_inputs()
        return True
