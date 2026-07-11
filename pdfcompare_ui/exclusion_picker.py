"""Visual exclusion-region picker for the Tkinter GUI.

Lets the user draw one or more rectangles on a rendered PDF page and returns
them as percent coordinates (the same form ``normalize_exclude_regions``
accepts). Ported from the MCP ``pick_pdf_exclude_region`` tool, but adapted to
run inside the existing GUI as a ``Toplevel`` (so it does not replace the main
Tk root) and to support multiple regions.
"""

from __future__ import annotations

import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

import fitz


def pick_exclude_regions(
    parent: tk.Misc,
    pdf_path: Path,
    page_number: int = 1,
    dpi: int = 120,
    *,
    existing: list[dict[str, float | str]] | None = None,
) -> list[dict[str, float | str]] | None:
    """Open a modal window to draw exclude regions.

    Returns a list of ``{x, y, w, h, unit, anchor}`` dicts in ``percent``
    coordinates (``top_left`` anchor), or ``None`` if the user cancelled.
    """
    pdf = Path(pdf_path)
    if not pdf.exists():
        return None
    page_index = int(page_number) - 1
    if page_index < 0:
        return None

    with fitz.open(pdf) as doc:
        if page_index >= doc.page_count:
            return None
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(float(dpi) / 72.0, float(dpi) / 72.0), alpha=False)
        image_width = int(pix.width)
        image_height = int(pix.height)
        tmp_dir = Path(tempfile.mkdtemp(prefix="pdfcompare_region_"))
        image_path = tmp_dir / "page.png"
        pix.save(image_path)

    dialog = tk.Toplevel(parent)
    dialog.title(parent._tr("pick_title") if hasattr(parent, "_tr") else "PDFCompare")
    dialog.geometry("1200x880")
    dialog.transient(parent)  # type: ignore[call-overload]
    dialog.grab_set()

    regions: list[dict[str, float | str]] = []
    rects: list[int] = []  # canvas rectangle item ids

    info = ttk.Label(
        dialog,
        text=(parent._tr("pick_hint") if hasattr(parent, "_tr") else "Draw regions, then OK."),
        anchor="w",
    )
    info.pack(fill=tk.X, padx=8, pady=(8, 4))

    image = tk.PhotoImage(file=str(image_path))
    max_w, max_h = 1160, 760
    scale = min(max_w / image_width, max_h / image_height, 1.0)
    if scale < 1.0:
        subsample = max(1, round(1.0 / scale))
        display_image = image.subsample(subsample, subsample)
        scale = display_image.width() / image_width
    else:
        display_image = image
    canvas = tk.Canvas(dialog, width=display_image.width(), height=display_image.height(), bg="white", cursor="crosshair")
    canvas.pack(padx=8, pady=4)
    canvas.create_image(0, 0, image=display_image, anchor="nw")

    # Pre-render any existing regions so they are visible on reopen.
    if existing:
        for region in existing:
            try:
                x = float(region["x"]) / 100.0 * image_width * scale
                y = float(region["y"]) / 100.0 * image_height * scale
                w = float(region["w"]) / 100.0 * image_width * scale
                h = float(region["h"]) / 100.0 * image_height * scale
                rid = canvas.create_rectangle(x, y, x + w, y + h, outline="#ff2d2d", width=2)
                rects.append(rid)
                regions.append(_to_percent(region, image_width, image_height))
            except (KeyError, ValueError, TypeError):
                continue

    start_box: list[tuple[float, float] | None] = [None]
    rect_id: list[int | None] = [None]

    def clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def on_press(event: tk.Event) -> None:
        start_box[0] = (clamp(event.x, 0, display_image.width()), clamp(event.y, 0, display_image.height()))
        if rect_id[0] is not None:
            canvas.delete(rect_id[0])
        rect_id[0] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#ff2d2d", width=2)

    def on_drag(event: tk.Event) -> None:
        if start_box[0] is None or rect_id[0] is None:
            return
        x0, y0 = start_box[0]
        x1 = clamp(event.x, 0, display_image.width())
        y1 = clamp(event.y, 0, display_image.height())
        canvas.coords(rect_id[0], x0, y0, x1, y1)

    def on_release(event: tk.Event) -> None:
        if start_box[0] is None or rect_id[0] is None:
            return
        x0, y0 = start_box[0]
        x1 = clamp(event.x, 0, display_image.width())
        y1 = clamp(event.y, 0, display_image.height())
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        if right - left < 3 or bottom - top < 3:
            return  # ignore tiny clicks
        # Convert to percent and clamp so x+w / y+h never exceed 100
        # (rounding each value independently can push the sum past 100,
        # which normalize_exclude_regions would reject).
        x_pct = round(left / scale / image_width * 100.0, 4)
        y_pct = round(top / scale / image_height * 100.0, 4)
        w_pct = round((right - left) / scale / image_width * 100.0, 4)
        h_pct = round((bottom - top) / scale / image_height * 100.0, 4)
        w_pct = min(w_pct, 100.0 - x_pct)
        h_pct = min(h_pct, 100.0 - y_pct)
        regions.append(
            {
                "x": x_pct,
                "y": y_pct,
                "w": w_pct,
                "h": h_pct,
                "unit": "percent",
                "anchor": "top_left",
            }
        )
        rects.append(rect_id[0])
        rect_id[0] = None
        start_box[0] = None

    def undo_last() -> None:
        if rects:
            canvas.delete(rects.pop())
            regions.pop()

    result: dict[str, Any] = {}

    def accept() -> None:
        result["regions"] = regions
        dialog.destroy()

    def cancel(_event: tk.Event | None = None) -> None:
        result["cancelled"] = True
        dialog.destroy()

    buttons = tk.Frame(dialog)
    buttons.pack(fill=tk.X, padx=8, pady=(4, 8))
    tk.Button(buttons, text=(parent._tr("pick_ok") if hasattr(parent, "_tr") else "OK"), command=accept, width=12).pack(side=tk.RIGHT, padx=(6, 0))
    tk.Button(buttons, text=(parent._tr("pick_cancel") if hasattr(parent, "_tr") else "Cancel"), command=cancel, width=12).pack(side=tk.RIGHT)
    tk.Button(buttons, text=(parent._tr("pick_undo") if hasattr(parent, "_tr") else "Undo"), command=undo_last, width=12).pack(side=tk.RIGHT, padx=(0, 6))

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    dialog.bind("<Escape>", cancel)
    parent.wait_window(dialog)

    # Cleanup the temp image; keep it simple and ignore errors.
    try:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass

    if result.get("cancelled"):
        return None
    value: list[dict[str, float | str]] | None = result.get("regions")
    if not value:
        return None
    return value


def _to_percent(region: dict[str, float | str], image_width: int, image_height: int) -> dict[str, float | str]:
    """Best-effort normalization of an existing region to percent form for re-rendering."""
    try:
        return {
            "x": float(region["x"]),
            "y": float(region["y"]),
            "w": float(region["w"]),
            "h": float(region["h"]),
            "unit": "percent",
            "anchor": "top_left",
        }
    except (KeyError, ValueError, TypeError):
        return region
