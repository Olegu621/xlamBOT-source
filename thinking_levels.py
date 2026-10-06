"""Actual perception/planning budgets. Recommendations never change the choice."""
from collections import deque
import math,time

PROFILES={
 'low':{'walls_interval':.20,'gas_interval':.20,'directions':8,'planning_steps':1},
 'medium':{'walls_interval':.10,'gas_interval':.15,'directions':12,'planning_steps':2},
 'high':{'walls_interval':.05,'gas_interval':.08,'directions':16,'planning_steps':3},
 'maximum':{'walls_interval':0.,'gas_interval':0.,'directions':32,'planning_steps':5},
}
LEVELS=tuple(PROFILES)

class ThinkingQuality:
    def __init__(self,mode='medium',fps_ceiling=60):
        self.fps_ceiling=max(1,min(120,int(fps_ceiling or 60)))
        self.mode=mode if mode in LEVELS else 'medium'
        self.recommended=None;self.observed_fps=None;self.capacity_fps=None
        self.samples=deque();self.candidate=None;self.candidate_since=None
        self.reason='measuring'

    def set_mode(self,mode,now=None):
        if mode not in LEVELS:raise ValueError('Invalid thinking level')
        if mode==self.mode:return
        self.mode=mode;self.samples.clear();self.candidate=None;self.candidate_since=None
        self.recommended=None;self.observed_fps=None;self.capacity_fps=None;self.reason='measuring'

    def observe(self,work_seconds,now=None,capture_fps=None):
        now=time.monotonic() if now is None else now
        if not math.isfinite(work_seconds) or not 0<work_seconds<=10:return self.snapshot()
        if self.samples and now-self.samples[-1][0]>max(3.,work_seconds*2.5):
            self.samples.clear();self.candidate=None;self.candidate_since=None
            self.recommended=None;self.reason='measuring'
        self.samples.append((now,work_seconds))
        while self.samples and now-self.samples[0][0]>60:self.samples.popleft()
        span=now-self.samples[0][0]
        if len(self.samples)<6 or span<8:return self.snapshot()
        self.observed_fps=(len(self.samples)-1)/span
        self.capacity_fps=1/(sum(cost for _,cost in self.samples)/len(self.samples))
        index=LEVELS.index(self.mode)
        desired=self.mode;reason='balanced'
        if self.observed_fps<=15 and self.capacity_fps<=17:
            desired=LEVELS[max(0,index-1)];reason='low_fps' if index else 'minimum'
        elif self.observed_fps>=30 and self.capacity_fps>=35:
            desired=LEVELS[min(3,index+1)];reason='headroom' if index<3 else 'maximum'
        elif capture_fps is not None and 0<capture_fps<=15 and self.capacity_fps>20:
            reason='capture_limit'
        faster_analysis=LEVELS.index(desired)>index
        if desired!=self.candidate:
            self.candidate=desired;self.candidate_since=now
        if desired==self.mode or now-self.candidate_since>=(20 if faster_analysis else 5):
            self.recommended=desired;self.reason=reason
        return self.snapshot()

    def snapshot(self):
        return {'mode':self.mode,'active':self.mode,'recommended':self.recommended,
                'profile':dict(PROFILES[self.mode]),'fps_ceiling':self.fps_ceiling,
                'capacity_fps':round(self.capacity_fps,1) if self.capacity_fps is not None else None,
                'observed_fps':round(self.observed_fps,1) if self.observed_fps is not None else None,
                'status':'ready' if self.recommended is not None else 'measuring','reason':self.reason}
