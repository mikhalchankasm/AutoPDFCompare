"""Pure-function helpers used by the GUI.

These are extracted from PDFCompareApp methods that did not depend on
widget state and can be tested in isolation.
"""

from __future__ import annotations

import logging
import re
import sys
import tkinter as tk
from pathlib import Path

import fitz

REVISION_RE = re.compile(r"r[Cc](\d{2,3})")
logger = logging.getLogger("pdfcompare.ui.utils")


def resource_path(*parts: str) -> Path:
    """A file that ships with the app, wherever the app is running from.

    From the repo that is just the source tree. In a PyInstaller build the data
    files are unpacked next to the bootloader instead, and only `sys._MEIPASS`
    knows where — the source layout does not exist there at all.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parents[1]
    return base.joinpath(*parts)


def screen_work_area(widget: tk.Misc) -> tuple[int, int]:
    """Usable desktop area — the screen minus the taskbar.

    Tk only reports the raw screen size, so a dialog sized from it hides behind
    the taskbar. Windows knows the real work area; ask it. Anywhere else, fall
    back to the screen with a conservative margin.
    """
    try:
        import ctypes

        class _Rect(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long),
            ]

        rect = _Rect()
        spi_getworkarea = 0x0030
        if ctypes.windll.user32.SystemParametersInfoW(spi_getworkarea, 0, ctypes.byref(rect), 0):
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width > 200 and height > 200:
                return width, height
    except Exception:
        logger.info("Could not query the Windows work area; using Tk dimensions", exc_info=True)
    return widget.winfo_screenwidth(), widget.winfo_screenheight() - 80


def format_duration_mmss(seconds: float) -> str:
    """Format a non-negative duration as MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def extract_revision_label(path_text: str) -> str:
    """Extract a 'v.Cxx' revision label from filenames like 'foo_rC03.pdf'."""
    name = Path(path_text).name
    m = REVISION_RE.search(name)
    return f"v.C{m.group(1)}" if m else ""


def count_pdf_pages_pair(old_pdf: Path, new_pdf: Path) -> str:
    """Return 'old_count/new_count' page counts; returns '' if PyMuPDF unavailable.

    Individual file failures degrade to 0 for that file.
    """
    old_count = 0
    new_count = 0
    try:
        with fitz.open(old_pdf) as doc:
            old_count = len(doc)
    except Exception:
        logger.info("Could not read page count from %s", old_pdf, exc_info=True)
    try:
        with fitz.open(new_pdf) as doc:
            new_count = len(doc)
    except Exception:
        logger.info("Could not read page count from %s", new_pdf, exc_info=True)
    return f"{old_count}/{new_count}"


def parse_dnd_filelist(root, data: str) -> list[Path]:
    """Parse tkinterdnd2 drop event.data (tcl-style quoted list) into existing Paths.

    `root` is a tk.Misc whose interpreter knows splitlist semantics.
    """
    files = root.tk.splitlist(data)
    return [Path(f) for f in files if Path(f).exists()]
