from dataclasses import replace
import logging
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QMainWindow,
                               QPushButton, QSlider, QVBoxLayout, QWidget, QScrollArea, QDoubleSpinBox)
from .config import save
from .controller import State
from .gestures import Mode
from .worker import Worker
from . import __version__

STATE_TEXT = {State.STOPPED: "已停止", State.STARTING: "初始化中", State.RUNNING: "运行中",
              State.PAUSED: "已暂停", State.ERROR: "设备或识别错误"}
MODE_TEXT = {Mode.NONE: "未检测到有效手势", Mode.POINTING: "移动鼠标", Mode.SCROLLING: "上下滚动",
             Mode.FIVE_FINGER: "五指张开即任务视图 · 左右划切桌面，下划桌面",
             Mode.PINCH_CANDIDATE: "正在确认轻捏", Mode.SHORTCUT: "无名指＋小指 · 保持约 0.8 秒发送 Ctrl+Q",
             Mode.LEFT_HELD: "左键已按住 · 满 1 秒后可移动捏合点",
             Mode.PINKY_STOP: "光标已锁定 · 小指明确收拢后恢复，其他命令仍可用",
             Mode.RECENTERING: "五指收起握拳 · 保持半秒回到屏幕中心",
             Mode.RIGHT_CLICK: "拇指＋小拇指右击手势",
             Mode.DRAGGING: "左键按住并移动 · 松开即释放"}


class Window(QMainWindow):
    def __init__(self, controller, worker_factory=Worker):
        super().__init__()
        self.controller, self.settings = controller, replace(controller.settings)
        self.worker_factory, self.worker = worker_factory, None
        self.floating = None
        self.closing, self.stopping_since = False, None
        self.setWindowTitle(f"AirMouse AI · 论文阅读助手 v{__version__}")
        self.resize(680, 760)
        self.setMinimumWidth(560)
        body = QWidget()
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setWidget(body)
        self.setCentralWidget(scroll_area)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        title = QLabel(f"AirMouse AI  ·  论文阅读助手 {__version__}")
        title.setStyleSheet("font-size:22px; font-weight:600")
        layout.addWidget(title)
        self.state_label = QLabel("已停止 · 摄像头未开启")
        layout.addWidget(self.state_label)
        self.preview = QLabel("点击“开始”开启摄像头\n所有识别均在本机完成")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(250)
        self.preview.setStyleSheet("background:#192532;color:#d2e5ee;border-radius:12px")
        layout.addWidget(self.preview, 1)
        self.action = QLabel("当前动作：未检测到手")
        self.action.setWordWrap(True)
        self.metrics = QLabel("推理上限 24 FPS · 预览上限 10 FPS · 单手识别")
        layout.addWidget(self.action)
        legend = QLabel('<span style="color:#a66b15">1:T 拇指</span>　'
                        '<span style="color:#127e9f">2:I 食指</span>　'
                        '<span style="color:#8b7407">3:M 中指</span>　'
                        '<span style="color:#8650b3">4:R 无名指</span>　'
                        '<span style="color:#287d46">5:P 小指</span>')
        legend.setWordWrap(True)
        layout.addWidget(legend)
        layout.addWidget(self.metrics)
        row = QHBoxLayout()
        row.addWidget(QLabel("摄像头"))
        self.camera = QComboBox()
        for i in range(10):
            self.camera.addItem(f"{i} · 默认摄像头" if i == 0 else f"{i} · 设备编号", i)
        self.camera.setCurrentIndex(self.settings.camera_index)
        self.camera.currentIndexChanged.connect(self.changed)
        row.addWidget(self.camera, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.start_button = QPushButton("开始")
        self.pause_button = QPushButton("暂停")
        self.stop_button = QPushButton("停止")
        for button, callback in ((self.start_button, self.start), (self.pause_button, self.toggle),
                                 (self.stop_button, self.stop)):
            row.addWidget(button)
            button.clicked.connect(callback)
        layout.addLayout(row)
        self.multiplier_inputs = {}
        self.scroll_slider, self.scroll_label = self.add_slider(layout, "滚动速度", 5, 100, self.settings.scroll_speed)
        self.scroll_input = self.multiplier_inputs[self.scroll_slider]
        vertical_note = QLabel("向上默认 1.8×，向下 1.3×；上下联动，始终保持向上至少高 0.1×")
        vertical_note.setWordWrap(True)
        layout.addWidget(vertical_note)
        self.direction_controls = {}
        for direction, label in (("up", "向上"), ("down", "向下"), ("left", "向左"), ("right", "向右")):
            self.direction_controls[direction] = self.add_slider(
                layout, f"光标{label}", 6 if direction=="up" else 5,
                99 if direction=="down" else 100, getattr(self.settings, f"cursor_{direction}_speed"))
        self.stabilization_slider, self.stabilization_label = self.add_slider(
            layout,"防抖强度",5,100,self.settings.stabilization)
        self.direction_inputs = {d:self.multiplier_inputs[control[0]] for d,control in self.direction_controls.items()}
        self.stabilization_input = self.multiplier_inputs[self.stabilization_slider]
        self.precision_check = QCheckBox("精细定位（推荐：慢动微调，快动跨屏）")
        self.precision_check.setChecked(self.settings.precise_cursor)
        self.precision_check.toggled.connect(self.changed)
        layout.addWidget(self.precision_check)
        pointer_note = QLabel("光标自动轻动精调、快划加速。建议防抖 1.0×；过高会让微动更费力。")
        pointer_note.setWordWrap(True)
        layout.addWidget(pointer_note)
        row = QHBoxLayout()
        self.preview_check = QCheckBox("主窗口预览")
        self.mirror_check = QCheckBox("镜像")
        self.landmark_check = QCheckBox("骨架与手指标识")
        for check, value in ((self.preview_check, self.settings.preview), (self.mirror_check, self.settings.mirror),
                             (self.landmark_check, self.settings.landmarks)):
            check.setChecked(value)
            check.toggled.connect(self.changed)
            row.addWidget(check)
        layout.addLayout(row)
        self.floating_check = QCheckBox("置顶悬浮小窗（可拖动、缩放，主窗口最小化仍显示）")
        self.floating_check.setChecked(self.settings.floating_preview)
        self.floating_check.toggled.connect(self._floating_toggled)
        layout.addWidget(self.floating_check)
        self.fps = QComboBox()
        for value in (15, 20, 24, 30):
            self.fps.addItem(f"识别上限 {value} FPS", value)
        self.fps.setCurrentIndex(max(0, self.fps.findData(self.settings.target_fps)))
        self.fps.currentIndexChanged.connect(self.changed)
        layout.addWidget(self.fps)
        help_label = QLabel("单独伸食指/中指/无名指 = 移动；小指伸出或接近伸直即锁定，收拢后恢复\n"
                            "五指张开确认后直接打开任务视图；继续左右划切桌面，下划显示/还原桌面\n"
                            "五指全部收起握拳保持半秒 = 光标回中；再伸单指匹配移动点\n"
                            "食指＋中指 / 中指＋无名指弯曲 = 向上滚；再伸拇指 = 向下滚；伸直双指复位\n"
                            "拇指食指轻捏 = 左键按住，松开释放；保持超过 1 秒可移动捏合点\n"
                            "拇指＋小拇指伸直、其余三指收起 = 右击一次\n"
                            "无名指和小指伸直、其余收起，保持 0.8 秒 = 发送 Ctrl+Q\n"
                            "重复快捷手势前放松手 0.3 秒；每次保持只发送一次\n"
                            "Ctrl+Alt+G = 暂停/恢复；暂停会释放摄像头和模型")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        self.notice = QLabel("")
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet("color:#ae4825")
        layout.addWidget(self.notice)
        self.setStyleSheet("QMainWindow{background:#f3f6f8} QLabel{color:#233646} "
                           "QPushButton{padding:9px;border:1px solid #b7cbd7;border-radius:6px;background:white} "
                           "QPushButton:disabled{color:#9aa9b0} QComboBox{padding:5px}")
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.persist)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.buttons()
        if self.settings.floating_preview:
            self._floating_toggled(True)

    def _floating_toggled(self, enabled):
        self.settings.floating_preview = enabled
        if enabled:
            if self.floating is None:
                from .floating import FloatingPreview
                self.floating = FloatingPreview(self.settings)
                self.floating.geometry_changed.connect(self._floating_geometry_changed)
                self.floating.dismissed.connect(lambda: self.floating_check.setChecked(False))
                self.floating.capture_clicked.connect(self._floating_capture)
                self.floating.main_clicked.connect(self._show_main)
            else:
                self.floating.restore_geometry(replace(self.settings))
            self.floating.showNormal()
            self._floating_geometry_changed(self.floating.pos().x(), self.floating.pos().y(),
                                            self.floating.width(), self.floating.height())
        elif self.floating is not None:
            self.floating.hide()
            self.floating.clear_preview("悬浮预览已关闭")
        self.controller.configure(self.settings)
        self.save_timer.start()
        self.buttons()

    def _floating_geometry_changed(self, x, y, width, height):
        self.settings.floating_x, self.settings.floating_y = x, y
        self.settings.floating_width, self.settings.floating_height = width, height
        self.save_timer.start()  # No per-pixel config writes or vision commands.

    def _floating_capture(self):
        if self.controller.state in (State.STOPPED, State.ERROR):
            self.start()
        else:
            self.toggle()

    def _show_main(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _floating_visible(self):
        return self.floating is not None and self.floating.isVisible() and not self.floating.isMinimized()

    def add_slider(self, layout, name, minimum, maximum, value):
        row = QHBoxLayout()
        label = QLabel(name)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(round(value*10))
        number = QDoubleSpinBox()
        number.setDecimals(1)
        number.setRange(minimum/10,maximum/10)
        number.setSingleStep(.1)
        number.setSuffix("×")
        number.setKeyboardTracking(False)
        number.setValue(value)
        number.setMinimumWidth(96)
        number.setAccessibleName(name+"倍率")
        number.setToolTip("直接输入数字后按回车或移开焦点；与滑块同步并自动保存")
        self.multiplier_inputs[slider] = number
        row.addWidget(label)
        row.addWidget(slider, 1)
        row.addWidget(number)
        layout.addLayout(row)
        number.valueChanged.connect(lambda v: slider.setValue(round(v*10)))
        slider.valueChanged.connect(lambda v: self._sync_multiplier(slider,v/10))
        slider.valueChanged.connect(self.changed)
        return slider, label

    def _sync_multiplier(self, slider, value):
        number = self.multiplier_inputs[slider]
        blocked = number.blockSignals(True)
        number.setValue(value)
        number.blockSignals(blocked)

    def changed(self, *_):
        self.settings.camera_index = self.camera.currentData()
        self.settings.scroll_speed = self.scroll_slider.value()/10
        for direction, (slider, label) in self.direction_controls.items():
            value = slider.value()/10
            setattr(self.settings, f"cursor_{direction}_speed", value)
        preferred = "up" if self.sender() is self.direction_controls['up'][0] else "down"
        self.settings.constrain_vertical(preferred)
        for direction, (slider, label) in self.direction_controls.items():
            value = getattr(self.settings, f"cursor_{direction}_speed")
            blocked = slider.blockSignals(True)
            slider.setValue(round(value*10))
            slider.blockSignals(blocked)
            self._sync_multiplier(slider,value)
            name = {"up": "向上", "down": "向下", "left": "向左", "right": "向右"}[direction]
            label.setText(f"光标{name}")
        self.settings.stabilization = self.stabilization_slider.value()/10
        self.settings.precise_cursor = self.precision_check.isChecked()
        self.settings.preview = self.preview_check.isChecked()
        self.settings.mirror = self.mirror_check.isChecked()
        self.settings.landmarks = self.landmark_check.isChecked()
        self.settings.target_fps = self.fps.currentData()
        self.controller.configure(self.settings)
        if not self.settings.preview:
            self.preview.clear()
            self.preview.setText("预览已关闭 · 识别可继续运行")
        self.save_timer.start()

    def persist(self):
        try:
            save(self.settings)
        except OSError as exc:
            self.notice.setText(f"设置保存失败：{exc}")
            logging.exception("配置保存失败")

    def start(self):
        if self.worker is not None or self.closing:
            return
        self.notice.clear()
        self.controller.set_state(State.STARTING)
        self.worker = self.worker_factory(self.controller)
        if self.floating is not None:
            self.floating.clear_preview("正在初始化摄像头…")
        self.worker.start()
        self.buttons()

    def toggle(self):
        if self.closing:
            return
        state = self.controller.state
        if state in (State.RUNNING, State.STARTING):
            self.halt(State.PAUSED)
        elif state == State.PAUSED and self.worker is None:
            self.start()

    def halt(self, state):
        self.controller.set_state(state)
        if self.worker is not None:
            self.worker.stop()
            self.stopping_since = time.monotonic()
        self.preview.clear()
        self.preview.setText("摄像头正在释放…" if self.worker else "摄像头已关闭")
        if self.floating is not None:
            self.floating.clear_preview("摄像头正在释放…" if self.worker else "摄像头已关闭")
            self.floating.action.setText("输入已禁用")
        self.buttons()

    def stop(self):
        self.halt(State.STOPPED)

    def buttons(self):
        state = self.controller.state
        busy = self.worker is not None
        self.start_button.setEnabled(not busy and not self.closing and state != State.PAUSED)
        self.pause_button.setText("继续" if state == State.PAUSED else "暂停")
        self.pause_button.setEnabled(not self.closing and (state in (State.RUNNING, State.STARTING) or
                                                          (state == State.PAUSED and not busy)))
        self.stop_button.setEnabled(not self.closing and (busy or state == State.PAUSED))
        self.camera.setEnabled(not busy)
        self.state_label.setText(STATE_TEXT[state] + (" · 正在释放资源" if self.stopping_since else ""))
        if self.floating is not None:
            self.floating.state_label.setText(self.state_label.text())
            self.floating.capture_button.setText("暂停" if state in (State.RUNNING, State.STARTING)
                                                else "继续" if state == State.PAUSED else "开始")
            self.floating.capture_button.setEnabled(not self.closing and not self.stopping_since and
                                                   (not busy or state in (State.RUNNING, State.STARTING)))

    def poll(self):
        worker = self.worker
        if worker is not None:
            worker.preview_visible = self.isVisible() and not self.isMinimized()
            worker.floating_preview_visible = self._floating_visible()
            if worker.ready and self.controller.state == State.STARTING:
                self.controller.set_state(State.RUNNING)
            image, (mode, event, fps, mean_ms) = worker.take()
            if image is not None and not self.stopping_since:
                if self.settings.preview and worker.preview_visible:
                    self.show_preview(image)
                if worker.floating_preview_visible:
                    self.floating.show_preview(image)
            text = {"LEFT_DOWN": "左键已按下 · 松开即释放", "LEFT_UP": "左键已释放",
                    "DESKTOP_LEFT": "已发送切换左侧虚拟桌面",
                    "DESKTOP_RIGHT": "已发送切换右侧虚拟桌面",
                    "TASK_VIEW": "已发送打开任务视图",
                    "SHOW_DESKTOP": "已发送显示/还原桌面",
                    "FIVE_BLOCKED": "五指命令未发送：请松开实体修饰键及目标键，再重新做手势",
                    "RIGHT_CLICK": "已右击",
                    "DRAG_START": "已保持超过 1 秒 · 可移动捏合点",
                    "RECENTER": "光标已回到中心 · 伸单指重新匹配移动点",
                    "CTRL_Q_BLOCKED": "Ctrl+Q未发送：实体修饰键或Q按住，请松开后重新做手势",
                    "CTRL_Q": "已发送 Ctrl+Q"}.get(event, MODE_TEXT[mode])
            if mode == Mode.SHORTCUT and event is None:
                with self.controller.lock:
                    engine = self.controller.engine
                    if engine.mode == Mode.SHORTCUT:
                        if not engine.shortcut_armed:
                            text = "手势已触发 · 放松 0.3 秒后可再做一次"
                        elif not engine.shortcut_previous_good:
                            text = "请伸直无名指和小指，其他手指自然收拢"
                        else:
                            progress = min(100, round(engine.shortcut_good_s / engine.t.shortcut_hold_s * 100))
                            text = f"Ctrl+Q 确认 {progress}% · 保持无名指和小指伸直"
            if mode == Mode.FIVE_FINGER and event is None:
                with self.controller.lock:
                    engine = self.controller.engine
                    swipe = engine.five
                    missing = [name for name,opened in zip(('拇指','食指','中指','无名指','小指'),engine.five_digits) if not opened]
                    if not swipe.armed:
                        text = "五指命令已触发 · 换其他手形0.3秒后可再做一次"
                    elif missing:
                        text = "五指识别不稳 · 请伸直："+'、'.join(missing)
                    elif swipe.ready_s < engine.t.five_hold_s:
                        text = f"五指确认 {min(100,round(swipe.ready_s/engine.t.five_hold_s*100))}% · 确认后直接打开任务视图"
                    else:
                        text = f"任务视图手势已触发 · 可继续左右划切桌面、下划桌面 · 划动{round(swipe.progress*100)}%"
            elif mode == Mode.PINKY_STOP and event is None:
                with self.controller.lock:
                    digits = self.controller.engine.five_digits
                    if not digits[0] and all(digits[1:]):
                        text = "已检测到四指 · 请同时伸直拇指，进入五指桌面划动"
            if self.controller.state != State.RUNNING:
                text = "输入已禁用"
            self.action.setText("当前动作：" + text)
            if self.floating is not None:
                self.floating.action.setText(text)
            self.metrics.setText(f"实际处理 {fps:.1f} FPS · 采集和推理平均 {mean_ms:.1f} ms")
            if not worker.isRunning():
                worker.wait(0)
                if worker.error:
                    self.notice.setText(worker.error)
                    self.controller.set_state(State.ERROR)
                self.worker = None
                worker.deleteLater()
                self.stopping_since = None
                self.preview.clear()
                self.preview.setText("摄像头已关闭")
                if self.floating is not None:
                    self.floating.clear_preview("摄像头已关闭")
                    self.floating.action.setText(self.notice.text() or "输入已禁用")
            elif self.stopping_since and time.monotonic() - self.stopping_since > 4:
                self.notice.setText("摄像头驱动响应缓慢，输入已禁用，正在等待驱动释放。请尝试断开外接摄像头。")
        self.buttons()
        if self.closing and self.worker is None:
            self.close()

    def show_preview(self, image):
        # A small laptop window must show the whole camera image, including status/IDs.
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(
            self.preview.size(),Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def closeEvent(self, event):
        if self.worker is not None:
            if not self.closing:
                self.closing = True
                self.halt(State.STOPPED)
            event.ignore()  # Asynchronous shutdown; never block the GUI or terminate a live QThread.
            return
        self.controller.set_state(State.STOPPED)
        if self.floating is not None:
            self.floating.shutting_down = True
            self.floating.close()
        self.save_timer.stop()
        self.persist()
        self.timer.stop()
        event.accept()
