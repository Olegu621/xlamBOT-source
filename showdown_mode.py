"""Select Trio Showdown through independently confirmed event controls."""
import time
import numpy as np
from onboarding import locate
from onboarding_assets import ROAD_HOME
from mode_assets import EVENT_NAV,SHOWDOWN_ICON,TRIO_CHOICE,TRIO_LOBBY,NEW_EVENT,TRIO_WIN,RESULT_NEXT

def trio_win_next(frame):
    if frame is None or locate(frame,TRIO_WIN,(0,0,.56,.17),.90) is None:return None
    point=locate(frame,RESULT_NEXT,(.77,.86,.99,.99),.93)
    if point is None:return None
    h,w=frame.shape[:2];x,y=map(round,point)
    patch=frame[max(0,y-round(h*.03)):min(h,y+round(h*.03)),max(0,x-round(w*.055)):min(w,x+round(w*.055))]
    return point if np.all(patch>200,axis=2).mean()>.04 else None

def selected_trio(frame):
    return frame is not None and locate(frame,TRIO_LOBBY,(.30,.82,.75,.99),.88) is not None

def event_screen(frame):
    return (frame is not None
            and locate(frame,EVENT_NAV,(.75,0,.93,.12),.92) is not None
            and locate(frame,ROAD_HOME,(.90,0,1,.12),.90) is not None)

def trio_choice(frame):
    if not event_screen(frame):return None
    point=locate(frame,TRIO_CHOICE,(0,.24,.98,.88),.88)
    if point is None:return None
    h,w=frame.shape[:2];x,y=map(round,point)
    patch=frame[max(0,y-35):min(h,y+35),min(w,x+45):min(w,x+130)]
    if not patch.size:return None
    yellow=(patch[:,:,0]>190)&(patch[:,:,1]>155)&(patch[:,:,2]<105)
    return (x+90,y) if yellow.mean()>.45 else None

class TrioSelector:
    def __init__(self):
        self.last_action=0.;self.swipes=0

    def step(self,stage,frame,lobby=False):
        if stage._should_stop() or stage._should_pause():return False
        if selected_trio(frame):self.swipes=0;return True
        now=time.monotonic()
        if now-self.last_action<1.5:return False
        h,w=frame.shape[:2];controller=stage.window_controller
        if lobby:
            from screen_evidence import current_lobby
            if not current_lobby(frame):return False
            self.last_action=now;controller.click(w*.54,h*.90);return False
        if not event_screen(frame):return False
        choice=trio_choice(frame)
        if choice:
            self.last_action=now;controller.click(*choice);return False
        tile=locate(frame,SHOWDOWN_ICON,(0,.15,.98,.86),.89)
        if tile:
            self.last_action=now;controller.click(*tile);return False
        new_tile=locate(frame,NEW_EVENT,(0,.20,.98,.85),.94)
        if new_tile:
            self.last_action=now;controller.click(*new_tile);return False
        if self.swipes>=3:
            raise RuntimeError('Trio Showdown was not confirmed in the event menu. / Трио не найдено в меню событий.')
        self.last_action=now;self.swipes+=1
        controller.swipe(w*.76,h*.48,w*.28,h*.48,duration=.3)
        return False
