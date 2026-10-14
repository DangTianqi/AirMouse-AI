"""Static five-finger Task View and pixel-scale pointer regression checks."""
from dataclasses import replace
import math
import pytest
from airmouse_ai.config import Settings,load,save
from airmouse_ai.cursor import CursorFilter
from airmouse_ai.controller import Controller,State
from airmouse_ai.gestures import GestureEngine,Mode
from test_interactions_v18 import five,prime,stroke
from test_interactions_v17 import flex
from conftest import hand_pose


@pytest.mark.parametrize('side',['Left','Right'])
def test_static_five_opens_task_view_once_without_any_motion(side):
    e=GestureEngine();events=[]
    for i in range(3): assert e.update(five(side),i*.04)==[]
    events+=e.update(five(side),.12)
    for i in range(4,100): events+=e.update(five(side),i*.04)
    assert [x.kind for x in events]==['TASK_VIEW']
    assert not e.five.view_armed and e.five.armed and e.pointer_blocked


@pytest.mark.parametrize('side',['Left','Right'])
def test_upward_movement_no_longer_sends_a_second_command(side):
    e=GestureEngine();prime(e,side)
    assert stroke(e,0,-.12,side=side)==[]
    assert e.five.armed and not e.five.view_armed


@pytest.mark.parametrize('dx,dy,action',[(-.09,0,'DESKTOP_LEFT'),(.09,0,'DESKTOP_RIGHT'),(0,.09,'SHOW_DESKTOP')])
def test_task_view_then_one_supported_swipe_keeps_pointer_locked(backend,dx,dy,action):
    c=Controller(backend,Settings(mirror=False));c.set_state(State.RUNNING)
    for i in range(10):c.process(five(),i*.04)
    for i in range(1,21):c.process(five(dx=dx*i/20,dy=dy*i/20),.36+i*.04)
    for i in range(21,40):c.process(five(dx=dx,dy=dy),.36+i*.04)
    assert backend.events==[('TASK_VIEW',),(action,)]
    assert backend.pos==(960,540) and c.engine.pointer_blocked


def test_short_or_uncertain_five_pose_never_opens_task_view():
    e=GestureEngine()
    e.update(five(),0);e.update(five(),.04)
    assert e.update(hand_pose(),.08)==[]
    e=GestureEngine()
    for i in range(40):assert e.update(flex(five(),0,42),i*.04)==[]


def test_task_view_requires_deliberate_release_after_loss_pause_or_uncertainty():
    e=GestureEngine();prime(e)
    e.update(None,.4);e.reset()
    for i in range(10):assert e.update(five(),.5+i*.04)==[]
    for i in range(10):assert e.update(flex(five(),0,42),.9+i*.04)==[]
    for i in range(10):assert e.update(five(),1.3+i*.04)==[]
    for i in range(10):e.update(hand_pose(),1.7+i*.04)
    events=[]
    for i in range(10):events+=e.update(five(),2.1+i*.04)
    assert [x.kind for x in events]==['TASK_VIEW']


def test_task_view_blocked_feedback_once_without_resend(backend,monkeypatch):
    c=Controller(backend,Settings());c.set_state(State.RUNNING)
    attempts=[]
    def blocked(action):attempts.append(action);return False
    monkeypatch.setattr(backend,'system_gesture',blocked)
    statuses=[c.process(five(),i*.04)[1] for i in range(100)]
    assert attempts==['TASK_VIEW'] and statuses.count('FIVE_BLOCKED')==1
    assert backend.events==[]


@pytest.mark.parametrize('mirror',[True,False])
def test_tiny_monotonic_correction_produces_individual_pixels(mirror):
    f=CursorFilter(1920,1080);f.update_relative(0,0,mirror,anchor=(500,500),now=0)
    moves=[]
    for i in range(1,9):
        p=f.update_relative(i*.0005,0,mirror,now=i/24)
        if p:moves.append(p[0])
    sign=-1 if mirror else 1
    assert moves==[500+sign,500+sign*2]
    assert f.position[1]==500


def test_same_tiny_motion_remains_below_ordinary_mode_deadband():
    f=CursorFilter(1920,1080);f.update_relative(0,0,False,anchor=(500,500),now=0,precision=False)
    for i in range(1,9):assert f.update_relative(i*.0005,0,False,now=i/24,precision=False) is None
    assert f.position==(500,500)


def test_slow_reversal_is_under_300ms_and_does_not_wait_for_old_deadband():
    f=CursorFilter(1920,1080);f.update_relative(0,0,False,anchor=(500,500),now=0)
    for i in range(1,49):f.update_relative(i*.0005,0,False,now=i/24)
    peak=f.position[0];first=None
    for i in range(1,20):
        f.update_relative(.024-i*.0005,0,False,now=2+i/24)
        if first is None and f.position[0]<peak-.5:first=i/24
    assert first is not None and first<=.3


@pytest.mark.parametrize('gain',[1.,10.])
def test_stopping_with_tested_tremor_does_not_create_delayed_drift(gain):
    f=CursorFilter(1920,1080);kw=dict(left_speed=gain,right_speed=gain)
    f.update_relative(0,0,False,anchor=(200,500),now=0,**kw)
    for i in range(1,25):f.update_relative(i*.003,0,False,now=i/24,**kw)
    end=f.position
    for i in range(1,300):f.update_relative(.072+.007*math.sin(i*1.7),.007*math.cos(i*2.1),False,now=1+i/24,**kw)
    assert f.position==end


@pytest.mark.parametrize('pinch',[False,True])
def test_controller_pointer_and_drag_can_make_small_pixel_steps(backend,pinch):
    c=Controller(backend,Settings(mirror=False));c.set_state(State.RUNNING)
    for i in range(35):c.process(hand_pose(pinch=.2 if pinch else None),i*.04)
    backend.events.clear();start=backend.pos[0]
    for i in range(1,31):
        c.process(hand_pose(pinch=.2 if pinch else None,dx=i*.00015 if pinch else 0,
                            finger_dx=0 if pinch else i*.00015),1.36+i*.04)
    moves=[p[1] for p in backend.events if p[0]=='move']
    steps=[b-a for a,b in zip([start]+moves,moves)]
    assert len(moves)>=8 and max(steps)<=2 and min(steps)>=1
    assert backend.held==pinch
    c.set_state(State.STOPPED);assert not backend.held


def test_precision_preference_migrates_persists_and_gui_toggle_reanchors(qt,backend,monkeypatch,tmp_path):
    from airmouse_ai.ui import Window
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    assert Settings.validated({'version':6}).precise_cursor
    save(Settings(precise_cursor=False));assert not load().precise_cursor
    c=Controller(backend,Settings());w=Window(c)
    try:
        assert w.precision_check.isChecked()
        c.set_state(State.RUNNING)
        for i in range(15):c.process(hand_pose(finger_dx=i*.003),i*.04)
        w.precision_check.setChecked(False)
        assert not c.settings.precise_cursor and c.cursor.position is None
        backend.events.clear();c.process(hand_pose(finger_dx=.2),.6)
        assert backend.events==[]
        w.persist();assert not load().precise_cursor
    finally:w.close();qt.processEvents()
