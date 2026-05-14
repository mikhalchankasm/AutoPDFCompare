"""History tab tree operations: refresh, selection, restore, save snapshot"""

from __future__ import annotations

import os
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from typing import Any
from .contracts import AppProtocol


class HistoryTabMixin:
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
        snap = self._capture_inputs()
        self._add_history_record(
            {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "result": "snapshot",
                "old_pdf": snap.get("old_pdf", ""),
                "new_pdf": snap.get("new_pdf", ""),
                "out_dir": snap.get("out_dir", ""),
                "dpi": snap.get("dpi", ""),
                "stroke_tol": snap.get("stroke_tol", ""),
                "workers": snap.get("workers", ""),
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

