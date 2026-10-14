import pytest
from airmouse_ai.scroll import ScrollFilter


@pytest.mark.parametrize('direction',[1,-1])
def test_bend_direction_stops_and_return_stroke_does_not_scroll(direction):
    f=ScrollFilter()
    assert f.update(0,direction)==0
    result=[f.update(i*.015,direction) for i in range(1,31)]
    assert sum(result)*direction>0
    assert all(x*direction>=0 for x in result)
    for _ in range(6): f.update(.45,direction)
    assert all(f.update(.45,direction)==0 for _ in range(30))
    assert all(f.update(.45-i*.015,direction)==0 for i in range(1,31))


def test_direction_change_and_reset_has_no_initial_wheel():
    f=ScrollFilter(); f.update(0,1)
    for i in range(1,20): f.update(i*.02,1)
    assert f.update(.4,-1)==0
    assert sum(f.update(.4+i*.01,-1) for i in range(1,20))<0
    f.reset()
    assert f.update(.8,1)==0


def test_noise_invalid_and_jump_do_not_scroll():
    f=ScrollFilter(); f.update(.1,1)
    for i in range(50): assert f.update(.1+(.001 if i%2 else -.001),1)==0
    assert f.update(float('nan'),1)==0
    assert f.update(.9,1)==0
    f.reset(); f.update(0,1)
    assert f.update(.9,1)==0


def test_small_bends_accumulate_and_speed_applies():
    def run(speed):
        f=ScrollFilter(); f.update(0,1)
        return sum(f.update(i*.002,1,speed) for i in range(1,151))
    assert run(1)>0
    assert run(3)>run(1)*2.5
    assert run(10)>run(1)*9.5
