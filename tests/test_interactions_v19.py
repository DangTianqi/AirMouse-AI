"""Five-finger trigger reliability and editable multipliers; no OS input."""
from dataclasses import replace
import math
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from airmouse_ai.config import Settings,load
from airmouse_ai.controller import Controller,State
from airmouse_ai.gestures import GestureEngine,Mode,classify
from conftest import hand_pose
from test_interactions_v18 import five,prime,stroke
from test_interactions_v17 import flex


@pytest.mark.parametrize('side',['Left','Right'])
@pytest.mark.parametrize('dx,dy',[(.048,0),(-.048,0),(0,.048),(0,-.048)])
def test_swipe_started_immediately_after_opening_is_not_discarded(side,dx,dy):
    e=GestureEngine(); assert e.update(five(side),0)==[]
    events=[]
    for i in range(1,7): events+=e.update(five(side,dx*i/6,dy*i/6),i*.04)
    assert [x.kind for x in events]==(['TASK_VIEW'] if dy<0 else ['TASK_VIEW','FIVE_SWIPE'])


@pytest.mark.parametrize('side',['Left','Right'])
def test_old_four_finger_shape_cannot_send_desktop_commands(backend,side):
    c=Controller(backend,Settings());c.set_state(State.RUNNING)
    for i in range(40): c.process(five(side,dx=i*.004,kind='open'),i*.04)
    assert c.engine.mode==Mode.PINKY_STOP and backend.events==[]


def test_natural_near_straight_finger_enters_five_mode_without_relaxing_pointer_lock():
    h=flex(five(),0,38)
    pose=classify(h)
    assert pose.geometry.fingers[0]==-1 and all(pose.geometry.open_digits)
    assert pose.mode==Mode.FIVE_FINGER
    e=GestureEngine()
    for i in range(10): e.update(h,i*.04)
    assert e.mode==Mode.FIVE_FINGER and e.pointer_blocked


def test_brief_uncertainty_preserves_stroke_and_does_not_count_time():
    e=GestureEngine(); prime(e)
    for i in range(1,5): assert e.update(five(dx=i*.006),.36+i*.04)==[]
    anchor=e.five.anchor; elapsed=e.five.ready_s
    for i in range(1,3):
        h=flex(five(dx=.024+i*.003),0,42)
        assert not all(classify(h).geometry.open_digits)
        assert e.update(h,.52+i*.04)==[]
        assert e.five.anchor==anchor and e.five.ready_s==elapsed
    events=[]
    for i in range(1,6): events+=e.update(five(dx=.030+i*.006),.60+i*.04)
    assert [x.kind for x in events]==['FIVE_SWIPE']


def test_long_uncertainty_discards_old_stroke_and_all_uncertain_never_sends():
    e=GestureEngine(); prime(e)
    for i in range(1,4): e.update(five(dx=i*.007),.36+i*.04)
    for i in range(1,9):
        assert e.update(flex(five(dx=.03+i*.005),0,42),.48+i*.04)==[]
    for i in range(10): assert e.update(five(dx=.07),.84+i*.04)==[]
    assert e.five.armed


def test_three_long_fingers_can_agree_with_one_tip_stationary():
    e=GestureEngine(); prime(e)
    events=[]
    for i in range(1,21):
        h=five();p=list(h.points)
        for m in (5,9,13):
            for j in (1,2,3):
                x,y,z=p[m+j];p[m+j]=(x+.06*i/20*j/3,y,z)
        events+=e.update(replace(h,points=tuple(p)),.36+i*.04)
    assert [x.kind for x in events]==['FIVE_SWIPE']


def test_one_tip_outlier_does_not_reset_other_three_tips():
    e=GestureEngine(); prime(e); events=[]
    for i in range(1,21):
        h=five(dx=.06*i/20);p=list(h.points)
        if i in (6,7):
            x,y,z=p[20];p[20]=(x+.3,y,z)
            # Real model world joints may remain stable during one bad image tip.
            h=replace(h,world_points=tuple(((x-.5)*.2,(y-.5)*.2,z*.2) for x,y,z in h.points))
        events+=e.update(replace(h,points=tuple(p)),.36+i*.04)
    assert [x.kind for x in events]==['FIVE_SWIPE']


def test_track_relocation_cannot_send_and_persistent_hold_stays_still():
    e=GestureEngine(); prime(e)
    for i in range(1,20): assert e.update(five(dx=.4),.36+i*.04)==[]
    assert e.five.armed


@pytest.fixture
def window(qt,backend,monkeypatch,tmp_path):
    from airmouse_ai.ui import Window
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    w=Window(Controller(backend,Settings()));w.show();qt.processEvents()
    yield w
    w.close();qt.processEvents()


def type_number(number,text):
    number.setFocus();number.lineEdit().selectAll()
    QTest.keyClicks(number.lineEdit(),text)
    QTest.keyClick(number.lineEdit(),Qt.Key.Key_Return)


@pytest.mark.parametrize('name,setting,value',[('scroll','scroll_speed',3.7),('stabilization','stabilization',1.6),
    ('up','cursor_up_speed',2.8),('down','cursor_down_speed',2.2),
    ('left','cursor_left_speed',4.3),('right','cursor_right_speed',5.9)])
def test_every_multiplier_supports_actual_keyboard_input_and_roundtrip(window,name,setting,value):
    w=window
    number=w.scroll_input if name=='scroll' else w.stabilization_input if name=='stabilization' else w.direction_inputs[name]
    slider=w.scroll_slider if name=='scroll' else w.stabilization_slider if name=='stabilization' else w.direction_controls[name][0]
    type_number(number,str(value))
    assert number.value()==value and slider.value()==round(value*10)
    assert getattr(w.controller.settings,setting)==value
    w.persist();assert getattr(load(),setting)==value
    slider.setValue(31)
    assert number.value()==3.1 and getattr(w.controller.settings,setting)==3.1


def test_vertical_inputs_both_follow_the_last_edited_direction(window):
    w=window
    type_number(w.direction_inputs['down'],'6.0')
    assert (w.direction_inputs['up'].value(),w.direction_inputs['down'].value())==(6.1,6)
    type_number(w.direction_inputs['up'],'2.0')
    assert (w.direction_inputs['up'].value(),w.direction_inputs['down'].value())==(2,1.9)
    assert (w.direction_controls['up'][0].value(),w.direction_controls['down'][0].value())==(20,19)
    assert w.controller.settings.cursor_up_speed==2 and w.controller.settings.cursor_down_speed==1.9


def test_partial_typing_is_not_applied_until_commit_and_blur_commits(window,qt):
    number=window.scroll_input
    number.setFocus();number.lineEdit().selectAll();QTest.keyClicks(number.lineEdit(),'8.4')
    assert window.controller.settings.scroll_speed==2
    window.stabilization_input.setFocus();qt.processEvents()
    assert window.controller.settings.scroll_speed==8.4


@pytest.mark.parametrize('text',['nan','inf','-5','100','abc',''])
def test_invalid_keyboard_text_cannot_save_invalid_multiplier(window,text):
    type_number(window.scroll_input,text)
    assert .5<=window.controller.settings.scroll_speed<=10
    assert math.isfinite(window.controller.settings.scroll_speed)
    assert window.scroll_slider.value()==round(window.scroll_input.value()*10)
    window.persist();assert load().scroll_speed==window.scroll_input.value()


def test_all_inputs_expose_range_and_cap_at_ten(window):
    for slider,number in window.multiplier_inputs.items():
        assert number.minimum()==slider.minimum()/10 and number.maximum()==slider.maximum()/10
        number.setValue(100)
        assert number.value()==(9.9 if slider is window.direction_controls['down'][0] else 10)
    assert window.direction_inputs['up'].value()>window.direction_inputs['down'].value()


@pytest.mark.parametrize('kind,expected',[('open','拇指'),('uncertain','食指'),('all_open','任务视图')])
def test_five_feedback_explains_missing_fingers_and_ready_state(window,qt,kind,expected):
    c=window.controller;c.set_state(State.RUNNING)
    h=flex(five(),0,42) if kind=='uncertain' else hand_pose(kind)
    for i in range(10): c.process(h,i*.04)
    class Mailbox:
        ready=True;error=None
        def isRunning(self):return True
        def take(self):return None,(c.engine.mode,None,24.,5.)
    window.worker=Mailbox()
    try:
        window.poll();assert expected in window.action.text()
    finally:window.worker=None
