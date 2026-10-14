"""Local, no-input smoke/benchmark. Never opens a camera unless --camera is passed."""
import argparse
import gc
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(name, "1")


class NoInput:
    def screen_size(self): return 1920, 1080
    def cursor_position(self): return 960, 540
    def release_all(self): pass
    def __getattr__(self, name):
        raise AssertionError(f"Benchmark must never send input: {name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=None)
    parser.add_argument("--camera-child", type=int, default=None)
    args = parser.parse_args()
    if args.camera_child is not None:
        from airmouse_ai.camera import Camera
        camera = Camera(args.camera_child)
        try:
            start = time.monotonic()
            frame = camera.read()
            print(json.dumps({"shape": list(frame.shape), "read_ms": (time.monotonic()-start)*1000}))
        finally:
            camera.close()
        return
    import psutil
    process = psutil.Process()
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    os.environ["LOCALAPPDATA"] = str(artifacts / "test-appdata")
    from PySide6.QtWidgets import QApplication
    from airmouse_ai.config import Settings, model_path
    from airmouse_ai.controller import Controller
    from airmouse_ai.ui import Window
    app = QApplication([])
    window = Window(Controller(NoInput(), Settings()))
    window.show()
    app.processEvents()
    window.grab().save(str(artifacts / "window.png"))
    idle_rss = process.memory_info().rss / 1024**2
    cpu0, wall0 = sum(process.cpu_times()[:2]), time.monotonic()
    end = wall0 + 3
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(.02)
    idle_cpu = (sum(process.cpu_times()[:2])-cpu0)/(time.monotonic()-wall0)*100
    lazy = "mediapipe" not in sys.modules and "cv2" not in sys.modules
    from airmouse_ai.vision import Vision
    import numpy as np
    import cv2
    cv2.setNumThreads(1)
    before = time.monotonic()
    vision = Vision(model_path())
    model_load_ms = (time.monotonic()-before)*1000
    rgb = np.zeros((480,640,3),dtype=np.uint8)
    timing=[]
    cpu0, wall0 = sum(process.cpu_times()[:2]), time.monotonic()
    for _ in range(100):
        start = time.monotonic()
        assert vision.detect(rgb,start) is None
        timing.append((time.monotonic()-start)*1000)
        app.processEvents()
        time.sleep(max(0,1/24-(time.monotonic()-start)))
    cpu = (sum(process.cpu_times()[:2])-cpu0)/(time.monotonic()-wall0)*100
    active_rss = process.memory_info().rss / 1024**2
    vision.close()
    del vision, rgb
    gc.collect()
    report = {"platform":sys.platform,"python":sys.version.split()[0],
              "idle_rss_mib":round(idle_rss,1),"idle_cpu_one_core_percent":round(idle_cpu,1),
              "lazy_vision_import_confirmed":lazy,"model_load_ms":round(model_load_ms,1),
              "blank_frame_inference_mean_ms":round(statistics.mean(timing),1),
              "blank_frame_inference_p95_ms":round(sorted(timing)[94],1),
              "blank_frame_rss_mib":round(active_rss,1),
              "blank_frame_cpu_one_core_percent":round(cpu,1),
              "after_model_close_rss_mib":round(process.memory_info().rss/1024**2,1),
              "note":"Blank frames only; not live hand tracking or end-to-end latency. CPU 100%=one logical core."}
    if args.camera is not None:
        try:
            child = subprocess.run([sys.executable,__file__,"--camera-child",str(args.camera)],
                                   capture_output=True,text=True,timeout=15)
            report["camera_probe"]={"exit_code":child.returncode,"stdout":child.stdout,"stderr":child.stderr[-2000:]}
        except subprocess.TimeoutExpired:
            report["camera_probe"]={"error":"Camera driver timed out after 15s; child process terminated."}
    (artifacts/"runtime-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    window.close()
    app.processEvents()


if __name__ == "__main__":
    main()
