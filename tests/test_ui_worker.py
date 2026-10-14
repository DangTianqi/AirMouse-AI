import sys
import time
import pytest
from airmouse_ai.config import Settings
from airmouse_ai.controller import Controller, State


def test_gui_starts_stopped_no_camera(qt,backend,monkeypatch,tmp_path):
    from airmouse_ai.ui import Window
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    def forbidden(*args): raise AssertionError('Must not open camera on startup')
    w=Window(Controller(backend,Settings()),worker_factory=forbidden)
    w.show(); qt.processEvents()
    assert w.controller.state==State.STOPPED
    assert w.worker is None
    assert w.scroll_slider.value()==20 and w.controller.settings.scroll_speed==2.0
    w.scroll_slider.setValue(22)
    assert w.controller.settings.scroll_speed==2.2
    assert w.landmark_check.isChecked()
    w.stabilization_slider.setValue(16)
    assert w.controller.settings.stabilization==1.6
    assert w.direction_controls['up'][0].value()==18
    for direction, (slider, label) in w.direction_controls.items():
        assert slider.maximum()==(99 if direction=='down' else 100)
        assert slider.minimum()==(6 if direction=='up' else 5)
        slider.setValue(100)
        assert getattr(w.controller.settings,f'cursor_{direction}_speed')==(9.9 if direction=='down' else 10)
        assert w.direction_inputs[direction].value()==(9.9 if direction=='down' else 10)
    for slider in (w.scroll_slider,w.stabilization_slider):
        slider.setValue(100)
    assert w.controller.settings.scroll_speed==w.controller.settings.stabilization==10
    from PySide6.QtGui import QImage
    w.resize(560,620); qt.processEvents()
    w.show_preview(QImage(480,360,QImage.Format.Format_RGB888))
    assert w.preview.pixmap().width()<=w.preview.width()
    assert w.preview.pixmap().height()<=w.preview.height()
    w.close(); qt.processEvents()
    assert not w.isVisible() and backend.events==[]
    from airmouse_ai.config import load
    assert load().cursor_up_speed==10 and load().cursor_down_speed==9.9


@pytest.mark.parametrize('failure',['camera','read','model',None])
def test_worker_errors_cleanup_and_mailbox(qt,backend,failure):
    import numpy as np
    from airmouse_ai.runtime import capture_loop
    import queue
    import threading
    closed=[]
    class V:
        def __init__(self,path):
            if failure=='model': raise ValueError('bad model')
        def detect(self,rgb,now): return None
        def close(self): closed.append('vision')
    class Cam:
        def __init__(self,index):
            if failure=='camera': raise OSError('camera occupied')
        def read(self):
            if failure=='read': raise OSError('disconnected')
            stop.set()
            return np.zeros((480,640,3),dtype=np.uint8)
        def close(self): closed.append('camera')
    c=Controller(backend,Settings())
    c.set_state(State.RUNNING)
    class Channel(queue.Queue):
        def cancel_join_thread(self): pass
    output, commands, errors = Channel(1),Channel(1),Channel(1)
    stop=threading.Event()
    capture_loop(output,commands,errors,stop,Settings(),None,Cam,V)
    assert ('vision' in closed)==(failure!='model')
    assert ('camera' in closed)==(failure not in ('model','camera'))
    assert (not errors.empty())==bool(failure)
    assert backend.events==[]


def test_video_timestamp_strictly_increases():
    import numpy as np
    from airmouse_ai.vision import Vision
    class Result: hand_landmarks=[]
    class Detector:
        def detect_for_video(self,image,timestamp):
            times.append(timestamp)
            return Result()
    class MP:
        class ImageFormat: SRGB=1
        def Image(self,**kwargs): return object()
    v=Vision.__new__(Vision)
    v.timestamp=-1; v.model=Detector(); v.mp=MP(); times=[]
    for t in (1.0,1.0,1.0001,1.02): v.detect(np.zeros((2,2,3),dtype=np.uint8),t)
    assert times==[1000,1001,1002,1020]
