import math
from dataclasses import replace
import pytest
from airmouse_ai.config import Settings
from airmouse_ai.controller import Controller,State
from airmouse_ai.cursor import CursorFilter
from airmouse_ai.gestures import Hand,GestureEngine,Mode,classify
from conftest import hand_pose


@pytest.mark.parametrize('kind,mode',[('point',Mode.POINTING),('middle',Mode.POINTING),('ring',Mode.POINTING),
    ('scroll',Mode.SCROLLING),('scroll_mr',Mode.SCROLLING),('scroll_rp',Mode.SHORTCUT),
    ('right',Mode.RIGHT_CLICK),('shortcut',Mode.SHORTCUT),('all_open',Mode.FIVE_FINGER)])
@pytest.mark.parametrize('yaw,pitch',[(0,0),(math.pi/2,0),(math.pi,0),(0,1.2),(1.1,-.7)])
@pytest.mark.parametrize('reflect',[False,True])
def test_all_faces_and_both_hands_geometry(kind,mode,yaw,pitch,reflect):
    h=hand_pose(kind)
    def rotate(p):
        x,y,z=p[0]-.5,p[1]-.5,p[2]
        x,z=x*math.cos(yaw)+z*math.sin(yaw),-x*math.sin(yaw)+z*math.cos(yaw)
        y,z=y*math.cos(pitch)-z*math.sin(pitch),y*math.sin(pitch)+z*math.cos(pitch)
        return (-x if reflect else x,y,z)
    xyz=[rotate(p) for p in h.points]
    image=tuple((x+.5,y+.5,z) for x,y,z in xyz)
    world=tuple((x*.20,y*.20,z*.20) for x,y,z in xyz)
    assert classify(Hand(image,world_points=world)).mode==mode


def test_world_geometry_priority():
    h=hand_pose(); p=list(h.points)
    p[6:9]=[(.38,.6,0),(.39,.67,0),(.38,.72,0)]
    world=tuple(((x-.5)*.2,(y-.5)*.2,z*.2) for x,y,z in h.points)
    assert classify(Hand(tuple(p),world_points=world)).mode==Mode.POINTING
    assert classify(Hand(tuple(p))).mode==Mode.RECENTERING


def test_tremor_and_acquisition_spikes_are_ignored():
    c=CursorFilter(1920,1080); c.update_relative(0,0,False,anchor=(800,500))
    assert c.update_relative(.2,.2,False) is None
    assert c.update_relative(0,0,False) is None
    for i in range(300):
        x=.2 if i in (30,100,180) else .007*math.sin(i*1.7)
        assert c.update_relative(x,.007*math.cos(i*2.1),False) is None
    assert c.position==(800.,500.)


def test_small_deliberate_motion_and_no_idle_catchup():
    c=CursorFilter(1920,1080); c.update_relative(0,0,False,anchor=(800,500))
    positions=[c.update_relative(i*.003,0,False) for i in range(1,61)]
    assert any(p is not None and p[0]>900 for p in positions)
    for _ in range(5): c.update_relative(.18,0,False)
    assert all(c.update_relative(.18,0,False) is None for _ in range(100))


@pytest.mark.parametrize('kind',['point','middle','ring'])
def test_finger_not_whole_hand_controls_pointer(backend,kind):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(10): c.process(hand_pose(kind),i*.04)
    for i in range(15): c.process(hand_pose(kind,dx=i*.002,dy=i*.002),.4+i*.04)
    assert backend.events==[]
    for i in range(20): c.process(hand_pose(kind,finger_dx=i*.003),1+i*.04)
    assert any(x[0]=='move' for x in backend.events)


def test_pinky_immediately_freezes_and_reentry_has_no_jump(backend):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(12): c.process(hand_pose(finger_dx=i*.004),i*.04)
    backend.events.clear()
    for i in range(12): c.process(hand_pose('pinky',dx=i*.01),.48+i*.04)
    assert backend.events==[] and c.engine.mode==Mode.PINKY_STOP
    for i in range(10): c.process(hand_pose(finger_dx=.2),1+i*.04)
    assert backend.events==[]


def test_switching_pointer_fingers_reanchors(backend):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(10): c.process(hand_pose(),i*.04)
    backend.events.clear()
    for i in range(10): c.process(hand_pose('ring',finger_dx=.15),.4+i*.04)
    assert backend.events==[]


@pytest.mark.parametrize('pair',['scroll','scroll_mr'])
@pytest.mark.parametrize('thumb',[False,True])
def test_adjacent_pairs_bend_scroll_direction(backend,pair,thumb):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(8): c.process(hand_pose(pair,thumb=thumb),i*.04)
    for i in range(1,19): c.process(hand_pose(pair,thumb=thumb,curl=i*.045),.32+i*.04)
    wheels=[x[1] for x in backend.events if x[0]=='scroll']
    assert wheels and all(v<0 if thumb else v>0 for v in wheels)
    assert not any(x[0]=='move' for x in backend.events)
    assert not backend.held


def test_scroll_thumb_direction_change_does_not_jump(backend):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(8): c.process(hand_pose('scroll'),i*.04)
    for i in range(8): c.process(hand_pose('scroll',curl=i*.07),.32+i*.04)
    backend.events.clear()
    for i in range(8): c.process(hand_pose('scroll',thumb=True,curl=.5),.64+i*.04)
    assert backend.events==[]
    for i in range(1,9): c.process(hand_pose('scroll',thumb=True,curl=.5+i*.025),.96+i*.04)
    assert any(x[0]=='scroll' and x[1]<0 for x in backend.events)


@pytest.mark.parametrize('thumb',[False,True])
def test_ring_pinky_is_reserved_and_never_scrolls(backend,thumb):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(10): c.process(hand_pose('fist'),i*.04)
    for i in range(30): c.process(hand_pose('scroll_rp',thumb=thumb),.4+i*.04)
    for i in range(18): c.process(hand_pose('scroll_rp',thumb=thumb,curl=i*.045),1.6+i*.04)
    assert not any(x[0] in ('scroll','move','down','right') for x in backend.events)
    assert backend.events.count(('ctrl_q',))==(0 if thumb else 1)


def test_old_index_pinky_shortcut_is_disabled(backend):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(10): c.process(hand_pose('fist'),i*.04)
    for i in range(50): c.process(hand_pose('old_shortcut'),.4+i*.04)
    assert backend.events==[]


def test_held_pinch_has_no_arbitrary_duration_limit(backend):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(1001): c.process(hand_pose(pinch=.2),i*.04)
    assert backend.held and backend.events==[('down',)]
    c.process(hand_pose(pinch=.5),40.04)
    c.process(hand_pose(pinch=.5),40.09)
    assert not backend.held and backend.events==[('down',),('up',)]


def test_press_before_one_second_is_frozen_and_after_one_second_moves(backend):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(25): c.process(hand_pose(pinch=.2,dx=i*.001),i*.04)
    assert backend.events==[('down',)] and backend.held
    for i in range(15): c.process(hand_pose(pinch=.2,dx=.025+i*.004),1+i*.04)
    assert any(x[0]=='move' for x in backend.events)
    assert backend.events.count(('down',))==1
    c.process(hand_pose(pinch=.5),1.60); c.process(hand_pose(pinch=.5),1.65)
    assert not backend.held and backend.events.count(('up',))==1
    assert ('click',) not in backend.events


def test_pinky_clutches_held_drag_without_release_or_jump(backend):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(30): c.process(hand_pose(pinch=.2),i*.04)
    assert backend.held
    backend.events.clear()
    for i in range(8): c.process(hand_pose(pinch=.2,clutch=True,dx=i*.02),1.2+i*.04)
    assert backend.events==[] and backend.held
    for i in range(8): c.process(hand_pose(pinch=.2,dx=.20),1.52+i*.04)
    assert backend.events==[] and backend.held
    for i in range(10): c.process(hand_pose(pinch=.2,dx=.20+i*.004),1.84+i*.04)
    assert any(x[0]=='move' for x in backend.events)
    c.process(None,2.24)
    assert not backend.held


@pytest.mark.parametrize('state',[State.STOPPED,State.PAUSED,State.ERROR,State.RUNNING])
def test_lifecycle_releases_even_before_drag_starts(backend,state):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(5): c.process(hand_pose(pinch=.2),i*.04)
    assert backend.held
    c.set_state(state)
    assert not backend.held and backend.events==[('down',),('up',)]


def test_physical_button_is_never_taken_over(backend,monkeypatch):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    monkeypatch.setattr(backend,'left_down',lambda:False)
    for i in range(40): c.process(hand_pose(pinch=.2),i*.04)
    assert not c.drag_active and backend.events==[]


def test_v1_settings_show_skeleton_v2_keeps_preference():
    assert Settings.validated({'version':1,'landmarks':False}).landmarks
    assert not Settings.validated({'version':2,'landmarks':False}).landmarks
