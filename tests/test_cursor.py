import pytest
from airmouse_ai.cursor import CursorFilter


@pytest.mark.parametrize("size", [(1920,1080),(2400,1350),(2880,1620)])
def test_physical_pixels_mirror_bounds(size):
    c=CursorFilter(*size)
    for mirror in (False,True):
        c.reset()
        center=(size[0]//2,size[1]//2)
        c.update_relative(0,0,mirror,anchor=center)
        for i in range(1,80): c.update_relative(i*.04,i*.04,mirror)
        assert c.position==(0 if mirror else size[0]-1,size[1]-1)


def test_filter_reentry_and_nan():
    c=CursorFilter(1920,1080)
    assert c.update_relative(0,0,False,anchor=(500,500)) is None
    c.update_relative(.05,.05,False)
    x,y=c.update_relative(.05,.05,False)
    assert 500<x<1919 and 500<y<1079
    assert ((x-500)**2+(y-500)**2)**.5 <= 151
    c.reset()
    assert c.update_relative(.1,.1,False,anchor=(x,y)) is None
    assert c.update_relative(float('nan'),.5) is None
    assert c.position is None
