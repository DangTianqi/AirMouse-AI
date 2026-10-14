"""Isolated vision runtime: no Qt and no OS input; resources die with this process."""
from dataclasses import asdict
import queue
import time
from .camera import Camera
from .vision import Vision
from .overlay import draw_preview


def latest(channel, item):
    try:
        channel.put_nowait(item)
        return True
    except queue.Full:
        try:
            channel.get_nowait()
        except queue.Empty:
            pass
        try:
            channel.put_nowait(item)
            return True
        except queue.Full:
            return False


def capture_loop(output, commands, errors, stop, settings, model,
                 camera_factory=Camera, vision_factory=Vision):
    """Bounded queues carry the newest result only; never build a video backlog."""
    camera = vision = None
    try:
        import cv2
        cv2.setNumThreads(1)
        vision = vision_factory(model)
        if stop.is_set():
            return
        camera = camera_factory(settings.camera_index)
        config = asdict(settings)
        preview_time = 0.0
        frames, total_ms, report_time = 0, 0.0, time.monotonic()
        fps, mean_ms = 0.0, 0.0
        while not stop.is_set():
            start = time.monotonic()
            try:
                config = commands.get_nowait()
            except queue.Empty:
                pass
            frame = camera.read()
            captured = time.monotonic()
            if stop.is_set():
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            hand = vision.detect(rgb, captured)
            frames += 1
            total_ms += (time.monotonic()-start)*1000
            now = time.monotonic()
            if now - report_time >= 1:
                fps, mean_ms = frames/(now-report_time), total_ms/frames
                frames, total_ms, report_time = 0, 0.0, now
            preview = None
            if config['preview'] and now-preview_time >= .1:
                preview = draw_preview(rgb,hand,config['mirror'],config['landmarks'])
                preview_time = now
            latest(output, (captured, hand, preview, fps, mean_ms))
            stop.wait(max(0,1/config['target_fps']-(time.monotonic()-start)))
    except Exception as exc:
        import traceback
        errors.put((str(exc),traceback.format_exc()))
    finally:
        for resource in (camera,vision):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass
        output.cancel_join_thread()
