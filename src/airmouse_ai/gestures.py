"""Pure gesture rules: thumb modifier, pinky clutch, true button down/up."""
from dataclasses import dataclass
from enum import Enum
import math
from .config import Tuning
from .hand_geometry import Hand, Geometry, analyze, angle
from .five_finger import FiveFingerSwipe

PAIRS=((0,1),(1,2))


class Mode(str,Enum):
    NONE='NONE'
    POINTING='POINTING'
    SCROLLING='SCROLLING'
    PINCH_CANDIDATE='PINCH_CANDIDATE'
    LEFT_HELD='LEFT_HELD'
    DRAGGING='DRAGGING'
    PINKY_STOP='PINKY_STOP'
    RIGHT_CLICK='RIGHT_CLICK'
    SHORTCUT='SHORTCUT'
    RECENTERING='RECENTERING'
    FIVE_FINGER='FIVE_FINGER'


@dataclass(frozen=True)
class Pose:
    mode: Mode
    geometry: Geometry
    point_finger: int | None=None
    pair: tuple[int,int] | None=None


@dataclass(frozen=True)
class Event:
    kind: str
    position: tuple[float,float] | None=None


def classify(hand: Hand | None,t: Tuning=Tuning()) -> Pose | None:
    g=analyze(hand,t)
    if g is None:
        return None
    fingers=g.fingers
    if g.fist:
        return Pose(Mode.RECENTERING,g)
    if all(g.open_digits) or (all(state!=0 for state in fingers) and g.thumb!=0):
        return Pose(Mode.FIVE_FINGER,g)
    if fingers[0:2]==(0,0) and fingers[2]!=0 and fingers[3]!=0 and g.thumb!=1:
        return Pose(Mode.SHORTCUT,g)
    if fingers==(0,0,0,1) and g.thumb==1:
        return Pose(Mode.RIGHT_CLICK,g)
    # Pinky is a cursor clutch, not an extra finger that cancels wheel commands.
    raised=tuple(i for i,state in enumerate(fingers[:3]) if state==1)
    exact=all(state==0 for i,state in enumerate(fingers[:3]) if i not in raised)
    if exact and raised in PAIRS and g.thumb in (0,1):
        return Pose(Mode.SCROLLING,g,pair=raised)
    if exact and raised in ((0,),(1,),(2,)) and g.thumb==0:
        return Pose(Mode.PINKY_STOP if fingers[3]!=0 else Mode.POINTING,g,point_finger=raised[0])
    return Pose(Mode.PINKY_STOP if fingers[3]!=0 else Mode.NONE,g)


class GestureEngine:
    def __init__(self,tuning: Tuning=Tuning()):
        self.t=tuning
        self.shortcut_armed=True
        self.right_armed=True
        self.recenter_armed=True
        self.pinch_blocked=False
        self.left_pressed=False
        self.pinch_start=None
        self.five=FiveFingerSwipe(tuning)
        self.reset()

    def reset(self):
        self.pinch_blocked |= self.left_pressed or self.pinch_start is not None
        self.mode=Mode.NONE
        self.control_token=None
        self.pending=None
        self.pending_since=None
        self.last_time=None
        self.identity=None
        self.pinch_start=None
        self.left_pressed=False
        self.release_since=None
        self.drag_engaged=False
        self.drag_scale=None
        self.scroll_pair=None
        self.single_since=None
        self.fold_since=None
        self.fold_curl=None
        self.shortcut_neutral=None
        self.right_neutral=None
        self.recenter_neutral=None
        self.pointer_blocked=True
        self.pinky_folded_since=None
        self.five.reset()
        self.five_digits=(False,)*5
        self._reset_shortcut_hold()
        # Hold/stop/tracking loss never rearms either shortcut or a closed pinch.

    def cancel_press(self):
        self.pinch_blocked=True
        self.reset()

    def _release(self):
        pressed=self.left_pressed
        self.reset()
        return [Event('LEFT_UP')] if pressed else []

    def _stable(self,key,mode,now,delay=None):
        if key!=self.pending:
            self.pending=key
            self.pending_since=now
        if now-self.pending_since<(self.t.stable_s if delay is None else delay):
            self.mode=Mode.NONE
            self.control_token=None
            return False
        self.mode=mode
        self.control_token=key
        return True

    def _rearm(self,raw,now):
        for mode,clock,armed,delay in ((Mode.SHORTCUT,'shortcut_neutral','shortcut_armed',self.t.shortcut_release_s),
                                       (Mode.RIGHT_CLICK,'right_neutral','right_armed',self.t.right_release_s),
                                       (Mode.RECENTERING,'recenter_neutral','recenter_armed',self.t.recenter_release_s)):
            if raw==mode:
                setattr(self,clock,None)
            else:
                if getattr(self,clock) is None:
                    setattr(self,clock,now)
                if now-getattr(self,clock)>=delay:
                    setattr(self,armed,True)

    def _update_pinky(self,g,now):
        if g.fingers[3]!=0:
            self.pointer_blocked=True
            self.pinky_folded_since=None
        elif self.pointer_blocked:
            if self.pinky_folded_since is None:
                self.pinky_folded_since=now
            if now-self.pinky_folded_since>=self.t.pinky_release_s:
                self.pointer_blocked=False

    def _reset_shortcut_hold(self):
        self.shortcut_good_s=0.0
        self.shortcut_last_good=None
        self.shortcut_seen_at=None
        self.shortcut_previous_good=False

    def _shortcut(self,g,now):
        self.mode=Mode.SHORTCUT
        self.control_token=None
        if not g.shortcut_ready:
            if self.shortcut_last_good is None or now-self.shortcut_last_good>self.t.shortcut_grace_s:
                self._reset_shortcut_hold()
            self.shortcut_previous_good=False
            self.shortcut_seen_at=now
            return []
        if (self.shortcut_last_good is None or
                (not self.shortcut_previous_good and now-self.shortcut_last_good>self.t.shortcut_grace_s)):
            self.shortcut_good_s=0.0
        else:
            self.shortcut_good_s+=now-self.shortcut_seen_at
        self.shortcut_seen_at=self.shortcut_last_good=now
        self.shortcut_previous_good=True
        if self.shortcut_good_s>=self.t.shortcut_hold_s and self.shortcut_armed:
            self.shortcut_armed=False
            return [Event('CTRL_Q')]
        return []

    def _scroll_pose(self,pose,now):
        """Latch an entered adjacent pair through its bend; never infer a pair from a fist."""
        g=pose.geometry
        pair=self.scroll_pair
        if pair is None:
            return pose
        if pose.mode in (Mode.SHORTCUT,Mode.RECENTERING) or (pose.pair and pose.pair!=pair):
            self.scroll_pair=None
            return pose
        if any(state!=0 for i,state in enumerate(g.fingers) if i not in pair and i!=3):
            self.scroll_pair=None
            return pose
        if pose.point_finger is not None:
            if self.single_since is None:
                self.single_since=now
            if now-self.single_since>=self.t.scroll_single_exit_s:
                self.scroll_pair=None
                return pose
        else:
            self.single_since=None
        if all(g.fingers[i]==0 for i in pair):
            curl=min(g.curls[i] for i in pair)
            if self.fold_since is None or self.fold_curl is None or abs(curl-self.fold_curl)>self.t.scroll_deadzone:
                self.fold_since=now
                self.fold_curl=curl
            if now-self.fold_since>=self.t.scroll_fold_exit_s:
                self.scroll_pair=None
                return pose
        else:
            self.fold_since=None
            self.fold_curl=None
        if g.thumb not in (0,1):
            return Pose(Mode.NONE,g)
        return Pose(Mode.SCROLLING,g,pair=pair)

    def _pinch(self,hand,g,now):
        if not g.pinch_shape:
            return self._release()
        if g.pinch>=self.t.pinch_exit:
            # Freeze on the first open frame; release after one short confirmation.
            self.drag_engaged=False
            self.control_token=None
            if not self.left_pressed:
                self.reset()
                self.pinch_blocked=False
                return []
            if self.release_since is None:
                self.release_since=now
            self.mode=Mode.LEFT_HELD
            if now-self.release_since>=self.t.pinch_release_s:
                events=self._release()
                self.pinch_blocked=False
                return events
            return [Event('POINTER_FREEZE')]
        self.release_since=None
        events=[]
        if not self.left_pressed:
            self.mode=Mode.PINCH_CANDIDATE
            self.control_token=None
            if now-self.pinch_start<self.t.pinch_min_s:
                return []
            self.left_pressed=True
            events.append(Event('LEFT_DOWN'))
        if self.pointer_blocked:
            self.mode=Mode.PINKY_STOP
            self.control_token=None
            self.drag_engaged=False
            return events+([Event('POINTER_FREEZE')] if g.fingers[3]!=0 else [])
        if now-self.pinch_start<self.t.drag_hold_s:
            self.mode=Mode.LEFT_HELD
            self.control_token=('held',)
            return events
        self.mode=Mode.DRAGGING
        if not self.drag_engaged:
            self.drag_engaged=True
            self.drag_scale=g.palm
            self.control_token=('pinch-move',now)
            return events+[Event('DRAG_START',self._pinch_position(hand))]
        return events+[Event('DRAG_MOVE',self._pinch_position(hand))]

    def update(self,hand: Hand | None,now: float) -> list[Event]:
        if not math.isfinite(now):
            return self._release()
        if self.last_time is not None and (now<=self.last_time or now-self.last_time>self.t.max_frame_gap_s):
            return self._release()
        self.last_time=now
        pose=classify(hand,self.t)
        if pose is None:
            return self._release()
        if hand.handedness:
            if self.identity and self.identity!=hand.handedness:
                events=self._release()
                self.identity=hand.handedness
                return events
            self.identity=hand.handedness
        g=pose.geometry
        # Keep an already acquired pointer finger through its extension boundary.
        # Moving that finger naturally bends it a little. Requiring a fresh 147°
        # entry on every frame repeatedly froze it; explicit folding still exits.
        if (self.mode==Mode.POINTING and self.control_token is not None and
                self.control_token[0]=='point' and g.thumb==0 and g.fingers[3]==0):
            finger=self.control_token[1]
            if g.fingers[finger]==-1 and all(
                    state==0 for i,state in enumerate(g.fingers[:3]) if i!=finger):
                pose=Pose(Mode.POINTING,g,point_finger=finger)
        self._update_pinky(g,now)
        self.five_digits=g.open_digits
        if pose.mode!=Mode.FIVE_FINGER:
            if -1 not in g.fingers and g.thumb in (0,1):
                self.five.neutral(now)
            else:
                self.five.reset()  # Uncertain recognition is not a deliberate release.
        if pose.mode!=Mode.SHORTCUT:
            self._reset_shortcut_hold()
        self._rearm(pose.mode,now)
        if g.pinch>=self.t.pinch_exit:
            self.pinch_blocked=False
        if self.pinch_start is not None:
            return self._pinch(hand,g,now)
        pose=self._scroll_pose(pose,now)
        if pose.mode==Mode.FIVE_FINGER:
            self.mode=Mode.FIVE_FINGER
            self.control_token=('five',)
            self.pending=None
            if all(g.open_digits):
                direction=self.five.update(hand,g.palm,now)
                events=[Event('TASK_VIEW')] if self.five.view_pending else []
                if direction is not None:
                    events.append(Event('FIVE_SWIPE',direction))
                return events
            else:
                self.five.uncertain(now)
            return []
        # A latched scrolling pair must not become a click while curling into the palm.
        if pose.mode!=Mode.SCROLLING and self.scroll_pair is None and g.pinch_shape and not self.pinch_blocked and g.pinch<=self.t.pinch_enter:
            self.pinch_start=now
            return self._pinch(hand,g,now)
        if pose.mode==Mode.SCROLLING:
            direction=-1 if g.thumb==1 else 1
            key=('scroll',pose.pair,direction)
            if self._stable(key,Mode.SCROLLING,now):
                self.scroll_pair=pose.pair
                # Both selected fingers bend together; extension resets the stroke.
                return [Event('SCROLL',(direction,min(g.curls[i] for i in pose.pair)))]
            return []
        if pose.mode==Mode.RECENTERING:
            ready=self._stable(('recenter',),Mode.RECENTERING,now,self.t.recenter_hold_s)
            self.mode=Mode.RECENTERING
            if ready and self.recenter_armed:
                self.recenter_armed=False
                return [Event('RECENTER')]
            return []
        if pose.mode==Mode.PINKY_STOP:
            self.mode=Mode.PINKY_STOP
            self.control_token=None
            self.pending=None
            return [Event('POINTER_FREEZE')]
        if pose.mode==Mode.POINTING:
            ready=self._stable(('point',pose.point_finger),Mode.POINTING,now)
            if self.pointer_blocked:
                self.mode=Mode.PINKY_STOP
                self.control_token=None
                return []
            if ready:
                return [Event('POINT_MOVE',g.local[pose.point_finger])]
            return []
        if pose.mode==Mode.SHORTCUT:
            return self._shortcut(g,now)
        if pose.mode==Mode.RIGHT_CLICK:
            if self._stable((pose.mode,),pose.mode,now,self.t.right_hold_s) and self.right_armed:
                self.right_armed=False
                return [Event('RIGHT_CLICK')]
            return []
        self.mode=Mode.NONE
        self.control_token=None
        self.pending=None
        return []

    def _pinch_position(self,hand):
        return ((hand.points[4][0]+hand.points[8][0])/(2*self.drag_scale),
                (hand.points[4][1]+hand.points[8][1])/(2*self.drag_scale))
