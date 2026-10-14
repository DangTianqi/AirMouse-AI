"""Safe packaged-model check: synthetic black image, no camera or input backend."""
import json
import multiprocessing as mp
from pathlib import Path
import queue
import sys
import time


def model_probe(result, camera_index=None):
    camera = None
    try:
        import numpy as np
        from .config import model_path
        from .vision import Vision
        vision = Vision(model_path())
        try:
            shapes=[]
            if camera_index is not None:
                from .camera import Camera
                camera=Camera(camera_index)
            for _ in range(12 if camera else 3):
                if camera:
                    import cv2
                    image=cv2.cvtColor(camera.read(),cv2.COLOR_BGR2RGB)
                else:
                    image=np.zeros((480,640,3),dtype=np.uint8)
                hand=vision.detect(image,time.monotonic())
                if camera is None:
                    assert hand is None
                shapes.append(list(image.shape))
            result.put({"ok":True,"model_bytes":model_path().stat().st_size,
                        "camera_index":camera_index,"frames":len(shapes),"frame_shape":shapes[-1]})
        finally:
            if camera:
                camera.close()
            vision.close()
    except Exception as exc:
        import traceback
        result.put({"ok":False,"error":str(exc),"traceback":traceback.format_exc()})


def run() -> int:
    ctx=mp.get_context('spawn')
    result=ctx.Queue(1)
    camera_index=int(sys.argv[sys.argv.index('--camera-self-test')+1]) if '--camera-self-test' in sys.argv else None
    process=ctx.Process(target=model_probe,args=(result,camera_index))
    process.start()
    process.join(25)
    if process.is_alive():
        process.terminate()
        process.join(3)
        report={"ok":False,"error":"Model subprocess timed out"}
    else:
        try:
            report=result.get(timeout=1)
        except queue.Empty:
            report={"ok":False,"error":f"Model subprocess exited {process.exitcode} without result"}
    if '--report' in sys.argv:
        path=Path(sys.argv[sys.argv.index('--report')+1])
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    result.close()
    process.close()
    return 0 if report['ok'] else 1
