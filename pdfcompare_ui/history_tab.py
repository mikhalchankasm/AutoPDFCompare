"""History tab tree operations: refresh, selection, restore, save snapshot"""

from __future__ import annotations

import os
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any
from .contracts import AppProtocol
from .styles import (
    BG_CARD,
    BG_SOFT,
    BG_WINDOW,
    BORDER_STRONG,
    PILL_CANCEL_BG,
    PILL_CANCEL_TEXT,
    PILL_OK_BG,
    PILL_OK_TEXT,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)


class HistoryTabMixin:
    history_tree: ttk.Treeview
    hist_open_btn: ttk.Button | None
    hist_refresh_btn: ttk.Button | None
    hist_restore_btn: tk.Button | None
    hist_snapshot_btn: ttk.Button | None
    history_hint_label: ttk.Label | None
    history_records: list[dict[str, Any]]
    history_search_entry: ttk.Entry | None

    def _build_history_tab(self: AppProtocol) -> None:
        """Search/filter toolbar, the runs table and the footer actions."""
        hist_tools = tk.Frame(self.history_tab, bg=BG_WINDOW, padx=14, pady=14)
        hist_tools.pack(fill=tk.X)
        search_frame = tk.Frame(hist_tools, bg=BG_SOFT, padx=10, pady=5)
        search_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(search_frame, text="⌕", bg=BG_SOFT, fg=TEXT_TERTIARY).pack(side=tk.LEFT)
        self.history_search_entry = ttk.Entry(search_frame, textvariable=self.history_search, style="Path.TEntry")
        self.history_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        self._set_history_placeholder()
        self.history_search_entry.bind("<FocusIn>", self._history_search_focus_in)
        self.history_search_entry.bind("<FocusOut>", self._history_search_focus_out)
        for value, key in (("all", "hist_filter_all"), ("done", "hist_filter_done"), ("cancelled", "hist_filter_cancelled")):
            btn = tk.Label(
                hist_tools, text=self._tr(key), padx=13, pady=6, bg=BG_CARD, fg=TEXT_SECONDARY,
                relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER_STRONG,
                font=("Segoe UI", 9, "bold"), cursor="hand2",
            )
            btn.pack(side=tk.LEFT, padx=(8, 0))
            btn.bind("<Button-1>", lambda _e, v=value: self._set_history_filter(v))  # type: ignore[misc]
            self.history_filter_buttons[value] = btn
        self.hist_refresh_btn = ttk.Button(hist_tools, text=f"↻ {self._tr('hist_refresh')}", style="Small.TButton", command=self._refresh_history_table)
        self.hist_refresh_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Create container for table and scrollbar
        tree_container = ttk.Frame(self.history_tab)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ("ts", "duration", "pages", "result", "old", "new", "out", "run")
        self.history_tree = ttk.Treeview(tree_container, columns=cols, show="headings", selectmode="browse", style="History.Treeview")
        self.history_tree.configure(displaycolumns=("ts", "duration", "pages", "result", "old", "new", "out"))
        self.history_tree.heading("ts", text=self._tr("hist_col_time"))
        self.history_tree.heading("duration", text=self._tr("hist_col_duration"))
        self.history_tree.heading("pages", text=self._tr("hist_col_pages"))
        self.history_tree.heading("result", text=self._tr("hist_col_result"))
        self.history_tree.heading("old", text=self._tr("hist_col_old"))
        self.history_tree.heading("new", text=self._tr("hist_col_new"))
        self.history_tree.heading("out", text=self._tr("hist_col_out"))
        self.history_tree.heading("run", text=self._tr("hist_col_run"))
        # All columns stretch proportionally
        self.history_tree.column("ts", width=140, minwidth=120, anchor="w", stretch=True)
        self.history_tree.column("duration", width=60, minwidth=50, anchor="center", stretch=True)
        self.history_tree.column("pages", width=70, minwidth=60, anchor="center", stretch=True)
        self.history_tree.column("result", width=80, minwidth=70, anchor="center", stretch=True)
        self.history_tree.column("old", width=150, minwidth=120, anchor="w", stretch=True)
        self.history_tree.column("new", width=150, minwidth=120, anchor="w", stretch=True)
        self.history_tree.column("out", width=120, minwidth=100, anchor="w", stretch=True)
        self.history_tree.column("run", width=200, minwidth=150, anchor="w", stretch=True)
        self.history_tree.tag_configure("pill_ok", background=PILL_OK_BG, foreground=PILL_OK_TEXT)
        self.history_tree.tag_configure("pill_cancel", background=PILL_CANCEL_BG, foreground=PILL_CANCEL_TEXT)

        hist_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.history_tree.yview)
        hist_scroll.pack(fill=tk.Y, side=tk.RIGHT)
        self.history_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        self.history_tree.configure(yscrollcommand=hist_scroll.set)
        self.history_tree.bind("<Double-1>", self._on_history_double_click)

        hist_footer = tk.Frame(self.history_tab, bg=BG_SOFT, padx=24, pady=12)
        hist_footer.pack(fill=tk.X)
        self.history_hint_label = ttk.Label(hist_footer, text=self._tr("hist_hint"), style="Hint.TLabel", background=BG_SOFT)
        self.history_hint_label.pack(side=tk.LEFT)
        self.hist_restore_btn = self._primary_button(hist_footer, self._tr("hist_restore"), self._restore_selected_history, compact=True)
        self.hist_restore_btn.pack(side=tk.RIGHT)
        self.hist_snapshot_btn = ttk.Button(hist_footer, text=self._tr("hist_snapshot"), style="Small.TButton", command=self._save_snapshot_to_history)
        self.hist_snapshot_btn.pack(side=tk.RIGHT, padx=8)
        self.hist_open_btn = ttk.Button(hist_footer, text=self._tr("hist_open_folder"), style="Small.TButton", command=self._open_selected_history_run)
        self.hist_open_btn.pack(side=tk.RIGHT)


    def _refresh_history_table(self: AppProtocol) -> None:
        if self.history_tree is None:
            return
        self._history_by_iid.clear()
        for iid in self.history_tree.get_children():
            self.history_tree.delete(iid)

        query = self.history_search.get().strip().lower()
        if query == self._tr("history_search_placeholder").lower():
            query = ""
        status_filter = self.history_filter.get()
        for rec_idx in range(len(self.history_records) - 1, -1, -1):
            rec = self.history_records[rec_idx]
            iid = str(rec_idx)
            raw_result = str(rec.get("result") or "").upper()
            if status_filter == "done" and raw_result not in {"DONE", "OK"}:
                continue
            if status_filter == "cancelled" and raw_result != "CANCELLED":
                continue
            searchable = " ".join(str(rec.get(k) or "") for k in ("old_pdf", "new_pdf", "out_dir", "run_dir")).lower()
            if query and query not in searchable:
                continue
            result = raw_result
            tag = ""
            if result == "DONE":
                result = self._tr("hist_result_done")
                tag = "pill_ok"
            elif result == "ERROR":
                result = self._tr("hist_result_error")
            elif result == "SNAPSHOT":
                result = self._tr("hist_result_snapshot")
            elif result == "CANCELLED":
                result = self._tr("hist_result_cancelled")
                tag = "pill_cancel"
            else:
                result = self._tr("hist_result_done") if result == "OK" else result
                tag = "pill_ok" if raw_result == "OK" else ""
            old_name = Path(str(rec.get("old_pdf") or "")).name
            new_name = Path(str(rec.get("new_pdf") or "")).name
            out_name = Path(str(rec.get("out_dir") or "")).name
            duration = rec.get("duration", "")
            pages = rec.get("pages", "")
            self.history_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    rec.get("ts", ""),
                    duration,
                    pages,
                    result,
                    old_name,
                    new_name,
                    out_name,
                    rec.get("run_dir", ""),
                ),
                tags=(tag,) if tag else (),
            )
            self._history_by_iid[iid] = rec
        if self.tabs is not None:
            self.tabs.tab(1, text=self._history_tab_text())
        self._update_history_filter_buttons()

    def _get_selected_history(self: AppProtocol) -> dict[str, Any] | None:
        selected = self.history_tree.selection()
        if not selected:
            return None
        return self._history_by_iid.get(selected[0])

    def _restore_selected_history(self: AppProtocol) -> None:
        rec = self._get_selected_history()
        if not rec:
            self._set_status("status_select_history_first")
            return
        data = dict(rec)
        data["last_run_dir"] = rec.get("run_dir", "")
        self._apply_inputs(data)
        old_ok = Path(self.old_pdf.get()).exists() if self.old_pdf.get() else False
        new_ok = Path(self.new_pdf.get()).exists() if self.new_pdf.get() else False
        msg = self._tr("status_history_restored")
        if not old_ok or not new_ok:
            msg += f" {self._tr('status_history_missing_files')}"
        self.status.set(msg)

    def _open_selected_history_run(self: AppProtocol) -> None:
        rec = self._get_selected_history()
        if not rec:
            self._set_status("status_select_history_first")
            return
        run_dir = str(rec.get("run_dir") or "").strip()
        if not run_dir:
            self._set_status("status_history_no_run")
            return
        p = Path(run_dir)
        if p.exists():
            os.startfile(str(p))
        else:
            messagebox.showerror(self._tr("err_folder_missing_title"), self._tr("err_not_found", path=p))

    def _on_history_double_click(self: AppProtocol, event: tk.Event) -> None:
        self._restore_selected_history()

    def _save_snapshot_to_history(self: AppProtocol) -> None:
        # Store the full input capture: restoring a snapshot must bring back
        # every option (strictness, exclusion zones, bbox merge, debug flag),
        # not just the file paths.
        snap = self._capture_inputs()
        snap.pop("last_run_dir", None)
        self._add_history_record(
            {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "result": "snapshot",
                **snap,
                "run_dir": "",
            }
        )
        self._set_status("status_snapshot_saved")

    def _add_history_record(self: AppProtocol, rec: dict[str, Any]) -> None:
        self.history_records.append(rec)
        if len(self.history_records) > 300:
            self.history_records = self.history_records[-300:]
        self._refresh_history_table()
        self._save_state()

