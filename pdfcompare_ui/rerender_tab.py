"""Rerender tab — load an existing run summary and regenerate selected pages."""

from __future__ import annotations

import json
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from compare_pdfs import find_summary_json_path, regenerate_report_pages

from .styles import BG_SOFT, BG_WINDOW

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
    rerender_open_report_btn: ttk.Button | None

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

        options_row = tk.Frame(self.rerender_tab, bg=BG_SOFT, padx=12, pady=10)
        options_row.pack(fill=tk.X, pady=(0, 10))
        self.rerender_dpi_label = ttk.Label(options_row, text=self._tr("rerender_dpi"), style="FileLabel.TLabel", background=BG_SOFT)
        self.rerender_dpi_label.pack(side=tk.LEFT)
        ttk.Entry(options_row, textvariable=self.rerender_dpi, width=8).pack(side=tk.LEFT, padx=(6, 18))
        self.rerender_workers_label = ttk.Label(options_row, text=self._tr("rerender_workers"), style="FileLabel.TLabel", background=BG_SOFT)
        self.rerender_workers_label.pack(side=tk.LEFT)
        ttk.Entry(options_row, textvariable=self.rerender_workers, width=8).pack(side=tk.LEFT, padx=(6, 18))
        self.rerender_start_btn = self._primary_button(options_row, self._tr("rerender_start"), self._start_rerender_selected, compact=True)
        self.rerender_start_btn.pack(side=tk.RIGHT)
        self.rerender_open_report_btn = ttk.Button(options_row, text=self._tr("btn_open_report"), style="Small.TButton", command=self._open_report)
        self.rerender_open_report_btn.pack(side=tk.RIGHT, padx=(0, 8))

        table_frame = ttk.Frame(self.rerender_tab)
        table_frame.pack(fill=tk.BOTH, expand=True)
        cols = ("seq", "a", "b", "level", "diff", "boxes", "pixels", "time")
        self.rerender_tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="extended", style="History.Treeview")
        for col, key in (
            ("seq", "rerender_col_seq"),
            ("a", "rerender_col_a"),
            ("b", "rerender_col_b"),
            ("level", "rerender_col_level"),
            ("diff", "rerender_col_diff"),
            ("boxes", "rerender_col_boxes"),
            ("pixels", "rerender_col_pixels"),
            ("time", "rerender_col_time"),
        ):
            self.rerender_tree.heading(col, text=self._tr(key))
        self.rerender_tree.column("seq", width=60, minwidth=50, anchor="center")
        self.rerender_tree.column("a", width=70, minwidth=60, anchor="center")
        self.rerender_tree.column("b", width=70, minwidth=60, anchor="center")
        self.rerender_tree.column("level", width=150, minwidth=100, anchor="w")
        self.rerender_tree.column("diff", width=90, minwidth=70, anchor="center")
        self.rerender_tree.column("boxes", width=80, minwidth=60, anchor="center")
        self.rerender_tree.column("pixels", width=120, minwidth=90, anchor="e")
        self.rerender_tree.column("time", width=80, minwidth=70, anchor="center")
        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.rerender_tree.yview)
        self.rerender_tree.configure(yscrollcommand=scroll.set)
        self.rerender_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

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
        self.rerender_by_iid.clear()
        for iid in self.rerender_tree.get_children():
            self.rerender_tree.delete(iid)
        for row in rows:
            seq = int(row.get("seq") or 0)
            pixels = row.get("pixel_count")
            pixels_text = f"{int(pixels):,}".replace(",", " ") if pixels else ""
            elapsed = row.get("elapsed_sec")
            elapsed_text = f"{float(elapsed):.1f}s" if elapsed not in (None, "") else ""  # type: ignore[arg-type]
            diff = row.get("diff_percent")
            diff_text = "" if diff in (None, "") else f"{float(diff):.3f}"  # type: ignore[arg-type]
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
                    diff_text,
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
        if self.open_report_btn is not None:
            self.open_report_btn.configure(state=tk.NORMAL)
        if self.open_run_btn is not None:
            self.open_run_btn.configure(state=tk.NORMAL)

    def _start_rerender_selected(self: AppProtocol) -> None:
        if self.running or self.rerender_running:
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
        if dpi < 72:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_rerender_dpi"))
            return
        if workers < 0:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_workers"))
            return
        run_dir = Path(self.rerender_run_dir.get().strip())
        seqs = [int(iid) for iid in selected]
        self.rerender_running = True
        if self.rerender_start_btn is not None:
            self.rerender_start_btn.configure(state=tk.DISABLED)
        self.progress.configure(value=0.0)
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        self.progress_pct.set("0%")
        self._set_status("status_rerender_running")
        t = threading.Thread(target=self._rerender_worker, args=(run_dir, seqs, dpi, workers), daemon=True)
        t.start()

    def _rerender_worker(self: AppProtocol, run_dir: Path, seqs: list[int], dpi: int, workers: int) -> None:
        try:
            def report_progress(pct: float, msg: str) -> None:
                self.worker_events.put(("rerender_progress", float(pct), str(msg)))

            result = regenerate_report_pages(
                run_dir,
                seqs,
                high_dpi=dpi,
                report_lang=self.lang.get(),
                workers=workers,
                progress_cb=report_progress,
            )
            self.worker_events.put(("rerender_done", result))
        except Exception as exc:
            self.worker_events.put(("rerender_error", str(exc), traceback.format_exc()))
