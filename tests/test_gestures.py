import math
from dataclasses import replace
import pytest
from airmouse_ai.gestures import GestureEngine,Hand,Mode,classify
from conftest import hand_pose


@pytest.mark.parametrize('kind,mode',[('point',Mode.POINTING),('middle',Mode.POINTING),('ring',Mode.POINTING),
    ('thumb',Mode.NONE),('pinky',Mode.PINKY_STOP),('scroll',Mode.SCROLLING),('scroll_mr',Mode.SCROLLING),
    ('scroll_rp',Mode.SHORTCUT),('right',Mode.RIGHT_CLICK),('shortcut',Mode.SHORTCUT),('fist',Mode.RECENTERING),('open',Mode.PINKY_STOP),('all_open',Mode.FIVE_FINGER)])
@pytest.mark.parametrize('rotation',[0,.7,-1.3,math.pi])
def test_rotated_classification(kind,mode,rotation):
    assert classify(hand_pose(kind,rotation=rotation)).mode==mode


@pytest.mark.parametrize('hand',[None,Hand(()),Hand(((0.,0.,0.),)*21),Hand(((float('nan'),0.,0.),)*21)])
def test_invalid(hand):
    e=GestureEngine()
    assert e.update(hand,0)==[] and e.mode==Mode.NONE


def feed(e,kind='point',start=0,count=6,**kwargs):
    result=[]
    for i in range(count): result+=e.update(hand_pose(kind,**kwargs),start+i*.04)
    return result


def press(e,start=0):
    return feed(e,start=start,count=4,pinch=.2)


def test_stability_and_pointer_jitter():
    e=GestureEngine()
    for i in range(20):
        assert e.update(hand_pose('point' if i%2 else 'middle'),i*.04)==[]
    assert any(x.kind=='POINT_MOVE' for x in feed(e,start=1))


def test_pinch_is_real_down_then_up_no_synthetic_click():
    e=GestureEngine()
    events=press(e)
    assert [x.kind for x in events]==['LEFT_DOWN']
    assert e.left_pressed and e.mode==Mode.LEFT_HELD
    for t in (.16,.20,.24): events+=e.update(hand_pose(pinch=.2),t)
    events+=e.update(hand_pose(pinch=.5),.28)
    events+=e.update(hand_pose(pinch=.5),.33)
    assert [x.kind for x in events if x.kind in ('LEFT_DOWN','LEFT_UP','LEFT_CLICK')]==['LEFT_DOWN','LEFT_UP']
    assert not e.left_pressed


def test_short_noise_touch_never_presses():
    e=GestureEngine()
    assert e.update(hand_pose(pinch=.2),0)==[]
    assert e.update(hand_pose(pinch=.5),.04)==[]
    assert not e.left_pressed


def test_hold_never_repeats_down_and_moves_only_after_one_second():
    e=GestureEngine(); events=[]
    for i in range(26):
        current=e.update(hand_pose(pinch=.2),i*.04)
        if i<25: assert not any(x.kind in ('DRAG_START','DRAG_MOVE') for x in current)
        events+=current
    assert sum(x.kind=='LEFT_DOWN' for x in events)==1
    assert sum(x.kind=='DRAG_START' for x in events)==1
    assert e.mode==Mode.DRAGGING
    assert [x.kind for x in e.update(hand_pose(pinch=.2,dx=.01),1.04)]==['DRAG_MOVE']


@pytest.mark.parametrize('reason',['lost','gap','invalid','shape','hand_switch'])
def test_pressed_button_safely_releases(reason):
    e=GestureEngine()
    h=replace(hand_pose(pinch=.2),handedness='Right')
    for i in range(4): e.update(h,i*.04)
    assert e.left_pressed
    now=.16; sample=h
    if reason=='lost': sample=None
    if reason=='gap': now=.6
    if reason=='invalid': now=float('nan')
    if reason=='shape': sample=hand_pose('open')
    if reason=='hand_switch': sample=replace(h,handedness='Left')
    assert any(x.kind=='LEFT_UP' for x in e.update(sample,now))
    assert not e.left_pressed


def test_pause_or_loss_requires_open_before_repress():
    e=GestureEngine(); press(e)
    e.reset()
    assert feed(e,start=1,count=10,pinch=.2)==[]
    e.update(hand_pose(),1.44)
    assert any(x.kind=='LEFT_DOWN' for x in press(e,1.48))


def test_fist_cannot_press_even_with_touching_thumb():
    e=GestureEngine()
    assert not classify(hand_pose('fist',pinch=.1)).geometry.pinch_shape
    assert not any(x.kind in ('LEFT_DOWN','RIGHT_CLICK') for x in feed(e,'fist',count=20,pinch=.1))


def test_right_click_once_per_thumb_pinky_raise():
    e=GestureEngine()
    events=feed(e,'right',count=40)
    assert [x.kind for x in events]==['RIGHT_CLICK']
    e.update(None,1.65)
    assert feed(e,'right',start=1.7,count=15)==[]
    feed(e,'fist',start=2.4,count=10)
    assert [x.kind for x in feed(e,'right',start=2.85,count=12)]==['RIGHT_CLICK']


def test_ring_pinky_ctrl_q_once_after_neutral():
    e=GestureEngine()
    feed(e,'fist',count=10)
    assert [x.kind for x in feed(e,'shortcut',start=.4,count=40)]==['CTRL_Q']
    e.reset()
    assert feed(e,'shortcut',start=2.1,count=25)==[]


def test_single_thumb_is_modifier_never_mouse():
    e=GestureEngine()
    events=feed(e,'thumb',count=30)
    assert not any(x.kind in ('POINT_MOVE','LEFT_DOWN','SCROLL','CTRL_Q','RIGHT_CLICK') for x in events)


def test_middle_alone_does_not_do_old_right_click():
    e=GestureEngine()
    events=feed(e,'middle',count=15)
    assert any(x.kind=='POINT_MOVE' for x in events)
    assert not any(x.kind=='RIGHT_CLICK' for x in events)
