"""Optional native topmost preview; no camera, model, thread or extra frame queue."""
from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton


class FloatingPreview(QWidget):
    dismissed = Signal()
    geometry_changed = Signal(int, int, int, int)
    capture_clicked = Signal()
    main_clicked = Signal()

    def __init__(self, settings):
        # Independent top-level window: minimizing the main window must not hide it.
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('AirMouse AI · 置顶预览')
        self.setMinimumSize(240, 240)
        self.shutting_down = False
        self.image = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.state_label = QLabel('已停止')
        layout.addWidget(self.state_label)
        self.preview = QLabel('摄像头未开启')
        self.preview.setMinimumSize(1, 80)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet('background:#192532;color:#d2e5ee;border-radius:8px')
        self.preview.installEventFilter(self)
        layout.addWidget(self.preview, 1)
        self.action = QLabel('握拳保持半秒 = 光标回中')
        self.action.setWordWrap(True)
        layout.addWidget(self.action)
        row = QHBoxLayout()
        self.capture_button = QPushButton('开始')
        self.main_button = QPushButton('主窗口')
        row.addWidget(self.capture_button)
        row.addWidget(self.main_button)
        layout.addLayout(row)
        self.capture_button.clicked.connect(self.capture_clicked.emit)
        self.main_button.clicked.connect(self.main_clicked.emit)
        self.setStyleSheet('QWidget{background:#f3f6f8} QLabel{color:#233646} QPushButton{padding:5px}')
        self.restore_geometry(settings)

    def restore_geometry(self, settings):
        areas = [screen.availableGeometry() for screen in QGuiApplication.screens()]
        area = next((r for r in areas if r.contains(QPoint(settings.floating_x, settings.floating_y))),
                    QGuiApplication.primaryScreen().availableGeometry())
        width = min(settings.floating_width, max(240, area.width() - 16))
        height = min(settings.floating_height, max(240, area.height() - 48))
        self.resize(width, height)
        self.move(max(area.left()+8, min(settings.floating_x, area.right()-width-8)),
                  max(area.top()+8, min(settings.floating_y, area.bottom()-height-40)))

    def show_preview(self, image):
        self.image = image  # QImage is implicitly shared; one bounded frame.
        self._render()

    def _render(self):
        if self.image is not None:
            self.preview.setPixmap(QPixmap.fromImage(self.image).scaled(
                self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def clear_preview(self, text):
        self.image = None
        self.preview.clear()
        self.preview.setText(text)

    def _remember(self):
        if not self.isMinimized():
            self.geometry_changed.emit(self.pos().x(), self.pos().y(), self.width(), self.height())

    def moveEvent(self, event):
        super().moveEvent(event)
        self._remember()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._remember()

    def eventFilter(self, watched, event):
        if watched is self.preview and event.type() == QEvent.Type.Resize:
            self._render()
        return super().eventFilter(watched, event)

    def closeEvent(self, event):
        self._remember()
        self.clear_preview('悬浮预览已关闭')
        if not self.shutting_down:
            self.dismissed.emit()
        event.accept()
