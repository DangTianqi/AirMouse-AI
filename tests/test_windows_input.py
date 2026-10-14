import ctypes
import pytest
from airmouse_ai.windows_input import INPUT, WindowsInput


class User32:
    def __init__(self): self.batches=[]; self.results=[]; self.modifier=0
    def SendInput(self,n,batch,size):
        assert size==ctypes.sizeof(INPUT)
        self.batches.append([(b.type,b.ki.wVk,b.ki.dwFlags) if b.type==1 else
                              (b.type,b.mi.dwFlags,b.mi.mouseData) for b in batch])
        return self.results.pop(0) if self.results else n
    def GetAsyncKeyState(self,vk): return self.modifier


def test_windows_abi():
    assert ctypes.sizeof(INPUT)==(40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)


def test_click_and_shortcut_event_order():
    u=User32(); b=WindowsInput(u)
    b.click_left()
    assert u.batches==[[(0,2,0),(0,4,0)]]
    b.ctrl_q()
    assert u.batches[1]==[(1,0x11,0),(1,0x51,0),(1,0x51,2),(1,0x11,2)]
    b.release_all()
    assert len(u.batches)==2
    b.scroll(-120)
    assert u.batches[-1]==[(0,0x800,(-120)&0xffffffff)]


@pytest.mark.parametrize("method,partial", [('click_left',1),('ctrl_q',2)])
def test_partial_send_releases(method,partial):
    u=User32(); u.results=[partial]
    b=WindowsInput(u)
    with pytest.raises(OSError): getattr(b,method)()
    assert u.batches[-1]== ([(0,4,0)] if method=='click_left' else [(1,0x51,2),(1,0x11,2)])
    assert not b.mouse_pending and not b.keys_pending


def test_physical_modifiers_do_not_get_released():
    u=User32(); u.modifier=0x8000
    WindowsInput(u).ctrl_q()
    assert u.batches==[]


def test_drag_down_is_held_until_explicit_release():
    u=User32(); b=WindowsInput(u)
    assert b.left_down()
    assert b.mouse_pending and u.batches==[[(0,2,0)]]
    assert b.left_down()
    assert len(u.batches)==1
    b.release_all(); b.release_all()
    assert u.batches==[[(0,2,0)],[(0,4,0)]]
    assert not b.mouse_pending


def test_right_click_flags_and_partial_cleanup():
    u=User32(); b=WindowsInput(u)
    b.click_right()
    assert u.batches==[[(0,8,0),(0,16,0)]]
    u.results=[1]
    with pytest.raises(OSError): b.click_right()
    assert u.batches[-1]==[(0,16,0)]
    assert not b.right_pending


def test_failed_drag_press_and_release_are_retried_safely():
    u=User32(); b=WindowsInput(u); u.results=[0]
    with pytest.raises(OSError): b.left_down()
    assert u.batches==[[(0,2,0)],[(0,4,0)]]
    assert not b.mouse_pending
    b.left_down(); u.results=[0]
    with pytest.raises(OSError): b.left_up()
    assert b.mouse_pending
    b.release_all()
    assert not b.mouse_pending
