# 验证记录 · 2026-10-14

## 已实际完成

- 环境：Windows x64，系统构建 26220；Python 3.11.7 x64，项目独立 `.venv`。未在 Windows 10、其他 Python 版本上验证。
- 最终完整构建脚本：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1`，退出码 **0**。
- 最终 pytest：**67 passed in 3.94s**；没有跳过项。真实模型进程集成测试已运行。输入全部使用 Fake/Mock，不在测试中操作真实鼠标或发送 Ctrl+Q。
- `python -m pip check`：`No broken requirements found.`；准确版本见 `requirements-lock.txt`。
- 模型：Google 官方 float16/v1 Hand Landmarker，7,819,105 字节；真实加载并执行黑帧推理。下载脚本按以下 SHA256 验证：`fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`。
- EXE：`dist\AirMouseAI\AirMouseAI.exe`，PyInstaller onedir，已生成；最终构建时 GUI 冒烟启动、模型子进程黑帧自检均退出 **0**。
- 打包后的真实相机自检：`--camera-self-test 0`，读取并推理 **12 帧 640×480**，退出 **0**。该模式不创建 Windows 输入后端，不存储相机画面。
- 中文界面已真实启动，截图 `artifacts/window.png` 已查看，文字和控件未发现裁切。
- 相机 0：沙箱内 DSHOW/MSMF 无法打开；沙箱外成功打开、读取并释放。此差异由执行环境访问限制引起，不是最终应用需管理员权限。
- 真实摄像头下的 GUI → 监督线程 → 独立视觉进程链路已短时运行，随后暂停、关闭；输入为 Fake 后端，未向系统发鼠标/键盘事件。
- 模拟永不响应取消的视觉进程，可在限定时间结束，Qt 主线程不被阻塞；错误、停止、暂停状态不会输出输入。

最终构建日志：`artifacts/final-build.log`。打包自检报告：`artifacts/exe-model-report.json`、`artifacts/exe-camera-report.json`。

## 资源与速度实测

短时资源样本，非长时间性能承诺。RSS 使用 psutil；运行态为主进程和视觉子进程求和，共享 DLL 页面可能重复计数。CPU 的 **100% 表示一个逻辑核心**，不是任务管理器整机占用百分比。测试过程有其他开发工作并行，数值仅作本机基线。

真实相机、模拟输入，使用实际软件进程结构（`scripts/benchmark_pipeline.py --camera 0`）：

| 状态 | 合计 RSS | 处理速度 / 说明 |
| --- | --- | --- |
| 首次启动已停止 | 67.3 MiB | 未加载 OpenCV、MediaPipe，未打开相机 |
| 运行，开启预览 | 255.5 MiB | 24.0 FPS，采集/推理平均 12.4 ms；CPU 32.3% 单核心 |
| 运行，关闭预览 | 253.6 MiB | 23.0 FPS，采集/推理平均 10.3 ms；CPU 33.1% 单核心 |
| 暂停、进程回收后 | 78.8 MiB | 暂停到完全回收约 625 ms，视觉子进程数 0 |

此测试无需用户摆手，不代表真实手势操作准确率。预览关闭不保证每次短时采样 CPU 均更低；核心收益是避免额外图像处理，并控制队列容量。

同样结构的合成黑帧样本：停止 62.9 MiB，运行 228.1–228.6 MiB，暂停 73.6 MiB；约 125 ms 回收，子进程数 0。主进程始终未加载 OpenCV/MediaPipe。

单独黑帧模型基线（`scripts/verify_runtime.py`，**此诊断为同进程模型测试，不是应用进程结构**）：模型加载约 703 ms；100 帧平均推理 10.1 ms，P95 16.0 ms。该样本不能用于声称实际端到端响应小于 150 ms。

原始 JSON：`artifacts/live-pipeline-report.json`、`artifacts/pipeline-report.json`、`artifacts/runtime-report.json`。相机源图像未存盘，只有空闲 GUI 截图和汇总数值。

## 待用户实机验证

1. Chrome/Edge 网页和至少一款 PDF 阅读器连续滚动 5 分钟，检查方向、停手停止、微动及误滚。
2. 真实手势单击 20 次、三种模式切换 20 次，记录成功率和误触；长捏/遮挡/手丢失/暂停不应点击。
3. 在可安全接收快捷键的窗口验证特殊手势仅发送一次 Ctrl+Q，放松后可再发送；确认 Ctrl+Alt+G 在其他窗口聚焦时工作。
4. 内置/USB 相机、暗光、占用/拔插、最小化与退出，100%/125% DPI 下光标边界和方向。
5. 30 分钟连续运行，观察 CPU/内存增长和稳定性；点击成功率 ≥90%、端到端 P95 <150 ms 均仍是待测目标。

本记录不把相机短时读取、合成帧测试或 GUI 冒烟启动当作已完成以上人工验收。

## 便携试用包交付复核

- 复核 pytest：**67 passed in 6.23s**，无失败、无跳过；依赖检查再次通过。
- 现有 EXE 的 GUI 冒烟启动及模型子进程自检再次退出 **0**；报告见 `artifacts/release-model-check.json`。
- 便携包：`releases/AirMouseAI-v1.0.0-Windows-x64.zip`，包含完整 onedir 程序、HTML/纯文本使用说明、测试记录和第三方说明。SHA256 校验文件在 ZIP 同目录。
- 当前交付状态为“功能开发和自动化验证完成，可试用，人工体验验收待完成”。此状态不表示上述人工验收项目已经通过。
