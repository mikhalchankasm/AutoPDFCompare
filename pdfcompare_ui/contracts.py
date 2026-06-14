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
    workers: tk.StringVar
    status: tk.StringVar
    progress_pct: tk.StringVar
    elapsed: tk.StringVar
    history_search: tk.StringVar
    history_filter: tk.StringVar
    rerender_run_dir: tk.StringVar
    rerender_dpi: tk.StringVar
    rerender_workers: tk.StringVar

    # --- Runtime flags / worker plumbing -------------------------------- #
    running: bool
    rerender_running: bool
    cancel_requested: threading.Event
    worker_thread: threading.Thread | None
    worker_events: queue.Queue[tuple]
    last_run_dir: Path | None

    # --- Persistence ---------------------------------------------------- #
    state_dir: Path
    state_path: Path
    last_inputs: dict[str, Any]
    history_records: list[dict[str, Any]]
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

    # --- Methods that mixins call across boundaries -------------------- #
    # i18n & status
    def _tr(self, key: str, **kwargs: object) -> str: ...
    def _set_status(self, key: str, **kwargs: object) -> None: ...
    def _refresh_status_links(self) -> None: ...

    # Compare-tab refresh
    def _refresh_drop_badges(self) -> None: ...
    def _refresh_file_cards(self) -> None: ...
    def _refresh_option_values(self) -> None: ...
    def _update_history_filter_buttons(self) -> None: ...

    # History
    def _refresh_history_table(self) -> None: ...
    def _add_history_record(self, rec: dict[str, Any]) -> None: ...
    def _get_selected_history(self) -> dict[str, Any] | None: ...
    def _restore_selected_history(self) -> None: ...
    def _history_tab_text(self) -> str: ...

    # State persistence
    def _save_state(self) -> None: ...
    def _capture_inputs(self) -> dict[str, Any]: ...
    def _apply_inputs(self, data: dict[str, Any]) -> None: ...

    # Rerender
    def _load_current_rerender_report(self) -> None: ...
    def _load_rerender_report(self, run_dir: Path | None = ..., quiet: bool = ...) -> None: ...
    def _pick_rerender_run_dir(self) -> None: ...
    def _start_rerender_selected(self) -> None: ...
    def _rerender_worker(self, run_dir: Path, seqs: list[int], dpi: int, workers: int) -> None: ...

    # DnD — _install_drop_hook wires these via self.X; tkinterdnd2 returns event.action
    def _handle_dropped_files(self, paths: Any) -> None: ...
    def _on_tkdnd_drop(self, event: Any) -> Any: ...
    def _on_tkdnd_drop_old(self, event: Any) -> Any: ...
    def _on_tkdnd_drop_new(self, event: Any) -> Any: ...
    def _on_tkdnd_drop_out(self, event: Any) -> Any: ...

    # Misc UI helpers used by mixins
    def _open_report(self) -> None: ...
    def _primary_button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        compact: bool = ...,
    ) -> tk.Button: ...
