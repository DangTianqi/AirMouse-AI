"""Five extended fingers: desktop swipes, without OS input during tests."""
from dataclasses import replace
import math
import pytest
from airmouse_ai.config import Settings
from airmouse_ai.controller import Controller, State
from airmouse_ai.gestures import GestureEngine, Mode, classify
from airmouse_ai.windows_input import WindowsInput
from conftest import hand_pose
from test_windows_input import User32
from test_interactions_v17 import flex


def five(side='Right', dx=0, dy=0, finger_only=False, kind='all_open'):
    h=hand_pose(kind, finger_dx=dx if finger_only else 0, finger_dy=dy if finger_only else 0)
    p=tuple((1-x if side=='Left' else x,y,z) for x,y,z in h.points)
    if not finger_only:
        p=tuple((x+dx,y+dy,z) for x,y,z in p)
    return replace(h,points=p,handedness=side)


def prime(engine,side='Right'):
    events=[]
    for i in range(10):
        events+=engine.update(five(side),i*.04)
    assert [x.kind for x in events]==['TASK_VIEW']
    assert not engine.five.view_armed
    assert engine.mode==Mode.FIVE_FINGER and engine.pointer_blocked


def stroke(engine,dx,dy,start=.4,side='Right',finger_only=False):
    events=[]
    for i in range(1,21):
        events+=engine.update(five(side,dx*i/20,dy*i/20,finger_only),start+(i-1)*.04)
    return events


@pytest.mark.parametrize('side',['Left','Right'])
@pytest.mark.parametrize('dx,dy',[(.09,0),(-.09,0),(0,.09)])
def test_five_fingers_swipe_once_in_all_directions_both_hands(side,dx,dy):
    e=GestureEngine(); prime(e,side)
    events=stroke(e,dx,dy,side=side)
    assert [x.kind for x in events]==['FIVE_SWIPE']
    assert not e.five.armed and e.pointer_blocked
    assert events[0].position[0]*dx+events[0].position[1]*dy>0
    for i in range(30):
        assert e.update(five(side,dx,dy),1.2+i*.04)==[]


@pytest.mark.parametrize('side',['Left','Right'])
def test_finger_motion_without_large_hand_translation_is_enough(side):
    e=GestureEngine(); prime(e,side)
    assert [x.kind for x in stroke(e,.09,0,side=side,finger_only=True)]==['FIVE_SWIPE']


@pytest.mark.parametrize('mirror',[True,False])
@pytest.mark.parametrize('side',['Left','Right'])
@pytest.mark.parametrize('dx,dy,action',[(.09,0,'DESKTOP_RIGHT'),(-.09,0,'DESKTOP_LEFT'),
                                      (0,.09,'SHOW_DESKTOP')])
def test_controller_maps_screen_directions_and_never_moves_cursor(backend,mirror,side,dx,dy,action):
    c=Controller(backend,Settings(mirror=mirror)); c.set_state(State.RUNNING)
    statuses=[]
    for i in range(10): c.process(five(side),i*.04)
    for i in range(1,21):
        statuses.append(c.process(five(side,dx*i/20,dy*i/20),.4+(i-1)*.04)[1])
    if mirror and dx:
        action='DESKTOP_LEFT' if action=='DESKTOP_RIGHT' else 'DESKTOP_RIGHT'
    assert backend.events==[('TASK_VIEW',),(action,)] and statuses.count(action)==1
    assert backend.pos==(960,540) and c.engine.pointer_blocked


def test_hold_jitter_opening_motion_diagonal_and_slow_drift_do_not_trigger():
    e=GestureEngine(); prime(e)
    # Static five fingers open Task View once; jitter must not add a swipe.
    for i in range(10,20): assert e.update(five(),i*.04)==[]
    for i in range(20,100):
        assert e.update(five(dx=.001*math.sin(i),dy=.001*math.cos(i)),i*.04)==[]
    e=GestureEngine(); prime(e)
    assert stroke(e,.09,.09)==[]
    e=GestureEngine(); prime(e)
    for i in range(1,151):
        assert e.update(five(dx=i*.0002),.36+i*.04)==[]


def test_single_bad_frame_or_one_moving_finger_does_not_trigger():
    e=GestureEngine(); prime(e)
    assert e.update(five(dx=.08),.4)==[]
    for i in range(1,10): assert e.update(five(),.4+i*.04)==[]
    h=five(); p=list(h.points)
    for i in range(10,30):
        # Translating just the index cannot stand in for five coordinated fingers.
        for k in (6,7,8):
            x,y,z=h.points[k]; p[k]=(x+.09,y,z)
        events=e.update(replace(h,points=tuple(p)),.4+i*.04)
        assert not any(x.kind=='FIVE_SWIPE' for x in events)


@pytest.mark.parametrize('kind',['point','middle','ring','pinky','scroll','scroll_mr','shortcut','open','thumb'])
def test_other_shapes_never_enter_five_finger_mode(kind):
    assert classify(hand_pose(kind)).mode != Mode.FIVE_FINGER


def test_loss_pause_and_brief_neutral_do_not_rearm_sent_stroke():
    e=GestureEngine(); prime(e)
    assert len(stroke(e,.09,0))==1
    e.update(None,1.2); e.reset()
    for i in range(10): assert e.update(five(),1.3+i*.04)==[]
    assert not e.five.armed
    for i in range(5): e.update(hand_pose('point'),1.7+i*.04)
    for i in range(10): assert e.update(five(),1.9+i*.04)==[]
    assert not e.five.armed
    for i in range(10): e.update(hand_pose('point'),2.3+i*.04)
    reopened=[]
    for i in range(10): reopened+=e.update(five(),2.7+i*.04)
    assert [x.kind for x in reopened]==['TASK_VIEW']
    assert [x.kind for x in stroke(e,-.09,0,start=3.1)]==['FIVE_SWIPE']


def test_loss_before_trigger_discards_old_anchor():
    e=GestureEngine(); prime(e)
    assert stroke(e,.03,0)==[]
    e.update(None,1.2)
    for i in range(20): assert e.update(five(dx=.2),1.3+i*.04)==[]


def test_uncertain_finger_cannot_rearm_even_if_uncertainty_lasts():
    e=GestureEngine(); prime(e)
    assert len(stroke(e,.09,0))==1
    uncertain=flex(five(),0)
    assert classify(uncertain).geometry.fingers[0]==-1
    for i in range(30): e.update(uncertain,1.2+i*.04)
    assert not e.five.armed
    for i in range(10): assert e.update(five(),2.4+i*.04)==[]
    assert stroke(e,-.09,0,start=2.8)==[]


def test_switching_from_drag_releases_before_five_swipe(backend):
    c=Controller(backend,Settings(mirror=False)); c.set_state(State.RUNNING)
    for i in range(30): c.process(hand_pose(pinch=.2),i*.04)
    assert backend.held
    c.process(five(),1.2)
    assert not backend.held and backend.events[-1]==('up',)
    for i in range(1,10): c.process(five(),1.2+i*.04)
    for i in range(1,21): c.process(five(dx=.09*i/20),1.6+(i-1)*.04)
    assert backend.events[-1]==('DESKTOP_RIGHT',)
    assert backend.events.count(('down',))==backend.events.count(('up',))==1


def test_blocked_native_command_reports_no_send_and_requires_new_stroke(backend,monkeypatch):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    monkeypatch.setattr(backend,'system_gesture',lambda action: False)
    statuses=[]
    for i in range(10): c.process(five(),i*.04)
    for i in range(1,21): statuses.append(c.process(five(dx=.09*i/20),.4+(i-1)*.04)[1])
    assert statuses.count('FIVE_BLOCKED')==1 and backend.events==[]
    assert not c.engine.five.armed


@pytest.mark.parametrize('action,keys',[('DESKTOP_LEFT',(0x5B,0x11,0x25)),
                                      ('DESKTOP_RIGHT',(0x5B,0x11,0x27)),
                                      ('TASK_VIEW',(0x5B,0x09)),('SHOW_DESKTOP',(0x5B,0x44))])
def test_system_shortcut_native_order_and_no_stuck_keys(action,keys):
    u=User32(); b=WindowsInput(u)
    assert b.system_gesture(action)
    def flags(k,up=False): return (2 if up else 0)|(1 if k in (0x5B,0x25,0x27) else 0)
    assert u.batches==[[(1,k,flags(k)) for k in keys]+[(1,k,flags(k,True)) for k in reversed(keys)]]
    b.release_all(); assert len(u.batches)==1 and not b.keys_pending and b.pending_keys==()


@pytest.mark.parametrize('partial',range(6))
def test_partial_desktop_shortcut_releases_all_owned_keys(partial):
    u=User32(); u.results=[partial]; b=WindowsInput(u)
    with pytest.raises(OSError): b.system_gesture('DESKTOP_LEFT')
    assert u.batches[-1]==[(1,0x25,3),(1,0x11,2),(1,0x5B,3)]
    assert not b.keys_pending and b.pending_keys==()


def test_failed_cleanup_can_retry_and_physical_keys_are_not_owned():
    u=User32(); u.results=[2,0]; b=WindowsInput(u)
    with pytest.raises(OSError): b.system_gesture('DESKTOP_RIGHT')
    assert b.keys_pending and b.pending_keys==(0x5B,0x11,0x27)
    b.release_all(); assert not b.keys_pending
    u.modifier=0x8000
    batches=len(u.batches)
    assert b.system_gesture('TASK_VIEW') is False
    assert len(u.batches)==batches and not b.keys_pending

@pytest.mark.parametrize('fps',[15,20,24,30])
def test_five_swipe_at_supported_frame_rates(fps):
    e=GestureEngine()
    opened=[]
    for i in range(fps): opened+=e.update(five(),i/fps)
    assert [x.kind for x in opened]==['TASK_VIEW']
    events=[]
    for i in range(1,fps+1):
        events+=e.update(five(dx=.09*i/fps),1+(i-1)/fps)
    assert [x.kind for x in events]==['FIVE_SWIPE']


@pytest.mark.parametrize('event,expected',[('DESKTOP_LEFT','左侧'),('DESKTOP_RIGHT','右侧'),
                                          ('TASK_VIEW','任务视图'),('SHOW_DESKTOP','显示/还原'),
                                          ('FIVE_BLOCKED','未发送'),(None,'0.3秒')])
def test_five_status_visible_in_both_windows(qt,backend,monkeypatch,tmp_path,event,expected):
    from airmouse_ai.ui import Window
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    c=Controller(backend,Settings(floating_preview=True)); c.set_state(State.RUNNING)
    c.engine.mode=Mode.FIVE_FINGER; c.engine.five.armed=False
    w=Window(c)
    class Mailbox:
        ready=True
        error=None
        def isRunning(self): return True
        def take(self): return None,(Mode.FIVE_FINGER,event,24.,5.)
    w.worker=Mailbox()
    try:
        w.poll()
        assert expected in w.action.text() and expected in w.floating.action.text()
    finally:
        w.worker=None; w.close(); qt.processEvents()
