import sys
import threading


class Camera:
    def __init__(self, index: int, cv=None):
        if cv is None:
            import cv2 as cv
        self.cv, self.cap = cv, None
        self.stop_event = threading.Event()
        self.condition = threading.Condition()
        self.frame = None
        self.sequence = 0
        self.consumed = 0
        self.error = None
        self.thread = None
        try:
            apis = [cv.CAP_DSHOW, cv.CAP_MSMF] if sys.platform == "win32" else [cv.CAP_ANY]
            for api in apis:
                cap = cv.VideoCapture(index, api)
                if cap.isOpened():
                    self.cap = cap
                    break
                cap.release()
            if self.cap is None:
                raise OSError(f"无法打开摄像头 {index}。请检查设备编号、系统相机权限及是否被其他应用占用。")
            self.cap.set(cv.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv.CAP_PROP_FPS, 30)
            self.cap.set(cv.CAP_PROP_BUFFERSIZE, 1)  # Best effort; driver may ignore this.
            self.thread = threading.Thread(target=self._capture, name="LatestCameraFrame", daemon=True)
            self.thread.start()
        except Exception:
            self.close()
            raise

    def read(self):
        with self.condition:
            ready = self.condition.wait_for(lambda: self.sequence != self.consumed or self.error or
                                            self.stop_event.is_set(), timeout=2.0)
            if self.error:
                raise OSError(self.error)
            if not ready or self.stop_event.is_set():
                raise OSError("摄像头读取超时，请检查相机或重新连接。")
            self.consumed = self.sequence
            return self.frame

    def _capture(self):
        try:
            while not self.stop_event.is_set():
                ok, frame = self.cap.read()
                if not ok or frame is None or not frame.size:
                    raise OSError("摄像头读取失败。设备可能已断开，请停止后重新连接。")
                with self.condition:
                    self.frame = frame  # One frame slot, overwritten at the device rate.
                    self.sequence += 1
                    self.condition.notify_all()
                self.stop_event.wait(.001)
        except Exception as exc:
            with self.condition:
                self.error = str(exc)
                self.condition.notify_all()
        finally:
            if self.cap is not None:
                self.cap.release()
                self.cap = None

    def close(self) -> None:
        self.stop_event.set()
        with self.condition:
            self.condition.notify_all()
        if self.thread is not None:
            self.thread.join(.4)
            # A broken native driver is bounded by the supervisor's process timeout.
            if not self.thread.is_alive():
                self.thread = None
        elif self.cap is not None:
            self.cap.release()
            self.cap = None
