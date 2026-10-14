from dataclasses import replace
import pytest
from airmouse_ai.gestures import Hand,GestureEngine,Mode
from airmouse_ai.controller import Controller,State
from airmouse_ai.config import Settings
from conftest import hand_pose


def sample(side,kind='point',**kwargs):
    h=hand_pose(kind,**kwargs)
    p=h.points if side=='Right' else tuple((1-x,y,z) for x,y,z in h.points)
    return Hand(p,handedness=side)


@pytest.mark.parametrize('side',['Left','Right'])
@pytest.mark.parametrize('kind',['point','middle','ring'])
def test_both_hands_pointer_fingers(side,kind):
    e=GestureEngine(); events=[]
    for i in range(10): events+=e.update(sample(side,kind),i*.04)
    assert any(x.kind=='POINT_MOVE' for x in events)


@pytest.mark.parametrize('side',['Left','Right'])
def test_both_hands_left_down_and_up(side):
    e=GestureEngine(); events=[]
    for i in range(5): events+=e.update(sample(side,pinch=.2),i*.04)
    events+=e.update(sample(side,pinch=.5),.20)
    events+=e.update(sample(side,pinch=.5),.25)
    assert [x.kind for x in events if x.kind in ('LEFT_DOWN','LEFT_UP')]==['LEFT_DOWN','LEFT_UP']


@pytest.mark.parametrize('side',['Left','Right'])
@pytest.mark.parametrize('kind,event',[('right','RIGHT_CLICK'),('shortcut','CTRL_Q')])
def test_both_hands_commands(side,kind,event):
    e=GestureEngine(); events=[]
    for i in range(10): e.update(sample(side,'fist'),i*.04)
    for i in range(35): events+=e.update(sample(side,kind),.4+i*.04)
    assert [x.kind for x in events]==[event]


def test_switch_hands_while_left_held_releases(backend):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(6): c.process(sample('Right',pinch=.2),i*.04)
    assert backend.held
    c.process(sample('Left',pinch=.2),.24)
    assert not backend.held and c.engine.mode==Mode.NONE
    assert backend.events.count(('up',))==1


@pytest.mark.parametrize('side',['Left','Right'])
@pytest.mark.parametrize('kind',['point','middle','ring'])
def test_both_hands_same_image_direction(backend,side,kind):
    c=Controller(backend,Settings(mirror=False)); c.set_state(State.RUNNING)
    for i in range(10): c.process(sample(side,kind),i*.04)
    start=backend.pos[0]
    for i in range(20):
        dx=i*.003*(1 if side=='Right' else -1)
        c.process(sample(side,kind,finger_dx=dx),.4+i*.04)
    assert backend.pos[0]>start
