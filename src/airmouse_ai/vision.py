from pathlib import Path
import os
from .gestures import Hand
from .config import Tuning


class Vision:
    def __init__(self, model: Path):
        if not model.is_file():
            raise FileNotFoundError(f"找不到本地模型：{model}。开发环境请运行 scripts/download_model.py；EXE 请保留完整文件夹。")
        # MediaPipe imports its optional drawing helpers eagerly. Use the small
        # noninteractive backend rather than allowing another GUI toolkit to load.
        os.environ.setdefault("MPLBACKEND", "Agg")
        if "MPLCONFIGDIR" not in os.environ:
            from .config import data_dir
            cache = data_dir() / "matplotlib"
            try:
                cache.mkdir(parents=True, exist_ok=True)
                os.environ["MPLCONFIGDIR"] = str(cache)
            except OSError:
                pass  # Matplotlib has its own temporary-directory fallback.
        import mediapipe as mp
        self.mp = mp
        tuning = Tuning()
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_buffer=model.read_bytes()),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=1, min_hand_detection_confidence=tuning.detection_confidence,
            min_hand_presence_confidence=tuning.presence_confidence,
            min_tracking_confidence=tuning.tracking_confidence)
        # Buffer loading also supports non-ASCII Windows project paths reliably.
        self.model = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self.timestamp = -1

    def detect(self, rgb, now: float) -> Hand | None:
        self.timestamp = max(self.timestamp + 1, int(now * 1000))
        result = self.model.detect_for_video(
            self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), self.timestamp)
        if not result.hand_landmarks:
            return None
        world = getattr(result, "hand_world_landmarks", [])
        handedness = getattr(result, "handedness", [])
        label = handedness[0][0].category_name if handedness and handedness[0] else ""
        return Hand(tuple((p.x, p.y, p.z) for p in result.hand_landmarks[0]),
                    rgb.shape[1] / rgb.shape[0],
                    tuple((p.x, p.y, p.z) for p in world[0]) if world else None, label)

    def close(self) -> None:
        self.model.close()
