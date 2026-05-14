"""Pure-function helpers used by the GUI.

These are extracted from PDFCompareApp methods that did not depend on
widget state and can be tested in isolation.
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz

REVISION_RE = re.compile(r"r[Cc](\d{2,3})")


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
        pass
    try:
        with fitz.open(new_pdf) as doc:
            new_count = len(doc)
    except Exception:
        pass
    return f"{old_count}/{new_count}"


def parse_dnd_filelist(root, data: str) -> list[Path]:
    """Parse tkinterdnd2 drop event.data (tcl-style quoted list) into existing Paths.

    `root` is a tk.Misc whose interpreter knows splitlist semantics.
    """
    files = root.tk.splitlist(data)
    return [Path(f) for f in files if Path(f).exists()]
