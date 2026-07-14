# -*- mode: python ; coding: utf-8 -*-
#
# One-DIR build — this is what the installer ships.
#
# The one-FILE build (PDFCompareLocal.spec) unpacks itself into %TEMP%\_MEI<pid>
# on every start and deletes that folder when it exits. During a silent
# auto-update the installer closes the running app and immediately relaunches
# the new one; Windows reuses process ids straight away, so the fresh process
# could start extracting into the very folder the dying one was deleting. The
# result was a half-extracted runtime and "Failed to load Python DLL … python312.dll:
# LoadLibrary: не найден указанный модуль" (the DLL is there, its CRT dependencies
# are not).
#
# A one-dir build has no extraction step at all: the runtime sits next to the exe.
# It also starts noticeably faster. The one-file exe stays as a download for
# people who want a single portable binary.

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

tkdnd_data = []
try:
    import tkinterdnd2
    tkdnd_path = Path(tkinterdnd2.__file__).parent
    tkdnd_data = [(str(tkdnd_path / 'tkdnd'), 'tkinterdnd2/tkdnd')]
except ImportError:
    pass

# The exe's resource icon is what Explorer and the taskbar shortcut show. Tk cannot
# read it, so the .ico also ships as a data file and the window loads it at runtime.
ICON = ROOT / 'packaging' / 'PDFCompareLocal.ico'
icon_data = [(str(ICON), 'packaging')] if ICON.exists() else []

a = Analysis(
    [str(ROOT / 'pdfcompare_gui.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=tkdnd_data + icon_data,
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
    [],
    exclude_binaries=True,
    name='PDFCompareLocal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX is off on purpose: compressing python3xx.dll / the CRT is the other
    # documented way to produce exactly the "Failed to load Python DLL" error.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='PDFCompareLocal',
)
