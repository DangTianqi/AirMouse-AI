"""Development/build only. The installed GUI never downloads a model."""
import hashlib
from pathlib import Path
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "assets/models/hand_landmarker.task"
URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
EXPECTED_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"


def validate(path: Path) -> None:
    if hashlib.sha256(path.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise ValueError("模型 SHA256 与已验证的官方版本不符，请重新下载并检查来源。")
    sys.path.insert(0, str(ROOT / "src"))
    from airmouse_ai.vision import Vision
    import numpy as np
    vision = Vision(path)
    try:
        assert vision.detect(np.zeros((480, 640, 3), dtype=np.uint8), 1.0) is None
    finally:
        vision.close()


def main():
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    if not MODEL.exists():
        temporary = MODEL.with_suffix(".download")
        try:
            with urlopen(URL, timeout=60) as response, temporary.open("wb") as stream:
                while block := response.read(256 * 1024):
                    stream.write(block)
            if temporary.stat().st_size < 1024 * 1024:
                raise ValueError("模型文件过小，下载无效")
            validate(temporary)
            temporary.replace(MODEL)
        finally:
            temporary.unlink(missing_ok=True)
    validate(MODEL)
    digest = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    print(f"Model load and blank-frame inference OK\nSHA256 {digest}\n{MODEL}")


if __name__ == "__main__":
    main()
