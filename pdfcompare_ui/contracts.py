"""Typing contract describing PDFCompareApp's shape, used by mixins.

The mixin modules (rerender_tab, history_tab, dnd, state_persistence) hold
methods that read/write attributes only defined on the concrete
PDFCompareApp class. To keep mypy happy without a circular import, each
mixin method annotates `self: AppProtocol` so attribute lookups resolve
against this Protocol instead of the bare mixin class.

This file is type-only (no runtime imports beyond `Protocol`). Add an
entry here whenever a mixin starts touching a new app-level attribute or
method.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk
from typing import Any, Protocol


class AppProtocol(Protocol):
    """Structural contract for PDFCompareApp from a mixin's point of view."""

    # --- Tk root + tabs ------------------------------------------------- #
    root: tk.Tk
    tabs: ttk.Notebook | None
    compare_tab: ttk.Frame | None
    history_tab: ttk.Frame | None
    rerender_tab: ttk.Frame | None

    # --- Tk state vars (input fields, options, status, progress) -------- #
    lang: tk.StringVar
    old_pdf: tk.StringVar
    new_pdf: tk.StringVar
    out_dir: tk.StringVar
    run_name: tk.StringVar
    dpi: tk.StringVar
    stroke_tol: tk.StringVar
    diff_strictness: tk.StringVar
    exclude_regions: tk.StringVar
    bbox_merge: tk.StringVar
    bbox_merge_gap: tk.StringVar
    bbox_merge_max_ratio: tk.StringVar
    keep_debug: tk.StringVar
    status: tk.StringVar
    progress_pct: tk.StringVar
    elapsed: tk.StringVar
    history_search: tk.StringVar
    history_filter: tk.StringVar
    rerender_run_dir: tk.StringVar
    rerender_dpi: tk.StringVar
    rerender_workers: tk.StringVar
    rerender_stroke_tol: tk.StringVar
    rerender_strictness: tk.StringVar
    rerender_exclude: tk.StringVar
    rerender_bbox_merge: tk.StringVar
    rerender_bbox_gap: tk.StringVar
    rerender_mode: tk.StringVar
    rerender_page_settings: dict[int, dict[str, Any]]
    rerender_source_pdf: Path | None

    # --- Runtime flags / worker plumbing -------------------------------- #
    running: bool
    rerender_running: bool
    cancel_requested: threading.Event
    rerender_cancel_requested: threading.Event
    worker_thread: threading.Thread | None
    rerender_thread: threading.Thread | None
    worker_events: queue.Queue[tuple]
    last_run_dir: Path | None

    # --- Persistence ---------------------------------------------------- #
    state_dir: Path
    state_path: Path
    last_inputs: dict[str, Any]
    history_records: list[dict[str, Any]]
    update_check_state: dict[str, Any]
    _history_by_iid: dict[str, dict[str, Any]]
    rerender_by_iid: dict[str, dict[str, Any]]
    _drop_hook: Any | None

    # --- Compare-tab widgets (created lazily in _build_ui) -------------- #
    # drop_canvas is a tk.Frame styled as a drop zone (not an actual Canvas).
    drop_canvas: tk.Frame | None
    # old_entry/new_entry are file-card Frames returned by _build_file_card,
    # despite the name. Only out_entry is a real ttk.Entry.
    old_entry: tk.Frame | None
    new_entry: tk.Frame | None
    out_entry: ttk.Entry | None
    progress: ttk.Progressbar
    run_btn: tk.Button | None
    open_report_btn: ttk.Button | None
    open_run_btn: ttk.Button | None
    report_ready_label: tk.Label | None
    bbox_merge_chip: ttk.Checkbutton | None
    bbox_merge_gap_entry: ttk.Entry | None
    bbox_merge_max_ratio_entry: ttk.Entry | None
    keep_debug_chip: ttk.Checkbutton | None
    exclude_pick_btn: ttk.Button | None
    update_badge: tk.Label | None

    # --- Widgets the compare/history tab builders create ----------------- #
    clear_btn: ttk.Button | None
    from_history_btn: ttk.Button | None
    swap_btn: ttk.Button | None
    run_name_entry: ttk.Entry
    run_name_label: ttk.Label | None
    run_name_hint_label: ttk.Label | None
    out_label: ttk.Label | None
    out_pick_btn: ttk.Button | None
    status_text_label: tk.Label | None
    options_body: tk.Frame | None
    options_strictness_label: ttk.Label | None
    options_strictness_hint_label: ttk.Label | None
    options_exclude_label: ttk.Label | None
    options_exclude_hint_label: ttk.Label | None
    options_bbox_merge_label: ttk.Label | None
    options_bbox_merge_hint_label: ttk.Label | None
    options_keep_debug_label: ttk.Label | None
    options_keep_debug_hint_label: ttk.Label | None
    strictness_chips: dict[str, tk.Label]
    dpi_value: tk.StringVar
    stroke_value: tk.StringVar
    hist_open_btn: ttk.Button | None
    hist_refresh_btn: ttk.Button | None
    hist_restore_btn: tk.Button | None
    hist_snapshot_btn: ttk.Button | None
    history_hint_label: ttk.Label | None
    history_search_entry: ttk.Entry | None
    check_updates_btn: tk.Label | None
    help_btn: tk.Label | None

    # --- History-tab widgets ------------------------------------------- #
    history_tree: ttk.Treeview
    history_filter_buttons: dict[str, tk.Label]

    # --- Rerender-tab widgets ------------------------------------------ #
    rerender_tree: ttk.Treeview | None
    rerender_title_label: ttk.Label | None
    rerender_hint_label: ttk.Label | None
    rerender_run_label: ttk.Label | None
    rerender_load_current_btn: ttk.Button | None
    rerender_pick_btn: ttk.Button | None
    rerender_reload_btn: ttk.Button | None
    rerender_dpi_label: ttk.Label | None
    rerender_workers_label: ttk.Label | None
    rerender_start_btn: tk.Button | None  # _primary_button returns tk.Button
    rerender_open_report_btn: ttk.Button | None
    rerender_mode_chips: dict[str, tk.Label]
    rerender_strictness_chips: dict[str, tk.Label]
    rerender_edit_selected_btn: ttk.Button | None
    rerender_exclude_pick_btn: ttk.Button | None

    # --- Methods that mixins call across boundaries -------------------- #
    # i18n & status
    def _tr(self, key: str, **kwargs: object) -> str: ...
    def _set_status(self, key: str, **kwargs: object) -> None: ...
    def _show_report_ready(self) -> None: ...
    def _hide_report_ready(self) -> None: ...

    # Compare-tab refresh
    def _refresh_drop_badges(self) -> None: ...
    def _refresh_file_cards(self) -> None: ...
    def _refresh_option_values(self) -> None: ...
    def _update_bbox_merge_fields(self) -> None: ...
    def _update_history_filter_buttons(self) -> None: ...

    # History
    def _refresh_history_table(self) -> None: ...
    def _add_history_record(self, rec: dict[str, Any]) -> None: ...
    def _get_selected_history(self) -> dict[str, Any] | None: ...
    def _restore_selected_history(self) -> None: ...
    def _history_tab_text(self) -> str: ...

    def _on_history_double_click(self, event: tk.Event) -> None: ...
    def _open_selected_history_run(self) -> None: ...
    def _save_snapshot_to_history(self) -> None: ...
    def _set_history_filter(self, value: str) -> None: ...
    def _set_history_placeholder(self) -> None: ...
    def _history_search_focus_in(self, _event: tk.Event) -> None: ...
    def _history_search_focus_out(self, _event: tk.Event) -> None: ...

    # Compare tab actions
    def start_compare(self) -> None: ...
    def _clear_inputs(self) -> None: ...
    def _swap_files(self) -> None: ...
    def _pick_out_dir(self) -> None: ...
    def _pick_exclude_regions(self) -> None: ...
    def _open_run_folder(self) -> None: ...
    def _build_file_card(self, parent: tk.Frame, var: tk.StringVar, old: bool) -> tk.Frame: ...
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
    ) -> None: ...

    # State persistence
    def _save_state(self) -> None: ...
    def _capture_inputs(self) -> dict[str, Any]: ...
    def _apply_inputs(self, data: dict[str, Any]) -> None: ...
    def _restore_last_inputs(self, startup: bool = ...) -> None: ...

    # Update check
    def _should_check_for_updates(self) -> bool: ...
    def _mark_update_checked(self) -> None: ...
    def _skip_update_version(self, version: str) -> None: ...
    def _default_update_check_state(self) -> dict[str, Any]: ...
    def _start_update_check(self) -> None: ...
    def _check_for_updates_now(self) -> None: ...
    def _show_update_badge(self, version: str, url: str) -> None: ...
    def _show_update_dialog(self, version: str, url: str, name: str, setup_url: str = ..., sums_url: str = ...) -> None: ...

    # Rerender
    def _load_current_rerender_report(self) -> None: ...
    def _load_rerender_report(self, run_dir: Path | None = ..., quiet: bool = ...) -> None: ...
    def _pick_rerender_run_dir(self) -> None: ...
    def _start_rerender_selected(self) -> None: ...
    def _pick_rerender_exclude_regions(self) -> None: ...
    def _rerender_worker(self, run_dir: Path, seqs: list[int], dpi: int, workers: int, overrides: dict[str, Any], report_lang: str) -> None: ...
    def _rerender_mixed_worker(self, run_dir: Path, page_settings: list[dict[str, Any]], dpi: int, workers: int, report_lang: str) -> None: ...
    def _edit_selected_page_settings(self) -> None: ...
    def _parse_optional_float(self, var: tk.StringVar) -> float | None: ...
    def _collect_uniform_overrides(self) -> dict[str, Any] | None: ...
    def _collect_uniform_overrides_safe(self) -> dict[str, Any]: ...
    def _build_page_settings(self, seqs: list[int]) -> list[dict[str, Any]]: ...
    def _begin_rerender_run(self) -> None: ...
    def _update_rerender_mode_chips(self) -> None: ...
    def _update_rerender_strictness_chips(self) -> None: ...

    # DnD — _install_drop_hook wires these via self.X; tkinterdnd2 returns event.action
    def _handle_dropped_files(self, paths: Any) -> None: ...
    def _on_tkdnd_drop(self, event: Any) -> Any: ...
    def _on_tkdnd_drop_old(self, event: Any) -> Any: ...
    def _on_tkdnd_drop_new(self, event: Any) -> Any: ...
    def _on_tkdnd_drop_out(self, event: Any) -> Any: ...

    # Misc UI helpers used by mixins
    def _open_report(self) -> None: ...
    def _set_primary_state(self, button: tk.Button, state: str) -> None: ...
    def _reset_rerender_button(self) -> None: ...
    def _request_rerender_cancel(self) -> None: ...
    def _primary_button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        compact: bool = ...,
    ) -> tk.Button: ...
