"""Rerender tab — load an existing run summary and regenerate selected pages."""

from __future__ import annotations

import json
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from compare_pdfs import (
    DIFF_STRICTNESS_CHOICES,
    find_summary_json_path,
    regenerate_report_pages,
    regenerate_report_pages_mixed,
)
from pdfcompare_core.constants import MAX_RENDER_DPI, MIN_RENDER_DPI
from pdfcompare_core.exclusions import normalize_exclude_regions
from pdfcompare_core.runner import RunCancelled

from .exclusion_picker import format_regions_for_field, pick_exclude_regions
from .styles import ACCENT, BG_CARD, BG_SOFT, BG_WINDOW, TEXT_SECONDARY

from .contracts import AppProtocol


class RerenderTabMixin:
    """Provides rerender-tab construction and worker logic.

    Must be mixed into a class that owns the shared state attributes
    (running, rerender_*, progress, worker_events, lang, _tr, _set_status,
    _primary_button, _open_report) — i.e. PDFCompareApp.
    """

    # Class-level annotations for attributes written by this mixin.
    # Without these mypy would infer the narrow concrete type from the first
    # `self.X = ...` assignment, which then conflicts with PDFCompareApp's
    # Optional `__init__` declarations.
    last_run_dir: Path | None
    rerender_tree: ttk.Treeview | None
    rerender_title_label: ttk.Label | None
    rerender_hint_label: ttk.Label | None
    rerender_run_label: ttk.Label | None
    rerender_load_current_btn: ttk.Button | None
    rerender_pick_btn: ttk.Button | None
    rerender_reload_btn: ttk.Button | None
    rerender_dpi_label: ttk.Label | None
    rerender_workers_label: ttk.Label | None
    rerender_start_btn: tk.Button | None  # _primary_button returns tk.Button, not ttk.Button
    rerender_thread: threading.Thread | None
    rerender_open_report_btn: ttk.Button | None
    rerender_mode_chips: dict[str, tk.Label]
    rerender_strictness_chips: dict[str, tk.Label]
    rerender_edit_selected_btn: ttk.Button | None
    rerender_exclude_pick_btn: ttk.Button | None
    rerender_source_pdf: Path | None

    def _build_rerender_tab(self: AppProtocol) -> None:
        if self.rerender_tab is None:
            return
        self.rerender_title_label = ttk.Label(self.rerender_tab, text=self._tr("rerender_title"), style="SubHeader.TLabel")
        self.rerender_title_label.pack(anchor="w")
        self.rerender_hint_label = ttk.Label(self.rerender_tab, text=self._tr("rerender_hint"), style="Hint.TLabel", wraplength=980)
        self.rerender_hint_label.pack(anchor="w", pady=(4, 12))

        run_row = tk.Frame(self.rerender_tab, bg=BG_WINDOW)
        run_row.pack(fill=tk.X, pady=(0, 10))
        self.rerender_run_label = ttk.Label(run_row, text=self._tr("rerender_run"), style="FileLabel.TLabel")
        self.rerender_run_label.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Entry(run_row, textvariable=self.rerender_run_dir, style="Path.TEntry").pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.rerender_load_current_btn = ttk.Button(
            run_row,
            text=self._tr("rerender_load_current"),
            style="Small.TButton",
            command=self._load_current_rerender_report,
        )
        self.rerender_load_current_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.rerender_pick_btn = ttk.Button(run_row, text=self._tr("rerender_pick"), style="Small.TButton", command=self._pick_rerender_run_dir)
        self.rerender_pick_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.rerender_reload_btn = ttk.Button(run_row, text=self._tr("rerender_reload"), style="Small.TButton", command=self._load_rerender_report)
        self.rerender_reload_btn.pack(side=tk.LEFT, padx=(8, 0))

        options_panel = tk.Frame(self.rerender_tab, bg=BG_SOFT, padx=12, pady=10)
        options_panel.pack(fill=tk.X, pady=(0, 10))

        # Top row: DPI / workers / actions (kept compact).
        options_row = tk.Frame(options_panel, bg=BG_SOFT)
        options_row.pack(fill=tk.X)
        self.rerender_dpi_label = ttk.Label(options_row, text=self._tr("rerender_dpi"), style="FileLabel.TLabel", background=BG_SOFT)
        self.rerender_dpi_label.pack(side=tk.LEFT)
        ttk.Entry(options_row, textvariable=self.rerender_dpi, width=8).pack(side=tk.LEFT, padx=(6, 18))
        self.rerender_workers_label = ttk.Label(options_row, text=self._tr("rerender_workers"), style="FileLabel.TLabel", background=BG_SOFT)
        self.rerender_workers_label.pack(side=tk.LEFT)
        ttk.Entry(options_row, textvariable=self.rerender_workers, width=8).pack(side=tk.LEFT, padx=(6, 18))
        self.rerender_open_report_btn = ttk.Button(options_row, text=self._tr("btn_open_report"), style="Small.TButton", command=self._open_report)
        self.rerender_open_report_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.rerender_start_btn = self._primary_button(options_row, self._tr("rerender_start"), self._start_rerender_selected, compact=True)
        self.rerender_start_btn.pack(side=tk.RIGHT)

        # Mode switch: uniform (one set of overrides for all selected) vs per-page.
        mode_row = tk.Frame(options_panel, bg=BG_SOFT)
        mode_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(mode_row, text=self._tr("rerender_mode"), style="FileLabel.TLabel", background=BG_SOFT).pack(side=tk.LEFT)
        for value, key in (("uniform", "rerender_mode_uniform"), ("perpage", "rerender_mode_perpage")):
            chip = tk.Label(mode_row, text=self._tr(key), padx=12, pady=4, bg=BG_CARD, fg=TEXT_SECONDARY, relief="solid", bd=1, cursor="hand2")
            chip.pack(side=tk.LEFT, padx=(8, 0))
            chip.bind("<Button-1>", lambda _e, v=value: self.rerender_mode.set(v))  # type: ignore[misc]
            self.rerender_mode_chips[value] = chip
        self.rerender_edit_selected_btn = ttk.Button(
            mode_row, text=self._tr("rerender_edit_selected"), style="Small.TButton", command=self._edit_selected_page_settings
        )
        self.rerender_edit_selected_btn.pack(side=tk.LEFT, padx=(12, 0))

        # Uniform overrides row: stroke / strictness / exclude / bbox merge.
        overrides_row = tk.Frame(options_panel, bg=BG_SOFT)
        overrides_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(overrides_row, text=self._tr("rerender_stroke"), style="FileLabel.TLabel", background=BG_SOFT).pack(side=tk.LEFT)
        ttk.Entry(overrides_row, textvariable=self.rerender_stroke_tol, width=6).pack(side=tk.LEFT, padx=(6, 16))
        ttk.Label(overrides_row, text=self._tr("rerender_strictness"), style="FileLabel.TLabel", background=BG_SOFT).pack(side=tk.LEFT)
        strict_chips = tk.Frame(overrides_row, bg=BG_SOFT)
        strict_chips.pack(side=tk.LEFT, padx=(6, 16))
        for value in DIFF_STRICTNESS_CHOICES:
            chip = tk.Label(strict_chips, text=self._tr(f"strictness_{value}"), padx=10, pady=4, bg=BG_CARD, fg=TEXT_SECONDARY, relief="solid", bd=1, cursor="hand2")
            chip.pack(side=tk.LEFT, padx=(0, 4))
            chip.bind("<Button-1>", lambda _e, v=value: self.rerender_strictness.set(v if self.rerender_strictness.get() != v else ""))  # type: ignore[misc]
            self.rerender_strictness_chips[value] = chip
        ttk.Label(overrides_row, text=self._tr("rerender_bbox_merge"), style="FileLabel.TLabel", background=BG_SOFT).pack(side=tk.LEFT)
        ttk.Entry(overrides_row, textvariable=self.rerender_bbox_gap, width=6).pack(side=tk.LEFT, padx=(6, 16))

        exclude_row = tk.Frame(options_panel, bg=BG_SOFT)
        exclude_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(exclude_row, text=self._tr("rerender_exclude"), style="FileLabel.TLabel", background=BG_SOFT).pack(side=tk.LEFT)
        ttk.Entry(exclude_row, textvariable=self.rerender_exclude, style="Path.TEntry").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        self.rerender_exclude_pick_btn = ttk.Button(
            exclude_row,
            text=self._tr("btn_pick_exclude"),
            style="Small.TButton",
            command=self._pick_rerender_exclude_regions,
        )
        self.rerender_exclude_pick_btn.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(options_panel, text=self._tr("rerender_overrides_hint"), style="Hint.TLabel", background=BG_SOFT).pack(anchor="w", pady=(6, 0))

        table_frame = ttk.Frame(self.rerender_tab)
        table_frame.pack(fill=tk.BOTH, expand=True)
        cols = ("seq", "a", "b", "level", "fg", "diff", "area", "boxes", "pixels", "time")
        self.rerender_tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="extended", style="History.Treeview")
        for col, key in (
            ("seq", "rerender_col_seq"),
            ("a", "rerender_col_a"),
            ("b", "rerender_col_b"),
            ("level", "rerender_col_level"),
            ("fg", "rerender_col_fg"),
            ("diff", "rerender_col_diff"),
            ("area", "rerender_col_area"),
            ("boxes", "rerender_col_boxes"),
            ("pixels", "rerender_col_pixels"),
            ("time", "rerender_col_time"),
        ):
            self.rerender_tree.heading(col, text=self._tr(key))
        self.rerender_tree.column("seq", width=60, minwidth=50, anchor="center")
        self.rerender_tree.column("a", width=70, minwidth=60, anchor="center")
        self.rerender_tree.column("b", width=70, minwidth=60, anchor="center")
        self.rerender_tree.column("level", width=150, minwidth=100, anchor="w")
        self.rerender_tree.column("fg", width=90, minwidth=70, anchor="center")
        self.rerender_tree.column("diff", width=90, minwidth=70, anchor="center")
        self.rerender_tree.column("area", width=90, minwidth=70, anchor="center")
        self.rerender_tree.column("boxes", width=80, minwidth=60, anchor="center")
        self.rerender_tree.column("pixels", width=120, minwidth=90, anchor="e")
        self.rerender_tree.column("time", width=80, minwidth=70, anchor="center")
        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.rerender_tree.yview)
        self.rerender_tree.configure(yscrollcommand=scroll.set)
        self.rerender_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Wire chip highlighting and initial state for the new toggles.
        self.rerender_mode.trace_add("write", lambda *_: self._update_rerender_mode_chips())
        self.rerender_strictness.trace_add("write", lambda *_: self._update_rerender_strictness_chips())
        self._update_rerender_mode_chips()
        self._update_rerender_strictness_chips()

    def _load_current_rerender_report(self: AppProtocol) -> None:
        if self.last_run_dir:
            self.rerender_run_dir.set(str(self.last_run_dir))
        self._load_rerender_report()

    def _pick_rerender_run_dir(self: AppProtocol) -> None:
        start_dir = self.rerender_run_dir.get().strip() or (str(self.last_run_dir) if self.last_run_dir else self.out_dir.get().strip())
        folder = filedialog.askdirectory(title=self._tr("rerender_run"), initialdir=start_dir if start_dir else None)
        if folder:
            self.rerender_run_dir.set(folder)
            self._load_rerender_report()

    def _load_rerender_report(self: AppProtocol, run_dir: Path | None = None, quiet: bool = False) -> None:
        if self.rerender_tree is None:
            return
        path_text = str(run_dir) if run_dir is not None else self.rerender_run_dir.get().strip()
        if not path_text:
            if not quiet:
                self._set_status("err_folder_missing_title")
            return
        path = Path(path_text)
        summary_path = find_summary_json_path(path)
        if not summary_path.exists():
            if not quiet:
                messagebox.showerror(self._tr("err_file_missing_title"), self._tr("err_not_found", path=summary_path))
            return
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            rows = [dict(row) for row in payload.get("pairs") or []]
        except Exception as exc:
            if not quiet:
                messagebox.showerror(self._tr("dlg_error_title"), str(exc))
            return
        self.rerender_run_dir.set(str(path))
        self.last_run_dir = path
        source = str(payload.get("file_a") or "").strip() or str(payload.get("file_b") or "").strip()
        self.rerender_source_pdf = Path(source) if source else None
        self.rerender_by_iid.clear()
        for iid in self.rerender_tree.get_children():
            self.rerender_tree.delete(iid)
        for row in rows:
            seq = int(row.get("seq") or 0)
            pixels = row.get("pixel_count")
            pixels_text = f"{int(pixels):,}".replace(",", " ") if pixels else ""
            elapsed = row.get("elapsed_sec")
            elapsed_text = f"{float(elapsed):.1f}s" if isinstance(elapsed, (int, float)) else ""
            diff = row.get("diff_percent")
            diff_text = f"{float(diff):.3f}" if isinstance(diff, (int, float)) else ""
            fg = row.get("diff_foreground_percent")
            fg_text = f"{float(fg):.2f}" if isinstance(fg, (int, float)) else ""
            area = row.get("diff_area_mm2")
            area_text = f"{float(area):.1f}" if isinstance(area, (int, float)) else ""
            level = str(row.get("change_level") or row.get("status") or "")
            iid = str(seq)
            self.rerender_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    seq,
                    row.get("a_page") or "-",
                    row.get("b_page") or "-",
                    level,
                    fg_text,
                    diff_text,
                    area_text,
                    row.get("bboxes_count") if row.get("bboxes_count") is not None else "",
                    pixels_text,
                    elapsed_text,
                ),
            )
            self.rerender_by_iid[iid] = row
        if rows:
            self._set_status("status_rerender_loaded", count=len(rows))
        else:
            self._set_status("status_rerender_empty")

    def _pick_rerender_exclude_regions(self: AppProtocol) -> None:
        """Open the visual picker on the loaded run's old PDF and fill the exclude field."""
        pdf_path = self.rerender_source_pdf
        if pdf_path is None or not pdf_path.exists():
            self._set_status("status_rerender_pick_no_pdf")
            return
        # With exactly one row selected, preview that sheet's page.
        page = 1
        if self.rerender_tree is not None:
            selected = self.rerender_tree.selection()
            if len(selected) == 1:
                row = self.rerender_by_iid.get(selected[0]) or {}
                try:
                    page = int(row.get("a_page") or row.get("b_page") or 1)
                except (TypeError, ValueError):
                    page = 1
        existing: list[dict[str, float | str]] = []
        raw = self.rerender_exclude.get().strip()
        if raw:
            try:
                existing = list(normalize_exclude_regions(raw))
            except ValueError:
                existing = []
        backdrop_out: dict[str, str] = {}
        regions = pick_exclude_regions(
            self.root, pdf_path, page_number=page, existing=existing,
            backdrop=self.picker_backdrop or None, backdrop_out=backdrop_out,
        )
        self.picker_backdrop = backdrop_out.get("path", self.picker_backdrop)
        if regions is None:
            return
        self.rerender_exclude.set(format_regions_for_field(regions))
        self._save_state()
        self._set_status("status_pick_added", count=len(regions))

    def _parse_optional_float(self: AppProtocol, var: tk.StringVar) -> float | None:
        text = var.get().strip()
        if not text:
            return None
        return float(text)

    def _collect_uniform_overrides(self: AppProtocol) -> dict[str, Any] | None:
        """Parse the uniform-override fields. Returns None on validation error (already shown)."""
        try:
            stroke = self._parse_optional_float(self.rerender_stroke_tol)
            gap = self._parse_optional_float(self.rerender_bbox_gap)
        except ValueError:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_parse"))
            return None
        strictness = self.rerender_strictness.get().strip().lower() or None
        if strictness is not None and strictness not in DIFF_STRICTNESS_CHOICES:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_strictness"))
            return None
        exclude_raw = self.rerender_exclude.get().strip() or None
        if gap is not None and (gap < 0 or gap > 50):
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_bbox_merge_gap"))
            return None
        overrides: dict[str, Any] = {}
        if stroke is not None:
            overrides["stroke_tol"] = stroke
        if strictness is not None:
            overrides["diff_strictness"] = strictness
        if exclude_raw:
            overrides["exclude_regions"] = exclude_raw
        if gap is not None:
            overrides["bbox_merge_gap_mm"] = gap
            # Enable bbox merge with a sane default for the ratio cap when only gap is given.
            overrides.setdefault("bbox_merge_max_area_ratio", 16.0)
        return overrides

    def _edit_selected_page_settings(self: AppProtocol) -> None:
        """Open a small dialog to set per-page overrides for the selected rows."""
        if self.rerender_tree is None:
            return
        selected = self.rerender_tree.selection()
        if not selected:
            self._set_status("status_rerender_select")
            return
        seqs = [int(iid) for iid in selected]
        self.rerender_mode.set("perpage")
        self._update_rerender_mode_chips()
        dialog = tk.Toplevel(self.root)
        dialog.title(self._tr("rerender_edit_selected"))
        dialog.geometry("420x300")
        dialog.transient(self.root)
        dialog.grab_set()
        local = {
            "dpi": tk.StringVar(value=""),
            "stroke_tol": tk.StringVar(value=""),
            "diff_strictness": tk.StringVar(value=""),
            "exclude_regions": tk.StringVar(value=""),
            "bbox_merge_gap_mm": tk.StringVar(value=""),
        }
        form = tk.Frame(dialog, padx=12, pady=12)
        form.pack(fill=tk.BOTH, expand=True)
        for key, label_key in (
            ("dpi", "rerender_dpi"),
            ("stroke_tol", "rerender_stroke"),
            ("diff_strictness", "rerender_strictness"),
            ("exclude_regions", "rerender_exclude"),
            ("bbox_merge_gap_mm", "rerender_bbox_merge"),
        ):
            ttk.Label(form, text=self._tr(label_key)).pack(anchor="w", pady=(4, 0))
            ttk.Entry(form, textvariable=local[key]).pack(fill=tk.X)
        hint = ttk.Label(form, text=self._tr("rerender_perpage_hint"), style="Hint.TLabel")
        hint.pack(anchor="w", pady=(8, 0))

        def apply_settings() -> None:
            for seq in seqs:
                spec: dict[str, Any] = {}
                dpi_txt = local["dpi"].get().strip()
                if dpi_txt:
                    try:
                        dpi_value = int(dpi_txt)
                    except ValueError:
                        messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_rerender_dpi"))
                        return
                    if dpi_value < MIN_RENDER_DPI or dpi_value > MAX_RENDER_DPI:
                        messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_rerender_dpi"))
                        return
                    spec["dpi"] = dpi_value
                try:
                    stroke_txt = local["stroke_tol"].get().strip()
                    if stroke_txt:
                        spec["stroke_tol"] = float(stroke_txt)
                    gap_txt = local["bbox_merge_gap_mm"].get().strip()
                    if gap_txt:
                        spec["bbox_merge_gap_mm"] = float(gap_txt)
                except ValueError:
                    messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_parse"))
                    return
                strict_txt = local["diff_strictness"].get().strip().lower()
                if strict_txt:
                    spec["diff_strictness"] = strict_txt
                excl_txt = local["exclude_regions"].get().strip()
                if excl_txt:
                    spec["exclude_regions"] = excl_txt
                self.rerender_page_settings[seq] = spec
            dialog.destroy()
            self._set_status("status_rerender_perpage_set", count=len(seqs))

        btns = tk.Frame(dialog, padx=12, pady=8)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text=self._tr("pick_ok"), command=apply_settings).pack(side=tk.RIGHT)
        ttk.Button(btns, text=self._tr("pick_cancel"), command=dialog.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    def _update_rerender_mode_chips(self: AppProtocol) -> None:
        current = self.rerender_mode.get().strip() or "uniform"
        for value, widget in self.rerender_mode_chips.items():
            active = value == current
            widget.configure(fg=ACCENT if active else TEXT_SECONDARY, bd=2 if active else 1)
        if self.rerender_edit_selected_btn is not None:
            self.rerender_edit_selected_btn.configure(state=tk.NORMAL if current == "perpage" else tk.DISABLED)

    def _update_rerender_strictness_chips(self: AppProtocol) -> None:
        current = self.rerender_strictness.get().strip().lower()
        for value, widget in self.rerender_strictness_chips.items():
            active = value == current
            widget.configure(fg=ACCENT if active else TEXT_SECONDARY, bd=2 if active else 1)

    def _request_rerender_cancel(self: AppProtocol) -> None:
        if not self.rerender_running:
            return
        self.rerender_cancel_requested.set()
        if self.rerender_start_btn is not None:
            self._set_primary_state(self.rerender_start_btn, tk.DISABLED)
            self.rerender_start_btn.configure(text=self._tr("btn_cancelling"))
        self._set_status("status_cancel_requested")

    def _start_rerender_selected(self: AppProtocol) -> None:
        # While a re-render is running the same button cancels it, like the
        # compare button does.
        if self.rerender_running:
            self._request_rerender_cancel()
            return
        if self.running:
            messagebox.showwarning(self._tr("err_invalid_input_title"), self._tr("err_rerender_busy"))
            return
        if self.rerender_tree is None:
            return
        selected = self.rerender_tree.selection()
        if not selected:
            self._set_status("status_rerender_select")
            return
        try:
            dpi = int(self.rerender_dpi.get().strip())
            workers = int(self.rerender_workers.get().strip() or "0")
        except ValueError:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_rerender_dpi"))
            return
        if dpi < MIN_RENDER_DPI or dpi > MAX_RENDER_DPI:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_rerender_dpi"))
            return
        if workers < 0:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_workers"))
            return
        run_dir = Path(self.rerender_run_dir.get().strip())
        seqs = [int(iid) for iid in selected]
        # Tk variables are not thread-safe: capture the language here, in the
        # UI thread, and hand the worker a plain string.
        report_lang = self.lang.get()

        if self.rerender_mode.get() == "perpage" and self.rerender_page_settings:
            # Mixed mode: group selected seqs that share identical settings.
            page_settings = self._build_page_settings(seqs)
            self._begin_rerender_run()
            t = threading.Thread(
                target=self._rerender_mixed_worker,
                args=(run_dir, page_settings, dpi, workers, report_lang),
                daemon=True,
            )
            self.rerender_thread = t
            t.start()
            return

        overrides = self._collect_uniform_overrides()
        if overrides is None:
            return
        self._begin_rerender_run()
        t = threading.Thread(
            target=self._rerender_worker,
            args=(run_dir, seqs, dpi, workers, overrides, report_lang),
            daemon=True,
        )
        self.rerender_thread = t
        t.start()

    def _build_page_settings(self: AppProtocol, seqs: list[int]) -> list[dict[str, Any]]:
        """Build a page_settings list for regenerate_report_pages_mixed.

        Seqs with explicit per-page overrides use those; the remaining seqs
        fall back to the uniform override fields (if any) or just inherit.
        """
        uniform = self._collect_uniform_overrides_safe()
        groups: dict[tuple, list[int]] = {}
        for seq in seqs:
            spec = self.rerender_page_settings.get(seq)
            if spec is None:
                spec = uniform if uniform else {}
            key = tuple(sorted(spec.items()))
            groups.setdefault(key, []).append(seq)
        return [{**dict(key), "seqs": sorted(group)} for key, group in groups.items()]

    def _collect_uniform_overrides_safe(self: AppProtocol) -> dict[str, Any]:
        """Like _collect_uniform_overrides but never raises/shows errors (best-effort)."""
        overrides: dict[str, Any] = {}
        try:
            stroke = self._parse_optional_float(self.rerender_stroke_tol)
            gap = self._parse_optional_float(self.rerender_bbox_gap)
        except ValueError:
            return overrides
        strictness = self.rerender_strictness.get().strip().lower() or None
        exclude_raw = self.rerender_exclude.get().strip() or None
        if stroke is not None:
            overrides["stroke_tol"] = stroke
        if strictness in DIFF_STRICTNESS_CHOICES:
            overrides["diff_strictness"] = strictness
        if exclude_raw:
            overrides["exclude_regions"] = exclude_raw
        if gap is not None and 0 <= gap <= 50:
            overrides["bbox_merge_gap_mm"] = gap
            overrides.setdefault("bbox_merge_max_area_ratio", 16.0)
        return overrides

    def _begin_rerender_run(self: AppProtocol) -> None:
        self.rerender_running = True
        self.rerender_cancel_requested.clear()
        if self.rerender_start_btn is not None:
            # Stays enabled: it is the cancel button for the duration of the run.
            self._set_primary_state(self.rerender_start_btn, tk.NORMAL)
            self.rerender_start_btn.configure(text=self._tr("btn_cancel"))
        self.progress.configure(value=0.0)
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        self.progress_pct.set("0%")
        self._set_status("status_rerender_running")

    def _rerender_worker(self: AppProtocol, run_dir: Path, seqs: list[int], dpi: int, workers: int, overrides: dict[str, Any], report_lang: str) -> None:
        try:
            def report_progress(pct: float, msg: str) -> None:
                self.worker_events.put(("rerender_progress", float(pct), str(msg)))

            result = regenerate_report_pages(
                run_dir,
                seqs,
                high_dpi=dpi,
                report_lang=report_lang,
                workers=workers,
                stroke_tol_px=overrides.get("stroke_tol"),
                diff_strictness=overrides.get("diff_strictness"),
                exclude_regions=overrides.get("exclude_regions"),
                bbox_merge_gap_mm=overrides.get("bbox_merge_gap_mm"),
                bbox_merge_max_area_ratio=overrides.get("bbox_merge_max_area_ratio"),
                progress_cb=report_progress,
                cancel_cb=self.rerender_cancel_requested.is_set,
            )
            self.worker_events.put(("rerender_done", result))
        except RunCancelled:
            # The run rolled itself back; the report is untouched.
            self.worker_events.put(("rerender_cancelled",))
        except Exception as exc:
            self.worker_events.put(("rerender_error", str(exc), traceback.format_exc()))

    def _rerender_mixed_worker(self: AppProtocol, run_dir: Path, page_settings: list[dict[str, Any]], dpi: int, workers: int, report_lang: str) -> None:
        try:
            def report_progress(pct: float, msg: str) -> None:
                self.worker_events.put(("rerender_progress", float(pct), str(msg)))

            result = regenerate_report_pages_mixed(
                run_dir,
                page_settings,
                high_dpi=dpi,
                report_lang=report_lang,
                workers=workers,
                progress_cb=report_progress,
                cancel_cb=self.rerender_cancel_requested.is_set,
            )
            self.worker_events.put(("rerender_done", result))
        except RunCancelled:
            self.worker_events.put(("rerender_cancelled",))
        except Exception as exc:
            self.worker_events.put(("rerender_error", str(exc), traceback.format_exc()))
