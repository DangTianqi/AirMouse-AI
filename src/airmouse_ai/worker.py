"""Qt supervisor for a disposable, bounded-memory camera/inference process."""
from dataclasses import asdict, replace
import logging
import multiprocessing as mp
import queue
import threading
import time
from PySide6.QtCore import QThread
from PySide6.QtGui import QImage
from .config import model_path
from .controller import State
from .gestures import Mode
from .runtime import capture_loop, latest


class Worker(QThread):
    def __init__(self, controller, runtime_target=capture_loop):
        super().__init__()
        self.controller = controller
        self.runtime_target = runtime_target
        self.cancel = threading.Event()
        self.mail_lock = threading.Lock()
        self.image = None
        self.status = (Mode.NONE, None, 0.0, 0.0)
        self.error = None
        self.ready = False
        self.preview_visible = True
        self.floating_preview_visible = False

    def stop(self):
        self.cancel.set()

    def take(self):
        with self.mail_lock:
            result = self.image, self.status
            self.image = None
            return result

    def run(self):
        ctx = mp.get_context('spawn')
        output, commands, errors = ctx.Queue(1), ctx.Queue(1), ctx.Queue(1)
        stop = ctx.Event()
        with self.controller.lock:
            initial = replace(self.controller.settings)
        process = ctx.Process(target=self.runtime_target,
                              args=(output,commands,errors,stop,initial,model_path()),
                              name='AirMouseVision',daemon=True)
        started = False
        try:
            process.start()
            started = True
            shown_event, until, last_config = None, 0.0, None
            last_frame = time.monotonic()
            started_at = last_frame
            while not self.cancel.is_set():
                try:
                    message, trace = errors.get_nowait()
                    logging.error("视觉进程错误：%s\n%s",message,trace)
                    raise RuntimeError(message)
                except queue.Empty:
                    pass
                if not self.ready and time.monotonic()-started_at > 20:
                    raise TimeoutError("摄像头或模型初始化超过 20 秒，请检查设备后重试。")
                with self.controller.lock:
                    config = asdict(self.controller.settings)
                config['preview'] = (config['preview'] and self.preview_visible) or self.floating_preview_visible
                if config != last_config:
                    if latest(commands,config):
                        last_config = config
                try:
                    captured,hand,rgb,fps,mean_ms = output.get(timeout=.1)
                except queue.Empty:
                    if time.monotonic()-last_frame > .2:
                        self.controller.process(None,time.monotonic())
                        with self.mail_lock:
                            self.status = Mode.NONE,None,0.0,0.0
                    if not process.is_alive():
                        try:
                            message,trace = errors.get(timeout=.2)
                            raise RuntimeError(message)
                        except queue.Empty:
                            raise RuntimeError(f"视觉进程意外退出（代码 {process.exitcode}）")
                    continue
                self.ready = True
                now = time.monotonic()
                last_frame = now
                if now-captured > .25:
                    hand = None
                mode,event = self.controller.process(hand,now,captured_at=captured)
                if event in ('LEFT_DOWN','LEFT_UP','RIGHT_CLICK','DRAG_START','CTRL_Q','CTRL_Q_BLOCKED','RECENTER',
                             'DESKTOP_LEFT','DESKTOP_RIGHT','TASK_VIEW','SHOW_DESKTOP','FIVE_BLOCKED'):
                    shown_event,until = event,now+.5
                if now>until:
                    shown_event = None
                image = None
                if rgb is not None and config['preview']:
                    h,w = rgb.shape[:2]
                    image = QImage(rgb.data,w,h,rgb.strides[0],QImage.Format.Format_RGB888).copy()
                with self.mail_lock:
                    if image is not None:
                        self.image = image
                    self.status = mode,shown_event,fps,mean_ms
        except Exception as exc:
            logging.exception("识别监督线程异常")
            self.error = str(exc)
            try:
                self.controller.set_state(State.ERROR)
            except OSError:
                logging.exception("输入清理失败")
        finally:
            self.ready = False
            stop.set()
            if started:
                process.join(1.5)
                if process.is_alive():
                    process.terminate()
                    process.join(1)
                if process.is_alive():
                    process.kill()
                    process.join(1)
                process.close()
            for channel in (output,commands,errors):
                channel.cancel_join_thread()
                channel.close()
            with self.mail_lock:
                self.image = None
