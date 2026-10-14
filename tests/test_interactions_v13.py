"""Regression coverage for strict pinky stopping and screen direction gains."""
from dataclasses import replace
import math
import pytest
from airmouse_ai.config import Settings
from airmouse_ai.controller import Controller,State
from airmouse_ai.cursor import CursorFilter
from airmouse_ai.gestures import Mode,classify
from conftest import hand_pose


def pinky_bend(hand,pip_degrees=0,dip_degrees=0):
    p=list(hand.points)
    x,y,z=p[17]
    pip=math.radians(pip_degrees); dip=pip+math.radians(dip_degrees)
    p[18]=(x,y-.18,z)
    p[19]=(x,y-.18-.15*math.cos(pip),z+.15*math.sin(pip))
    p[20]=(x,y-.18-.15*math.cos(pip)-.15*math.cos(dip),z+.15*math.sin(pip)+.15*math.sin(dip))
    return replace(hand,points=tuple(p))


@pytest.mark.parametrize('pip,dip,state',[(0,0,1),(10,10,1),(20,0,1),(0,20,1),
                                         (25,25,1),(40,40,-1),(90,90,0)])
@pytest.mark.parametrize('reflect',[False,True])
def test_pinky_natural_extension_uncertainty_and_folding(pip,dip,state,reflect):
    h=pinky_bend(hand_pose(),pip,dip)
    if reflect: h=replace(h,points=tuple((1-x,y,z) for x,y,z in h.points))
    pose=classify(h)
    assert pose.geometry.fingers[3]==state
    assert pose.mode==(Mode.PINKY_STOP if state!=0 else Mode.POINTING)


@pytest.mark.parametrize('pinch',[False,True])
def test_clearly_folded_pinky_allows_motion_and_straight_pinky_freezes(backend,pinch):
    c=Controller(backend,Settings(mirror=False)); c.set_state(State.RUNNING)
    for i in range(35):
        h=hand_pose(pinch=.2 if pinch else None)
        c.process(pinky_bend(h,55,55),i*.04)
    backend.events.clear()
    for i in range(15):
        h=hand_pose(pinch=.2 if pinch else None,dx=i*.004 if pinch else 0,
                    finger_dx=0 if pinch else i*.004)
        c.process(pinky_bend(h,55,55),1.4+i*.04)
    assert any(e[0]=='move' for e in backend.events)
    assert backend.held==pinch
    backend.events.clear()
    for i in range(12):
        h=hand_pose(pinch=.2 if pinch else None,dx=i*.01,finger_dx=i*.004)
        c.process(pinky_bend(h),2+i*.04)
    assert backend.events==[] and c.engine.mode==Mode.PINKY_STOP
    assert backend.held==pinch


def displacement(dx,dy,mirror=False,**speeds):
    f=CursorFilter(1000,1000)
    f.update_relative(0,0,mirror,anchor=(500,500),**speeds)
    f.update_relative(0,0,mirror,**speeds)
    # Exercise direction gains below the safety speed cap. A sudden step at 10x
    # correctly hits that cap and cannot be expected to retain an exact ratio.
    for i in range(1,25):
        f.update_relative(dx*i/24,dy*i/24,mirror,**speeds)
    return f.position[0]-500,f.position[1]-500


@pytest.mark.parametrize('direction,dx,dy,axis',[('up',0,-.031,1),('down',0,.031,1),
                                                ('left',-.031,0,0),('right',.031,0,0)])
def test_each_direction_can_reach_ten_without_changing_opposite(direction,dx,dy,axis):
    baseline=displacement(dx,dy)[axis]
    boosted=displacement(dx,dy,**{direction+'_speed':10})[axis]
    assert boosted==pytest.approx(baseline*10)
    assert displacement(-dx,-dy,**{direction+'_speed':10})==displacement(-dx,-dy)


def test_left_right_direction_settings_follow_screen_after_mirroring():
    assert displacement(.031,0,mirror=True,left_speed=3)[0]==pytest.approx(displacement(-.031,0)[0]*3)
    assert displacement(-.031,0,mirror=True,left_speed=3)[0]==displacement(.031,0)[0]


def test_upward_default_is_stronger_and_does_not_change_other_directions():
    s=Settings()
    assert s.cursor_up_speed==1.8
    assert s.cursor_down_speed==1.3 and s.cursor_left_speed==s.cursor_right_speed==1
    assert displacement(0,-.031,up_speed=s.cursor_up_speed)[1]==pytest.approx(displacement(0,-.031)[1]*1.8)


def test_ten_times_gain_does_not_amplify_stationary_tremor():
    f=CursorFilter(1920,1080)
    gains=dict(up_speed=10,down_speed=10,left_speed=10,right_speed=10)
    f.update_relative(0,0,anchor=(800,500),**gains)
    for i in range(100):
        assert f.update_relative(.007*math.sin(i),.007*math.cos(i),**gains) is None
    assert f.position==(800,500)


@pytest.mark.parametrize('pinch',[False,True])
def test_direction_settings_reach_pointer_and_drag(backend,pinch):
    def run(up_speed):
        backend.events.clear(); backend.pos=(960,540); backend.held=False
        c=Controller(backend,Settings(cursor_up_speed=up_speed,cursor_down_speed=.5)); c.set_state(State.RUNNING)
        for i in range(30): c.process(hand_pose(pinch=.2 if pinch else None),i*.04)
        for i in range(15):
            c.process(hand_pose(pinch=.2 if pinch else None,dy=-i*.001 if pinch else 0,
                               finger_dy=0 if pinch else -i*.001),1.2+i*.04)
        return 540-backend.pos[1]
    normal=run(1); faster=run(3)
    assert normal>0 and faster>normal*2.5
