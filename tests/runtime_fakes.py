"""Spawn-safe fakes: exercise real process lifecycle without camera or real input."""
import time


class BlankCamera:
    def __init__(self,index): pass
    def read(self):
        import numpy as np
        time.sleep(.025)
        return np.zeros((480,640,3),dtype=np.uint8)
    def close(self): pass


def blocked_runtime(output,commands,errors,stop,settings,model):
    # Simulate a native camera call that ignores cancellation.
    time.sleep(120)


def failed_runtime(output,commands,errors,stop,settings,model):
    errors.put(("模拟摄像头被占用","test"))


def blank_runtime(output,commands,errors,stop,settings,model):
    from airmouse_ai.runtime import capture_loop
    capture_loop(output,commands,errors,stop,settings,model,camera_factory=BlankCamera)


def preview_runtime(output,commands,errors,stop,settings,model):
    import queue
    import numpy as np
    from airmouse_ai.runtime import latest
    enabled=settings.preview
    while not stop.is_set():
        try:
            enabled=commands.get_nowait()['preview']
        except queue.Empty:
            pass
        rgb=np.zeros((360,480,3),dtype=np.uint8) if enabled else None
        latest(output,(time.monotonic(),None,rgb,24.0,5.0))
        stop.wait(.04)
    output.cancel_join_thread()
