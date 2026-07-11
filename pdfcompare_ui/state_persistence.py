"""Persist the GUI's input fields and history to ~/.pdfcompare_local/state.json"""

from __future__ import annotations

import json
import os
import tkinter as tk
from pathlib import Path
from typing import Any

from .i18n import I18N
from .contracts import AppProtocol


class StatePersistenceMixin:
    # Class-level annotation: mypy would otherwise infer "None" from
    # `self.last_run_dir = None` below, conflicting with PDFCompareApp's init.
    last_run_dir: Path | None
    last_inputs: dict[str, Any]
    history_records: list[dict[str, Any]]

    def _capture_inputs(self: AppProtocol) -> dict[str, Any]:
        return {
            "old_pdf": self.old_pdf.get().strip(),
            "new_pdf": self.new_pdf.get().strip(),
            "out_dir": self.out_dir.get().strip(),
            "run_name": self.run_name.get().strip(),
            "dpi": self.dpi.get().strip(),
            "stroke_tol": self.stroke_tol.get().strip(),
            "diff_strictness": self.diff_strictness.get().strip(),
            "exclude_regions": self.exclude_regions.get().strip(),
            "workers": self.workers.get().strip(),
            "bbox_merge": self.bbox_merge.get().strip(),
            "bbox_merge_gap": self.bbox_merge_gap.get().strip(),
            "bbox_merge_max_ratio": self.bbox_merge_max_ratio.get().strip(),
            "keep_debug": self.keep_debug.get().strip(),
            "last_run_dir": str(self.last_run_dir) if self.last_run_dir else "",
        }

    def _apply_inputs(self: AppProtocol, data: dict[str, Any]) -> None:
        self.old_pdf.set(str(data.get("old_pdf") or ""))
        self.new_pdf.set(str(data.get("new_pdf") or ""))
        self.out_dir.set(str(data.get("out_dir") or ""))
        self.run_name.set(str(data.get("run_name") or ""))
        self.dpi.set(str(data.get("dpi") or "250"))
        self.stroke_tol.set(str(data.get("stroke_tol") or "2.0"))
        self.diff_strictness.set(str(data.get("diff_strictness") or "normal"))
        self.exclude_regions.set(str(data.get("exclude_regions") or ""))
        self.workers.set(str(data.get("workers") or "0"))
        self.bbox_merge.set(str(data.get("bbox_merge") or "off"))
        self.bbox_merge_gap.set(str(data.get("bbox_merge_gap") or "5"))
        self.bbox_merge_max_ratio.set(str(data.get("bbox_merge_max_ratio") or "16"))
        self.keep_debug.set(str(data.get("keep_debug") or "off"))
        if self.open_report_btn is not None:
            self.open_report_btn.configure(state=tk.DISABLED)
        if self.open_run_btn is not None:
            self.open_run_btn.configure(state=tk.DISABLED)
        self.last_run_dir = None
        run_dir = str(data.get("last_run_dir") or "").strip()
        if run_dir:
            self.last_run_dir = Path(run_dir)
            self.rerender_run_dir.set(str(self.last_run_dir))
            if self.last_run_dir.exists():
                if self.open_report_btn is not None:
                    self.open_report_btn.configure(state=tk.NORMAL)
                if self.open_run_btn is not None:
                    self.open_run_btn.configure(state=tk.NORMAL)
        self.last_inputs = self._capture_inputs()
        self._refresh_drop_badges()
        self._refresh_file_cards()
        self._refresh_option_values()
        self._refresh_status_links()

    def _load_state(self: AppProtocol) -> None:
        try:
            if not self.state_path.exists():
                return
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                last_inputs = data.get("last_inputs")
                history = data.get("history")
                lang = str(data.get("language") or "").strip().lower()
                if lang in I18N:
                    self.lang.set(lang)
                if isinstance(last_inputs, dict):
                    self.last_inputs = last_inputs
                if isinstance(history, list):
                    self.history_records = [h for h in history if isinstance(h, dict)][-300:]
        except Exception:
            self.last_inputs = {}
            self.history_records = []

    def _save_state(self: AppProtocol) -> None:
        # State persistence is a UX feature; it must never crash the app.
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "language": self.lang.get(),
                "last_inputs": self._capture_inputs(),
                "history": self.history_records[-300:],
            }
            tmp_path = self.state_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp_path, self.state_path)
        except Exception:
            pass

    def _restore_last_inputs(self: AppProtocol, startup: bool = False) -> None:
        if not self.last_inputs:
            if not startup:
                self._set_status("status_no_saved")
            return
        self._apply_inputs(self.last_inputs)
        if startup:
            self._set_status("status_restored_startup")
        else:
            self._set_status("status_restored")

