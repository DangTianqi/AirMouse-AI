import ctypes as C
from ctypes import wintypes as W
import sys
from PySide6.QtCore import QAbstractNativeEventFilter


class Hotkey(QAbstractNativeEventFilter):
    ID = 0xA17

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.registered = False
        self.error = ""
        if sys.platform != "win32":
            self.error = "全局热键仅在 Windows 可用"
            return
        self.u = C.WinDLL("user32", use_last_error=True)
        self.registered = bool(self.u.RegisterHotKey(None, self.ID, 0x4000 | 0x0001 | 0x0002, 0x47))
        if not self.registered:
            self.error = f"Ctrl+Alt+G 注册失败（系统错误 {C.get_last_error()}），仍可使用界面按钮。"

    def nativeEventFilter(self, event_type, message):
        if self.registered and bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = W.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == self.ID:
                self.callback()
                return True, 0
        return False, 0

    def close(self):
        if self.registered:
            self.u.UnregisterHotKey(None, self.ID)
            self.registered = False
