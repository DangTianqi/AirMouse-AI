# 第三方组件与分发说明

依赖版本以 `pyproject.toml` 和 `requirements-lock.txt` 为准。

| 组件 | 主要授权/来源 |
| --- | --- |
| Python | PSF License；https://docs.python.org/3/license.html |
| MediaPipe | Apache-2.0；https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE |
| Hand Landmarker 模型 | 官方模型页面：https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/index#models；官方 MediaPipe 项目 Apache-2.0 声明及模型卡需随分发版本复核 |
| OpenCV 4.11 / contrib | Apache-2.0；wheel 内另含第三方许可，见 https://github.com/opencv/opencv-python/blob/master/LICENSE-3RD-PARTY.txt |
| NumPy | BSD-3-Clause；wheel 内可能包含其他数学库许可 |
| PySide6-Essentials / Shiboken6 / Qt 6.8.3 | LGPLv3 / GPLv3 / 商业授权，具体组件以 wheel 中许可证为准；https://doc.qt.io/qtforpython-6/licenses.html |
| PyInstaller（构建工具） | GPL-2.0-or-later 加 bootloader 分发例外；https://pyinstaller.org/en/stable/license.html |
| pytest、psutil（开发测试工具） | MIT、BSD-3-Clause；不作为产品运行功能打包 |

构建时 `scripts/collect_licenses.py` 收集已安装包的 LICENSE、NOTICE、COPYING 文件到 `artifacts/third-party`，一并放入 EXE 文件夹。依赖的准确附属许可证请以这些文件为准。

Qt 使用动态库、onedir 分发，不捆绑 Qt WebEngine；商业分发前须核对所用 Qt 模块、许可通知、修改源码提供义务及用户替换动态库等 LGPL 要求，或选用适用的商业授权。此表为工程来源记录，不代表已完成商业合规审查。项目自身未擅自指定用户代码的开源许可证。

模型下载地址（仅开发/构建阶段访问）：
https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
