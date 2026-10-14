import logging
from logging.handlers import RotatingFileHandler
import os
import sys


def main() -> int:
    # Bound native math pools before loading the vision stack.
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(key, "1")
    if "--model-self-test" in sys.argv or "--camera-self-test" in sys.argv:
        from .selftest import run
        return run()
    from .windows_input import WindowsInput, enable_dpi_awareness
    enable_dpi_awareness()
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .config import data_dir, load
    from .controller import Controller
    from .hotkey import Hotkey
    from .ui import Window
    app = QApplication(sys.argv)
    app.setApplicationName("AirMouseAI")
    try:
        directory = data_dir()
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / "airmouse.log", maxBytes=512*1024, backupCount=2, encoding="utf-8")
        logging.basicConfig(level=logging.WARNING, handlers=[handler],
                            format="%(asctime)s %(levelname)s %(message)s")
        window = Window(Controller(WindowsInput(), load()))
        hotkey = Hotkey(window.toggle)
        app.installNativeEventFilter(hotkey)
        if hotkey.error:
            window.notice.setText(hotkey.error)
        app.aboutToQuit.connect(hotkey.close)
        window.show()
        # Smoke mode never starts a camera, model, or input event.
        if "--smoke-test" in sys.argv:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1200, window.close)
        return app.exec()
    except Exception as exc:
        logging.exception("启动失败")
        QMessageBox.critical(None, "AirMouse AI 启动失败", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
