import math
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from airmouse_ai.gestures import Hand


def hand_pose(kind="point", dy=0.0, dx=0.0, pinch=None, rotation=0.0,
              finger_dx=0.0,finger_dy=0.0,right_pinch=None,
              thumb=False,curl=0.0,clutch=False):
    p = [(0.5, 0.9, 0.0)] * 21
    p[1:5] = [(0.43, 0.83, 0), (0.33, 0.75, 0), (0.32, 0.69, 0), (0.34, 0.68, 0)]
    extended = {"point": [5],"index":[5],"middle":[9],"ring":[13],"pinky":[17],
                "scroll": [5,9],"scroll_mr":[9,13],"scroll_rp":[13,17],
                "shortcut": [13,17],"old_shortcut":[5,17],"fist": [],"thumb":[],
                "open": [5,9,13,17],"all_open":[5,9,13,17],"right":[17]}[kind].copy()
    if clutch and 17 not in extended: extended.append(17)
    thumb = thumb or kind in ('right','thumb','all_open')
    if thumb:
        p[1:5]=[(.39,.84,0),(.30,.78,0),(.18,.70,0),(.06,.62,0)]
    for mcp, x in zip((5, 9, 13, 17), (0.38, 0.47, 0.56, 0.65)):
        p[mcp] = (x, 0.68, 0)
        if mcp in extended:
            p[mcp+1:mcp+4] = [(x, 0.50, 0), (x, 0.35, 0), (x, 0.20, 0)]
            if curl:
                theta=curl*math.pi/2
                p[mcp+2]=(x,.50-.15*math.cos(theta),.15*math.sin(theta))
                p[mcp+3]=(x,.50-.15*math.cos(theta)-.15*math.cos(2*theta),
                           .15*math.sin(theta)+.15*math.sin(2*theta))
        else:
            p[mcp+1:mcp+4] = [(x, 0.53, 0), (x+0.025, 0.66, 0), (x, 0.76, 0)]
        if mcp in extended:
            for j in (1,2,3):
                x,y,z=p[mcp+j]
                p[mcp+j]=(x+finger_dx*j/3,y+finger_dy*j/3,z)
    if pinch is not None:
        p[4] = (p[8][0] + pinch*0.27, p[8][1], 0)
    if right_pinch is not None:
        p[4] = (p[12][0]+right_pinch*.27,p[12][1],0)
    c, s = math.cos(rotation), math.sin(rotation)
    return Hand(tuple(((x-.5)*c-(y-.5)*s+.5+dx, (x-.5)*s+(y-.5)*c+.5+dy, z) for x,y,z in p))


class FakeInput:
    def __init__(self):
        self.events = []
        self.pos = (960, 540)
        self.held = False
    def screen_size(self): return 1920, 1080
    def cursor_position(self): return self.pos
    def move_cursor(self, x, y):
        self.pos = (x,y)
        self.events.append(("move", x,y))
    def scroll(self, delta): self.events.append(("scroll", delta))
    def click_left(self): self.events.append(("click",))
    def click_right(self): self.events.append(("right",))
    def left_down(self):
        self.held=True
        self.events.append(("down",))
    def left_up(self):
        if self.held:
            self.events.append(("up",))
            self.held=False
    def ctrl_q(self): self.events.append(("ctrl_q",))
    def system_gesture(self, action): self.events.append((action,))
    def release_all(self): self.left_up()


@pytest.fixture
def backend(): return FakeInput()


@pytest.fixture(scope="session")
def qt():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
