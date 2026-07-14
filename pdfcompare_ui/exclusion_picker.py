"""Visual exclusion-region picker for the Tkinter GUI.

The regions are physical: each one is stored and exported as millimetres from a
chosen page corner (``unit: "mm"`` + ``anchor``). That is what makes a zone
reusable — a 185×55 mm title block anchored to the bottom-right corner stays
185×55 mm on A4, A3, A1 and A0, in both orientations. Percent regions cannot do
this: 185 mm is 62% of an A4 sheet but only 16% of an A0 one, so the same
percent box would swallow a quarter of a large sheet. Percent export stays
available for anyone who wants a zone that scales with the sheet.

The preview is always a BLANK sheet, never the drawing itself. Zones are placed
by size from a corner, so the artwork underneath is noise — and a zone drawn on
one sheet is meant to be used on all of them. The opened document's format is
detected and preselected; switching format only changes which sheet the zones
are drawn on, so you can check where they land on A0 before running anything.

Features:
- blank sheet of the chosen format, A4…A0, portrait or landscape, with the
  drawing frame and a dashed 185×55 mm title-block guide;
- millimetre grid with selectable step and a live size readout;
- regions can be drawn, selected, moved, resized by handles and deleted, and are
  listed with their size, anchor and unit;
- per-region corner anchor and per-region unit: a zone is written back in the
  unit it arrived in, so opening a set that mixes percent and mm and pressing OK
  changes nothing. Converting between the two is a real data migration — it
  happens only on an explicit click on the unit selector, and only after the user
  confirms it.
"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

import fitz

from pdfcompare_core.exclusions import exclusion_regions_to_mm_rects

from .i18n import I18N
from .styles import BG_WINDOW
from .utils import screen_work_area

PT_PER_MM = 72.0 / 25.4

# ISO A-series paper sizes (portrait, mm).
ISO_FORMATS: list[tuple[str, float, float]] = [
    ("A4", 210.0, 297.0),
    ("A3", 297.0, 420.0),
    ("A2", 420.0, 594.0),
    ("A1", 594.0, 841.0),
    ("A0", 841.0, 1189.0),
]
FORMAT_NAMES = [name for name, _w, _h in ISO_FORMATS]
FORMAT_TOLERANCE_MM = 8.0

GRID_STEPS_MM = (5, 10, 25, 50)
HANDLE_PX = 4  # half-size of a resize handle square
HIT_PX = 8  # grab radius around a handle centre
MIN_BOX_MM = 1.0

UNIT_MM = "mm"
UNIT_PERCENT = "percent"

BOX_COLOR = "#e11d48"
BOX_SELECTED_COLOR = "#2563eb"
GRID_MINOR_COLOR = "#d7dee8"
GRID_MAJOR_COLOR = "#b5c0cf"
SHEET_EDGE_COLOR = "#94a3b8"
SHEET_FRAME_COLOR = "#64748b"

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

ANCHORS = ("top_left", "top_right", "bottom_left", "bottom_right")
ANCHOR_ALIASES = {
    "top_left": "top_left", "left_top": "top_left", "tl": "top_left",
    "top_right": "top_right", "right_top": "top_right", "tr": "top_right",
    "bottom_left": "bottom_left", "left_bottom": "bottom_left", "bl": "bottom_left",
    "bottom_right": "bottom_right", "right_bottom": "bottom_right", "br": "bottom_right",
}
ANCHOR_ARROWS = {"top_left": "↖", "top_right": "↗", "bottom_left": "↙", "bottom_right": "↘"}
ANCHOR_KEYS = {
    "top_left": "pick_anchor_tl",
    "top_right": "pick_anchor_tr",
    "bottom_left": "pick_anchor_bl",
    "bottom_right": "pick_anchor_br",
}

# Reference title block drawn on the sheet (GOST form 1).
STAMP_W_MM = 185.0
STAMP_H_MM = 55.0

# Paddings around the settings panel (body padx, the gap before the sheet and the
# canvas border) — what the sheet cannot use, besides the panel itself.
PANEL_PADDING_PX = 34

# The window frame itself (title bar + borders) plus a small breathing margin.
WINDOW_CHROME_PX = 56


def _canonical_anchor(raw: object) -> str:
    text = str(raw or "top_left").strip().casefold().replace("-", "_")
    return ANCHOR_ALIASES.get(text, "top_left")


def region_rect_mm(region: dict[str, Any], sheet_w: float, sheet_h: float) -> tuple[float, float, float, float]:
    """Anchored region -> (left, top, w, h) in mm from the sheet's top-left."""
    anchor = _canonical_anchor(region.get("anchor"))
    x, y = float(region["x_mm"]), float(region["y_mm"])
    w, h = float(region["w_mm"]), float(region["h_mm"])
    left = x if "left" in anchor else sheet_w - x - w
    top = y if "top" in anchor else sheet_h - y - h
    return left, top, w, h


def region_from_rect_mm(
    left: float, top: float, w: float, h: float, anchor: str, sheet_w: float, sheet_h: float
) -> dict[str, Any]:
    """(left, top, w, h) in mm from the top-left -> region anchored to a corner."""
    anchor = _canonical_anchor(anchor)
    x = left if "left" in anchor else sheet_w - left - w
    y = top if "top" in anchor else sheet_h - top - h
    return {"anchor": anchor, "x_mm": max(0.0, x), "y_mm": max(0.0, y), "w_mm": w, "h_mm": h}


def region_to_export(region: dict[str, Any], sheet_w: float, sheet_h: float, unit: str) -> dict[str, float | str]:
    """Export one region in the requested unit.

    ``mm`` keeps the zone physically identical on every sheet format; ``percent``
    makes it scale with the sheet (relative to the sheet it was drawn on).
    """
    anchor = _canonical_anchor(region.get("anchor"))
    x, y = float(region["x_mm"]), float(region["y_mm"])
    w, h = float(region["w_mm"]), float(region["h_mm"])
    if unit == UNIT_PERCENT:
        return {
            "x": round(x / sheet_w * 100.0, 4),
            "y": round(y / sheet_h * 100.0, 4),
            "w": round(w / sheet_w * 100.0, 4),
            "h": round(h / sheet_h * 100.0, 4),
            "unit": UNIT_PERCENT,
            "anchor": anchor,
        }
    return {
        "x": round(x, 2),
        "y": round(y, 2),
        "w": round(w, 2),
        "h": round(h, 2),
        "unit": UNIT_MM,
        "anchor": anchor,
    }


def format_regions_for_field(regions: list[dict[str, float | str]]) -> str:
    """Serialize picker output for the "Exclude regions" entry field.

    Plain ``x,y,w,h;…`` only for the legacy shape (percent, top_left); anything
    carrying a unit or an anchor becomes compact JSON, which the core parses.
    """
    def is_legacy(region: dict[str, float | str]) -> bool:
        unit = str(region.get("unit") or UNIT_PERCENT).casefold()
        return unit in {UNIT_PERCENT, "%"} and _canonical_anchor(region.get("anchor")) == "top_left"

    if regions and all(is_legacy(r) for r in regions):
        return ";".join(f"{float(r['x']):.4g},{float(r['y']):.4g},{float(r['w']):.4g},{float(r['h']):.4g}" for r in regions)
    items = [
        {
            "x": float(r["x"]),
            "y": float(r["y"]),
            "w": float(r["w"]),
            "h": float(r["h"]),
            "unit": str(r.get("unit") or UNIT_PERCENT),
            "anchor": _canonical_anchor(r.get("anchor")),
        }
        for r in regions
    ]
    return json.dumps(items, ensure_ascii=False, separators=(",", ":"))


def detect_format(w_mm: float, h_mm: float) -> str | None:
    """Exact ISO match within a few mm, or None (a scan, a custom sheet…)."""
    short, long_ = sorted((w_mm, h_mm))
    for name, fw, fh in ISO_FORMATS:
        if abs(short - fw) <= FORMAT_TOLERANCE_MM and abs(long_ - fh) <= FORMAT_TOLERANCE_MM:
            return name
    return None


def region_unit(raw: object) -> str:
    """The picker unit an incoming zone is *stored* in, so OK gives it back.

    The picker exports two units, mm and percent, and each region remembers its
    own — a set holding both survives open→OK untouched. Units the picker cannot
    reproduce (``px`` is tied to a raster's DPI, ``ratio`` to the sheet) map to
    mm, the physical representation, exactly as before.
    """
    unit = str((raw.get("unit") if isinstance(raw, dict) else None) or UNIT_PERCENT).strip().casefold()
    return UNIT_PERCENT if unit in {UNIT_PERCENT, "%"} else UNIT_MM


def incoming_unit(existing: list[dict[str, float | str]] | None) -> str:
    """Which unit the *unit selector* starts on — the unit new zones get.

    It no longer decides how existing zones are written back: every region keeps
    its own unit (see ``region_unit``). This only picks a sensible default for
    zones drawn from now on: keep working in percent if that is all that came in,
    otherwise mm.
    """
    if not existing:
        return UNIT_MM
    if all(region_unit(r) == UNIT_PERCENT for r in existing):
        return UNIT_PERCENT
    return UNIT_MM


def nearest_format(w_mm: float, h_mm: float) -> str:
    """Closest ISO format by area — the sheet to show for a non-standard page."""
    area = max(w_mm * h_mm, 1.0)
    return min(ISO_FORMATS, key=lambda f: abs(f[1] * f[2] - area))[0]


def import_regions_to_model(
    existing: list[dict[str, float | str]] | None,
    sheet_w: float,
    sheet_h: float,
    *,
    px_dpi: float = 96.0,
) -> list[dict[str, Any]]:
    """What opening the dialog does: incoming zones -> the picker's mm model.

    Each region is converted on its own, so one malformed neighbour cannot drop
    the rest, and each one remembers the unit it came in with.
    """
    model: list[dict[str, Any]] = []
    for raw in existing or []:
        try:
            rects = exclusion_regions_to_mm_rects([raw], sheet_w, sheet_h, px_dpi=px_dpi)
        except (ValueError, KeyError, TypeError):
            continue
        if not rects:
            continue
        left, top, w, h = rects[0]
        anchor = _canonical_anchor(raw.get("anchor") if isinstance(raw, dict) else None)
        region = region_from_rect_mm(left, top, w, h, anchor, sheet_w, sheet_h)
        region["unit"] = region_unit(raw)
        model.append(region)
    return model


def rescale_relative_regions(
    regions: list[dict[str, Any]], old_w: float, old_h: float, new_w: float, new_h: float
) -> None:
    """Move the percent zones onto a new sheet without changing what they say.

    The editor works in millimetres, which is right for drawing and wrong for
    *storing* a percent zone: a percent zone is defined **relative to the sheet** —
    that is the entire reason to choose percent — so on a different sheet it covers
    proportionally the same area and its numbers do not move. Keeping only its
    millimetres meant a plain A4 → A0 switch re-derived them against the new sheet
    and rewrote 70% as 17.4792%, a unit migration nobody asked for.

    So a percent zone's millimetres are re-derived for the new sheet: scaling its
    offsets and its size by the sheet ratio leaves its percentages bit-for-bit
    identical. An mm zone is physical and is deliberately left alone — surviving the
    switch unchanged is what it is *for*.
    """
    if old_w <= 0 or old_h <= 0:
        return
    fx, fy = new_w / old_w, new_h / old_h
    for region in regions:
        if str(region.get("unit") or UNIT_MM) != UNIT_PERCENT:
            continue
        region["x_mm"] = float(region["x_mm"]) * fx
        region["y_mm"] = float(region["y_mm"]) * fy
        region["w_mm"] = float(region["w_mm"]) * fx
        region["h_mm"] = float(region["h_mm"]) * fy


def export_regions_from_model(
    regions: list[dict[str, Any]], sheet_w: float, sheet_h: float, default_unit: str = UNIT_MM
) -> list[dict[str, float | str]]:
    """What pressing OK does: the mm model -> zones, each in its own unit.

    A region keeps the unit it was imported (or drawn) with. That is what makes
    open→OK a no-op even for a set holding both percent and mm zones — the old
    single dialog-wide unit quietly rewrote one of the two.
    """
    out: list[dict[str, float | str]] = []
    for region in regions:
        if float(region["w_mm"]) <= 0 or float(region["h_mm"]) <= 0:
            continue
        out.append(region_to_export(region, sheet_w, sheet_h, str(region.get("unit") or default_unit)))
    return out


class _RegionPicker:
    def __init__(
        self,
        parent: tk.Misc,
        doc: fitz.Document,
        page_number: int,
        existing: list[dict[str, float | str]] | None,
        initial_anchor: str = "top_left",
        lang: str = "ru",
    ) -> None:
        self.parent = parent
        self.result: dict[str, Any] = {}
        self.lang = "en" if str(lang).lower().startswith("en") else "ru"

        # The document is only measured, never drawn: we need its format, not its
        # artwork. Zones are placed by size from a corner.
        page_index = min(max(int(page_number) - 1, 0), doc.page_count - 1)
        rect = doc[page_index].rect
        self.doc_w_mm = max(rect.width / PT_PER_MM, 1.0)
        self.doc_h_mm = max(rect.height / PT_PER_MM, 1.0)
        self.doc_format = detect_format(self.doc_w_mm, self.doc_h_mm)

        # Model: physical regions — mm offsets from the region's anchor corner.
        self.regions: list[dict[str, Any]] = []
        self.selected: int | None = None
        self.default_anchor = _canonical_anchor(initial_anchor)

        # Interaction state.
        self._mode: str | None = None  # 'draw' | 'move' | 'resize'
        self._press_xy = (0.0, 0.0)
        self._orig_px: tuple[float, float, float, float] | None = None
        self._handle: str | None = None
        self._draw_rect_px: tuple[float, float, float, float] | None = None
        self._syncing_list = False

        self.dialog = tk.Toplevel(parent)
        self.dialog.title(self._tr("pick_title"))
        # The plain tk.Frames in here default to the system grey, while the ttk
        # labels on top of them are painted the app's window colour — which showed
        # up as a grey box behind every hint. One option-database entry lines the
        # two up; the Canvas (its own class) keeps its white sheet.
        self.dialog.configure(bg=BG_WINDOW)
        self.dialog.option_add("*Frame.background", BG_WINDOW)
        # A transient of an unmapped owner never maps on Windows — skip it when
        # the parent is a hidden service root (e.g. the MCP picker).
        try:
            if parent.winfo_viewable():
                self.dialog.transient(parent)  # type: ignore[call-overload]
        except tk.TclError:
            pass
        self.dialog.grab_set()
        self.dialog.resizable(False, False)

        self.format_var = tk.StringVar(value=self.doc_format or nearest_format(self.doc_w_mm, self.doc_h_mm))
        self.orient_var = tk.StringVar(value="landscape" if self.doc_w_mm >= self.doc_h_mm else "portrait")
        self.grid_var = tk.StringVar(value="10")
        self.anchor_var = tk.StringVar(value=self.default_anchor)
        # Opening zones and pressing OK unchanged must not rewrite them: the unit
        # follows what came in. Percent zones stay percent unless the user says
        # otherwise; mm is only the default for a fresh set.
        self.unit_var = tk.StringVar(value=incoming_unit(existing))
        # The sheet the mm model is currently expressed on. A percent zone has to be
        # re-derived whenever this changes, so we must know what it changed *from* —
        # the radiobutton command fires after its variable is already set.
        self._sheet = self._sheet_mm()

        # Footer first: packed against the window bottom it can never be pushed
        # off-screen by a tall sheet.
        footer = tk.Frame(self.dialog)
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(footer, text=self._tr("pick_ok"), command=self._accept, width=14).pack(side=tk.RIGHT)
        ttk.Button(footer, text=self._tr("pick_cancel"), command=self._cancel, width=12).pack(side=tk.RIGHT, padx=(0, 6))

        body = tk.Frame(self.dialog)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._build_side_panel(body)

        right = tk.Frame(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))
        self.canvas = tk.Canvas(
            right, bg="white", cursor="crosshair", highlightthickness=1, highlightbackground="#c9d2de"
        )
        self.canvas.pack()
        self.hint_label = ttk.Label(right, text=self._tr("pick_hint"), anchor="w", foreground="#6b7280")
        self.hint_label.pack(fill=tk.X, pady=(6, 0))

        self._fit_sheet_to_screen()
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

    def _tr(self, key: str, **kwargs: object) -> str:
        text = str(I18N[self.lang].get(key, I18N["ru"].get(key, key)))
        return text.format(**kwargs) if kwargs else text

    def _mm(self) -> str:
        return self._tr("pick_mm")

    # ----- side panel -----

    def _build_side_panel(self, parent: tk.Frame) -> None:
        """Everything the user sets lives in one vertical column next to the
        sheet, as visible toggles rather than dropdowns: the whole state of the
        picker is readable at a glance."""
        panel = tk.Frame(parent, width=290)
        panel.pack(side=tk.LEFT, fill=tk.Y)
        panel.pack_propagate(False)
        self.panel = panel

        format_group = self._group(panel, "pick_format")
        row1 = tk.Frame(format_group)
        row1.pack(fill=tk.X)
        for name in FORMAT_NAMES:
            ttk.Radiobutton(
                row1, text=name, value=name, variable=self.format_var,
                style="Toolbutton", command=self._on_format_change, width=6,
            ).pack(side=tk.LEFT, padx=(0, 3))
        self.sheet_label = ttk.Label(format_group, text="", foreground="#6b7280", wraplength=280)
        self.sheet_label.pack(anchor="w", pady=(6, 0))

        orient_group = self._group(panel, "pick_orientation")
        orow = tk.Frame(orient_group)
        orow.pack(fill=tk.X)
        ttk.Radiobutton(
            orow, text=self._tr("pick_portrait"), value="portrait", variable=self.orient_var,
            style="Toolbutton", command=self._on_format_change, width=16,
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Radiobutton(
            orow, text=self._tr("pick_landscape"), value="landscape", variable=self.orient_var,
            style="Toolbutton", command=self._on_format_change, width=16,
        ).pack(side=tk.LEFT)

        grid_group = self._group(panel, "pick_grid")
        grow = tk.Frame(grid_group)
        grow.pack(fill=tk.X)
        ttk.Radiobutton(
            grow, text=self._tr("pick_grid_off"), value="off", variable=self.grid_var,
            style="Toolbutton", command=self._redraw, width=6,
        ).pack(side=tk.LEFT, padx=(0, 3))
        for step in GRID_STEPS_MM:
            ttk.Radiobutton(
                grow, text=str(step), value=str(step), variable=self.grid_var,
                style="Toolbutton", command=self._redraw, width=4,
            ).pack(side=tk.LEFT, padx=(0, 2))

        anchor_group = self._group(panel, "pick_anchor")
        arow = tk.Frame(anchor_group)
        arow.pack(fill=tk.X)
        # 2x2, mirroring the corners they stand for.
        for idx, anchor in enumerate(ANCHORS):
            ttk.Radiobutton(
                arow,
                text=f"{ANCHOR_ARROWS[anchor]} {self._tr(ANCHOR_KEYS[anchor])}",
                value=anchor,
                variable=self.anchor_var,
                style="Toolbutton",
                command=self._on_anchor_change,
                width=14,
            ).grid(row=idx // 2, column=idx % 2, padx=(0, 4), pady=(0, 4), sticky="ew")
        ttk.Label(anchor_group, text=self._tr("pick_anchor_hint"), foreground="#6b7280", wraplength=280).pack(
            anchor="w", pady=(6, 0)
        )

        unit_group = self._group(panel, "pick_units")
        urow = tk.Frame(unit_group)
        urow.pack(fill=tk.X)
        ttk.Radiobutton(
            urow, text=self._tr("pick_unit_mm"), value=UNIT_MM, variable=self.unit_var,
            style="Toolbutton", command=self._on_unit_change, width=12,
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Radiobutton(
            urow, text=self._tr("pick_unit_percent"), value=UNIT_PERCENT, variable=self.unit_var,
            style="Toolbutton", command=self._on_unit_change, width=12,
        ).pack(side=tk.LEFT)
        self.unit_hint = ttk.Label(unit_group, text=self._tr("pick_unit_mm_hint"), foreground="#6b7280", wraplength=280)
        self.unit_hint.pack(anchor="w", pady=(6, 0))

        list_group = self._group(panel, "pick_regions")
        self.region_list = ttk.Treeview(
            list_group, columns=("n", "size", "anchor", "unit"), show="headings", height=5, selectmode="browse"
        )
        self.region_list.heading("n", text="#")
        self.region_list.heading("size", text=self._tr("pick_col_size"))
        self.region_list.heading("anchor", text=self._tr("pick_col_anchor"))
        self.region_list.heading("unit", text=self._tr("pick_col_unit"))
        self.region_list.column("n", width=26, anchor="center", stretch=False)
        self.region_list.column("size", width=94, anchor="w")
        self.region_list.column("anchor", width=98, anchor="w")
        self.region_list.column("unit", width=62, anchor="w", stretch=False)
        self.region_list.pack(fill=tk.X)
        self.region_list.bind("<<TreeviewSelect>>", self._on_list_select)

        lrow = tk.Frame(list_group)
        lrow.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(lrow, text=self._tr("pick_delete"), command=self._delete_selected).pack(side=tk.LEFT)
        ttk.Button(lrow, text=self._tr("pick_clear"), command=self._clear_regions).pack(side=tk.LEFT, padx=(6, 0))
        self.readout = ttk.Label(list_group, text="", foreground="#374151")
        self.readout.pack(anchor="w", pady=(6, 0))

    def _group(self, parent: tk.Frame, title_key: str) -> tk.Frame:
        wrap = tk.Frame(parent)
        wrap.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(wrap, text=self._tr(title_key), font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))
        inner = tk.Frame(wrap)
        inner.pack(fill=tk.X)
        return inner

    # ----- sheet geometry -----

    def _sheet_mm(self) -> tuple[float, float]:
        for name, fw, fh in ISO_FORMATS:
            if self.format_var.get() == name:
                if self.orient_var.get() == "landscape":
                    return max(fw, fh), min(fw, fh)
                return min(fw, fh), max(fw, fh)
        return self.doc_w_mm, self.doc_h_mm

    def _px_per_mm(self) -> tuple[float, float]:
        sheet_w, sheet_h = self._sheet_mm()
        return self.disp_w / sheet_w, self.disp_h / sheet_h

    def _fit_sheet_to_screen(self) -> None:
        """Size the sheet from the space actually left on this screen.

        A hardcoded cap is wrong: it fits a 1600px monitor and pushes the OK /
        Cancel buttons off the bottom of a 1080px (or DPI-scaled) one. So measure
        the window with a 1×1 canvas — that gives everything the dialog needs
        *besides* the sheet — and give the sheet the rest.
        """
        self.canvas.configure(width=1, height=1)
        self.dialog.update_idletasks()

        work_w, work_h = screen_work_area(self.dialog)
        usable_h = max(360, work_h - WINDOW_CHROME_PX)
        usable_w = max(480, work_w - WINDOW_CHROME_PX)

        panel_h = self.panel.winfo_reqheight()
        hint_h = self.hint_label.winfo_reqheight()
        # With a 1x1 canvas the window is as tall as the panel plus the footer and
        # paddings; what sits *below* the sheet is therefore that remainder plus
        # the hint under the canvas.
        below_sheet = (self.dialog.winfo_reqheight() - panel_h) + hint_h
        # Width is measured from the panel, not from the window: the one-line hint
        # under the sheet asks for its full text width and would otherwise look
        # like several hundred pixels of occupied space. (It wraps — see below.)
        beside_sheet = self.panel.winfo_reqwidth() + PANEL_PADDING_PX

        # No arbitrary cap: a landscape sheet limited by width would leave the
        # window shorter than the screen allows, wasting the space. Let the sheet
        # grow until it hits the height instead. (The upper bound only keeps it
        # sane on an ultrawide monitor.)
        self.max_h = max(280, usable_h - below_sheet)
        self.max_w = max(360, min(1800, usable_w - beside_sheet))
        self._apply_view()

    def _apply_view(self) -> None:
        sheet_w, sheet_h = self._sheet_mm()
        px_per_mm = min(self.max_w / sheet_w, self.max_h / sheet_h)
        self.disp_w = max(1, int(round(sheet_w * px_per_mm)))
        self.disp_h = max(1, int(round(sheet_h * px_per_mm)))
        self.canvas.configure(width=self.disp_w, height=self.disp_h)
        # Wrap the hint to the sheet: unwrapped it demands its full text width and
        # stretches the window.
        self.hint_label.configure(wraplength=max(200, self.disp_w))
        self._update_sheet_label()

    def _update_sheet_label(self) -> None:
        sheet_w, sheet_h = self._sheet_mm()
        orient = self._tr("pick_landscape" if self.orient_var.get() == "landscape" else "pick_portrait")
        text = f"{self.format_var.get()} · {orient} · {sheet_w:.0f}×{sheet_h:.0f} {self._mm()}"
        # Say what the opened document actually is, so an unusual sheet (a scan)
        # is not silently presented as a standard one.
        doc_name = self.doc_format or f"{self.doc_w_mm:.0f}×{self.doc_h_mm:.0f} {self._mm()}"
        text += "\n" + self._tr("pick_doc_is", size=doc_name)
        self.sheet_label.configure(text=text)

    def _on_format_change(self) -> None:
        # mm zones are physical, so they survive the switch untouched — that is
        # exactly what the switch is for: seeing where the same zone lands on another
        # sheet. percent zones are relative and must keep their percentages instead,
        # or switching A4 -> A0 would quietly rewrite 70% as 17.48%.
        old_w, old_h = self._sheet
        new_w, new_h = self._sheet_mm()
        rescale_relative_regions(self.regions, old_w, old_h, new_w, new_h)
        self._sheet = (new_w, new_h)
        self._apply_view()
        self._redraw()

    def _grid_step_mm(self) -> float | None:
        try:
            return float(self.grid_var.get())
        except ValueError:
            return None  # "off"

    # ----- model <-> canvas -----

    def _to_px(self, region: dict[str, Any]) -> tuple[float, float, float, float]:
        sheet_w, sheet_h = self._sheet_mm()
        ppx, ppy = self._px_per_mm()
        left, top, w, h = region_rect_mm(region, sheet_w, sheet_h)
        return left * ppx, top * ppy, w * ppx, h * ppy

    def _set_from_px(self, region: dict[str, Any], x: float, y: float, w: float, h: float) -> None:
        sheet_w, sheet_h = self._sheet_mm()
        ppx, ppy = self._px_per_mm()
        region.update(
            region_from_rect_mm(
                x / ppx, y / ppy, w / ppx, h / ppy, _canonical_anchor(region.get("anchor")), sheet_w, sheet_h
            )
        )

    def _clamp_x(self, x: float) -> float:
        return max(0.0, min(float(self.disp_w), x))

    def _clamp_y(self, y: float) -> float:
        return max(0.0, min(float(self.disp_h), y))

    def _import_existing(self, existing: list[dict[str, float | str]]) -> None:
        sheet_w, sheet_h = self._sheet_mm()
        ppx, _ppy = self._px_per_mm()
        self.regions.extend(
            import_regions_to_model(existing, sheet_w, sheet_h, px_dpi=ppx * 25.4)
        )

    # ----- drawing -----

    def _redraw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        self._draw_sheet()
        self._draw_grid()
        for idx, region in enumerate(self.regions):
            self._draw_region(idx, region)
        if self._draw_rect_px is not None:
            x, y, w, h = self._draw_rect_px
            canvas.create_rectangle(x, y, x + w, y + h, outline=BOX_COLOR, width=2, dash=(4, 3))
        self._refresh_region_list()
        self._update_readout()

    def _draw_sheet(self) -> None:
        """Blank sheet of the chosen format: the drawing frame (20 mm binding
        margin, 5 mm elsewhere) and a dashed 185×55 mm title block, so the user
        sees where the stamp sits and can trace it."""
        sheet_w, sheet_h = self._sheet_mm()
        ppx, ppy = self._px_per_mm()
        canvas = self.canvas
        canvas.create_rectangle(0, 0, self.disp_w, self.disp_h, fill="#ffffff", outline=SHEET_EDGE_COLOR)
        frame_x0, frame_y0 = 20.0 * ppx, 5.0 * ppy
        frame_x1, frame_y1 = self.disp_w - 5.0 * ppx, self.disp_h - 5.0 * ppy
        canvas.create_rectangle(frame_x0, frame_y0, frame_x1, frame_y1, outline=SHEET_FRAME_COLOR, width=2)
        stamp_w, stamp_h = STAMP_W_MM * ppx, STAMP_H_MM * ppy
        stamp_x0, stamp_y0 = frame_x1 - stamp_w, frame_y1 - stamp_h
        if stamp_x0 > frame_x0 and stamp_y0 > frame_y0:
            canvas.create_rectangle(stamp_x0, stamp_y0, frame_x1, frame_y1, outline=SHEET_EDGE_COLOR, dash=(5, 3))
            canvas.create_text(
                (stamp_x0 + frame_x1) / 2,
                (stamp_y0 + frame_y1) / 2,
                text=self._tr("pick_stamp_ref"),
                fill=SHEET_EDGE_COLOR,
                font=("TkDefaultFont", 9),
            )
        caption = f"{self.format_var.get()} · {sheet_w:.0f}×{sheet_h:.0f} {self._mm()}"
        canvas.create_text(
            self.disp_w / 2, frame_y0 + 16, text=caption, fill=SHEET_EDGE_COLOR, font=("TkDefaultFont", 10, "bold")
        )

    def _draw_grid(self) -> None:
        step = self._grid_step_mm()
        if not step:
            return
        ppx, ppy = self._px_per_mm()
        i = 1
        x = step * ppx
        while x < self.disp_w:
            major = (i * step) % 50 == 0
            self.canvas.create_line(x, 0, x, self.disp_h, fill=GRID_MAJOR_COLOR if major else GRID_MINOR_COLOR)
            i += 1
            x = i * step * ppx
        i = 1
        y = step * ppy
        while y < self.disp_h:
            major = (i * step) % 50 == 0
            self.canvas.create_line(0, y, self.disp_w, y, fill=GRID_MAJOR_COLOR if major else GRID_MINOR_COLOR)
            i += 1
            y = i * step * ppy

    def _draw_region(self, idx: int, region: dict[str, Any]) -> None:
        x, y, w, h = self._to_px(region)
        selected = idx == self.selected
        color = BOX_SELECTED_COLOR if selected else BOX_COLOR
        self.canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=2)
        anchor = _canonical_anchor(region.get("anchor"))
        # Mark the anchored corner: that is the corner the zone is measured from.
        ax = x if "left" in anchor else x + w
        ay = y if "top" in anchor else y + h
        self.canvas.create_rectangle(ax - 5, ay - 5, ax + 5, ay + 5, fill=color, outline="#ffffff", width=1)
        label = f"{idx + 1} · {ANCHOR_ARROWS[anchor]} {float(region['w_mm']):.0f}×{float(region['h_mm']):.0f} {self._mm()}"
        text_id = self.canvas.create_text(
            x + 4, y + 3, text=label, anchor="nw", fill=color, font=("TkDefaultFont", 8, "bold")
        )
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

    def _handle_positions(self, region: dict[str, Any]) -> dict[str, tuple[float, float]]:
        x, y, w, h = self._to_px(region)
        return {hid: (x + fx * w, y + fy * h) for hid, (fx, fy) in HANDLES.items()}

    def _draw_live_label(self, x: float, y: float, w_px: float, h_px: float) -> None:
        ppx, ppy = self._px_per_mm()
        label = f"{w_px / ppx:.0f}×{h_px / ppy:.0f} {self._mm()}"
        tx = min(x + 14, self.disp_w - 40)
        ty = max(y - 12, 8)
        text_id = self.canvas.create_text(tx, ty, text=label, anchor="w", fill="#111827", font=("TkDefaultFont", 9, "bold"))
        bbox = self.canvas.bbox(text_id)
        if bbox:
            bg = self.canvas.create_rectangle(bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1, fill="#fef3c7", outline="#f59e0b")
            self.canvas.tag_lower(bg, text_id)

    # ----- region list -----

    def _refresh_region_list(self) -> None:
        self._syncing_list = True
        try:
            self.region_list.delete(*self.region_list.get_children())
            for idx, region in enumerate(self.regions):
                anchor = _canonical_anchor(region.get("anchor"))
                self.region_list.insert(
                    "",
                    tk.END,
                    iid=str(idx),
                    values=(
                        idx + 1,
                        f"{float(region['w_mm']):.0f}×{float(region['h_mm']):.0f} {self._mm()}",
                        f"{ANCHOR_ARROWS[anchor]} {self._tr(ANCHOR_KEYS[anchor])}",
                        self._unit_label(region),
                    ),
                )
            if self.selected is not None and self.selected < len(self.regions):
                self.region_list.selection_set(str(self.selected))
        finally:
            self._syncing_list = False

    def _on_list_select(self, _event: tk.Event) -> None:
        # Guard against a feedback loop: _refresh_region_list re-selects the row,
        # which fires this event again. The flag alone is not enough — Tk delivers
        # <<TreeviewSelect>> asynchronously, after the flag is cleared — so bail
        # out when the selection already matches the model.
        if self._syncing_list:
            return
        sel = self.region_list.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx == self.selected:
            return
        self.selected = idx
        self._sync_anchor_control()
        self._redraw()

    def _unit_label(self, region: dict[str, Any]) -> str:
        key = "pick_unit_mm" if str(region.get("unit") or UNIT_MM) == UNIT_MM else "pick_unit_percent"
        return self._tr(key)

    def _units_in_use(self) -> set[str]:
        return {str(region.get("unit") or UNIT_MM) for region in self.regions}

    def _update_readout(self) -> None:
        unit_mm = self.unit_var.get() == UNIT_MM
        # With zones in both units the hint must say so, or the selector reads as
        # "everything here is mm" while half the set is still percent.
        if len(self._units_in_use()) > 1:
            hint = self._tr("pick_unit_mixed_hint")
        else:
            hint = self._tr("pick_unit_mm_hint" if unit_mm else "pick_unit_percent_hint")
        self.unit_hint.configure(text=hint)
        if self.selected is None or self.selected >= len(self.regions):
            self.readout.configure(text=self._tr("pick_count", count=len(self.regions)))
            return
        region = self.regions[self.selected]
        anchor = _canonical_anchor(region.get("anchor"))
        arrow = ANCHOR_ARROWS[anchor]
        x, y = float(region["x_mm"]), float(region["y_mm"])
        w, h = float(region["w_mm"]), float(region["h_mm"])
        unit = self._unit_label(region)
        self.readout.configure(text=f"{arrow} x {x:.0f} · y {y:.0f} · {w:.0f}×{h:.0f} {self._mm()} → {unit}")

    # ----- units -----

    def _confirm_unit_migration(self, count: int, unit: str) -> bool:
        return bool(
            messagebox.askyesno(
                self._tr("pick_unit_migrate_title"),
                self._tr(
                    "pick_unit_migrate_body",
                    count=count,
                    unit=self._tr("pick_unit_mm" if unit == UNIT_MM else "pick_unit_percent"),
                ),
                parent=self.dialog,
            )
        )

    def _on_unit_change(self) -> None:
        """The unit selector is the *only* thing that may rewrite a saved zone.

        Converting a zone between mm and percent changes what it excludes on a
        differently sized sheet, so it happens on an explicit click and only after
        the user confirms it. Declining still switches the unit for zones drawn
        from now on — the existing ones simply keep theirs.
        """
        unit = self.unit_var.get()
        stale = [region for region in self.regions if str(region.get("unit") or UNIT_MM) != unit]
        if stale and self._confirm_unit_migration(len(stale), unit):
            for region in stale:
                region["unit"] = unit
        self._redraw()

    # ----- anchor -----

    def _sync_anchor_control(self) -> None:
        anchor = self.default_anchor
        if self.selected is not None and self.selected < len(self.regions):
            anchor = _canonical_anchor(self.regions[self.selected].get("anchor"))
        self.anchor_var.set(anchor)

    def _on_anchor_change(self) -> None:
        anchor = _canonical_anchor(self.anchor_var.get())
        # New boxes inherit the last chosen anchor; a selected box is re-anchored
        # in place (its rectangle does not move, only what it is measured from —
        # so it now follows that corner on other formats).
        self.default_anchor = anchor
        if self.selected is not None and self.selected < len(self.regions):
            region = self.regions[self.selected]
            sheet_w, sheet_h = self._sheet_mm()
            left, top, w, h = region_rect_mm(region, sheet_w, sheet_h)
            region.update(region_from_rect_mm(left, top, w, h, anchor, sheet_w, sheet_h))
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
            self._sync_anchor_control()
            self._redraw()
            return
        self.selected = None
        self._mode = "draw"
        self._draw_rect_px = (x, y, 0.0, 0.0)
        self._sync_anchor_control()
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
        ppx, ppy = self._px_per_mm()
        min_w, min_h = MIN_BOX_MM * ppx, MIN_BOX_MM * ppy
        ox, oy, ow, oh = self._orig_px
        left, top, right, bottom = ox, oy, ox + ow, oy + oh
        h = self._handle
        if "w" in h:
            left = min(x, right - min_w)
        if "e" in h:
            right = max(x, left + min_w)
        if "n" in h:
            top = min(y, bottom - min_h)
        if "s" in h:
            bottom = max(y, top + min_h)
        left, right = self._clamp_x(left), self._clamp_x(right)
        top, bottom = self._clamp_y(top), self._clamp_y(bottom)
        self._set_from_px(self.regions[self.selected], left, top, right - left, bottom - top)

    def _on_release(self, _event: tk.Event) -> None:
        if self._mode == "draw" and self._draw_rect_px is not None:
            x, y, w, h = self._draw_rect_px
            ppx, ppy = self._px_per_mm()
            if w / ppx >= MIN_BOX_MM and h / ppy >= MIN_BOX_MM:
                sheet_w, sheet_h = self._sheet_mm()
                region = region_from_rect_mm(
                    x / ppx, y / ppy, w / ppx, h / ppy, self.default_anchor, sheet_w, sheet_h
                )
                # A newly drawn zone is written in whatever the unit selector shows.
                region["unit"] = self.unit_var.get()
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
            self._sync_anchor_control()
            self._redraw()
            return
        self._cancel()

    # ----- region actions -----

    def _on_delete_key(self, _event: tk.Event | None = None) -> None:
        widget = self.dialog.focus_get()
        # Don't hijack Delete/Backspace while typing in an entry.
        if isinstance(widget, (tk.Entry, ttk.Entry)):
            return
        self._delete_selected()

    def _delete_selected(self) -> None:
        if self.selected is None or self.selected >= len(self.regions):
            return
        self.regions.pop(self.selected)
        self.selected = None
        self._sync_anchor_control()
        self._redraw()

    def _clear_regions(self) -> None:
        self.regions.clear()
        self.selected = None
        self._redraw()

    # ----- dialog result -----

    def _accept(self) -> None:
        sheet_w, sheet_h = self._sheet_mm()
        self.result["regions"] = export_regions_from_model(
            self.regions, sheet_w, sheet_h, default_unit=self.unit_var.get()
        )
        self.dialog.destroy()

    def _cancel(self, _event: tk.Event | None = None) -> None:
        self.result["cancelled"] = True
        self.dialog.destroy()


def pick_exclude_regions(
    parent: tk.Misc,
    pdf_path: Path,
    page_number: int = 1,
    dpi: int = 120,  # kept for backwards compatibility; the sheet is drawn, not rendered
    *,
    existing: list[dict[str, float | str]] | None = None,
    initial_anchor: str = "top_left",
    lang: str = "ru",
) -> list[dict[str, float | str]] | None:
    """Open a modal window to draw/edit exclude regions on a blank sheet.

    The PDF is only measured (to preselect its format), never drawn: regions are
    placed by size from a corner. Returns ``{x, y, w, h, unit, anchor}`` dicts —
    by default in ``mm`` from each region's anchor corner, which is what makes a
    zone valid on every sheet format. An empty list means the user removed all
    regions and confirmed; ``None`` means cancelled.
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
        picker = _RegionPicker(parent, doc, page_number, existing, initial_anchor=initial_anchor, lang=lang)
        parent.wait_window(picker.dialog)
    finally:
        doc.close()
    if picker is None or picker.result.get("cancelled"):
        return None
    regions: list[dict[str, float | str]] | None = picker.result.get("regions")
    if regions is None:
        return None  # window closed via [X] — treat as cancel
    return regions
