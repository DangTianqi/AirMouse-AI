"""Natural pinky extension, release hysteresis and Ctrl+Q recognition regressions."""
from dataclasses import replace
import math
import pytest
from airmouse_ai.config import Settings
from airmouse_ai.controller import Controller,State
from airmouse_ai.gestures import GestureEngine,Mode,classify
from conftest import hand_pose
from test_interactions_v13 import pinky_bend


def side(hand,label):
    return replace(hand,points=hand.points if label=='Right' else tuple((1-x,y,z) for x,y,z in hand.points),handedness=label)


def ring_bend(hand,degrees):
    p=list(hand.points); x,y,z=p[13]; a=math.radians(degrees)
    p[14]=(x,y-.18,z)
    p[15]=(x,y-.18-.15*math.cos(a),z+.15*math.sin(a))
    p[16]=(x,y-.18-.15*math.cos(a)-.15*math.cos(2*a),z+.15*math.sin(a)+.15*math.sin(2*a))
    return replace(hand,points=tuple(p))


def shortcut(label='Right',uncertain=False,thumb_uncertain=False):
    h=pinky_bend(hand_pose('shortcut'),20,20)
    if uncertain: h=ring_bend(h,35)
    if thumb_uncertain:
        p=list(h.points); p[4]=(.30,.60,0); h=replace(h,points=tuple(p))
        assert classify(h).geometry.thumb==-1
    return side(h,label)


@pytest.mark.parametrize('label',['Left','Right'])
@pytest.mark.parametrize('pinch',[False,True])
def test_naturally_extended_pinky_freezes_pointer_and_drag(backend,label,pinch):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(35): c.process(side(hand_pose(pinch=.2 if pinch else None),label),i*.04)
    backend.events.clear()
    for i in range(20):
        h=hand_pose(pinch=.2 if pinch else None,dx=i*.01,finger_dx=i*.004)
        c.process(side(pinky_bend(h,20,20),label),1.4+i*.04)
    assert c.engine.pointer_blocked and c.engine.mode==Mode.PINKY_STOP
    assert not any(e[0]=='move' for e in backend.events)
    assert backend.held==pinch


@pytest.mark.parametrize('label',['Left','Right'])
def test_initial_uncertain_pinky_cannot_move_pointer(backend,label):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(30):
        h=pinky_bend(hand_pose(finger_dx=i*.004),40,40)
        c.process(side(h,label),i*.04)
    assert c.engine.pointer_blocked and backend.events==[]


def test_single_folded_glitch_does_not_unlock_and_release_reanchors(backend):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(10): c.process(pinky_bend(hand_pose(),20,20),i*.04)
    backend.events.clear()
    c.process(hand_pose(finger_dx=.2),.4)  # One wrong folded estimate.
    for i in range(8): c.process(pinky_bend(hand_pose(finger_dx=.2),40,40),.44+i*.04)
    assert c.engine.pointer_blocked and backend.events==[]
    for i in range(10): c.process(hand_pose(finger_dx=.2),.76+i*.04)
    assert not c.engine.pointer_blocked and backend.events==[]
    for i in range(15): c.process(hand_pose(finger_dx=.2+i*.004),1.16+i*.04)
    assert any(e[0]=='move' for e in backend.events)


@pytest.mark.parametrize('label',['Left','Right'])
@pytest.mark.parametrize('thumb_uncertain',[False,True])
def test_ctrl_q_works_as_first_gesture_with_natural_pinky(label,thumb_uncertain):
    e=GestureEngine(); events=[]; h=shortcut(label,thumb_uncertain=thumb_uncertain)
    assert classify(h).mode==Mode.SHORTCUT and classify(h).geometry.shortcut_ready
    for i in range(40):
        current=e.update(h,i*.04)
        if i*.04<.8: assert not any(x.kind=='CTRL_Q' for x in current)
        events+=current
    assert [x.kind for x in events]==['CTRL_Q']
    assert e.pointer_blocked


@pytest.mark.parametrize('label',['Left','Right'])
def test_shortcut_brief_uncertain_frames_pause_instead_of_restart(label):
    e=GestureEngine(); events=[]
    for i in range(55):
        h=shortcut(label,uncertain=i%6==5)
        if i%6==5:
            assert classify(h).mode==Mode.SHORTCUT
            assert not classify(h).geometry.shortcut_ready
        events+=e.update(h,i*.04)
    assert [x.kind for x in events]==['CTRL_Q']


def test_long_uncertainty_restarts_shortcut_hold():
    e=GestureEngine(); events=[]
    for i in range(15): events+=e.update(shortcut(),i*.04)
    for i in range(6): events+=e.update(shortcut(uncertain=True),.6+i*.04)
    for i in range(10): events+=e.update(shortcut(),.84+i*.04)
    assert not events
    for i in range(15): events+=e.update(shortcut(),1.24+i*.04)
    assert [x.kind for x in events]==['CTRL_Q']


def test_valid_shortcut_frames_at_low_fps_still_accumulate():
    e=GestureEngine(); events=[]
    for i in range(8): events+=e.update(shortcut(),i*.16)
    assert [x.kind for x in events]==['CTRL_Q']


def test_alternating_brief_uncertainty_can_confirm_but_not_before_valid_time():
    e=GestureEngine(); events=[]
    for i in range(51):
        current=e.update(shortcut(uncertain=i%2==1),i*.04)
        if i*.04<1.6: assert not any(x.kind=='CTRL_Q' for x in current)
        events+=current
    assert [x.kind for x in events]==['CTRL_Q']


def test_uncertain_pose_alone_never_sends_and_never_moves():
    e=GestureEngine(); events=[]
    for i in range(60): events+=e.update(shortcut(uncertain=True),i*.04)
    assert not events and e.pointer_blocked


def test_shortcut_no_repeat_after_noise_loss_or_reset_until_real_neutral():
    e=GestureEngine(); events=[]
    for i in range(30): events+=e.update(shortcut(),i*.04)
    assert [x.kind for x in events]==['CTRL_Q']
    for i in range(10): assert e.update(shortcut(uncertain=True),1.2+i*.04)==[]
    e.update(None,1.6)
    for i in range(30): assert e.update(shortcut(),1.64+i*.04)==[]
    for i in range(10): e.update(hand_pose('ring'),2.84+i*.04)
    events=[]
    for i in range(30): events+=e.update(shortcut(),3.24+i*.04)
    assert [x.kind for x in events]==['CTRL_Q']


@pytest.mark.parametrize('kind',['point','middle','ring','right','old_shortcut','open','all_open'])
def test_other_gestures_never_send_ctrl_q(kind):
    e=GestureEngine(); events=[]
    for i in range(40): events+=e.update(hand_pose(kind),i*.04)
    assert not any(x.kind=='CTRL_Q' for x in events)


def test_fully_extended_thumb_does_not_send_ctrl_q():
    e=GestureEngine(); events=[]
    for i in range(40): events+=e.update(hand_pose('shortcut',thumb=True),i*.04)
    assert not any(x.kind=='CTRL_Q' for x in events)


def test_physical_key_block_is_reported_without_claiming_sent(backend,monkeypatch):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    monkeypatch.setattr(backend,'ctrl_q',lambda:False)
    statuses=[c.process(shortcut(),i*.04)[1] for i in range(40)]
    assert statuses.count('CTRL_Q_BLOCKED')==1 and 'CTRL_Q' not in statuses
    assert backend.events==[]


@pytest.mark.parametrize('label',['Left','Right'])
@pytest.mark.parametrize('thumb',[False,True])
def test_pinky_lock_does_not_block_wheel_or_pinch_release(backend,label,thumb):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(8): c.process(side(pinky_bend(hand_pose('scroll',thumb=thumb),20,20),label),i*.04)
    for i in range(1,18): c.process(side(pinky_bend(hand_pose('scroll',thumb=thumb,curl=i*.04),20,20),label),.32+i*.04)
    assert c.engine.pointer_blocked and any(e[0]=='scroll' for e in backend.events)
    assert not any(e[0]=='move' for e in backend.events)


def test_ui_shows_block_reason_on_main_and_floating(qt,backend,monkeypatch,tmp_path):
    from PySide6.QtGui import QImage
    from airmouse_ai.ui import Window
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    w=Window(Controller(backend,Settings(floating_preview=True))); w.show(); qt.processEvents()
    image=QImage(480,360,QImage.Format.Format_RGB888)
    class Mailbox:
        ready=True
        error=None
        def isRunning(self): return True
        def take(self): return image,(Mode.SHORTCUT,'CTRL_Q_BLOCKED',24.,5.)
    w.worker=Mailbox(); w.controller.set_state(State.RUNNING)
    try:
        w.poll(); qt.processEvents()
        assert '未发送' in w.action.text() and '未发送' in w.floating.action.text()
    finally:
        w.worker=None; w.close(); qt.processEvents()


def test_ui_shows_confirmation_progress(qt,backend,monkeypatch,tmp_path):
    from airmouse_ai.ui import Window
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(10): c.process(shortcut(),i*.04)
    w=Window(c); w.show(); qt.processEvents()
    class Mailbox:
        ready=True
        error=None
        def isRunning(self): return True
        def take(self): return None,(Mode.SHORTCUT,None,24.,5.)
    w.worker=Mailbox()
    try:
        w.poll()
        assert '45%' in w.action.text() and 'Ctrl+Q' in w.action.text()
    finally:
        w.worker=None; w.close(); qt.processEvents()
