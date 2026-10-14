"""Five-finger desktop swipes with bounded state, brief uncertainty grace and no IO."""
import math
from statistics import median
from .config import Tuning


class FiveFingerSwipe:
    def __init__(self, tuning: Tuning = Tuning()):
        self.t = tuning
        self.armed = True
        self.view_armed = True
        self.reset()

    def _clear_motion(self):
        self.anchor = self.previous = None
        self.scale = None
        self.started = None
        self.last_good = None
        self.pose_ready = False
        self.ready_s = 0.0
        self.candidate = None
        self.confirm_s = 0.0
        self.candidate_good = False
        self.progress = 0.0
        self.view_pending = False

    def reset(self):
        # Pause/loss clears the stroke, never permission to repeat a sent command.
        self._clear_motion()
        self.neutral_since = None

    def neutral(self, now):
        self._clear_motion()
        if self.neutral_since is None:
            self.neutral_since = now
        if now-self.neutral_since >= self.t.five_release_s:
            self.armed = True
            self.view_armed = True

    def uncertain(self, now):
        self.neutral_since = None
        self.pose_ready = self.candidate_good = False
        if self.last_good is None or now-self.last_good > self.t.five_grace_s+1e-9:
            self._clear_motion()

    def _seed(self, points, palm, now):
        self._clear_motion()
        self.anchor = self.previous = points
        self.scale, self.last_good = palm, now
        self.pose_ready = True

    def update(self, hand, palm, now):
        self.view_pending = False
        self.neutral_since = None
        if not self.armed:
            return None
        # Thumb must be open, but need not travel as far as the long fingers.
        # Three agreeing long-finger tips tolerate one noisy landmark.
        points = tuple((hand.points[i][0]*hand.aspect, hand.points[i][1]) for i in (8,12,16,20))
        if (self.anchor is None or
                (not self.pose_ready and now-self.last_good > self.t.five_grace_s+1e-9)):
            self._seed(points,palm,now)
            return None
        valid = [i for i in range(4) if math.dist(points[i],self.previous[i])/self.scale <= self.t.five_max_step]
        if len(valid) < 3:
            self._seed(points,palm,now)
            return None
        dt = now-self.last_good if self.pose_ready else 0.0
        self.ready_s += dt
        self.last_good, self.pose_ready, self.previous = now, True, points
        deltas = [tuple((b-a)/self.scale for a,b in zip(self.anchor[i],points[i])) for i in valid]
        dx,dy = (median(d[a] for d in deltas) for a in (0,1))
        axis = 0 if abs(dx)>=abs(dy) else 1
        dominant,cross = (dx,dy) if axis==0 else (dy,dx)
        sign = 1 if dominant>0 else -1
        distance = abs(dominant)
        self.progress = min(1.0,distance/self.t.five_distance)
        votes = sum(d[axis]*sign >= self.t.five_distance*.35 for d in deltas)
        if distance < self.t.five_start_distance:
            self.started = None
        elif self.started is None and votes >= 3:
            self.started = now
        if self.started is not None and now-self.started > self.t.five_stroke_s:
            self._seed(points,palm,now)
            return None
        if self.view_armed and self.ready_s+1e-9 >= self.t.five_hold_s:
            self.view_armed = False
            self.view_pending = True
        allowed = axis==0 or sign>0  # Upward swipes have been removed.
        if allowed and distance >= self.t.five_distance and distance >= self.t.five_axis_ratio*abs(cross) and votes >= 3:
            direction = (axis,sign)
            if self.candidate != direction:
                self.candidate, self.confirm_s = direction, 0.0
            elif self.candidate_good:
                self.confirm_s += dt
            self.candidate_good = True
            if self.ready_s+1e-9 >= self.t.five_hold_s and self.confirm_s+1e-9 >= self.t.five_confirm_s:
                self.armed = False
                return (dx,dy)
        else:
            self.candidate = None
            self.confirm_s = 0.0
            self.candidate_good = False
        return None
