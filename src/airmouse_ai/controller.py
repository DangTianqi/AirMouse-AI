from dataclasses import asdict
from enum import Enum
import threading
import logging
from .config import Settings
from .cursor import CursorFilter
from .gestures import GestureEngine, Mode
from .scroll import ScrollFilter


class State(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"


class Controller:
    """One lock gates all input, so pause/stop cannot race a late inference."""
    def __init__(self, backend, settings: Settings):
        self.backend, self.settings = backend, Settings.validated(asdict(settings))
        self.state = State.STOPPED
        self.lock = threading.RLock()
        self.engine = GestureEngine()
        self.scroll = ScrollFilter()
        self.cursor = CursorFilter(*backend.screen_size())
        self.previous_mode = Mode.NONE
        self.previous_token = None
        self.last_point = None
        self.drag_active = False

    def configure(self, settings: Settings) -> None:
        with self.lock:
            configured = Settings.validated(asdict(settings))
            if any(getattr(configured, name) != getattr(self.settings, name) for name in
                   ('mirror', 'stabilization', 'precise_cursor', 'cursor_up_speed', 'cursor_down_speed',
                    'cursor_left_speed', 'cursor_right_speed')):
                self.cursor.reset()
            self.settings = configured

    def set_state(self, state: State) -> None:
        with self.lock:
            self.state = state
            self.engine.reset()
            self.scroll.reset()
            self.cursor.reset()
            self.previous_mode = Mode.NONE
            self.previous_token = None
            self.last_point = None
            self.drag_active = False
            try:
                self.backend.release_all()
            except OSError:
                logging.exception("释放已发送输入失败；输入保持禁用")

    def process(self, hand, now: float, *, captured_at: float | None = None) -> tuple[Mode, str | None]:
        with self.lock:
            if self.state != State.RUNNING:
                return Mode.NONE, None
            events = self.engine.update(hand, now)
            mode = self.engine.mode
            if self.drag_active and not self.engine.left_pressed:
                self.backend.left_up()
                self.drag_active = False
            if mode != self.previous_mode or self.engine.control_token != self.previous_token:
                self.scroll.reset()
                self.cursor.reset()
                if mode == Mode.POINTING:
                    self.last_point = self.backend.cursor_position()
            self.previous_mode = mode
            self.previous_token = self.engine.control_token
            last_event = None
            for event in events:
                if event.kind in ("POINT_MOVE", "DRAG_MOVE"):
                    if self.engine.pointer_blocked:
                        self.cursor.reset()
                        continue
                    if event.kind == "DRAG_MOVE" and not self.drag_active:
                        continue
                    size = self.backend.screen_size()
                    if size != (self.cursor.width, self.cursor.height):
                        self.cursor = CursorFilter(*size)
                    pos = self.cursor.update_relative(*event.position, self.settings.mirror,
                                             anchor=self.backend.cursor_position(),
                                             stabilization=self.settings.stabilization,
                                             up_speed=self.settings.cursor_up_speed,
                                             down_speed=self.settings.cursor_down_speed,
                                             left_speed=self.settings.cursor_left_speed,
                                             right_speed=self.settings.cursor_right_speed,
                                             now=now if captured_at is None else captured_at,
                                             precision=self.settings.precise_cursor)
                    if pos is not None:
                        self.backend.move_cursor(*pos)
                        self.last_point = pos
                    elif self.last_point is None:
                        self.last_point = self.backend.cursor_position()
                elif event.kind == "SCROLL":
                    delta = self.scroll.update(event.position[1],int(event.position[0]),self.settings.scroll_speed)
                    if delta:
                        self.backend.scroll(delta)
                elif event.kind == "LEFT_DOWN":
                    if self.backend.left_down() is False:
                        self.engine.cancel_press()
                        mode = Mode.NONE
                        continue
                    self.drag_active = True
                    self.last_point = self.backend.cursor_position()
                elif event.kind == "LEFT_UP":
                    if self.drag_active:
                        self.backend.left_up()
                        self.drag_active = False
                elif event.kind == "RIGHT_CLICK":
                    self.backend.click_right()
                elif event.kind == "DRAG_START":
                    if not self.drag_active:
                        continue
                    self.cursor.reset()
                    self.cursor.update_relative(*event.position,self.settings.mirror,
                                                anchor=self.backend.cursor_position(),
                                                now=now if captured_at is None else captured_at)
                elif event.kind == "POINTER_FREEZE":
                    self.cursor.reset()
                elif event.kind == "CTRL_Q":
                    if self.backend.ctrl_q() is False:
                        last_event = "CTRL_Q_BLOCKED"
                        continue
                elif event.kind == "FIVE_SWIPE":
                    dx,dy=event.position
                    dx=-dx if self.settings.mirror else dx
                    if abs(dy)>abs(dx) and dy<0:
                        continue
                    action=(('DESKTOP_LEFT' if dx<0 else 'DESKTOP_RIGHT') if abs(dx)>=abs(dy)
                            else 'SHOW_DESKTOP')
                    last_event = action if self.backend.system_gesture(action) is not False else 'FIVE_BLOCKED'
                    continue
                elif event.kind == "TASK_VIEW":
                    last_event = 'TASK_VIEW' if self.backend.system_gesture('TASK_VIEW') is not False else 'FIVE_BLOCKED'
                    continue
                elif event.kind == "RECENTER":
                    self.cursor.reset()
                    self.scroll.reset()
                    width, height = self.backend.screen_size()
                    self.backend.move_cursor(width // 2, height // 2)
                    self.last_point = self.backend.cursor_position()
                last_event = event.kind
            return mode, last_event
