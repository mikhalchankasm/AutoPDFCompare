"""Visual exclusion-region picker for the Tkinter GUI.

Lets the user draw one or more rectangles on a rendered PDF page and returns
them as percent coordinates (the same form ``normalize_exclude_regions``
accepts). Runs inside the existing GUI as a ``Toplevel``.

Features:
- paper format readout/override (auto-detected A4/A3/A2/A1/A0 or custom);
- millimetre grid overlay with selectable step;
- live size label (in mm) while drawing or resizing;
- boxes can be selected, moved, resized via handles and deleted;
- per-region corner anchor (e.g. bottom_right keeps a stamp zone in place
  on sheets of different formats);
- page navigation for multi-page documents;
- existing regions from the entry field are shown and stay editable.
"""

from __future__ import annotations

import base64
import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

import fitz

from pdfcompare_core.exclusions import exclusion_regions_to_pixel_boxes

PT_PER_MM = 72.0 / 25.4

# ISO A-series paper sizes (portrait, mm).
ISO_FORMATS: list[tuple[str, float, float]] = [
    ("A4", 210.0, 297.0),
    ("A3", 297.0, 420.0),
    ("A2", 420.0, 594.0),
    ("A1", 594.0, 841.0),
    ("A0", 841.0, 1189.0),
]
FORMAT_TOLERANCE_MM = 8.0

GRID_STEPS_MM = (5, 10, 25, 50)
HANDLE_PX = 4  # half-size of a resize handle square
HIT_PX = 8  # grab radius around a handle centre
MIN_BOX_PX = 3

BOX_COLOR = "#e11d48"
BOX_SELECTED_COLOR = "#2563eb"
GRID_MINOR_COLOR = "#d7dee8"
GRID_MAJOR_COLOR = "#b5c0cf"

# Resize handles: id -> (x factor, y factor) inside the box rectangle.
HANDLES: dict[str, tuple[float, float]] = {
    "nw": (0.0, 0.0), "n": (0.5, 0.0), "ne": (1.0, 0.0),
    "e": (1.0, 0.5), "se": (1.0, 1.0), "s": (0.5, 1.0),
    "sw": (0.0, 1.0), "w": (0.0, 0.5),
}
HANDLE_CURSORS = {
    "nw": "size_nw_se", "se": "size_nw_se",
    "ne": "size_ne_sw", "sw": "size_ne_sw",
    "n": "size_ns", "s": "size_ns",
    "e": "size_we", "w": "size_we",
}

# Region anchor: which page corner x/y are measured from. bottom_right keeps
# a stamp zone in place on sheets of different formats.
ANCHORS = ("top_left", "top_right", "bottom_left", "bottom_right")
ANCHOR_ALIASES = {
    "top_left": "top_left", "left_top": "top_left", "tl": "top_left",
    "top_right": "top_right", "right_top": "top_right", "tr": "top_right",
    "bottom_left": "bottom_left", "left_bottom": "bottom_left", "bl": "bottom_left",
    "bottom_right": "bottom_right", "right_bottom": "bottom_right", "br": "bottom_right",
}
ANCHOR_ARROWS = {"top_left": "↖", "top_right": "↗", "bottom_left": "↙", "bottom_right": "↘"}


def _canonical_anchor(raw: object) -> str:
    text = str(raw or "top_left").strip().casefold().replace("-", "_")
    return ANCHOR_ALIASES.get(text, "top_left")


def format_regions_for_field(regions: list[dict[str, float | str]]) -> str:
    """Serialize picker output for the "Exclude regions" entry field.

    Plain ``x,y,w,h;…`` percent text while every region is top_left-anchored
    (backwards compatible); compact JSON once any region carries an anchor.
    """
    if all(_canonical_anchor(r.get("anchor")) == "top_left" for r in regions):
        return ";".join(f"{r['x']:.4g},{r['y']:.4g},{r['w']:.4g},{r['h']:.4g}" for r in regions)
    items = [
        {
            "x": round(float(r["x"]), 3),
            "y": round(float(r["y"]), 3),
            "w": round(float(r["w"]), 3),
            "h": round(float(r["h"]), 3),
            "unit": "percent",
            "anchor": _canonical_anchor(r.get("anchor")),
        }
        for r in regions
    ]
    return json.dumps(items, ensure_ascii=False, separators=(",", ":"))


def _detect_format(w_mm: float, h_mm: float) -> str | None:
    short, long_ = sorted((w_mm, h_mm))
    for name, fw, fh in ISO_FORMATS:
        if abs(short - fw) <= FORMAT_TOLERANCE_MM and abs(long_ - fh) <= FORMAT_TOLERANCE_MM:
            return name
    return None


class _RegionPicker:
    def __init__(
        self,
        parent: tk.Misc,
        doc: fitz.Document,
        page_number: int,
        existing: list[dict[str, float | str]] | None,
        initial_anchor: str = "top_left",
    ) -> None:
        self.parent = parent
        self.doc = doc
        self.page_index = min(max(int(page_number) - 1, 0), doc.page_count - 1)
        self.result: dict[str, Any] = {}

        # Model: regions as percent-of-page dicts {x, y, w, h} in top-left
        # coordinates (canvas space); "anchor" only changes how the region is
        # exported on OK and how the readout counts offsets.
        self.regions: list[dict[str, Any]] = []
        self.selected: int | None = None
        self.default_anchor = _canonical_anchor(initial_anchor)

        # Interaction state.
        self._mode: str | None = None  # 'draw' | 'move' | 'resize'
        self._press_xy = (0.0, 0.0)
        self._orig_px: tuple[float, float, float, float] | None = None
        self._handle: str | None = None
        self._draw_rect_px: tuple[float, float, float, float] | None = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title(self._tr("pick_title", "PDFCompare: select exclude regions"))
        # A transient of an unmapped owner never maps on Windows — skip it when
        # the parent is a hidden service root (e.g. the MCP picker).
        try:
            if parent.winfo_viewable():
                self.dialog.transient(parent)  # type: ignore[call-overload]
        except tk.TclError:
            pass
        self.dialog.grab_set()
        self.dialog.resizable(False, False)

        screen_w = self.dialog.winfo_screenwidth()
        screen_h = self.dialog.winfo_screenheight()
        self.max_w = min(1360, max(640, screen_w - 220))
        self.max_h = min(860, max(480, screen_h - 260))

        toolbar = tk.Frame(self.dialog)
        toolbar.pack(fill=tk.X, padx=8, pady=(8, 2))

        ttk.Label(toolbar, text=self._tr("pick_format", "Format:")).pack(side=tk.LEFT)
        self.format_var = tk.StringVar()
        self.format_combo = ttk.Combobox(toolbar, textvariable=self.format_var, state="readonly", width=22)
        self.format_combo.pack(side=tk.LEFT, padx=(4, 14))
        self.format_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_format_change())

        ttk.Label(toolbar, text=self._tr("pick_grid", "Grid:")).pack(side=tk.LEFT)
        self.grid_var = tk.StringVar(value=f"10 {self._mm()}")
        grid_values = [self._tr("pick_grid_off", "Off")] + [f"{step} {self._mm()}" for step in GRID_STEPS_MM]
        self.grid_combo = ttk.Combobox(toolbar, textvariable=self.grid_var, state="readonly", width=8, values=grid_values)
        self.grid_combo.pack(side=tk.LEFT, padx=(4, 14))
        self.grid_combo.bind("<<ComboboxSelected>>", lambda _e: self._redraw())

        ttk.Label(toolbar, text=self._tr("pick_anchor", "Anchor:")).pack(side=tk.LEFT)
        self._anchor_labels = {
            "top_left": self._tr("pick_anchor_tl", "↖ top-left"),
            "top_right": self._tr("pick_anchor_tr", "↗ top-right"),
            "bottom_left": self._tr("pick_anchor_bl", "↙ bottom-left"),
            "bottom_right": self._tr("pick_anchor_br", "↘ bottom-right"),
        }
        self.anchor_var = tk.StringVar(value=self._anchor_labels[self.default_anchor])
        self.anchor_combo = ttk.Combobox(
            toolbar, textvariable=self.anchor_var, state="readonly", width=16,
            values=[self._anchor_labels[a] for a in ANCHORS],
        )
        self.anchor_combo.pack(side=tk.LEFT, padx=(4, 14))
        self.anchor_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_anchor_change())

        ttk.Label(toolbar, text=self._tr("pick_page", "Page:")).pack(side=tk.LEFT)
        self.page_var: tk.StringVar | None = tk.StringVar(value=str(self.page_index + 1))
        self.page_spin = ttk.Spinbox(
            toolbar, from_=1, to=max(1, doc.page_count), textvariable=self.page_var, width=5,
            command=self._on_page_change,
        )
        self.page_spin.pack(side=tk.LEFT, padx=(4, 2))
        self.page_spin.bind("<Return>", lambda _e: self._on_page_change())
        self.page_total_label = ttk.Label(toolbar, text=f"/ {doc.page_count}")
        self.page_total_label.pack(side=tk.LEFT, padx=(0, 14))

        # Any PDF can serve as the drawing backdrop: pick a cleaner revision or
        # a template sheet and trace exclusion zones over it. Zones stay in
        # percent of the page, so they apply to the compared documents as-is.
        self._owned_docs: list[fitz.Document] = []
        self.backdrop_path = ""
        ttk.Button(toolbar, text=self._tr("pick_backdrop", "Backdrop…"), command=self._choose_backdrop).pack(side=tk.LEFT)

        self.readout = ttk.Label(toolbar, text="")
        self.readout.pack(side=tk.RIGHT)

        hint = ttk.Label(
            self.dialog,
            text=self._tr(
                "pick_hint",
                "Drag to draw a region · drag a box to move it · drag handles to resize · Del removes selected · Esc cancels.",
            ),
            anchor="w",
        )
        hint.pack(fill=tk.X, padx=8, pady=(0, 4))

        self.canvas = tk.Canvas(self.dialog, bg="white", cursor="crosshair", highlightthickness=1, highlightbackground="#c9d2de")
        self.canvas.pack(padx=8, pady=2)

        buttons = tk.Frame(self.dialog)
        buttons.pack(fill=tk.X, padx=8, pady=(4, 8))
        tk.Button(buttons, text=self._tr("pick_ok", "OK"), command=self._accept, width=12).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(buttons, text=self._tr("pick_cancel", "Cancel"), command=self._cancel, width=12).pack(side=tk.RIGHT)
        tk.Button(buttons, text=self._tr("pick_delete", "Delete selected"), command=self._delete_selected, width=18).pack(side=tk.LEFT)
        tk.Button(buttons, text=self._tr("pick_undo", "Undo last"), command=self._undo_last, width=18).pack(side=tk.LEFT, padx=(6, 0))

        self._load_page()
        self._import_existing(existing or [])

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_motion)
        self.dialog.bind("<Escape>", self._on_escape)
        self.dialog.bind("<Delete>", self._on_delete_key)
        self.dialog.bind("<BackSpace>", self._on_delete_key)

        self.dialog.lift()
        self.dialog.focus_force()
        self._redraw()

    # ----- i18n -----

    def _tr(self, key: str, fallback: str, **kwargs: object) -> str:
        tr = getattr(self.parent, "_tr", None)
        if callable(tr):
            try:
                text = tr(key, **kwargs)
                if text != key:
                    return text
            except Exception:
                pass
        return fallback.format(**kwargs) if kwargs else fallback

    def _mm(self) -> str:
        return self._tr("pick_mm", "mm")

    # ----- page rendering / geometry -----

    def _load_page(self) -> None:
        page = self.doc[self.page_index]
        rect = page.rect
        self.page_w_mm = max(rect.width / PT_PER_MM, 1.0)
        self.page_h_mm = max(rect.height / PT_PER_MM, 1.0)
        zoom = min(self.max_w / max(rect.width, 1.0), self.max_h / max(rect.height, 1.0), 4.0)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        self.photo = tk.PhotoImage(data=base64.b64encode(pix.tobytes("png")))
        self.page_view_w = self.photo.width()
        self.page_view_h = self.photo.height()
        self._refresh_format_choices()
        self._apply_view()

    def _is_schematic(self) -> bool:
        """An explicit format override shows a blank schematic sheet instead of
        the real page — the user asked to trace stamp zones on a clean sheet
        of the target format, not on a live drawing."""
        return self.format_var.get() != self._auto_label

    def _apply_view(self) -> None:
        """Size the canvas: real page render in Auto mode, blank sheet of the
        chosen format (true proportions) in schematic mode."""
        if self._is_schematic():
            fmt_w, fmt_h = self._format_mm()
            px_per_mm = min(self.max_w / fmt_w, self.max_h / fmt_h)
            self.disp_w = max(1, int(round(fmt_w * px_per_mm)))
            self.disp_h = max(1, int(round(fmt_h * px_per_mm)))
        else:
            self.disp_w = self.page_view_w
            self.disp_h = self.page_view_h
        self.canvas.configure(width=self.disp_w, height=self.disp_h)

    def _on_format_change(self) -> None:
        self._apply_view()
        self._redraw()

    def _refresh_format_choices(self) -> None:
        detected = _detect_format(self.page_w_mm, self.page_h_mm)
        if detected:
            auto_size = f"{detected} · {self.page_w_mm:.0f}×{self.page_h_mm:.0f} {self._mm()}"
        else:
            auto_size = f"{self.page_w_mm:.0f}×{self.page_h_mm:.0f} {self._mm()}"
        auto_label = self._tr("pick_format_auto", "Auto: {size}", size=auto_size)
        values = [auto_label] + [name for name, _w, _h in ISO_FORMATS]
        current = self.format_var.get()
        self.format_combo.configure(values=values)
        # Keep an explicit override across page switches; otherwise track auto.
        if current not in values:
            self.format_var.set(auto_label)
        self._auto_label = auto_label

    def _format_mm(self) -> tuple[float, float]:
        """Sheet size in mm used for the grid and size labels."""
        choice = self.format_var.get()
        for name, fw, fh in ISO_FORMATS:
            if choice == name:
                # Orient the chosen format to match the page orientation
                # (from the page's physical size, not the current canvas).
                if self.page_w_mm >= self.page_h_mm:
                    return max(fw, fh), min(fw, fh)
                return min(fw, fh), max(fw, fh)
        return self.page_w_mm, self.page_h_mm

    def _grid_step_mm(self) -> float | None:
        raw = self.grid_var.get().split()[0]
        try:
            return float(raw)
        except ValueError:
            return None  # "Off"

    # ----- model/coordinate helpers -----

    def _to_px(self, region: dict[str, Any]) -> tuple[float, float, float, float]:
        return (
            float(region["x"]) / 100.0 * self.disp_w,
            float(region["y"]) / 100.0 * self.disp_h,
            float(region["w"]) / 100.0 * self.disp_w,
            float(region["h"]) / 100.0 * self.disp_h,
        )

    def _set_from_px(self, region: dict[str, Any], x: float, y: float, w: float, h: float) -> None:
        region["x"] = x / self.disp_w * 100.0
        region["y"] = y / self.disp_h * 100.0
        region["w"] = w / self.disp_w * 100.0
        region["h"] = h / self.disp_h * 100.0

    def _size_mm(self, region: dict[str, Any]) -> tuple[float, float]:
        fmt_w, fmt_h = self._format_mm()
        return float(region["w"]) / 100.0 * fmt_w, float(region["h"]) / 100.0 * fmt_h

    def _clamp_x(self, x: float) -> float:
        return max(0.0, min(float(self.disp_w), x))

    def _clamp_y(self, y: float) -> float:
        return max(0.0, min(float(self.disp_h), y))

    def _import_existing(self, existing: list[dict[str, float | str]]) -> None:
        """Convert incoming regions (any supported unit/anchor) to percent boxes.

        Converted one by one so each region keeps its own anchor even if a
        malformed neighbour gets dropped.
        """
        display_dpi = self.disp_w / self.page_w_mm * 25.4
        for raw in existing or []:
            try:
                boxes = exclusion_regions_to_pixel_boxes([raw], self.disp_w, self.disp_h, dpi=display_dpi)
            except (ValueError, KeyError, TypeError):
                continue
            if not boxes:
                continue
            x_px, y_px, w_px, h_px = boxes[0]
            region: dict[str, Any] = {"anchor": _canonical_anchor(raw.get("anchor") if isinstance(raw, dict) else None)}
            self._set_from_px(region, float(x_px), float(y_px), max(float(w_px), 1.0), max(float(h_px), 1.0))
            self.regions.append(region)

    # ----- drawing -----

    def _redraw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        if self._is_schematic():
            self._draw_schematic_sheet()
        else:
            canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self._draw_grid()
        for idx, region in enumerate(self.regions):
            self._draw_region(idx, region)
        if self._draw_rect_px is not None:
            x, y, w, h = self._draw_rect_px
            canvas.create_rectangle(x, y, x + w, y + h, outline=BOX_COLOR, width=2, dash=(4, 3))
        self._update_readout()

    def _draw_schematic_sheet(self) -> None:
        """Blank sheet of the chosen format: GOST-style frame (20 mm binding
        margin on the left, 5 mm elsewhere) and a dashed reference title block
        185×55 mm in the bottom-right corner, so the user immediately sees
        where stamps live and can trace them."""
        fmt_w, fmt_h = self._format_mm()
        ppx = self.disp_w / fmt_w
        ppy = self.disp_h / fmt_h
        canvas = self.canvas
        canvas.create_rectangle(0, 0, self.disp_w, self.disp_h, fill="#ffffff", outline="#94a3b8")
        frame_x0, frame_y0 = 20.0 * ppx, 5.0 * ppy
        frame_x1, frame_y1 = self.disp_w - 5.0 * ppx, self.disp_h - 5.0 * ppy
        canvas.create_rectangle(frame_x0, frame_y0, frame_x1, frame_y1, outline="#64748b", width=2)
        stamp_w, stamp_h = 185.0 * ppx, 55.0 * ppy
        stamp_x0, stamp_y0 = frame_x1 - stamp_w, frame_y1 - stamp_h
        if stamp_x0 > frame_x0 and stamp_y0 > frame_y0:
            canvas.create_rectangle(stamp_x0, stamp_y0, frame_x1, frame_y1, outline="#94a3b8", dash=(5, 3))
            canvas.create_text(
                (stamp_x0 + frame_x1) / 2,
                (stamp_y0 + frame_y1) / 2,
                text=self._tr("pick_stamp_ref", "Title block 185×55 mm"),
                fill="#94a3b8",
                font=("TkDefaultFont", 9),
            )
        caption = f"{self.format_var.get()} · {fmt_w:.0f}×{fmt_h:.0f} {self._mm()}"
        canvas.create_text(self.disp_w / 2, frame_y0 + 16, text=caption, fill="#94a3b8", font=("TkDefaultFont", 10, "bold"))

    def _draw_grid(self) -> None:
        step = self._grid_step_mm()
        if not step:
            return
        fmt_w, fmt_h = self._format_mm()
        px_per_mm_x = self.disp_w / fmt_w
        px_per_mm_y = self.disp_h / fmt_h
        i = 1
        x = step * px_per_mm_x
        while x < self.disp_w:
            major = (i * step) % 50 == 0
            self.canvas.create_line(x, 0, x, self.disp_h, fill=GRID_MAJOR_COLOR if major else GRID_MINOR_COLOR)
            i += 1
            x = i * step * px_per_mm_x
        i = 1
        y = step * px_per_mm_y
        while y < self.disp_h:
            major = (i * step) % 50 == 0
            self.canvas.create_line(0, y, self.disp_w, y, fill=GRID_MAJOR_COLOR if major else GRID_MINOR_COLOR)
            i += 1
            y = i * step * px_per_mm_y

    def _draw_region(self, idx: int, region: dict[str, Any]) -> None:
        x, y, w, h = self._to_px(region)
        selected = idx == self.selected
        color = BOX_SELECTED_COLOR if selected else BOX_COLOR
        self.canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=2)
        anchor = _canonical_anchor(region.get("anchor"))
        if anchor != "top_left":
            # Mark the anchored corner with a small filled square.
            ax = x if "left" in anchor else x + w
            ay = y if "top" in anchor else y + h
            self.canvas.create_rectangle(ax - 5, ay - 5, ax + 5, ay + 5, fill=color, outline="#ffffff", width=1)
        w_mm, h_mm = self._size_mm(region)
        arrow = "" if anchor == "top_left" else ANCHOR_ARROWS[anchor] + " "
        label = f"{arrow}{w_mm:.0f}×{h_mm:.0f} {self._mm()}"
        text_id = self.canvas.create_text(x + 4, y + 3, text=label, anchor="nw", fill=color, font=("TkDefaultFont", 8, "bold"))
        bbox = self.canvas.bbox(text_id)
        if bbox:
            bg = self.canvas.create_rectangle(bbox[0] - 1, bbox[1], bbox[2] + 1, bbox[3], fill="#ffffff", outline="")
            self.canvas.tag_lower(bg, text_id)
        if selected:
            for hx, hy in self._handle_positions(region).values():
                self.canvas.create_rectangle(
                    hx - HANDLE_PX, hy - HANDLE_PX, hx + HANDLE_PX, hy + HANDLE_PX,
                    fill="#ffffff", outline=color, width=2,
                )

    def _handle_positions(self, region: dict[str, float]) -> dict[str, tuple[float, float]]:
        x, y, w, h = self._to_px(region)
        return {hid: (x + fx * w, y + fy * h) for hid, (fx, fy) in HANDLES.items()}

    def _draw_live_label(self, x: float, y: float, w_px: float, h_px: float) -> None:
        fmt_w, fmt_h = self._format_mm()
        w_mm = w_px / self.disp_w * fmt_w
        h_mm = h_px / self.disp_h * fmt_h
        label = f"{w_mm:.0f}×{h_mm:.0f} {self._mm()}"
        tx = min(x + 14, self.disp_w - 40)
        ty = max(y - 12, 8)
        text_id = self.canvas.create_text(tx, ty, text=label, anchor="w", fill="#111827", font=("TkDefaultFont", 9, "bold"))
        bbox = self.canvas.bbox(text_id)
        if bbox:
            bg = self.canvas.create_rectangle(bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1, fill="#fef3c7", outline="#f59e0b")
            self.canvas.tag_lower(bg, text_id)

    def _update_readout(self) -> None:
        if self.selected is None or self.selected >= len(self.regions):
            self.readout.configure(text=self._tr("pick_count", "Regions: {count}", count=len(self.regions)))
            return
        region = self.regions[self.selected]
        fmt_w, fmt_h = self._format_mm()
        anchor = _canonical_anchor(region.get("anchor"))
        # Offsets are measured from the anchored corner, matching the export.
        x_pct, y_pct = float(region["x"]), float(region["y"])
        w_pct, h_pct = float(region["w"]), float(region["h"])
        x_off = (100.0 - x_pct - w_pct) if "right" in anchor else x_pct
        y_off = (100.0 - y_pct - h_pct) if "bottom" in anchor else y_pct
        x_mm = x_off / 100.0 * fmt_w
        y_mm = y_off / 100.0 * fmt_h
        w_mm, h_mm = self._size_mm(region)
        arrow = ANCHOR_ARROWS[anchor]
        self.readout.configure(text=f"{arrow} x {x_mm:.0f} · y {y_mm:.0f} · {w_mm:.0f}×{h_mm:.0f} {self._mm()}")

    # ----- anchor -----

    def _sync_anchor_combo(self) -> None:
        anchor = self.default_anchor
        if self.selected is not None and self.selected < len(self.regions):
            anchor = _canonical_anchor(self.regions[self.selected].get("anchor"))
        self.anchor_var.set(self._anchor_labels[anchor])

    def _on_anchor_change(self) -> None:
        idx = self.anchor_combo.current()
        if idx < 0 or idx >= len(ANCHORS):
            return
        anchor = ANCHORS[idx]
        # New boxes inherit the last chosen anchor; a selected box changes too.
        self.default_anchor = anchor
        if self.selected is not None and self.selected < len(self.regions):
            self.regions[self.selected]["anchor"] = anchor
        self._redraw()

    # ----- interaction -----

    def _hit_handle(self, x: float, y: float) -> str | None:
        if self.selected is None or self.selected >= len(self.regions):
            return None
        for hid, (hx, hy) in self._handle_positions(self.regions[self.selected]).items():
            if abs(x - hx) <= HIT_PX and abs(y - hy) <= HIT_PX:
                return hid
        return None

    def _hit_region(self, x: float, y: float) -> int | None:
        for idx in range(len(self.regions) - 1, -1, -1):
            rx, ry, rw, rh = self._to_px(self.regions[idx])
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return idx
        return None

    def _on_press(self, event: tk.Event) -> None:
        x, y = self._clamp_x(event.x), self._clamp_y(event.y)
        self._press_xy = (x, y)
        handle = self._hit_handle(x, y)
        if handle is not None and self.selected is not None:
            self._mode = "resize"
            self._handle = handle
            self._orig_px = self._to_px(self.regions[self.selected])
            return
        idx = self._hit_region(x, y)
        if idx is not None:
            self.selected = idx
            self._mode = "move"
            self._orig_px = self._to_px(self.regions[idx])
            self._sync_anchor_combo()
            self._redraw()
            return
        self.selected = None
        self._mode = "draw"
        self._draw_rect_px = (x, y, 0.0, 0.0)
        self._sync_anchor_combo()
        self._redraw()

    def _on_drag(self, event: tk.Event) -> None:
        if self._mode is None:
            return
        x, y = self._clamp_x(event.x), self._clamp_y(event.y)
        px, py = self._press_xy
        if self._mode == "draw":
            left, right = sorted((px, x))
            top, bottom = sorted((py, y))
            self._draw_rect_px = (left, top, right - left, bottom - top)
            self._redraw()
            self._draw_live_label(x, y, right - left, bottom - top)
        elif self._mode == "move" and self.selected is not None and self._orig_px is not None:
            ox, oy, ow, oh = self._orig_px
            nx = max(0.0, min(self.disp_w - ow, ox + (x - px)))
            ny = max(0.0, min(self.disp_h - oh, oy + (y - py)))
            self._set_from_px(self.regions[self.selected], nx, ny, ow, oh)
            self._redraw()
        elif self._mode == "resize" and self.selected is not None and self._orig_px is not None:
            self._apply_resize(x, y)
            self._redraw()
            rx, ry, rw, rh = self._to_px(self.regions[self.selected])
            self._draw_live_label(x, y, rw, rh)

    def _apply_resize(self, x: float, y: float) -> None:
        assert self._orig_px is not None and self._handle is not None and self.selected is not None
        ox, oy, ow, oh = self._orig_px
        left, top, right, bottom = ox, oy, ox + ow, oy + oh
        h = self._handle
        if "w" in h:
            left = min(x, right - MIN_BOX_PX)
        if "e" in h:
            right = max(x, left + MIN_BOX_PX)
        if "n" in h:
            top = min(y, bottom - MIN_BOX_PX)
        if "s" in h:
            bottom = max(y, top + MIN_BOX_PX)
        left, right = self._clamp_x(left), self._clamp_x(right)
        top, bottom = self._clamp_y(top), self._clamp_y(bottom)
        self._set_from_px(self.regions[self.selected], left, top, right - left, bottom - top)

    def _on_release(self, event: tk.Event) -> None:
        if self._mode == "draw" and self._draw_rect_px is not None:
            x, y, w, h = self._draw_rect_px
            if w >= MIN_BOX_PX and h >= MIN_BOX_PX:
                region: dict[str, Any] = {"anchor": self.default_anchor}
                self._set_from_px(region, x, y, w, h)
                self.regions.append(region)
                self.selected = len(self.regions) - 1
        self._mode = None
        self._handle = None
        self._orig_px = None
        self._draw_rect_px = None
        self._redraw()

    def _on_motion(self, event: tk.Event) -> None:
        if self._mode is not None:
            return
        handle = self._hit_handle(event.x, event.y)
        if handle is not None:
            self.canvas.configure(cursor=HANDLE_CURSORS.get(handle, "crosshair"))
        elif self._hit_region(event.x, event.y) is not None:
            self.canvas.configure(cursor="fleur")
        else:
            self.canvas.configure(cursor="crosshair")

    def _on_escape(self, _event: tk.Event | None = None) -> None:
        if self.selected is not None:
            self.selected = None
            self._sync_anchor_combo()
            self._redraw()
            return
        self._cancel()

    def _on_page_change(self) -> None:
        if self.page_var is None:
            return
        try:
            page = int(self.page_var.get())
        except (ValueError, tk.TclError):
            return
        page_index = min(max(page - 1, 0), self.doc.page_count - 1)
        if page_index == self.page_index:
            return
        self.page_index = page_index
        self._load_page()
        self._redraw()

    # ----- backdrop -----

    def _choose_backdrop(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            parent=self.dialog,
            title=self._tr("pick_backdrop_dlg", "Choose backdrop PDF"),
            filetypes=[("PDF", "*.pdf")],
        )
        if path:
            self.set_backdrop(Path(path))

    def set_backdrop(self, path: Path) -> bool:
        """Switch the preview document to another PDF (visual reference only)."""
        try:
            doc = fitz.open(path)
        except Exception:
            return False
        if doc.page_count < 1:
            doc.close()
            return False
        self._owned_docs.append(doc)
        self.doc = doc
        self.backdrop_path = str(path)
        self.page_index = 0
        if self.page_var is not None:
            self.page_var.set("1")
        self.page_spin.configure(to=doc.page_count)
        self.page_total_label.configure(text=f"/ {doc.page_count}")
        self.dialog.title(f"{self._tr('pick_title', 'PDFCompare: select exclude regions')} — {Path(path).name}")
        self._load_page()
        self._redraw()
        return True

    def close_owned_documents(self) -> None:
        for doc in self._owned_docs:
            try:
                doc.close()
            except Exception:
                pass
        self._owned_docs.clear()

    def _on_delete_key(self, _event: tk.Event | None = None) -> None:
        widget = self.dialog.focus_get()
        # Don't hijack Delete/Backspace while typing in the page spinbox etc.
        if isinstance(widget, (tk.Entry, ttk.Entry)):
            return
        self._delete_selected()

    def _delete_selected(self) -> None:
        if self.selected is None or self.selected >= len(self.regions):
            return
        self.regions.pop(self.selected)
        self.selected = None
        self._sync_anchor_combo()
        self._redraw()

    def _undo_last(self) -> None:
        if not self.regions:
            return
        self.regions.pop()
        if self.selected is not None and self.selected >= len(self.regions):
            self.selected = None
        self._redraw()

    # ----- dialog result -----

    def _accept(self) -> None:
        out: list[dict[str, float | str]] = []
        for region in self.regions:
            x = round(max(0.0, min(100.0, float(region["x"]))), 4)
            y = round(max(0.0, min(100.0, float(region["y"]))), 4)
            w = round(max(0.0, float(region["w"])), 4)
            h = round(max(0.0, float(region["h"])), 4)
            w = min(w, round(100.0 - x, 4))
            h = min(h, round(100.0 - y, 4))
            if w <= 0 or h <= 0:
                continue
            anchor = _canonical_anchor(region.get("anchor"))
            # Model x/y are top-left based; export offsets from the anchored corner.
            out_x = round(max(0.0, 100.0 - x - w), 4) if "right" in anchor else x
            out_y = round(max(0.0, 100.0 - y - h), 4) if "bottom" in anchor else y
            out.append({"x": out_x, "y": out_y, "w": w, "h": h, "unit": "percent", "anchor": anchor})
        self.result["regions"] = out
        self.dialog.destroy()

    def _cancel(self, _event: tk.Event | None = None) -> None:
        self.result["cancelled"] = True
        self.dialog.destroy()


def pick_exclude_regions(
    parent: tk.Misc,
    pdf_path: Path,
    page_number: int = 1,
    dpi: int = 120,  # kept for backwards compatibility; rendering now fits the window
    *,
    existing: list[dict[str, float | str]] | None = None,
    initial_anchor: str = "top_left",
    backdrop: str | Path | None = None,
    backdrop_out: dict[str, str] | None = None,
) -> list[dict[str, float | str]] | None:
    """Open a modal window to draw/edit exclude regions.

    ``backdrop`` preloads another PDF as the visual reference; ``backdrop_out``
    (if given) receives {"path": …} with the backdrop in effect when the
    dialog closed, so the caller can persist the choice. Returns a list of
    ``{x, y, w, h, unit, anchor}`` dicts in ``percent`` coordinates (offsets
    measured from each region's anchor corner). An empty list means the user
    removed all regions and confirmed; ``None`` means the dialog was
    cancelled.
    """
    del dpi
    pdf = Path(pdf_path)
    if not pdf.exists():
        return None
    try:
        doc = fitz.open(pdf)
    except Exception:
        return None
    picker: _RegionPicker | None = None
    try:
        if doc.page_count < 1:
            return None
        picker = _RegionPicker(parent, doc, page_number, existing, initial_anchor=initial_anchor)
        if backdrop:
            backdrop_path = Path(backdrop)
            if backdrop_path.exists() and backdrop_path.resolve() != pdf.resolve():
                picker.set_backdrop(backdrop_path)
        parent.wait_window(picker.dialog)
        if backdrop_out is not None:
            backdrop_out["path"] = picker.backdrop_path
    finally:
        if picker is not None:
            picker.close_owned_documents()
        doc.close()
    if picker is None or picker.result.get("cancelled"):
        return None
    regions: list[dict[str, float | str]] | None = picker.result.get("regions")
    if regions is None:
        return None  # window closed via [X] — treat as cancel
    return regions
