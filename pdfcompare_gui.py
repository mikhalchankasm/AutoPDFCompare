from __future__ import annotations

import multiprocessing
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any
from collections.abc import Callable

from compare_pdfs import (
    APP_NAME,
    APP_VERSION,
    DIFF_STRICTNESS_CHOICES,
    LIVE_REPORT_EVENT_PREFIX,
    MAX_RENDER_DPI,
    MIN_RENDER_DPI,
    START_REPORT_FILE,
    RunCancelled,
    compare_pdfs,
    normalize_exclude_regions,
    sanitize_run_folder_name,
)
from pdfcompare_ui.compare_tab import CompareTabMixin
from pdfcompare_ui.dnd import DragDropMixin
from pdfcompare_ui.exclusion_picker import format_regions_for_field, pick_exclude_regions
from pdfcompare_ui.history_tab import HistoryTabMixin
from pdfcompare_ui.i18n import I18N
from pdfcompare_ui.rerender_tab import RerenderTabMixin
from pdfcompare_ui.state_persistence import StatePersistenceMixin
from pdfcompare_ui.update_check import (
    SETUP_ASSET_NAME,
    fetch_latest_release,
    fetch_text,
    is_newer,
    parse_sha256sums,
    sha256_of_file,
)
from pdfcompare_ui.utils import (
    count_pdf_pages_pair,
    extract_revision_label,
    format_duration_mmss,
)
from pdfcompare_ui.styles import (
    ACCENT,
    ACCENT_DARK,
    BG_CARD,
    BG_INFO,
    BG_SOFT,
    BG_WINDOW,
    BORDER_STRONG,
    BORDER_THIN,
    NEW_BORDER,
    NEW_DOT,
    OLD_BORDER,
    OLD_DOT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    configure_ttk_styles,
)

# Try to import tkinterdnd2 for drag & drop support
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_TKDND = True
except ImportError:
    HAS_TKDND = False
    TkinterDnD = None
    DND_FILES = None





class PDFCompareApp(
    CompareTabMixin,
    RerenderTabMixin,
    StatePersistenceMixin,
    HistoryTabMixin,
    DragDropMixin,
):
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.lang = tk.StringVar(value="ru")
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1100x820")
        self.root.minsize(920, 700)
        self.root.configure(bg=BG_WINDOW)

        self.old_pdf = tk.StringVar()
        self.new_pdf = tk.StringVar()
        self.out_dir = tk.StringVar()
        self.run_name = tk.StringVar()
        self.dpi = tk.StringVar(value="250")
        self.stroke_tol = tk.StringVar(value="2.0")
        self.diff_strictness = tk.StringVar(value="normal")
        self.exclude_regions = tk.StringVar(value="")
        self.workers = tk.StringVar(value="0")
        # Bbox merge is experimental and off by default (matches MCP/CLI).
        self.bbox_merge = tk.StringVar(value="off")
        self.bbox_merge_gap = tk.StringVar(value="5")
        self.bbox_merge_max_ratio = tk.StringVar(value="16")
        self.keep_debug = tk.StringVar(value="off")
        self.status = tk.StringVar(value="")
        self.progress_pct = tk.StringVar(value="0%")
        self.elapsed = tk.StringVar(value="00:00")
        self.drop_badges_var = tk.StringVar(value="")
        self.options_expanded = False
        self.old_file_name = tk.StringVar(value="")
        self.old_file_path = tk.StringVar(value="")
        self.old_file_version = tk.StringVar(value="")
        self.new_file_name = tk.StringVar(value="")
        self.new_file_path = tk.StringVar(value="")
        self.new_file_version = tk.StringVar(value="")
        self.dpi_value = tk.StringVar(value=self.dpi.get())
        self.stroke_value = tk.StringVar(value=self.stroke_tol.get())
        self.history_search = tk.StringVar(value="")
        self.history_filter = tk.StringVar(value="all")
        self.rerender_run_dir = tk.StringVar(value="")
        self.rerender_dpi = tk.StringVar(value="500")
        self.rerender_workers = tk.StringVar(value="0")
        # Rerender overrides: empty/"" means "inherit from the original summary"
        # (same convention the MCP rerender tool uses with None values).
        self.rerender_stroke_tol = tk.StringVar(value="")
        self.rerender_strictness = tk.StringVar(value="")
        self.rerender_exclude = tk.StringVar(value="")
        self.rerender_bbox_merge = tk.StringVar(value="off")
        self.rerender_bbox_gap = tk.StringVar(value="")
        self.rerender_mode = tk.StringVar(value="uniform")
        # Per-page overrides in mixed mode: {seq: {dpi, stroke_tol, ...}}.
        self.rerender_page_settings: dict[int, dict[str, Any]] = {}
        # Old PDF of the loaded run (from summary.json) — used by the exclude picker.
        self.rerender_source_pdf: Path | None = None

        self.worker_events: queue.Queue[tuple] = queue.Queue()
        self.running = False
        self.cancel_requested = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self._run_started_monotonic = 0.0
        self._timer_job: str | None = None
        self.last_run_dir: Path | None = None
        self._drop_hook: Any | None = None
        self._history_by_iid: dict[str, dict[str, Any]] = {}
        # Widget refs created by _build_ui (called at end of __init__).
        # run_btn is unguarded in many places; the others are guarded with
        # `is not None` so they keep Optional.
        self.run_btn: tk.Button | None = None
        self.open_report_btn: ttk.Button | None = None
        self.open_run_btn: ttk.Button | None = None
        self.options_body: tk.Frame | None = None
        self.options_toggle_btn: ttk.Button | None = None
        self.drop_canvas: tk.Frame | None = None
        self.lang_ru_btn: tk.Label | None = None
        self.lang_en_btn: tk.Label | None = None
        self.update_badge: tk.Label | None = None
        self.check_updates_btn: tk.Label | None = None
        self.subtitle_label: ttk.Label | None = None
        self.tabs: ttk.Notebook | None = None
        self.compare_tab: ttk.Frame | None = None
        self.history_tab: ttk.Frame | None = None
        self.rerender_tab: ttk.Frame | None = None
        self.old_label: ttk.Label | None = None
        self.new_label: ttk.Label | None = None
        self.out_label: ttk.Label | None = None
        self.run_name_label: ttk.Label | None = None
        self.run_name_hint_label: ttk.Label | None = None
        # old_entry / new_entry are file-card containers (tk.Frame returned
        # by _build_file_card); only out_entry is a real Entry widget.
        self.old_entry: tk.Frame | None = None
        self.new_entry: tk.Frame | None = None
        self.out_entry: ttk.Entry | None = None
        self.old_pick_btn: ttk.Button | None = None
        self.new_pick_btn: ttk.Button | None = None
        self.out_pick_btn: ttk.Button | None = None
        self.options_dpi_label: ttk.Label | None = None
        self.options_dpi_hint_label: ttk.Label | None = None
        self.options_stroke_label: ttk.Label | None = None
        self.options_stroke_hint_label: ttk.Label | None = None
        self.options_strictness_label: ttk.Label | None = None
        self.options_strictness_hint_label: ttk.Label | None = None
        self.options_exclude_label: ttk.Label | None = None
        self.options_exclude_hint_label: ttk.Label | None = None
        self.options_bbox_merge_label: ttk.Label | None = None
        self.options_bbox_merge_hint_label: ttk.Label | None = None
        self.options_keep_debug_label: ttk.Label | None = None
        self.options_keep_debug_hint_label: ttk.Label | None = None
        self.bbox_merge_chip: ttk.Checkbutton | None = None
        self.bbox_merge_gap_entry: ttk.Entry | None = None
        self.bbox_merge_max_ratio_entry: ttk.Entry | None = None
        self.keep_debug_chip: ttk.Checkbutton | None = None
        self.clear_btn: ttk.Button | None = None
        self.from_history_btn: ttk.Button | None = None
        self.exclude_pick_btn: ttk.Button | None = None
        self.hist_restore_btn: tk.Button | None = None
        self.hist_snapshot_btn: ttk.Button | None = None
        self.hist_open_btn: ttk.Button | None = None
        self.hist_refresh_btn: ttk.Button | None = None
        self.history_hint_label: ttk.Label | None = None
        self.status_text_label: tk.Label | None = None
        self.report_ready_label: tk.Label | None = None
        self.history_search_entry: ttk.Entry | None = None
        self.rerender_tree: ttk.Treeview | None = None
        self.rerender_title_label: ttk.Label | None = None
        self.rerender_hint_label: ttk.Label | None = None
        self.rerender_run_label: ttk.Label | None = None
        self.rerender_load_current_btn: ttk.Button | None = None
        self.rerender_pick_btn: ttk.Button | None = None
        self.rerender_reload_btn: ttk.Button | None = None
        self.rerender_dpi_label: ttk.Label | None = None
        self.rerender_workers_label: ttk.Label | None = None
        self.rerender_start_btn: tk.Button | None = None
        self.rerender_open_report_btn: ttk.Button | None = None
        self.rerender_mode_chips: dict[str, tk.Label] = {}
        self.rerender_strictness_chips: dict[str, tk.Label] = {}
        self.rerender_edit_selected_btn: ttk.Button | None = None
        self.rerender_exclude_pick_btn: ttk.Button | None = None
        self.history_filter_buttons: dict[str, tk.Label] = {}
        self.strictness_chips: dict[str, tk.Label] = {}
        self.rerender_by_iid: dict[str, dict[str, Any]] = {}
        self.rerender_running = False
        self.rerender_cancel_requested = threading.Event()
        self.rerender_thread: threading.Thread | None = None

        self.state_dir = Path.home() / ".pdfcompare_local"
        self.state_path = self.state_dir / "state.json"
        self.last_inputs: dict[str, Any] = {}
        self.history_records: list[dict[str, Any]] = []
        self.update_check_state: dict[str, Any] = self._default_update_check_state()
        self._load_state()

        self._build_ui()
        self._bind_input_tracking()
        self._restore_last_inputs(startup=True)
        self._update_run_availability()
        self._refresh_history_table()
        self._install_drop_hook()
        self.root.bind("<Return>", self._on_enter)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._poll_worker_events)
        self.root.after(800, self._start_update_check)

    def _tr(self, key: str, **kwargs: object) -> str:
        lang = self.lang.get() if self.lang.get() in I18N else "ru"
        template = I18N.get(lang, I18N["ru"]).get(key, I18N["ru"].get(key, key))
        return template.format(**kwargs)

    def _set_status(self, key: str, **kwargs: object) -> None:
        self.status.set(self._tr(key, **kwargs))

    def _show_report_ready(self) -> None:
        if self.report_ready_label is not None:
            self.report_ready_label.pack(side=tk.RIGHT, padx=(8, 0))

    def _hide_report_ready(self) -> None:
        if self.report_ready_label is not None:
            self.report_ready_label.pack_forget()

    def _set_language(self, lang_code: str) -> None:
        """Set language and update button styles"""
        self.lang.set(lang_code)
        self._update_lang_buttons()
        self._apply_locale()
        self._save_state()

    def _update_lang_buttons(self) -> None:
        """Update language button styles to show active language"""
        if self.lang_ru_btn is None or self.lang_en_btn is None:
            return
        current = self.lang.get()
        self.lang_ru_btn.configure(
            bg=BG_CARD if current == "ru" else BG_SOFT,
            fg=TEXT_PRIMARY if current == "ru" else TEXT_SECONDARY,
            font=("Segoe UI", 9, "bold" if current == "ru" else "normal"),
        )
        self.lang_en_btn.configure(
            bg=BG_CARD if current == "en" else BG_SOFT,
            fg=TEXT_PRIMARY if current == "en" else TEXT_SECONDARY,
            font=("Segoe UI", 9, "bold" if current == "en" else "normal"),
        )

    def _apply_locale(self) -> None:
        self.root.title(f"{self._tr('window_title')} {APP_VERSION}")
        if self.subtitle_label is not None:
            self.subtitle_label.configure(text=self._tr("app_subtitle"))
        if self.report_ready_label is not None:
            self.report_ready_label.configure(text=self._tr("status_report_ready"))
        if self.tabs is not None:
            self.tabs.tab(0, text=self._tr("tab_compare"))
            self.tabs.tab(1, text=self._history_tab_text())
            if self.tabs.index("end") > 2:
                self.tabs.tab(2, text=self._tr("tab_rerender"))
        if self.old_label is not None:
            self.old_label.configure(text=self._tr("path_old").replace("● ", ""))
        if self.new_label is not None:
            self.new_label.configure(text=self._tr("path_new").replace("● ", ""))
        if self.out_label is not None:
            self.out_label.configure(text=self._tr("path_out"))
        if self.run_name_label is not None:
            self.run_name_label.configure(text=self._tr("path_run_name"))
        if self.run_name_hint_label is not None:
            self.run_name_hint_label.configure(text=self._tr("path_run_name_hint"))
        if self.old_pick_btn is not None:
            self.old_pick_btn.configure(text=self._tr("btn_select"))
        if self.swap_btn is not None:
            self.swap_btn.configure(text=self._tr("btn_swap"))
        if self.new_pick_btn is not None:
            self.new_pick_btn.configure(text=self._tr("btn_select"))
        if self.out_pick_btn is not None:
            self.out_pick_btn.configure(text=self._tr("btn_select"))
        if self.options_dpi_label is not None:
            self.options_dpi_label.configure(text=self._option_label_text("opts_dpi"))
        if self.options_dpi_hint_label is not None:
            self.options_dpi_hint_label.configure(text=self._tr("opts_dpi_hint"))
        if self.options_stroke_label is not None:
            self.options_stroke_label.configure(text=self._option_label_text("opts_stroke"))
        if self.options_stroke_hint_label is not None:
            self.options_stroke_hint_label.configure(text=self._tr("opts_stroke_hint"))
        if self.options_strictness_label is not None:
            self.options_strictness_label.configure(text=self._tr("opts_strictness"))
        if self.options_strictness_hint_label is not None:
            self.options_strictness_hint_label.configure(text=self._tr("opts_strictness_hint"))
        if self.options_exclude_label is not None:
            self.options_exclude_label.configure(text=self._tr("opts_exclude"))
        if self.options_exclude_hint_label is not None:
            self.options_exclude_hint_label.configure(text=self._tr("opts_exclude_hint"))
        if self.run_btn is not None:
            if self.running:
                self.run_btn.configure(text=self._tr("btn_cancelling" if self.cancel_requested.is_set() else "btn_cancel"))
            else:
                self.run_btn.configure(text=self._tr("btn_compare_short"))
        if self.clear_btn is not None:
            self.clear_btn.configure(text=self._tr("btn_clear"))
        if self.from_history_btn is not None:
            self.from_history_btn.configure(text=self._tr("btn_from_history"))
        if self.open_report_btn is not None:
            self.open_report_btn.configure(text=self._tr("btn_open_report"))
        if self.open_run_btn is not None:
            self.open_run_btn.configure(text=self._tr("btn_open_folder"))
        if self.hist_restore_btn is not None:
            self.hist_restore_btn.configure(text=self._tr("hist_restore"))
        if self.hist_snapshot_btn is not None:
            self.hist_snapshot_btn.configure(text=self._tr("hist_snapshot"))
        if self.hist_open_btn is not None:
            self.hist_open_btn.configure(text=self._tr("hist_open_folder"))
        if self.hist_refresh_btn is not None:
            self.hist_refresh_btn.configure(text=f"↻ {self._tr('hist_refresh')}")
        if self.history_tree is not None:
            self.history_tree.heading("ts", text=self._tr("hist_col_time"))
            self.history_tree.heading("duration", text=self._tr("hist_col_duration"))
            self.history_tree.heading("pages", text=self._tr("hist_col_pages"))
            self.history_tree.heading("result", text=self._tr("hist_col_result"))
            self.history_tree.heading("old", text=self._tr("hist_col_old"))
            self.history_tree.heading("new", text=self._tr("hist_col_new"))
            self.history_tree.heading("out", text=self._tr("hist_col_out"))
            self.history_tree.heading("run", text=self._tr("hist_col_run"))
        if self.history_hint_label is not None:
            self.history_hint_label.configure(text=self._tr("hist_hint"))
        if self.rerender_title_label is not None:
            self.rerender_title_label.configure(text=self._tr("rerender_title"))
        if self.rerender_hint_label is not None:
            self.rerender_hint_label.configure(text=self._tr("rerender_hint"))
        if self.rerender_run_label is not None:
            self.rerender_run_label.configure(text=self._tr("rerender_run"))
        if self.rerender_load_current_btn is not None:
            self.rerender_load_current_btn.configure(text=self._tr("rerender_load_current"))
        if self.rerender_pick_btn is not None:
            self.rerender_pick_btn.configure(text=self._tr("rerender_pick"))
        if self.rerender_reload_btn is not None:
            self.rerender_reload_btn.configure(text=self._tr("rerender_reload"))
        if self.rerender_dpi_label is not None:
            self.rerender_dpi_label.configure(text=self._tr("rerender_dpi"))
        if self.rerender_workers_label is not None:
            self.rerender_workers_label.configure(text=self._tr("rerender_workers"))
        if self.rerender_start_btn is not None:
            if self.rerender_running:
                key = "btn_cancelling" if self.rerender_cancel_requested.is_set() else "btn_cancel"
                self.rerender_start_btn.configure(text=self._tr(key))
            else:
                self.rerender_start_btn.configure(text=self._tr("rerender_start"))
        if self.rerender_open_report_btn is not None:
            self.rerender_open_report_btn.configure(text=self._tr("btn_open_report"))
        if self.rerender_tree is not None:
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
        if self.history_search_entry is not None:
            if not self.history_search.get() or self.history_search.get() in (
                I18N["ru"].get("history_search_placeholder"),
                I18N["en"].get("history_search_placeholder"),
            ):
                self.history_search.set("")
                self._set_history_placeholder()
        for value, key in (("all", "hist_filter_all"), ("done", "hist_filter_done"), ("cancelled", "hist_filter_cancelled")):
            if value in self.history_filter_buttons:
                self.history_filter_buttons[value].configure(text=self._tr(key))
        for value, widget in self.strictness_chips.items():
            widget.configure(text=self._tr(f"strictness_{value}"))
        self._update_lang_buttons()
        self._draw_drop_zone()
        self._refresh_drop_badges()
        self._refresh_file_cards()
        self._refresh_option_values()
        self._update_history_filter_buttons()
        self._update_strictness_chips()
        self._refresh_history_table()

    def _build_ui(self) -> None:
        configure_ttk_styles(self.root)

        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(outer)
        top.pack(fill=tk.X)
        top_left = ttk.Frame(top)
        top_left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(top_left, text=self._tr("app_title"), style="Header.TLabel").pack(anchor="w")
        self.subtitle_label = ttk.Label(
            top_left,
            text=self._tr("app_subtitle"),
            style="SubHeader.TLabel",
        )
        self.subtitle_label.pack(anchor="w", pady=(2, 8))

        right_top = tk.Frame(top, bg=BG_WINDOW)
        right_top.pack(side=tk.RIGHT)

        lang_frame = tk.Frame(right_top, bg=BG_SOFT, padx=2, pady=2, highlightthickness=1, highlightbackground=BORDER_THIN)
        lang_frame.pack(side=tk.RIGHT)
        self.lang_ru_btn = tk.Label(lang_frame, text="RU", padx=12, pady=4, cursor="hand2", font=("Segoe UI", 9))
        self.lang_ru_btn.pack(side=tk.LEFT)
        self.lang_ru_btn.bind("<Button-1>", lambda _e: self._set_language("ru"))
        self.lang_en_btn = tk.Label(lang_frame, text="EN", padx=12, pady=4, cursor="hand2", font=("Segoe UI", 9))
        self.lang_en_btn.pack(side=tk.LEFT)
        self.lang_en_btn.bind("<Button-1>", lambda _e: self._set_language("en"))

        # "Check for updates" button — explicit refresh icon.
        self.check_updates_btn = tk.Label(
            right_top,
            text="↻",
            width=3,
            height=1,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            relief="solid",
            bd=1,
            font=("Segoe UI", 13),
            cursor="hand2",
        )
        self.check_updates_btn.pack(side=tk.RIGHT, padx=(8, 6))
        self.check_updates_btn.bind("<Button-1>", lambda _e: self._check_for_updates_now())

        # Update badge — hidden until a newer release is found.
        self.update_badge = tk.Label(
            right_top,
            text="★",
            padx=10,
            pady=4,
            bg=BG_INFO,
            fg=ACCENT_DARK,
            relief="solid",
            bd=1,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        )
        # Not packed here; shown by _show_update_badge when an update exists.

        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill=tk.BOTH, expand=True)
        self.compare_tab = ttk.Frame(self.tabs, padding=14)
        self.history_tab = ttk.Frame(self.tabs, padding=0)
        self.rerender_tab = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(self.compare_tab, text=self._tr("tab_compare"))
        self.tabs.add(self.history_tab, text=self._history_tab_text())
        self.tabs.add(self.rerender_tab, text=self._tr("tab_rerender"))

        self._build_files_section()
        self._build_output_section()
        self._build_options_section()
        self._build_actions_section()
        self._build_status_panel()
        self._build_history_tab()
        self._build_rerender_tab()
        self._update_lang_buttons()
        self._apply_locale()

    def _path_row(
        self, parent: ttk.Frame, var: tk.StringVar, pick_cmd: Callable[[], None], label_style: str = ""
    ) -> tuple[ttk.Label, ttk.Entry, ttk.Button]:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        label = ttk.Label(row, text="", width=20, style=label_style if label_style else "TLabel")
        label.pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        btn = ttk.Button(row, text=self._tr("btn_select"), style="Small.TButton", command=pick_cmd)
        btn.pack(side=tk.LEFT, padx=(8, 0))
        return label, entry, btn

    def _option_label_text(self, label_key: str) -> str:
        return f"{self._tr(label_key).rstrip(':')}:"

    def _primary_button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        compact: bool = False,
    ) -> tk.Button:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACCENT,
            fg=BG_CARD,
            activebackground=ACCENT_DARK,
            activeforeground=BG_CARD,
            disabledforeground=TEXT_TERTIARY,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            padx=14 if compact else 18,
            pady=7 if compact else 11,
            cursor="hand2",
            font=("Segoe UI", 10 if compact else 11, "bold"),
        )
        button.bind("<Enter>", lambda _e, w=button: self._set_primary_hover(w, True))  # type: ignore[misc]
        button.bind("<Leave>", lambda _e, w=button: self._set_primary_hover(w, False))  # type: ignore[misc]
        return button

    def _set_primary_hover(self, button: tk.Button, active: bool) -> None:
        if str(button.cget("state")) == tk.DISABLED:
            return
        button.configure(bg=ACCENT_DARK if active else ACCENT, fg=BG_CARD)

    def _set_primary_state(self, button: tk.Button, state: str) -> None:
        if state == tk.DISABLED:
            button.configure(
                state=tk.DISABLED,
                bg=BORDER_STRONG,
                fg=TEXT_SECONDARY,
                disabledforeground=TEXT_SECONDARY,
                cursor="",
            )
        else:
            button.configure(
                state=tk.NORMAL,
                bg=ACCENT,
                fg=BG_CARD,
                disabledforeground=TEXT_TERTIARY,
                cursor="hand2",
            )

    def _history_tab_text(self) -> str:
        return f"{self._tr('tab_history')} · {len(self.history_records)}"

    def _extract_revision(self, path_text: str) -> str:
        return extract_revision_label(path_text)

    def _clear_old_pdf(self) -> None:
        if not self.running:
            self.old_pdf.set("")
            self._save_state()

    def _clear_new_pdf(self) -> None:
        if not self.running:
            self.new_pdf.set("")
            self._save_state()

    def _build_file_card(self, parent: tk.Frame, var: tk.StringVar, old: bool) -> tk.Frame:
        border = OLD_BORDER if old else NEW_BORDER
        dot = OLD_DOT if old else NEW_DOT
        label_style = "Red.TLabel" if old else "Green.TLabel"
        pick_cmd = self._pick_old_pdf if old else self._pick_new_pdf
        clear_cmd = self._clear_old_pdf if old else self._clear_new_pdf
        name_var = self.old_file_name if old else self.new_file_name
        path_var = self.old_file_path if old else self.new_file_path
        version_var = self.old_file_version if old else self.new_file_version

        card = tk.Frame(parent, bg=BG_CARD, padx=14, pady=14, highlightthickness=1, highlightbackground=border)
        head = tk.Frame(card, bg=BG_CARD)
        head.pack(fill=tk.X)
        dot_canvas = tk.Canvas(head, width=8, height=8, bg=BG_CARD, highlightthickness=0)
        dot_canvas.pack(side=tk.LEFT, padx=(0, 6))
        dot_canvas.create_oval(1, 1, 7, 7, fill=dot, outline=dot)
        label_key = "path_old" if old else "path_new"
        label = ttk.Label(head, text=self._tr(label_key).replace("● ", ""), style=label_style)
        label.pack(side=tk.LEFT)
        ttk.Label(head, textvariable=version_var, style="Hint.TLabel", background=BG_CARD).pack(side=tk.RIGHT)
        ttk.Label(card, textvariable=name_var, font=("Segoe UI", 11), foreground=TEXT_PRIMARY, background=BG_CARD, wraplength=380).pack(
            anchor="w", pady=(8, 0)
        )
        ttk.Label(card, textvariable=path_var, style="Hint.TLabel", background=BG_CARD, wraplength=380).pack(anchor="w", pady=(6, 0))
        actions = tk.Frame(card, bg=BG_CARD)
        actions.pack(anchor="w", pady=(12, 0))
        pick_btn = ttk.Button(actions, text=self._tr("btn_select"), style="Small.TButton", command=pick_cmd)
        pick_btn.pack(side=tk.LEFT)
        ttk.Button(actions, text=self._tr("btn_clear"), style="Small.TButton", command=clear_cmd).pack(side=tk.LEFT, padx=(6, 0))
        if old:
            self.old_label = label
            self.old_pick_btn = pick_btn
        else:
            self.new_label = label
            self.new_pick_btn = pick_btn
        return card

    def _build_scale_option(
        self,
        parent: tk.Frame,
        col: int,
        label_key: str,
        var: tk.StringVar,
        display_var: tk.StringVar,
        from_value: float,
        to_value: float,
        resolution: float,
    ) -> None:
        frame = tk.Frame(parent, bg=BG_SOFT)
        frame.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 12, 0))
        head = tk.Frame(frame, bg=BG_SOFT)
        head.pack(anchor="w", pady=(0, 4))
        label = ttk.Label(head, text=self._option_label_text(label_key), style="SubHeader.TLabel", background=BG_SOFT)
        label.pack(side=tk.LEFT)
        tk.Label(
            head,
            textvariable=display_var,
            bg=BG_SOFT,
            fg=TEXT_PRIMARY,
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT, padx=(4, 0))
        if label_key == "opts_dpi":
            self.options_dpi_label = label
        elif label_key == "opts_stroke":
            self.options_stroke_label = label
        row = tk.Frame(frame, bg=BG_SOFT)
        row.pack(fill=tk.X)
        scale = tk.Scale(
            row,
            from_=from_value,
            to=to_value,
            resolution=resolution,
            orient=tk.HORIZONTAL,
            variable=var,  # type: ignore[arg-type]
            showvalue=False,
            bg=BG_SOFT,
            troughcolor=BG_CARD,
            highlightthickness=0,
            length=180,
        )
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        hint_key = "opts_dpi_hint" if label_key == "opts_dpi" else "opts_stroke_hint"
        hint = ttk.Label(frame, text=self._tr(hint_key), style="Hint.TLabel", background=BG_SOFT)
        hint.pack(anchor="w", pady=(4, 0))
        if label_key == "opts_dpi":
            self.options_dpi_hint_label = hint
        elif label_key == "opts_stroke":
            self.options_stroke_hint_label = hint

    def _set_history_filter(self, value: str) -> None:
        self.history_filter.set(value)
        self._refresh_history_table()

    def _set_history_placeholder(self) -> None:
        if self.history_search_entry is None:
            return
        if not self.history_search.get():
            self.history_search.set(self._tr("history_search_placeholder"))
            self.history_search_entry.configure(foreground=TEXT_TERTIARY)

    def _history_search_focus_in(self, _event: tk.Event) -> None:
        if self.history_search.get() == self._tr("history_search_placeholder"):
            self.history_search.set("")
            if self.history_search_entry is not None:
                self.history_search_entry.configure(foreground=TEXT_PRIMARY)

    def _history_search_focus_out(self, _event: tk.Event) -> None:
        self._set_history_placeholder()

    def _update_strictness_chips(self) -> None:
        current = self.diff_strictness.get().strip().lower() or "normal"
        for value, widget in self.strictness_chips.items():
            active = value == current
            widget.configure(fg=ACCENT if active else TEXT_SECONDARY, relief="solid", bd=2 if active else 1)

    def _update_bbox_merge_fields(self) -> None:
        """Enable/disable the gap/ratio fields based on the bbox-merge checkbox."""
        state = tk.NORMAL if self.bbox_merge.get() == "on" else tk.DISABLED
        for widget in (self.bbox_merge_gap_entry, self.bbox_merge_max_ratio_entry):
            if widget is not None:
                widget.configure(state=state)

    def _update_history_filter_buttons(self) -> None:
        current = self.history_filter.get()
        for value, widget in self.history_filter_buttons.items():
            active = value == current
            widget.configure(fg=ACCENT if active else TEXT_SECONDARY, bd=2 if active else 1)

    # Options are now always visible - toggle removed

    def _format_duration(self, seconds: float) -> str:
        return format_duration_mmss(seconds)

    def _get_pages_str(self, old_pdf: Path, new_pdf: Path) -> str:
        return count_pdf_pages_pair(old_pdf, new_pdf)

    def _pick_exclude_regions(self) -> None:
        """Open the visual picker to draw exclude regions on the Old PDF."""
        pdf_text = self.old_pdf.get().strip() or self.new_pdf.get().strip()
        if not pdf_text:
            self._set_status("status_pick_no_pdf")
            return
        pdf_path = Path(pdf_text)
        if not pdf_path.exists():
            messagebox.showerror(self._tr("err_file_missing_title"), self._tr("err_old_missing"))
            return
        existing: list[dict[str, float | str]] = []
        existing_raw = self.exclude_regions.get().strip()
        if existing_raw:
            try:
                existing = list(normalize_exclude_regions(existing_raw))
            except ValueError:
                existing = []
        regions = pick_exclude_regions(self.root, pdf_path, existing=existing, lang=self.lang.get())
        if regions is None:
            return
        self.exclude_regions.set(format_regions_for_field(regions))
        self._save_state()
        self._set_status("status_pick_added", count=len(regions))

    def _start_timer(self) -> None:
        """Start the elapsed time timer"""
        if self._timer_job is not None:
            self.root.after_cancel(self._timer_job)
        self._timer_tick()

    def _stop_timer(self) -> None:
        """Stop the elapsed time timer"""
        if self._timer_job is not None:
            self.root.after_cancel(self._timer_job)
            self._timer_job = None

    def _timer_tick(self) -> None:
        """Update elapsed time display"""
        if not self.running:
            return
        elapsed_sec = time.monotonic() - self._run_started_monotonic
        self.elapsed.set(self._format_duration(elapsed_sec))
        self._timer_job = self.root.after(250, self._timer_tick)

    def _draw_drop_zone(self) -> None:
        return

    def _refresh_drop_badges(self) -> None:
        def short_name(p: str) -> str:
            if not p:
                return ""
            path = Path(p)
            return path.name if path.name else p

        old_name = short_name(self.old_pdf.get().strip())
        new_name = short_name(self.new_pdf.get().strip())
        if old_name or new_name:
            self.drop_badges_var.set(
                f"{self._tr('badge_old')}: {old_name or self._tr('badge_not_selected')}   |   "
                f"{self._tr('badge_new')}: {new_name or self._tr('badge_not_selected')}"
            )
        else:
            self.drop_badges_var.set("")

    def _refresh_file_cards(self) -> None:
        def apply(path_text: str, name_var: tk.StringVar, path_var: tk.StringVar, version_var: tk.StringVar) -> None:
            if path_text:
                p = Path(path_text)
                name_var.set(p.name)
                path_var.set(str(p.parent))
                version_var.set(self._extract_revision(path_text))
            else:
                name_var.set(self._tr("file_not_selected"))
                path_var.set(self._tr("file_path_hint"))
                version_var.set("")

        apply(self.old_pdf.get().strip(), self.old_file_name, self.old_file_path, self.old_file_version)
        apply(self.new_pdf.get().strip(), self.new_file_name, self.new_file_path, self.new_file_version)

    def _refresh_option_values(self) -> None:
        self.dpi_value.set(str(self.dpi.get()).split(".")[0])
        try:
            self.stroke_value.set(f"{float(self.stroke_tol.get()):.1f}")
        except ValueError:
            self.stroke_value.set(self.stroke_tol.get())
        self._update_strictness_chips()
        self._update_bbox_merge_fields()

    def _bind_input_tracking(self) -> None:
        for var in (
            self.old_pdf,
            self.new_pdf,
            self.out_dir,
            self.run_name,
            self.dpi,
            self.stroke_tol,
            self.diff_strictness,
            self.exclude_regions,
            self.bbox_merge,
            self.bbox_merge_gap,
            self.bbox_merge_max_ratio,
            self.keep_debug,
        ):
            var.trace_add("write", self._on_inputs_changed)
        self.history_search.trace_add("write", lambda *_: self._refresh_history_table())

    def _on_inputs_changed(self, *_: object) -> None:
        self.last_inputs = self._capture_inputs()
        self._refresh_drop_badges()
        self._refresh_file_cards()
        self._refresh_option_values()
        self._update_run_availability()

    def _update_run_availability(self) -> None:
        if self.run_btn is None:
            return
        if self.running:
            self._set_primary_state(self.run_btn, tk.DISABLED if self.cancel_requested.is_set() else tk.NORMAL)
            return
        old = self.old_pdf.get().strip()
        new = self.new_pdf.get().strip()
        ready = bool(old and new)
        if ready:
            try:
                old_p = Path(old)
                new_p = Path(new)
                ready = old_p.exists() and new_p.exists() and old_p.resolve() != new_p.resolve()
            except Exception:
                ready = False
        self._set_primary_state(self.run_btn, tk.NORMAL if ready else tk.DISABLED)

    def _dialog_initialdir(self, *candidates: str) -> str | None:
        """Pick the folder file dialogs should open in: the first field value
        that points at (or into) an existing directory — so the dialog opens
        where the field already points instead of the OS's last-used folder.
        None is fine: tkinter skips None-valued dialog options."""
        for raw in candidates:
            text = (raw or "").strip()
            if not text:
                continue
            try:
                path = Path(text)
                folder = path if path.is_dir() else path.parent
                if folder.is_dir() and str(folder) not in ("", "."):
                    return str(folder)
            except OSError:
                continue
        return None

    def _pick_old_pdf(self) -> None:
        start = self._dialog_initialdir(self.old_pdf.get(), self.new_pdf.get())
        p = filedialog.askopenfilename(title=self._tr("dlg_pick_old"), filetypes=[("PDF", "*.pdf")], initialdir=start)
        if p:
            self.old_pdf.set(p)
            self._save_state()

    def _pick_new_pdf(self) -> None:
        start = self._dialog_initialdir(self.new_pdf.get(), self.old_pdf.get())
        p = filedialog.askopenfilename(title=self._tr("dlg_pick_new"), filetypes=[("PDF", "*.pdf")], initialdir=start)
        if p:
            self.new_pdf.set(p)
            self._save_state()

    def _pick_out_dir(self) -> None:
        start = self._dialog_initialdir(self.out_dir.get(), self.old_pdf.get())
        p = filedialog.askdirectory(title=self._tr("dlg_pick_out"), initialdir=start)
        if p:
            self.out_dir.set(p)
            self._save_state()

    def _swap_files(self) -> None:
        """Swap old and new PDF paths"""
        old_val = self.old_pdf.get()
        new_val = self.new_pdf.get()
        self.old_pdf.set(new_val)
        self.new_pdf.set(old_val)
        self._save_state()

    def _clear_inputs(self) -> None:
        if self.running:
            return
        self.old_pdf.set("")
        self.new_pdf.set("")
        self.out_dir.set("")
        self.run_name.set("")
        self.exclude_regions.set("")
        self.bbox_merge.set("off")
        self.bbox_merge_gap.set("5")
        self.bbox_merge_max_ratio.set("16")
        self.keep_debug.set("off")
        self.progress.configure(value=0.0)
        self.progress_pct.set("0%")
        self.last_run_dir = None
        self._set_status("status_cleared")
        self._save_state()

    def _on_enter(self, event: tk.Event) -> None:
        if not self.running:
            self.start_compare()
        else:
            self._request_cancel()

    def _reset_rerender_button(self) -> None:
        """Back to "Перегенерировать" after a run ends, however it ended."""
        self.rerender_cancel_requested.clear()
        if self.rerender_start_btn is not None:
            self._set_primary_state(self.rerender_start_btn, tk.NORMAL)
            self.rerender_start_btn.configure(text=self._tr("rerender_start"))

    def _request_cancel(self) -> None:
        if not self.running:
            return
        self.cancel_requested.set()
        if self.run_btn is not None:
            self._set_primary_state(self.run_btn, tk.DISABLED)
            self.run_btn.configure(text=self._tr("btn_cancelling"))
        self._set_status("status_cancel_requested")

    def start_compare(self) -> None:
        if self.running:
            return

        old = Path(self.old_pdf.get().strip()) if self.old_pdf.get().strip() else None
        new = Path(self.new_pdf.get().strip()) if self.new_pdf.get().strip() else None
        if not old or not old.exists():
            messagebox.showerror(self._tr("err_file_missing_title"), self._tr("err_old_missing"))
            return
        if not new or not new.exists():
            messagebox.showerror(self._tr("err_file_missing_title"), self._tr("err_new_missing"))
            return
        if old.resolve() == new.resolve():
            messagebox.showerror(self._tr("err_invalid_input_title"), self._tr("err_same_files"))
            return

        out = self.out_dir.get().strip()
        if not out:
            selected = filedialog.askdirectory(title=self._tr("dlg_pick_out"), initialdir=self._dialog_initialdir(self.old_pdf.get()))
            if not selected:
                self._set_status("status_run_cancel_no_out")
                return
            self.out_dir.set(selected)
            out = selected
        out_path = Path(out)
        out_path.mkdir(parents=True, exist_ok=True)

        try:
            dpi = int(self.dpi.get().strip())
            stroke_tol = float(self.stroke_tol.get().strip())
            exclude_regions = normalize_exclude_regions(self.exclude_regions.get())
            bbox_merge_gap = float(self.bbox_merge_gap.get().strip()) if self.bbox_merge.get() == "on" else 0.0
            bbox_merge_ratio = float(self.bbox_merge_max_ratio.get().strip()) if self.bbox_merge.get() == "on" else 16.0
        except ValueError as exc:
            messagebox.showerror(self._tr("err_invalid_option_title"), f"{self._tr('err_invalid_option_parse')}\n\n{exc}")
            return
        diff_strictness = self.diff_strictness.get().strip().lower() or "normal"
        keep_debug = self.keep_debug.get() == "on"

        if self.bbox_merge.get() == "on":
            if bbox_merge_gap < 0 or bbox_merge_gap > 50:
                messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_bbox_merge_gap"))
                return
            if bbox_merge_ratio < 1 or bbox_merge_ratio > 100:
                messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_bbox_merge_ratio"))
                return

        # Guard against typos and accidental huge values that exhaust memory.
        if dpi < MIN_RENDER_DPI or dpi > MAX_RENDER_DPI:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_dpi"))
            return
        if stroke_tol < 0:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_stroke"))
            return
        if diff_strictness not in DIFF_STRICTNESS_CHOICES:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_strictness"))
            return
        run_name = self.run_name.get().strip() or None
        if run_name is not None:
            try:
                run_name = sanitize_run_folder_name(run_name)
            except ValueError as exc:
                messagebox.showerror(self._tr("err_invalid_option_title"), str(exc))
                return
            self.run_name.set(run_name)
            if (out_path / run_name).exists():
                messagebox.showerror(
                    self._tr("err_invalid_option_title"),
                    self._tr("err_run_exists", path=out_path / run_name),
                )
                return

        self.last_inputs = self._capture_inputs()
        self._save_state()
        self.cancel_requested.clear()
        self.last_run_dir = None
        self._set_running(True)
        self._set_status("status_running")
        # Workers control removed from UI — always use auto/parallel processing.
        workers = 0
        t = threading.Thread(
            target=self._run_worker,
            args=(
                old, new, out_path, dpi, stroke_tol, workers, self.lang.get(), run_name,
                exclude_regions, diff_strictness, bbox_merge_gap, bbox_merge_ratio, keep_debug,
            ),
            daemon=True,
        )
        self.worker_thread = t
        t.start()

    def _run_worker(
        self,
        old: Path,
        new: Path,
        out_path: Path,
        dpi: int,
        stroke_tol: float,
        workers: int,
        report_lang: str,
        run_name: str | None,
        exclude_regions: list[dict[str, float | str]],
        diff_strictness: str,
        bbox_merge_gap_mm: float,
        bbox_merge_max_area_ratio: float,
        keep_debug_images: bool,
    ) -> None:
        try:
            def report_progress(pct: float, msg: str) -> None:
                if self.cancel_requested.is_set():
                    raise RuntimeError("__CANCELLED__")
                self.worker_events.put(("progress", float(pct), str(msg)))

            run_dir = compare_pdfs(
                old,
                new,
                out_path,
                high_dpi=dpi,
                stroke_tol_px=stroke_tol,
                report_lang=report_lang,
                run_name=run_name,
                workers=workers,
                exclude_regions=exclude_regions,
                diff_strictness=diff_strictness,
                bbox_merge_gap_mm=bbox_merge_gap_mm,
                bbox_merge_max_area_ratio=bbox_merge_max_area_ratio,
                keep_debug_images=keep_debug_images,
                progress_cb=report_progress,
                cancel_cb=self.cancel_requested.is_set,
            )
            if self.cancel_requested.is_set():
                self.worker_events.put(("cancelled", old, new, out_path, dpi, stroke_tol, workers, diff_strictness, exclude_regions))
                return
            self.worker_events.put(("done", run_dir, old, new, out_path, dpi, stroke_tol, workers, diff_strictness, exclude_regions))
        except Exception as exc:
            if isinstance(exc, RunCancelled) or str(exc) == "__CANCELLED__":
                self.worker_events.put(("cancelled", old, new, out_path, dpi, stroke_tol, workers, diff_strictness, exclude_regions))
                return
            self.worker_events.put(("error", str(exc), traceback.format_exc(), old, new, out_path, dpi, stroke_tol, workers, diff_strictness, exclude_regions))

    def _poll_worker_events(self) -> None:
        has_more = False
        try:
            max_batch = 50
            processed = 0
            while processed < max_batch:
                event = self.worker_events.get_nowait()
                processed += 1
                kind = event[0]
                if kind == "progress":
                    pct = max(0.0, min(100.0, float(event[1])))
                    msg = str(event[2])
                    if msg.startswith(LIVE_REPORT_EVENT_PREFIX):
                        self.last_run_dir = Path(msg[len(LIVE_REPORT_EVENT_PREFIX):])
                        self._show_report_ready()
                        msg = self._tr("status_live_report")
                    self.progress.configure(value=pct)
                    self.progress_pct.set(f"{pct:.0f}%")
                    self.status.set(f"{msg} ({pct:.0f}%)")
                elif kind == "rerender_progress":
                    pct = max(0.0, min(100.0, float(event[1])))
                    msg = str(event[2])
                    self.progress.configure(value=pct)
                    self.progress_pct.set(f"{pct:.0f}%")
                    self.status.set(f"{msg} ({pct:.0f}%)")
                elif kind == "rerender_cancelled":
                    self.rerender_running = False
                    self._reset_rerender_button()
                    self.progress.configure(value=0.0)
                    self.progress_pct.set("0%")
                    self._set_status("status_rerender_cancelled")
                elif kind == "rerender_done":
                    run_dir: Path = event[1]
                    self.rerender_running = False
                    self.last_run_dir = run_dir
                    self.progress.configure(value=100.0)
                    self.progress_pct.set("100%")
                    self._reset_rerender_button()
                    self._load_rerender_report(run_dir, quiet=True)
                    self._set_status("status_rerender_done")
                    messagebox.showinfo(
                        self._tr("dlg_done_title"),
                        self._tr("dlg_rerender_done_body", report=run_dir / START_REPORT_FILE),
                    )
                elif kind == "rerender_error":
                    self.rerender_running = False
                    self._reset_rerender_button()
                    err = event[1]
                    tb = event[2]
                    self._set_status("status_error", error=err)
                    messagebox.showerror(self._tr("dlg_error_title"), f"{err}\n\n{tb}")
                elif kind == "done":
                    run_dir = event[1]
                    old, new, out_dir, dpi, stroke_tol, workers = event[2], event[3], event[4], event[5], event[6], event[7]
                    diff_strictness = event[8]
                    self.last_run_dir = run_dir
                    self._hide_report_ready()
                    self._set_running(False)
                    self.progress.configure(value=100.0)
                    self.progress_pct.set("100%")
                    self._set_status("status_done", path=run_dir / START_REPORT_FILE)

                    # Calculate duration
                    duration_sec = time.monotonic() - self._run_started_monotonic
                    duration_str = self._format_duration(duration_sec)

                    # Get page counts from PDFs
                    pages_str = self._get_pages_str(old, new)

                    self._add_history_record(
                        {
                            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "result": "done",
                            "duration": duration_str,
                            "pages": pages_str,
                            "old_pdf": str(old),
                            "new_pdf": str(new),
                            "out_dir": str(out_dir),
                            "dpi": str(dpi),
                            "stroke_tol": str(stroke_tol),
                            "diff_strictness": str(diff_strictness),
                            "exclude_regions": self.exclude_regions.get().strip(),
                            "bbox_merge": self.bbox_merge.get().strip(),
                            "bbox_merge_gap": self.bbox_merge_gap.get().strip(),
                            "bbox_merge_max_ratio": self.bbox_merge_max_ratio.get().strip(),
                            "keep_debug": self.keep_debug.get().strip(),
                            "workers": str(workers),
                            "run_dir": str(run_dir),
                        }
                    )
                    self.run_name.set("")
                    self._save_state()
                    self._load_rerender_report(run_dir, quiet=True)
                    messagebox.showinfo(self._tr("dlg_done_title"), self._tr("dlg_done_body", run_dir=run_dir))
                elif kind == "cancelled":
                    old, new, out_dir, dpi, stroke_tol, workers = event[1], event[2], event[3], event[4], event[5], event[6]
                    diff_strictness = event[7] if len(event) > 7 else self.diff_strictness.get()
                    self._hide_report_ready()
                    self._set_running(False)
                    self.progress.configure(value=0.0)
                    self.progress_pct.set("0%")
                    self._set_status("status_cancelled")
                    self._add_history_record(
                        {
                            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "result": "cancelled",
                            "old_pdf": str(old),
                            "new_pdf": str(new),
                            "out_dir": str(out_dir),
                            "dpi": str(dpi),
                            "stroke_tol": str(stroke_tol),
                            "diff_strictness": str(diff_strictness),
                            "exclude_regions": self.exclude_regions.get().strip(),
                            "bbox_merge": self.bbox_merge.get().strip(),
                            "bbox_merge_gap": self.bbox_merge_gap.get().strip(),
                            "bbox_merge_max_ratio": self.bbox_merge_max_ratio.get().strip(),
                            "keep_debug": self.keep_debug.get().strip(),
                            "workers": str(workers),
                            "run_dir": "",
                        }
                    )
                elif kind == "error":
                    self._hide_report_ready()
                    self._set_running(False)
                    err = event[1]
                    tb = event[2]
                    old, new, out_dir, dpi, stroke_tol, workers = event[3], event[4], event[5], event[6], event[7], event[8]
                    diff_strictness = event[9] if len(event) > 9 else self.diff_strictness.get()
                    self._set_status("status_error", error=err)
                    self._add_history_record(
                        {
                            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "result": "error",
                            "old_pdf": str(old),
                            "new_pdf": str(new),
                            "out_dir": str(out_dir),
                            "dpi": str(dpi),
                            "stroke_tol": str(stroke_tol),
                            "diff_strictness": str(diff_strictness),
                            "exclude_regions": self.exclude_regions.get().strip(),
                            "bbox_merge": self.bbox_merge.get().strip(),
                            "bbox_merge_gap": self.bbox_merge_gap.get().strip(),
                            "bbox_merge_max_ratio": self.bbox_merge_max_ratio.get().strip(),
                            "keep_debug": self.keep_debug.get().strip(),
                            "workers": str(workers),
                            "run_dir": "",
                            "error": err,
                        }
                    )
                    messagebox.showerror(self._tr("dlg_error_title"), f"{err}\n\n{tb}")
                elif kind == "update_checked":
                    self._mark_update_checked()
                elif kind == "update_available":
                    version = str(event[1])
                    url = str(event[2])
                    name = str(event[3])
                    setup_url = str(event[4]) if len(event) > 4 else ""
                    sums_url = str(event[5]) if len(event) > 5 else ""
                    self._show_update_badge(version, url)
                    self._show_update_dialog(version, url, name, setup_url, sums_url)
                elif kind == "update_downloaded":
                    self._launch_update_installer(Path(str(event[1])))
                elif kind == "update_download_failed":
                    url = str(event[2]) if len(event) > 2 else ""
                    self._set_status("status_update_download_failed")
                    messagebox.showwarning(self._tr("dlg_update_title"), self._tr("dlg_update_download_failed"))
                    if url:
                        webbrowser.open(url)
                elif kind == "update_uptodate":
                    manual = len(event) > 1 and bool(event[1])
                    if manual:
                        messagebox.showinfo(
                            self._tr("dlg_update_title"),
                            self._tr("dlg_update_uptodate", version=APP_VERSION),
                        )
                elif kind == "update_failed":
                    manual = len(event) > 1 and bool(event[1])
                    if manual:
                        messagebox.showwarning(
                            self._tr("dlg_update_title"),
                            self._tr("dlg_update_check_failed"),
                        )
            has_more = not self.worker_events.empty()
        except queue.Empty:
            pass
        finally:
            self.root.after(20 if has_more else 150, self._poll_worker_events)

    def _start_update_check(self) -> None:
        if not self._should_check_for_updates():
            return
        threading.Thread(target=self._update_check_worker, args=(False,), daemon=True).start()

    def _check_for_updates_now(self) -> None:
        """Manual check triggered by the gear icon — bypasses the 24h gate."""
        threading.Thread(target=self._update_check_worker, args=(True,), daemon=True).start()

    def _update_check_worker(self, manual: bool) -> None:
        release = fetch_latest_release()
        # _mark_update_checked touches Tk variables via _save_state — hand it
        # to the UI thread instead of calling it from this worker.
        self.worker_events.put(("update_checked",))
        if release is None:
            if manual:
                self.worker_events.put(("update_failed", True))
            return
        tag = release.get("tag") or ""
        if is_newer(APP_VERSION, tag):
            self.worker_events.put((
                "update_available",
                tag,
                release.get("html_url") or "",
                release.get("name") or tag,
                release.get("setup_url") or "",
                release.get("sums_url") or "",
            ))
        elif manual:
            self.worker_events.put(("update_uptodate", True))

    def _show_update_badge(self, version: str, url: str) -> None:
        if self.update_badge is None:
            return
        self.update_badge.configure(text=f"★ {version}")
        self.update_badge.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))  # type: ignore[misc]
        self.update_badge.pack(side=tk.RIGHT, padx=(8, 6))

    def _show_update_dialog(self, version: str, url: str, name: str, setup_url: str = "", sums_url: str = "") -> None:
        skip_version = str(self.update_check_state.get("skip_version") or "")
        if skip_version == version:
            return  # user previously dismissed this exact version
        # In-place update only makes sense for the packaged exe, and only when
        # the release ships a checksum manifest to verify the download against;
        # running from source keeps the old "open the release page" flow.
        can_autoupdate = bool(setup_url) and bool(sums_url) and bool(getattr(sys, "frozen", False))
        if can_autoupdate:
            if messagebox.askyesno(self._tr("dlg_update_title"), self._tr("dlg_update_install_body", version=version)):
                self._download_update_installer(setup_url, sums_url, url, version)
                return
        else:
            body = self._tr("dlg_update_body", version=version)
            if messagebox.askyesno(self._tr("dlg_update_title"), body):
                webbrowser.open(url)
                return
        # Offer to skip this version so the dialog stops reappearing.
        if messagebox.askyesno(
            self._tr("dlg_update_title"),
            self._tr("dlg_update_skip_prompt", version=version),
        ):
            self._skip_update_version(version)

    def _download_update_installer(self, setup_url: str, sums_url: str, page_url: str, version: str) -> None:
        """Fetch the installer asset in the background; the poll loop launches it
        only after the SHA-256 from the release manifest matched."""
        self._set_status("status_update_downloading", version=version)

        def worker() -> None:
            import tempfile
            import urllib.request

            target = Path(tempfile.gettempdir()) / f"PDFCompareLocal-setup-{version}.exe"
            try:
                expected = parse_sha256sums(fetch_text(sums_url)).get(SETUP_ASSET_NAME, "")
                if not expected:
                    raise RuntimeError(f"В манифесте релиза нет хеша для {SETUP_ASSET_NAME}")
                req = urllib.request.Request(
                    setup_url,
                    headers={"User-Agent": f"PDFCompareLocal/{APP_VERSION}"},
                )
                with urllib.request.urlopen(req, timeout=120) as resp, open(target, "wb") as fh:  # noqa: S310
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        fh.write(chunk)
                actual = sha256_of_file(target)
                if actual != expected:
                    raise RuntimeError(f"SHA-256 инсталлятора не совпал: {actual} != {expected}")
                self.worker_events.put(("update_downloaded", str(target)))
            except Exception as exc:
                # Never launch an unverified download.
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
                self.worker_events.put(("update_download_failed", str(exc), page_url))

        threading.Thread(target=worker, daemon=True).start()

    def _launch_update_installer(self, setup_path: Path) -> None:
        """Run the downloaded installer silently and close the app so files can be replaced."""
        if not setup_path.exists():
            self._set_status("status_update_download_failed")
            return
        try:
            subprocess.Popen([str(setup_path), "/SILENT", "/NORESTART"], close_fds=True)
        except OSError as exc:
            messagebox.showerror(self._tr("dlg_update_title"), str(exc))
            return
        self._on_close()

    def _set_running(self, running: bool) -> None:
        self.running = running
        # run_btn is always created in _build_ui before _set_running can fire.
        assert self.run_btn is not None
        if running:
            self._hide_report_ready()
            self.progress.configure(value=0.0)
            self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
            self.progress_pct.set("0%")
            self.elapsed.set("00:00")
            self._run_started_monotonic = time.monotonic()
            self._start_timer()
            self._set_primary_state(self.run_btn, tk.NORMAL)
            self.run_btn.configure(command=self._request_cancel)
            self.run_btn.configure(text=self._tr("btn_cancel"))
        else:
            self._stop_timer()
            self.cancel_requested.clear()
            self.worker_thread = None
            self.progress.pack_forget()
            self.run_btn.configure(command=self.start_compare)
            self.run_btn.configure(text=self._tr("btn_compare_short"))
            self._update_run_availability()

    def _open_report(self) -> None:
        if not self.last_run_dir or not (self.last_run_dir / START_REPORT_FILE).exists():
            messagebox.showinfo(self._tr("dlg_info_title"), self._tr("status_no_report"))
            return
        report_html = self.last_run_dir / START_REPORT_FILE
        if not report_html.exists():
            legacy_html = self.last_run_dir / "report_bundle" / "index.html"
            if legacy_html.exists():
                report_html = legacy_html
        if report_html.exists():
            os.startfile(str(report_html))
        else:
            messagebox.showerror(self._tr("err_file_missing_title"), self._tr("err_not_found", path=report_html))

    def _open_run_folder(self) -> None:
        if not self.last_run_dir:
            # No run yet — fall back to the output folder from the field.
            out_text = self.out_dir.get().strip()
            if out_text and Path(out_text).is_dir():
                os.startfile(out_text)
                return
            messagebox.showinfo(self._tr("dlg_info_title"), self._tr("status_no_folder"))
            return
        if self.last_run_dir.exists():
            os.startfile(str(self.last_run_dir))
        else:
            messagebox.showerror(self._tr("err_folder_missing_title"), self._tr("err_not_found", path=self.last_run_dir))

    def _on_close(self) -> None:
        # A re-render is mid-transaction: give it a moment to unwind and restore
        # the run, instead of killing the daemon thread with the swap half-done.
        if self.running or self.rerender_running:
            self.cancel_requested.set()
            self.rerender_cancel_requested.set()
            self._set_status("status_cancel_requested")
            deadline = time.monotonic() + 3.0
            while True:
                workers = [t for t in (self.worker_thread, self.rerender_thread) if t is not None and t.is_alive()]
                if not workers:
                    break
                for worker in workers:
                    worker.join(timeout=0.05)
                if time.monotonic() >= deadline:
                    break
                try:
                    self.root.update_idletasks()
                except Exception:
                    break
        self._save_state()
        if self._drop_hook is not None:
            try:
                self._drop_hook.close()
            except Exception:
                pass
        self.root.destroy()


def main() -> None:
    # Use TkinterDnD if available for better drag & drop support
    root: tk.Tk | None = None
    if HAS_TKDND and TkinterDnD is not None:
        try:
            root = TkinterDnD.Tk()
        except Exception:
            # tkinterdnd2 imported but its tkdnd Tcl package failed to load
            # (broken install / missing binaries). Start without DnD instead
            # of crashing; _install_drop_hook will report it in the status bar.
            root = None
    if root is None:
        root = tk.Tk()

    # Use default Windows scaling/behavior but keep predictable font.
    try:
        style = ttk.Style(root)
        style.theme_use("vista")
    except Exception:
        pass
    PDFCompareApp(root)
    root.mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
