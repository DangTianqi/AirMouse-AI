"""Pinky independence, vertical order and fist recentering regressions."""
from dataclasses import asdict,replace
import pytest
from airmouse_ai.config import Settings,load,save
from airmouse_ai.controller import Controller,State
from airmouse_ai.gestures import GestureEngine,Mode,classify
from conftest import hand_pose
from test_both_hands import sample
from test_interactions_v13 import pinky_bend


@pytest.mark.parametrize('side',['Left','Right'])
@pytest.mark.parametrize('pair',['scroll','scroll_mr'])
@pytest.mark.parametrize('thumb',[False,True])
def test_pinky_does_not_cancel_or_change_scroll(backend,side,pair,thumb):
    def run(pinky):
        backend.events.clear()
        c=Controller(backend,Settings()); c.set_state(State.RUNNING)
        for i in range(8): c.process(sample(side,pair,thumb=thumb,clutch=pinky),i*.04)
        for i in range(1,20):
            c.process(sample(side,pair,thumb=thumb,clutch=pinky,curl=i*.04),.32+i*.04)
        assert not any(e[0] in ('move','down','up','right','ctrl_q') for e in backend.events)
        return [e for e in backend.events if e[0]=='scroll']
    baseline=run(False)
    assert baseline and run(True)==baseline


@pytest.mark.parametrize('side',['Left','Right'])
def test_raising_pinky_during_scroll_keeps_current_stroke(backend,side):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(8): c.process(sample(side,'scroll'),i*.04)
    for i in range(1,9): c.process(sample(side,'scroll',curl=i*.02),.32+i*.04)
    backend.events.clear()
    for i in range(9,20): c.process(sample(side,'scroll',clutch=True,curl=i*.02),.32+i*.04)
    assert any(e[0]=='scroll' for e in backend.events)
    assert c.engine.mode==Mode.SCROLLING


@pytest.mark.parametrize('side',['Left','Right'])
def test_pinky_preserves_click_release_right_click_and_shortcut(backend,side):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(5): c.process(sample(side,pinch=.2,clutch=True),i*.04)
    assert backend.held and backend.events==[('down',)]
    c.process(sample(side,pinch=.5,clutch=True),.20)
    c.process(sample(side,pinch=.5,clutch=True),.25)
    assert not backend.held and backend.events==[('down',),('up',)]
    for i in range(10): c.process(sample(side,'fist'),.3+i*.04)
    for i in range(12): c.process(sample(side,'right'),.7+i*.04)
    assert backend.events.count(('right',))==1
    for i in range(10): c.process(sample(side,'fist'),1.2+i*.04)
    for i in range(30): c.process(sample(side,'shortcut'),1.6+i*.04)
    assert backend.events.count(('ctrl_q',))==1
    assert not any(e[0]=='move' for e in backend.events)


@pytest.mark.parametrize('side',['Left','Right'])
def test_fist_recenters_once_and_requires_neutral(side):
    e=GestureEngine(); events=[]
    assert classify(sample(side,'fist')).mode==Mode.RECENTERING
    for i in range(40):
        current=e.update(sample(side,'fist'),i*.04)
        if i*.04<.5: assert not current
        events+=current
    assert [x.kind for x in events]==['RECENTER']
    # Tracking loss/reset while still clenched must not fire again.
    e.update(None,1.6)
    for i in range(30): assert e.update(sample(side,'fist'),1.64+i*.04)==[]
    for i in range(10): e.update(sample(side,'point'),2.84+i*.04)
    events=[]
    for i in range(20): events+=e.update(sample(side,'fist'),3.24+i*.04)
    assert [x.kind for x in events]==['RECENTER']


@pytest.mark.parametrize('kind',['open','point','middle','ring','pinky','right','shortcut','all_open'])
def test_partial_hand_never_recenters(kind):
    e=GestureEngine()
    events=[]
    for i in range(40): events+=e.update(hand_pose(kind),i*.04)
    assert not any(x.kind=='RECENTER' for x in events)


def test_extended_pinky_and_short_fist_do_not_recenter():
    e=GestureEngine(); events=[]
    for i in range(10): events+=e.update(hand_pose('fist'),i*.04)
    for i in range(30): events+=e.update(pinky_bend(hand_pose('fist'),0,0),.4+i*.04)
    assert not any(x.kind=='RECENTER' for x in events)


@pytest.mark.parametrize('side',['Left','Right'])
@pytest.mark.parametrize('kind',['point','middle','ring'])
def test_recenter_matches_next_finger_without_jump(backend,side,kind):
    backend.pos=(150,90)
    c=Controller(backend,Settings(mirror=False)); c.set_state(State.RUNNING)
    for i in range(20): c.process(sample(side,'fist'),i*.04)
    assert backend.events==[('move',960,540)] and backend.pos==(960,540)
    backend.events.clear()
    for i in range(12): c.process(sample(side,kind,finger_dx=.12),.8+i*.04)
    assert backend.events==[]
    for i in range(15): c.process(sample(side,kind,finger_dx=.12+i*.003),1.28+i*.04)
    assert any(e[0]=='move' for e in backend.events)


def test_fist_releases_left_before_recentering(backend):
    backend.pos=(100,100)
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(30): c.process(hand_pose(pinch=.2),i*.04)
    assert backend.held
    for i in range(20): c.process(hand_pose('fist'),1.2+i*.04)
    assert backend.events==[('down',),('up',),('move',960,540)]


@pytest.mark.parametrize('state',[State.STOPPED,State.PAUSED,State.ERROR])
def test_recenter_does_not_operate_outside_running(backend,state):
    c=Controller(backend,Settings()); c.set_state(state)
    for i in range(30): c.process(hand_pose('fist'),i*.04)
    assert backend.events==[]


@pytest.mark.parametrize('up,down',[(.5,.5),(1,7),(10,10),(9.8,9.9),(4,2)])
def test_vertical_order_survives_validation_controller_and_restart(tmp_path,backend,up,down):
    raw={'version':4,'cursor_up_speed':up,'cursor_down_speed':down}
    settings=Settings.validated(raw)
    assert .5<=settings.cursor_down_speed<settings.cursor_up_speed<=10
    assert settings.cursor_up_speed-settings.cursor_down_speed>=.099
    c=Controller(backend,Settings(cursor_up_speed=up,cursor_down_speed=down))
    assert c.settings.cursor_up_speed>c.settings.cursor_down_speed
    p=tmp_path/'config.json'; save(settings,p)
    assert load(p)==settings
    assert Settings.validated(asdict(settings))==settings


def test_v3_default_speeds_upgrade_once():
    s=Settings.validated({'version':3,'cursor_up_speed':1.6,'cursor_down_speed':1.0,'landmarks':False})
    assert s.version==6 and (s.cursor_up_speed,s.cursor_down_speed)==(1.8,1.3)
    assert not s.landmarks and Settings.validated(asdict(s))==s


def test_vertical_slider_linking_respects_edited_direction(qt,backend,monkeypatch,tmp_path):
    from airmouse_ai.ui import Window
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    w=Window(Controller(backend,Settings()))
    up=w.direction_controls['up'][0]; down=w.direction_controls['down'][0]
    down.setValue(60)
    assert (up.value(),down.value())==(61,60)
    up.setValue(20)
    assert (up.value(),down.value())==(20,19)
    down.setValue(100)
    assert (up.value(),down.value())==(100,99)
    assert w.controller.settings.cursor_up_speed>w.controller.settings.cursor_down_speed
    w.close(); qt.processEvents()
    assert load().cursor_up_speed==10 and load().cursor_down_speed==9.9
