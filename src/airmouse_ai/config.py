from dataclasses import asdict, dataclass, fields
import json
import math
import os
from pathlib import Path
import sys
import tempfile


def data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "AirMouseAI"


def model_path() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / "assets/models/hand_landmarker.task"


@dataclass
class Settings:
    version: int = 6
    camera_index: int = 0
    scroll_speed: float = 2.0
    cursor_up_speed: float = 1.8
    cursor_down_speed: float = 1.3
    cursor_left_speed: float = 1.0
    cursor_right_speed: float = 1.0
    mirror: bool = True
    preview: bool = True
    landmarks: bool = True
    stabilization: float = 1.0
    precise_cursor: bool = True
    target_fps: int = 24
    floating_preview: bool = False
    floating_x: int = 80
    floating_y: int = 80
    floating_width: int = 360
    floating_height: int = 360

    def constrain_vertical(self, prefer: str = "down") -> None:
        """Keep a one-tick gap; the slider being edited takes precedence."""
        up = max(6, min(100, round(self.cursor_up_speed * 10)))
        down = max(5, min(99, round(self.cursor_down_speed * 10)))
        if up <= down:
            if prefer == "up":
                down = up - 1
            else:
                up = down + 1
        self.cursor_up_speed, self.cursor_down_speed = up / 10, down / 10

    @classmethod
    def validated(cls, raw: object) -> "Settings":
        result = cls()
        if not isinstance(raw, dict):
            return result
        for f in fields(result):
            value = raw.get(f.name)
            default = getattr(result, f.name)
            if isinstance(default, bool):
                if type(value) is bool:
                    setattr(result, f.name, value)
            elif type(value) in (int, float) and math.isfinite(value):
                bounds = {"version": (6, 6), "camera_index": (0, 9),
                          "scroll_speed": (0.5, 10.0),
                          "cursor_up_speed": (0.5, 10.0), "cursor_down_speed": (0.5, 10.0),
                          "cursor_left_speed": (0.5, 10.0), "cursor_right_speed": (0.5, 10.0),
                          "target_fps": (15, 30), "stabilization": (0.5, 10.0),
                          "floating_x": (-65536, 65536), "floating_y": (-65536, 65536),
                          "floating_width": (240, 7680), "floating_height": (240, 4320)}
                lo, hi = bounds[f.name]
                if lo <= value <= hi and (not isinstance(default, int) or int(value) == value):
                    setattr(result, f.name, type(default)(value))
        if raw.get("version", 1) in (1, 2):
            # Replace the old shared cursor slider with four independent speeds.
            legacy = raw.get("cursor_speed", 1.0)
            if type(legacy) in (int, float) and math.isfinite(legacy) and 0.5 <= legacy <= 10:
                for direction in ("up", "down", "left", "right"):
                    name = f"cursor_{direction}_speed"
                    if name not in raw:
                        factor = 1.8 if direction == "up" else 1.3 if direction == "down" else 1.0
                        setattr(result, name, min(10.0, legacy * factor))
        if raw.get("version") == 3 and result.cursor_up_speed == 1.6 and result.cursor_down_speed == 1.0:
            result.cursor_up_speed, result.cursor_down_speed = 1.8, 1.3
        if (raw.get("version", 1) in (1, 2, 3, 4, 5) and
                type(raw.get("scroll_speed")) in (int, float) and raw["scroll_speed"] == 1.0):
            result.scroll_speed = 2.0
        result.constrain_vertical()
        if raw.get("version", 1) not in (2, 3, 4, 5, 6):
            result.landmarks = True  # Make detection visible when upgrading v1 settings.
        return result


def load(path: Path | None = None) -> Settings:
    try:
        return Settings.validated(json.loads((path or data_dir() / "config.json").read_text("utf-8")))
    except (OSError, ValueError, TypeError):
        return Settings()


def save(settings: Settings, path: Path | None = None) -> None:
    path = path or data_dir() / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False, suffix=".tmp") as stream:
            temporary = Path(stream.name)
            json.dump(asdict(Settings.validated(asdict(settings))), stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class Tuning:
    stable_s: float = 0.15
    max_frame_gap_s: float = 0.25
    extended_angle: float = 147.0
    folded_angle: float = 130.0
    extended_straightness: float = 0.88
    pinky_extended_angle: float = 150.0
    pinky_extended_straightness: float = 0.90
    pinky_folded_angle: float = 135.0
    pinky_folded_straightness: float = 0.82
    pinky_release_s: float = 0.12
    folded_straightness: float = 0.72
    thumb_reach: float = 1.12
    thumb_fold_reach: float = 1.04
    detection_confidence: float = 0.55
    presence_confidence: float = 0.55
    tracking_confidence: float = 0.55
    min_palm: float = 0.035
    pinch_enter: float = 0.30
    pinch_exit: float = 0.42
    pinch_min_s: float = 0.065
    pinch_release_s: float = 0.040
    pinch_distal_angle: float = 130.0
    pinch_index_reach: float = 0.42
    fist_tip_reach: float = 0.75
    drag_hold_s: float = 1.0
    right_hold_s: float = 0.18
    right_release_s: float = 0.30
    shortcut_hold_s: float = 0.8
    shortcut_grace_s: float = 0.12
    shortcut_release_s: float = 0.30
    recenter_hold_s: float = 0.50
    recenter_release_s: float = 0.30
    five_hold_s: float = 0.12
    five_release_s: float = 0.30
    five_distance: float = 0.12
    five_start_distance: float = 0.025
    five_axis_ratio: float = 1.25
    five_confirm_s: float = 0.04
    five_grace_s: float = 0.12
    five_stroke_s: float = 1.60
    five_max_step: float = 0.80
    five_extended_angle: float = 140.0
    five_straightness: float = 0.84
    five_thumb_reach: float = 1.08
    scroll_alpha: float = 0.55
    scroll_deadzone: float = 0.018
    scroll_gain: float = 900.0
    wheel_quantum: int = 30
    scroll_max_step: float = 0.65
    scroll_return_deadzone: float = 0.01
    scroll_single_exit_s: float = 0.18
    scroll_fold_exit_s: float = 0.35
    cursor_max_speed_px_s: float = 3600.0
    finger_deadzone: float = 0.0075
    finger_gain: float = 1.55
    finger_max_step: float = 0.50
    finger_min_cutoff: float = 4.0
    finger_cutoff_beta: float = 16.0
    finger_velocity_cutoff: float = 6.0
    finger_precision_gain: float = 0.70
    finger_fast_gain: float = 1.75
    finger_settle_s: float = 0.060
    cursor_fine_gain: float = 0.30
    cursor_fine_deadzone: float = 0.00035
    cursor_intent_span: float = 0.0015
    cursor_accel_start: float = 0.10
    cursor_accel_end: float = 0.55
