# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Locate tkinterdnd2 package data
tkdnd_data = []
try:
    import tkinterdnd2
    tkdnd_path = Path(tkinterdnd2.__file__).parent
    tkdnd_data = [(str(tkdnd_path / 'tkdnd'), 'tkinterdnd2/tkdnd')]
except ImportError:
    pass

a = Analysis(
    [str(ROOT / 'pdfcompare_gui.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=tkdnd_data,
    hiddenimports=['tkinterdnd2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['scipy', 'pandas', 'torch', 'tensorflow', 'PyQt5', 'PyQt6', 'PySide6', 'matplotlib', 'IPython', 'numba', 'llvmlite', 'pyarrow', 'openpyxl', 'jupyter'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PDFCompareLocal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
