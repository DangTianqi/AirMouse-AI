"""Small ctypes backend. Tests inject a user32 fake and never send real input."""
import ctypes as C
from ctypes import wintypes as W
import sys

ULONG_PTR = C.c_size_t


class MOUSEINPUT(C.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD),
                ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(C.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(C.Structure):
    _fields_ = [("uMsg", W.DWORD), ("wParamL", W.WORD), ("wParamH", W.WORD)]


class INPUTUNION(C.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(C.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", W.DWORD), ("data", INPUTUNION)]


def enable_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            if C.windll.user32.SetProcessDpiAwarenessContext(C.c_void_p(-4)):
                return
        except (AttributeError, OSError):
            pass
        try:
            C.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            C.windll.user32.SetProcessDPIAware()


class WindowsInput:
    def __init__(self, user32=None):
        if user32 is None and sys.platform != "win32":
            raise OSError("当前系统仅支持模拟测试；实际控制需要 Windows")
        self.u = user32 or C.WinDLL("user32", use_last_error=True)
        if user32 is None:
            self.u.SendInput.argtypes = [W.UINT, C.POINTER(INPUT), C.c_int]
            self.u.SendInput.restype = W.UINT
            self.u.SetCursorPos.argtypes = [C.c_int, C.c_int]
            self.u.GetCursorPos.argtypes = [C.POINTER(W.POINT)]
        self.mouse_pending = False
        self.right_pending = False
        self.keys_pending = False
        self.pending_keys = ()

    def screen_size(self) -> tuple[int, int]:
        return self.u.GetSystemMetrics(0), self.u.GetSystemMetrics(1)

    def cursor_position(self) -> tuple[int, int]:
        point = W.POINT()
        if not self.u.GetCursorPos(C.byref(point)):
            raise OSError("无法读取光标位置")
        return point.x, point.y

    def move_cursor(self, x: int, y: int) -> None:
        w, h = self.screen_size()
        if not self.u.SetCursorPos(max(0, min(w-1, x)), max(0, min(h-1, y))):
            raise OSError("无法移动光标")

    def _send(self, items: list[INPUT]) -> None:
        batch = (INPUT * len(items))(*items)
        sent = self.u.SendInput(len(items), batch, C.sizeof(INPUT))
        if sent != len(items):
            raise OSError("Windows 输入未完整发送；请确认目标窗口权限与本程序一致")

    @staticmethod
    def mouse(flags: int, data: int = 0) -> INPUT:
        return INPUT(type=0, data=INPUTUNION(mi=MOUSEINPUT(0, 0, data & 0xFFFFFFFF, flags, 0, 0)))

    @staticmethod
    def key(vk: int, up: bool = False) -> INPUT:
        flags = (2 if up else 0) | (1 if vk in (0x25,0x27,0x5B,0x5C) else 0)
        return INPUT(type=1, data=INPUTUNION(ki=KEYBDINPUT(vk, 0, flags, 0, 0)))

    def scroll(self, delta: int) -> None:
        self._send([self.mouse(0x0800, delta)])

    def click_left(self) -> None:
        self.mouse_pending = True
        try:
            self._send([self.mouse(0x0002), self.mouse(0x0004)])
            self.mouse_pending = False
        finally:
            self.release_all()

    def left_down(self) -> bool:
        if self.mouse_pending:
            return True
        if self.u.GetAsyncKeyState(0x01) & 0x8000:
            return False
        self.mouse_pending = True
        try:
            self._send([self.mouse(0x0002)])
        except OSError:
            self.release_all()
            raise
        return True

    def left_up(self) -> None:
        if self.mouse_pending:
            self._send([self.mouse(0x0004)])
            self.mouse_pending = False

    def click_right(self) -> None:
        self.right_pending = True
        try:
            self._send([self.mouse(0x0008),self.mouse(0x0010)])
            self.right_pending = False
        finally:
            self.release_all()

    def ctrl_q(self) -> bool:
        return self._chord((0x11,0x51))

    def system_gesture(self, action: str) -> bool:
        keys = {'DESKTOP_LEFT': (0x5B,0x11,0x25), 'DESKTOP_RIGHT': (0x5B,0x11,0x27),
                'TASK_VIEW': (0x5B,0x09), 'SHOW_DESKTOP': (0x5B,0x44)}[action]
        return self._chord(keys)

    def _chord(self, keys) -> bool:
        # Avoid modifying a physical modifier already being held by the user.
        if any(self.u.GetAsyncKeyState(vk) & 0x8000 for vk in set((0x10,0x11,0x12,0x5B,0x5C)+keys)):
            return False
        self.keys_pending = True
        self.pending_keys = keys
        try:
            self._send([self.key(vk) for vk in keys]+[self.key(vk,True) for vk in reversed(keys)])
            self.keys_pending = False
            self.pending_keys = ()
        finally:
            self.release_all()
        return True

    def release_all(self) -> None:
        error = None
        for attr,events in (("mouse_pending",[self.mouse(0x0004)]),
                            ("right_pending",[self.mouse(0x0010)]),
                            ("keys_pending",[self.key(vk,True) for vk in reversed(self.pending_keys)])):
            if getattr(self,attr):
                try:
                    self._send(events)
                    setattr(self,attr,False)
                    if attr=='keys_pending':
                        self.pending_keys=()
                except OSError as exc:
                    error = exc
        if error:
            raise error

    stop = release_all
