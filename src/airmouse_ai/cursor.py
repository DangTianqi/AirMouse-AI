"""Small, time-aware relative pointer filter; no prediction or queued motion."""
import math
from collections import deque
from statistics import median
from .config import Tuning


class CursorFilter:
    def __init__(self, width: int, height: int, tuning: Tuning = Tuning()):
        self.width, self.height, self.t = width, height, tuning
        self.reset()

    def reset(self) -> None:
        self.position = None
        self.samples = deque(maxlen=3)
        self.input_anchor = None
        self.filtered = None
        self.previous_sample = None
        self.velocity = (0.0, 0.0)
        self.last_time = None
        self.quiet_s = 0.0
        self.raw_history = deque(maxlen=5)
        self.precise_axes = (False, False)
        self.sample_time = None

    @staticmethod
    def _alpha(cutoff, dt):
        return -math.expm1(-2 * math.pi * cutoff * dt)

    def _intent(self, axis, stabilization):
        """A coherent trend can be much smaller than stationary tremor's envelope."""
        values = [p[axis] for p in self.raw_history]
        if len(values) < 5:
            return False
        def coherent(v, minimum_step):
            steps = [b-a for a,b in zip(v,v[1:])]
            sign = 1 if v[-1]>v[0] else -1
            if not all(d*sign > minimum_step for d in steps):
                return False
            if max(abs(d) for d in steps) > 2*min(abs(d) for d in steps):
                return False
            if abs(v[-1]-v[0]) < self.t.cursor_intent_span*math.sqrt(stabilization):
                return False
            mean = sum(v)/len(v)
            center = (len(v)-1)/2
            slope = sum((i-center)*(x-mean) for i,x in enumerate(v))/sum((i-center)**2 for i in range(len(v)))
            total = sum((x-mean)**2 for x in v)
            residual = sum((x-mean-slope*(i-center))**2 for i,x in enumerate(v))
            return total > 1e-12 and residual/total < .02
        # Four steps reject the tested oscillatory tremor. A clear, larger
        # reversal can respond one frame sooner without chasing old velocity.
        return coherent(values,.00005) or coherent(values[-4:],.006*math.sqrt(stabilization))

    def update_relative(self, x: float, y: float, mirror: bool = True, speed: float = 1.0,
                        anchor: tuple[int, int] | None = None, stabilization: float = 1.0,
                        *, up_speed: float = 1.0, down_speed: float = 1.0,
                        left_speed: float = 1.0, right_speed: float = 1.0,
                        now: float | None = None, precision: bool = True):
        """Reject isolated spikes, smooth positions adaptively, then apply a soft deadband.

        Slow movements retain small steps; fast strokes increase travel automatically.
        Gains are applied after noise rejection, in actual screen directions. Optional
        timestamps describe samples, not calls to the filter. Fractional pixels survive.
        """
        if (not all(math.isfinite(v) for v in
                    (x, y, speed, stabilization, up_speed, down_speed, left_speed, right_speed, *(anchor or ())))
                or min(speed, stabilization, up_speed, down_speed, left_speed, right_speed) <= 0
                or (now is not None and not math.isfinite(now))):
            self.reset()
            return None
        timestamp = (0.0 if self.last_time is None else self.last_time + 1 / 24) if now is None else now
        dt = 1 / 24 if self.last_time is None else timestamp - self.last_time
        if dt <= 0 or dt > self.t.max_frame_gap_s:
            self.reset()
            dt = 1 / 24
        self.last_time = timestamp
        sample = (-x if mirror else x, y)
        # A physical mouse/another application may have moved the cursor since our
        # last output. Re-anchor instead of pulling it back to our cached position.
        external_move = anchor is not None and self.position is not None and math.dist(
            anchor, tuple(round(v) for v in self.position)) > 2
        if self.input_anchor is None or external_move:
            self.samples.clear()
            self.samples.append(sample)
            self.input_anchor = self.filtered = self.previous_sample = sample
            self.position = tuple(float(v) for v in (anchor or (0, 0)))
            self.velocity = (0.0, 0.0)
            self.quiet_s = 0.0
            self.raw_history.clear()
            self.raw_history.append(sample)
            self.precise_axes = (False, False)
            self.sample_time = timestamp
            return None
        self.samples.append(sample)
        self.raw_history.append(sample)
        if len(self.samples) < 3:
            return None
        raw = sample
        sample = tuple(median(s[i] for s in self.samples) for i in (0, 1))
        if math.dist(raw, self.previous_sample) > self.t.finger_max_step and math.dist(
                sample, self.previous_sample) <= self.t.finger_max_step:
            return None  # Do not even advance an old trajectory on a relocalization frame.
        # A median costs one full frame even on a clean trajectory. Once successive
        # steps agree in direction and size, use the newest point without that lag.
        a, b, c = self.samples
        d1 = tuple(y-x for x, y in zip(a, b))
        d2 = tuple(y-x for x, y in zip(b, c))
        n1, n2 = math.hypot(*d1), math.hypot(*d2)
        if n1 > 1e-8 and .25*n1 <= n2 <= 4*n1 and sum(x*y for x, y in zip(d1, d2)) > .8*n1*n2:
            sample = raw
        step = tuple(b - a for a, b in zip(self.previous_sample, sample))
        if math.hypot(*step) > self.t.finger_max_step:
            self.samples.clear()
            self.samples.append(sample)
            self.input_anchor = self.filtered = self.previous_sample = sample
            self.velocity = (0.0, 0.0)
            self.quiet_s = 0.0
            self.raw_history.clear()
            self.raw_history.append(sample)
            self.precise_axes = (False, False)
            self.sample_time = timestamp
            return None
        filter_dt = timestamp-self.sample_time
        self.sample_time = timestamp
        va = self._alpha(self.t.finger_velocity_cutoff, filter_dt)
        self.velocity = tuple(v + va * (d / filter_dt - v) for v, d in zip(self.velocity, step))
        velocity = math.hypot(*self.velocity)
        cutoff = (self.t.finger_min_cutoff + self.t.finger_cutoff_beta * velocity) / math.sqrt(stabilization)
        alpha = self._alpha(cutoff, filter_dt)
        self.filtered = tuple(a + alpha * (b - a) for a, b in zip(self.filtered, sample))
        precise_axes = tuple(precision and self._intent(i,stabilization) for i in (0,1))
        self.filtered = tuple(raw[i] if precise_axes[i] else self.filtered[i] for i in (0,1))
        # Do not release accumulated deadband/filter lag when entering precision.
        # Only the newest deliberate step is eligible, including on reversal.
        previous_raw = self.raw_history[-2]
        self.input_anchor = tuple(previous_raw[i]
                                  if precise_axes[i] and not self.precise_axes[i]
                                  else self.input_anchor[i] for i in (0,1))
        self.precise_axes = precise_axes
        if any(precise_axes):
            velocity = math.hypot(*(self.velocity[i] if precise_axes[i] else 0.0 for i in (0,1)))
        self.previous_sample = sample
        self.quiet_s = self.quiet_s + dt if math.hypot(*step) < 1e-8 else 0.0
        if self.quiet_s >= self.t.finger_settle_s:
            # Discard filter lag once a sample is stationary. Never chase a target
            # after stopping, including with a high direction multiplier.
            self.filtered = sample
            self.velocity = (0.0, 0.0)
            return None
        delta = tuple(b - a for a, b in zip(self.input_anchor, self.filtered))
        radii = tuple(self.t.cursor_fine_deadzone*math.sqrt(stabilization) if active
                      else self.t.finger_deadzone*stabilization for active in precise_axes)
        accepted = tuple(math.copysign(max(0.0, abs(d) - radius), d) for d,radius in zip(delta,radii))
        self.input_anchor = tuple(a + d for a, d in zip(self.input_anchor, accepted))
        # Smooth acceleration uses hand speed, independent of FPS or chosen gains.
        start,end = (self.t.cursor_accel_start,self.t.cursor_accel_end) if precision else (.06,.80)
        blend = max(0.0, min(1.0, (velocity - start) / (end-start)))
        blend = blend * blend * (3 - 2 * blend)
        fine_gain = self.t.cursor_fine_gain if precision else self.t.finger_precision_gain
        acceleration = fine_gain + blend * (self.t.finger_fast_gain-fine_gain)
        gain = self.t.finger_gain * speed * acceleration
        pixels = (accepted[0] * self.width * gain * (left_speed if accepted[0] < 0 else right_speed),
                  accepted[1] * self.height * gain * (up_speed if accepted[1] < 0 else down_speed))
        length = math.hypot(*pixels)
        cap = min(1.0, self.t.cursor_max_speed_px_s * dt / max(length, 1e-8))
        new = (max(0.0, min(self.width - 1, self.position[0] + pixels[0] * cap)),
               max(0.0, min(self.height - 1, self.position[1] + pixels[1] * cap)))
        old = tuple(round(v) for v in self.position)
        self.position = new
        result = tuple(round(v) for v in new)
        return result if result != old else None
