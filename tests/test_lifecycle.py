import pytest
from airmouse_ai.config import Settings
from airmouse_ai.controller import Controller, State
from conftest import hand_pose


@pytest.mark.parametrize('state',[State.STOPPED,State.PAUSED,State.ERROR,State.STARTING])
def test_disabled_never_inputs(backend,state):
    c=Controller(backend,Settings())
    c.set_state(state)
    for i in range(60): c.process(hand_pose('scroll',dy=i*.001),i*.04)
    assert backend.events==[]


def test_modes_stop_pause_and_release(backend):
    c=Controller(backend,Settings())
    c.set_state(State.RUNNING)
    for i in range(30): c.process(hand_pose('scroll',curl=i*.025),i*.04)
    assert any(e[0]=='scroll' and e[1]>0 for e in backend.events)
    c.process(None,1.21)
    assert c.scroll.remainder==0
    before=len(backend.events)
    c.set_state(State.PAUSED)
    for i in range(10): c.process(hand_pose(),2+i*.04)
    assert len(backend.events)==before
    c.set_state(State.RUNNING)
    assert c.process(hand_pose(),3)[1] is None
    assert len(backend.events)==before


def test_switch_has_no_first_move_or_scroll(backend):
    c=Controller(backend,Settings())
    c.set_state(State.RUNNING)
    for i in range(10): c.process(hand_pose(),i*.04)
    backend.events.clear()
    for i in range(5): c.process(hand_pose('scroll',dy=.15),.4+i*.04)
    assert backend.events==[]
    for i in range(5): c.process(hand_pose('point',dx=.15),.6+i*.04)
    assert backend.events==[]


def test_camera_failure_releases():
    from airmouse_ai.camera import Camera
    class Cap:
        def isOpened(self): return False
        def release(self): released.append(True)
    class CV:
        CAP_DSHOW=1; CAP_MSMF=2; CAP_ANY=0
        def VideoCapture(self,*args): return Cap()
    released=[]
    with pytest.raises(OSError): Camera(0,CV())
    assert len(released)>=1


def test_missing_model():
    from pathlib import Path
    from airmouse_ai.vision import Vision
    with pytest.raises(FileNotFoundError): Vision(Path('missing-model.task'))
