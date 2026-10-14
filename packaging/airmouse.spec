# PyInstaller onedir; include only the Qt modules the desktop UI actually uses.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH).parent
datas = [(str(root / 'assets/models/hand_landmarker.task'), 'assets/models'),
         (str(root / 'THIRD_PARTY_NOTICES.md'), '.'),
         (str(root / 'artifacts/third-party'), 'third-party')]
datas += collect_data_files('mediapipe')
binaries = collect_dynamic_libs('mediapipe')
a = Analysis([str(root / 'packaging/launcher.py')], pathex=[str(root / 'src')],
             binaries=binaries, datas=datas,
             hiddenimports=['mediapipe.tasks.c', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets'],
             hooksconfig={'matplotlib': {'backends': ['Agg']}},
             excludes=['tkinter', 'pytest', 'psutil', 'IPython', 'pandas',
                       'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtNetwork',
                       'PySide6.QtMultimedia', 'PySide6.QtWebEngineCore'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AirMouseAI',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, uac_admin=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='AirMouseAI')
