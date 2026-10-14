"""Measure the actual GUI/supervisor/vision topology, using blank frames and no input."""
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


class BlankCamera:
    def __init__(self,index): pass
    def read(self):
        import numpy as np
        time.sleep(.02)
        return np.zeros((480,640,3),dtype=np.uint8)
    def close(self): pass


def blank_runtime(*args):
    from airmouse_ai.runtime import capture_loop
    capture_loop(*args,camera_factory=BlankCamera)


class NoInput:
    def __init__(self): self.events={}
    def screen_size(self): return 1920,1080
    def cursor_position(self): return 960,540
    def release_all(self): pass
    def move_cursor(self,*args): self.events['move']=self.events.get('move',0)+1
    def scroll(self,*args): self.events['scroll']=self.events.get('scroll',0)+1
    def click_left(self): self.events['click']=self.events.get('click',0)+1
    def click_right(self): self.events['right']=self.events.get('right',0)+1
    def left_down(self): self.events['down']=self.events.get('down',0)+1
    def left_up(self): self.events['up']=self.events.get('up',0)+1
    def ctrl_q(self): self.events['ctrl_q']=self.events.get('ctrl_q',0)+1
    def system_gesture(self,action): self.events[action]=self.events.get(action,0)+1


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--camera',type=int,default=None)
    parser.add_argument('--floating',action='store_true')
    args=parser.parse_args()
    import psutil
    from PySide6.QtWidgets import QApplication
    from airmouse_ai.config import Settings
    from airmouse_ai.controller import Controller,State
    from airmouse_ai.ui import Window
    from airmouse_ai.worker import Worker
    artifacts=ROOT/'artifacts'
    artifacts.mkdir(exist_ok=True)
    os.environ['LOCALAPPDATA']=str(artifacts/'test-appdata')
    app=QApplication([])
    process=psutil.Process()
    from airmouse_ai.runtime import capture_loop
    settings=Settings(camera_index=args.camera or 0)
    target=blank_runtime if args.camera is None else capture_loop
    w=Window(Controller(NoInput(),settings),worker_factory=lambda c: Worker(c,runtime_target=target))
    w.show()
    def pump(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.02)
    def rss():
        return round(sum(p.memory_info().rss for p in [process]+process.children(recursive=True)
                         if p.is_running())/1024**2,1)
    pump(1)
    report={'scope':('Synthetic black camera' if args.camera is None else 'Live camera, no recorded images')+
                    '; actual application process topology; fake input; aggregate RSS includes shared pages more than once.',
            'idle_rss_mib':rss(),'idle_vision_unloaded':'mediapipe' not in sys.modules and 'cv2' not in sys.modules}
    modes=['preview_on','preview_off']+(['floating_only'] if args.floating else [])
    for mode in modes:
        if mode=='preview_on':
            w.start()
        elif mode=='preview_off':
            w.preview_check.setChecked(False)
        else:
            w.floating_check.setChecked(True)
            w.showMinimized()
        deadline=time.monotonic()+15
        while w.controller.state==State.STARTING and time.monotonic()<deadline:
            pump(.1)
        if w.controller.state!=State.RUNNING:
            raise RuntimeError(w.worker.error if w.worker else w.notice.text())
        pump(2)
        children=process.children(recursive=True)
        cpu0=sum(sum(p.cpu_times()[:2]) for p in [process]+children)
        wall0=time.monotonic()
        pump(4)
        cpu1=sum(sum(p.cpu_times()[:2]) for p in [process]+children if p.is_running())
        report[mode]={
            'rss_mib':rss(),'cpu_one_core_percent':round((cpu1-cpu0)/(time.monotonic()-wall0)*100,1),
            'gui_metrics':w.metrics.text(),'child_count':len(children)}
        if mode=='floating_only':
            report[mode].update(main_minimized=w.isMinimized(),floating_visible=w._floating_visible(),
                               frame_received=w.floating.image is not None,
                               camera_count=len(children))
    start=time.monotonic()
    w.toggle()
    deadline=start+5
    while w.worker is not None and time.monotonic()<deadline:
        pump(.05)
    report['pause_release_ms']=round((time.monotonic()-start)*1000,1)
    report['paused_rss_mib']=rss()
    report['paused_child_count']=len(process.children(recursive=True))
    report['gui_never_loaded_vision']='mediapipe' not in sys.modules and 'cv2' not in sys.modules
    w.close(); app.processEvents()
    filename='pipeline-report.json' if args.camera is None else 'live-pipeline-report.json'
    (artifacts/filename).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
        os.environ.setdefault(key,'1')
    main()
