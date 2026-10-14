"""Fist reset and optional independent topmost preview integration."""
from dataclasses import asdict,replace
import math,time
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QGuiApplication
from airmouse_ai.config import Settings,load,save
from airmouse_ai.controller import Controller,State
from airmouse_ai.gestures import Hand,GestureEngine,Mode,classify
from conftest import hand_pose
from test_interactions_v13 import pinky_bend


@pytest.mark.parametrize('yaw',[0,math.pi/2,math.pi])
@pytest.mark.parametrize('reflect',[False,True])
def test_folded_fist_both_hands_and_faces(yaw,reflect):
    h=hand_pose('fist')
    def rotate(p):
        x,y,z=p[0]-.5,p[1]-.5,p[2]
        x,z=x*math.cos(yaw)+z*math.sin(yaw),-x*math.sin(yaw)+z*math.cos(yaw)
        return (-x if reflect else x,y,z)
    xyz=[rotate(p) for p in h.points]
    image=tuple((x+.5,y+.5,z) for x,y,z in xyz)
    world=tuple((x*.2,y*.2,z*.2) for x,y,z in xyz)
    assert classify(Hand(image,world_points=world)).mode==Mode.RECENTERING


@pytest.mark.parametrize('bend',[0,10,25,40])
def test_pinky_not_fully_tucked_is_not_fist(bend):
    h=pinky_bend(hand_pose('fist'),bend,bend)
    assert not classify(h).geometry.fist
    e=GestureEngine(); events=[]
    for i in range(30): events+=e.update(h,i*.04)
    assert not any(x.kind=='RECENTER' for x in events)


def test_open_hand_no_longer_recenters_and_fist_does(backend):
    c=Controller(backend,Settings()); c.set_state(State.RUNNING)
    for i in range(30): c.process(hand_pose('all_open'),i*.04)
    assert backend.events==[('TASK_VIEW',)]
    for i in range(30): c.process(hand_pose('fist'),1.2+i*.04)
    assert backend.events==[('TASK_VIEW',),('move',960,540)]


def test_floating_settings_preserve_v4_preferences_and_roundtrip(tmp_path):
    s=Settings.validated({'version':4,'landmarks':False,'cursor_up_speed':3.2,
                          'cursor_down_speed':1.7,'floating_preview':True,
                          'floating_x':-700,'floating_y':50,'floating_width':480,'floating_height':320})
    assert s.version==6 and not s.landmarks
    assert (s.cursor_up_speed,s.cursor_down_speed)==(3.2,1.7)
    assert s.floating_preview and s.floating_x==-700
    p=tmp_path/'config.json'; save(s,p)
    assert load(p)==s and Settings.validated(asdict(s))==s
    bad=Settings.validated({'floating_preview':'yes','floating_x':float('nan'),
                            'floating_y':True,'floating_width':1,'floating_height':999999})
    assert bad==Settings()


def make_window(backend,monkeypatch,tmp_path,**kwargs):
    from airmouse_ai.ui import Window
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    def forbidden(*args): raise AssertionError('Opening floating preview must not start a camera')
    return Window(Controller(backend,Settings(**kwargs)),worker_factory=forbidden)


def test_topmost_is_optional_native_and_does_not_start_camera(qt,backend,monkeypatch,tmp_path):
    w=make_window(backend,monkeypatch,tmp_path); w.show(); qt.processEvents()
    try:
        assert w.floating is None and not w.floating_check.isChecked()
        w.floating_check.setChecked(True); qt.processEvents()
        f=w.floating
        assert f.isVisible() and f.parent() is None
        assert f.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        assert w.worker is None and w.controller.state==State.STOPPED
        f.resize(320,300); f.move(100,90); qt.processEvents()
        assert (w.settings.floating_width,w.settings.floating_height)==(320,300)
        w.floating_check.setChecked(False); qt.processEvents()
        assert not f.isVisible() and f.image is None
        w.persist(); s=load()
        assert not s.floating_preview and s.floating_width==320 and s.floating_height==300
        # Reopen after the old monitor has disappeared, without restarting the app.
        w.settings.floating_x=60000; w.settings.floating_y=-60000
        w.floating_check.setChecked(True); qt.processEvents()
        assert QGuiApplication.primaryScreen().availableGeometry().contains(f.pos())
    finally:
        w.close(); qt.processEvents()
    assert backend.events==[]


def test_preview_keeps_aspect_on_resize_and_clears_when_closed(qt,backend,monkeypatch,tmp_path):
    w=make_window(backend,monkeypatch,tmp_path,floating_preview=True); w.show(); qt.processEvents()
    try:
        f=w.floating
        image=QImage(480,360,QImage.Format.Format_RGB888); image.fill(0x305060)
        f.show_preview(image)
        for size in ((500,400),(260,280),(600,300)):
            f.resize(*size); qt.processEvents()
            pix=f.preview.pixmap()
            assert pix.width()<=f.preview.width() and pix.height()<=f.preview.height()
            assert abs(pix.width()/pix.height()-4/3)<.02
        f.resize(50,50); qt.processEvents()
        assert f.width()>=240 and f.height()>=240
        f.close(); qt.processEvents()
        assert not w.floating_check.isChecked() and not w.settings.floating_preview
        assert f.image is None and w.controller.state==State.STOPPED
    finally:
        w.close(); qt.processEvents()


def test_floating_geometry_restores_and_clamps_removed_monitor(qt,backend,monkeypatch,tmp_path):
    w=make_window(backend,monkeypatch,tmp_path,floating_preview=True)
    w.show(); qt.processEvents()
    w.floating.resize(420,340); w.floating.move(130,100); qt.processEvents()
    before=(w.floating.pos().x(),w.floating.pos().y(),w.floating.width(),w.floating.height())
    w.close(); qt.processEvents()
    assert load().floating_preview and not w.floating.isVisible()
    from airmouse_ai.ui import Window
    restored=Window(Controller(backend,load())); restored.show(); qt.processEvents()
    try:
        f=restored.floating
        assert (f.pos().x(),f.pos().y(),f.width(),f.height())==before
        assert restored.worker is None and restored.controller.state==State.STOPPED
    finally:
        restored.close(); qt.processEvents()
    offscreen=make_window(backend,monkeypatch,tmp_path,floating_preview=True,
                           floating_x=60000,floating_y=-60000,floating_width=7680,floating_height=4320)
    offscreen.show(); qt.processEvents()
    try:
        f=offscreen.floating; area=QGuiApplication.primaryScreen().availableGeometry()
        assert area.contains(f.pos())
        assert f.width()<=area.width() and f.height()<=area.height()
    finally:
        offscreen.close(); qt.processEvents()


def test_minimized_main_still_routes_frames_and_status_to_floating(qt,backend,monkeypatch,tmp_path):
    w=make_window(backend,monkeypatch,tmp_path,preview=False,floating_preview=True)
    w.show(); qt.processEvents(); w.showMinimized(); qt.processEvents()
    image=QImage(480,360,QImage.Format.Format_RGB888); image.fill(0)
    class Mailbox:
        ready=True
        error=None
        def isRunning(self): return True
        def take(self): return image,(Mode.POINTING,None,24.,5.)
    worker=Mailbox(); w.worker=worker; w.controller.set_state(State.RUNNING)
    try:
        assert w.floating.isVisible() and w.isMinimized()
        w.poll(); qt.processEvents()
        assert not worker.preview_visible and worker.floating_preview_visible
        assert w.floating.image is image and '移动鼠标' in w.floating.action.text()
        w.floating.main_button.click(); qt.processEvents()
        assert not w.isMinimized() and w.isVisible()
        w.floating.close(); qt.processEvents(); w.poll()
        assert not worker.floating_preview_visible and w.controller.state==State.RUNNING
    finally:
        w.worker=None; w.close(); qt.processEvents()


def test_supervisor_requests_frames_for_floating_only_and_stops_after_hiding(qt,backend):
    from airmouse_ai.worker import Worker
    from runtime_fakes import preview_runtime
    c=Controller(backend,Settings(preview=False)); c.set_state(State.RUNNING)
    worker=Worker(c,runtime_target=preview_runtime)
    worker.preview_visible=False; worker.start()
    def pump(seconds):
        images=[]; deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            qt.processEvents(); img,_=worker.take()
            if img is not None: images.append(img)
            time.sleep(.02)
        return images
    try:
        assert pump(.6)==[]
        worker.floating_preview_visible=True
        assert pump(.6), worker.error
        worker.floating_preview_visible=False
        pump(.3)  # Drain in-flight frame.
        assert pump(.3)==[]
    finally:
        worker.stop(); assert worker.wait(5000)
    assert backend.events==[]
