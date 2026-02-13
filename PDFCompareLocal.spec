# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['pdfcompare_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
