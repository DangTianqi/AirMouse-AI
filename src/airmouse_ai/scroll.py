"""Bend strokes: thumb selects direction, extension rearms without scrolling."""
import math
from .config import Tuning


class ScrollFilter:
    def __init__(self,tuning: Tuning=Tuning()):
        self.t=tuning
        self.reset()

    def reset(self):
        self.previous=None
        self.filtered=None
        self.raw=None
        self.direction=None
        self.remainder=0.0

    def update(self,curl: float,direction: int,speed: float=1.0) -> int:
        if not math.isfinite(curl) or not math.isfinite(speed) or direction not in (-1,1):
            self.reset()
            return 0
        curl=max(0,min(1,curl))
        if self.previous is None or direction!=self.direction:
            self.previous=self.filtered=self.raw=curl
            self.direction=direction
            self.remainder=0.0
            return 0
        if abs(curl-self.raw)>self.t.scroll_max_step:
            self.reset()
            return self.update(curl,direction,speed)
        if curl<self.raw-self.t.scroll_return_deadzone:
            self.previous=self.filtered=self.raw=curl
            self.remainder=0.0
            return 0
        self.raw=curl
        self.filtered+=self.t.scroll_alpha*(curl-self.filtered)
        delta=self.filtered-self.previous
        if delta<-self.t.scroll_deadzone:
            self.previous=self.filtered
            self.remainder=0.0
            return 0
        if delta<self.t.scroll_deadzone:
            return 0
        self.previous=self.filtered
        self.remainder+=delta*self.t.scroll_gain*speed
        amount=math.trunc(self.remainder/self.t.wheel_quantum)*self.t.wheel_quantum
        self.remainder-=amount
        return direction*amount
