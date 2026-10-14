"""Exercise actual Win32 SendInput, intercepting only this test's marked events.

No desktop command reaches other windows. Unmarked physical input is forwarded
immediately and never recorded. The temporary hook is always removed.
"""
import ctypes as C
from ctypes import wintypes as W
import json,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from airmouse_ai.windows_input import WindowsInput
from airmouse_ai.controller import Controller,State
from airmouse_ai.config import Settings
from test_interactions_v18 import five

MARK=0x414D1939
class KeyEvent(C.Structure):
    _fields_=[('vk',W.DWORD),('scan',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('extra',C.c_size_t)]
CALLBACK=C.WINFUNCTYPE(C.c_ssize_t,C.c_int,W.WPARAM,W.LPARAM)
u=C.WinDLL('user32',use_last_error=True)
k=C.WinDLL('kernel32',use_last_error=True)
u.SetWindowsHookExW.argtypes=[C.c_int,CALLBACK,C.c_void_p,W.DWORD];u.SetWindowsHookExW.restype=C.c_void_p
u.CallNextHookEx.argtypes=[C.c_void_p,C.c_int,W.WPARAM,W.LPARAM];u.CallNextHookEx.restype=C.c_ssize_t
u.UnhookWindowsHookEx.argtypes=[C.c_void_p]
u.PeekMessageW.argtypes=[C.POINTER(W.MSG),C.c_void_p,W.UINT,W.UINT,W.UINT]
k.GetModuleHandleW.argtypes=[W.LPCWSTR];k.GetModuleHandleW.restype=C.c_void_p
received=[]
@CALLBACK
def intercept(code,wparam,lparam):
    if code>=0:
        e=C.cast(lparam,C.POINTER(KeyEvent)).contents
        if e.extra==MARK:
            received.append((int(e.vk),bool(e.flags&128),bool(e.flags&1)))
            return 1
    return u.CallNextHookEx(None,code,wparam,lparam)

class MarkedInput(WindowsInput):
    @staticmethod
    def key(vk,up=False):
        item=WindowsInput.key(vk,up);item.ki.dwExtraInfo=MARK;return item
    def move_cursor(self,*args): raise AssertionError('No real cursor movement allowed')

finished=threading.Event(); failures=[];results={}
def send():
    try:
        # Prove interception with a tagged F24 probe before any desktop shortcut.
        probe=MarkedInput()
        probe._send([probe.key(0x87),probe.key(0x87,True)])
        deadline=time.monotonic()+1
        while len(received)<2 and time.monotonic()<deadline: time.sleep(.002)
        assert received==[(0x87,False,False),(0x87,True,False)], 'Native intercept probe unavailable; no desktop shortcuts attempted'
        received.clear()
        for action,dx,dy,keys in [('DESKTOP_LEFT',-.06,0,(0x5B,0x11,0x25)),
                                 ('DESKTOP_RIGHT',.06,0,(0x5B,0x11,0x27)),
                                 ('TASK_VIEW',0,0,(0x5B,9)),('SHOW_DESKTOP',0,.06,(0x5B,0x44))]:
            start=len(received)
            backend=MarkedInput();c=Controller(backend,Settings(mirror=False));c.set_state(State.RUNNING)
            statuses=[]
            for i in range(10): statuses.append(c.process(five(),i*.04)[1])
            if action!='TASK_VIEW':
                for i in range(1,21):statuses.append(c.process(five(dx=dx*i/20,dy=dy*i/20),.36+i*.04)[1])
            chords=[(0x5B,9)]+([keys] if action!='TASK_VIEW' else [])
            expected=[]
            for chord in chords:
                expected.extend([(v,False,v in (0x5B,0x25,0x27)) for v in chord]+[(v,True,v in (0x5B,0x25,0x27)) for v in reversed(chord)])
            assert statuses.count(action)==1,(action,statuses)
            assert not backend.keys_pending and backend.pending_keys==()
            deadline=time.monotonic()+1
            while len(received)-start < len(expected) and time.monotonic()<deadline:
                time.sleep(.002)
            actual=[(0x11 if vk in (0xA2,0xA3) else vk,up,ext) for vk,up,ext in received[start:]]
            assert actual==expected,(action,actual,expected)
            results[action]={'native_events_intercepted':len(actual),'order_ok':True,'all_keys_released':True}
    except BaseException as e:failures.append(repr(e))
    finally:finished.set()

hook=u.SetWindowsHookExW(13,intercept,k.GetModuleHandleW(None),0)
if not hook:raise C.WinError(C.get_last_error())
try:
    worker=threading.Thread(target=send);worker.start()
    message=W.MSG()
    while not finished.is_set():
        while u.PeekMessageW(C.byref(message),None,0,0,1):
            u.TranslateMessage(C.byref(message));u.DispatchMessageW(C.byref(message))
        time.sleep(.001)
    worker.join()
finally:
    removed=bool(u.UnhookWindowsHookEx(hook))
report={'ok':not failures,'scope':'Synthetic five-finger -> production Controller -> actual Win32 SendInput -> temporary marked-event-only intercept; commands blocked before reaching Shell/windows; no physical keys recorded.',
        'actions':results,'tagged_events':len(received),'hook_removed':removed,'failures':failures}
(ROOT/'artifacts/native-input-v1.10.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
assert report['ok'] and removed
