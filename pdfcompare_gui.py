from __future__ import annotations

import ctypes
import json
import os
import queue
import threading
import traceback
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Iterable

from compare_pdfs import compare_pdfs


class WindowsDropHook:
    """Enable Explorer drag-and-drop into a Tk window on Windows."""

    GWL_WNDPROC = -4
    WM_DROPFILES = 0x0233
    UINT_MAX = 0xFFFFFFFF

    def __init__(self, widget: tk.Misc, on_drop: Callable[[list[Path]], None]) -> None:
        if os.name != "nt":
            raise RuntimeError("Перетаскивание поддерживается только в Windows.")

        self.widget = widget
        self.on_drop = on_drop
        self.hwnd = widget.winfo_id()
        self._active = False

        self._user32 = ctypes.windll.user32
        self._shell32 = ctypes.windll.shell32

        if ctypes.sizeof(ctypes.c_void_p) == 8:
            self._long_ptr_t = ctypes.c_longlong
            self._get_wndproc = self._user32.GetWindowLongPtrW
            self._set_wndproc = self._user32.SetWindowLongPtrW
        else:
            self._long_ptr_t = ctypes.c_long
            self._get_wndproc = self._user32.GetWindowLongW
            self._set_wndproc = self._user32.SetWindowLongW

        self._wndproc_type = ctypes.WINFUNCTYPE(
            self._long_ptr_t,
            ctypes.wintypes.HWND,
            ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM,
            ctypes.wintypes.LPARAM,
        )

        self._call_wndproc = self._user32.CallWindowProcW
        self._call_wndproc.argtypes = [
            self._long_ptr_t,
            ctypes.wintypes.HWND,
            ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM,
            ctypes.wintypes.LPARAM,
        ]
        self._call_wndproc.restype = self._long_ptr_t

        self._shell32.DragQueryFileW.argtypes = [
            ctypes.wintypes.HANDLE,
            ctypes.wintypes.UINT,
            ctypes.wintypes.LPWSTR,
            ctypes.wintypes.UINT,
        ]
        self._shell32.DragQueryFileW.restype = ctypes.wintypes.UINT

        self._shell32.DragAcceptFiles.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.BOOL]
        self._shell32.DragAcceptFiles.restype = None

        self._shell32.DragFinish.argtypes = [ctypes.wintypes.HANDLE]
        self._shell32.DragFinish.restype = None

        self._old_wndproc = self._get_wndproc(self.hwnd, self.GWL_WNDPROC)
        self._new_wndproc = self._wndproc_type(self._wndproc)
        self._set_wndproc(self.hwnd, self.GWL_WNDPROC, ctypes.cast(self._new_wndproc, ctypes.c_void_p).value)
        self._shell32.DragAcceptFiles(self.hwnd, True)
        self._active = True

    def close(self) -> None:
        if not self._active:
            return
        self._shell32.DragAcceptFiles(self.hwnd, False)
        self._set_wndproc(self.hwnd, self.GWL_WNDPROC, self._old_wndproc)
        self._active = False

    def _wndproc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == self.WM_DROPFILES:
            hdrop = wparam
            count = self._shell32.DragQueryFileW(hdrop, self.UINT_MAX, None, 0)
            paths: list[Path] = []
            for idx in range(count):
                buf_len = self._shell32.DragQueryFileW(hdrop, idx, None, 0) + 1
                buf = ctypes.create_unicode_buffer(buf_len)
                self._shell32.DragQueryFileW(hdrop, idx, buf, buf_len)
                p = Path(buf.value)
                if p.exists():
                    paths.append(p)
            self._shell32.DragFinish(hdrop)
            if paths:
                self.widget.after(0, lambda: self.on_drop(paths))
            return 0

        return self._call_wndproc(self._old_wndproc, hwnd, msg, wparam, lparam)


class PDFCompareApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PDFCompare Local")
        self.root.geometry("900x580")
        self.root.minsize(800, 500)

        self.old_pdf = tk.StringVar()
        self.new_pdf = tk.StringVar()
        self.out_dir = tk.StringVar()
        self.dpi = tk.StringVar(value="250")
        self.stroke_tol = tk.StringVar(value="2.0")
        self.status = tk.StringVar(value="Перетащите 2 PDF-файла и нажмите Enter для запуска.")
        self.progress_pct = tk.StringVar(value="0%")
        self.drop_badges_var = tk.StringVar(value="")
        self.options_expanded = False

        self.worker_events: queue.Queue[tuple] = queue.Queue()
        self.running = False
        self.last_run_dir: Path | None = None
        self._drop_hook: WindowsDropHook | None = None
        self._history_by_iid: dict[str, dict[str, Any]] = {}
        self.run_btn: ttk.Button | None = None
        self.open_report_btn: ttk.Button | None = None
        self.open_run_btn: ttk.Button | None = None
        self.options_body: ttk.Frame | None = None
        self.options_toggle_btn: ttk.Button | None = None
        self.drop_canvas: tk.Canvas | None = None

        self.state_dir = Path.home() / ".pdfcompare_local"
        self.state_path = self.state_dir / "state.json"
        self.last_inputs: dict[str, Any] = {}
        self.history_records: list[dict[str, Any]] = []
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

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("SubHeader.TLabel", font=("Segoe UI", 11))
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"))
        style.configure("Small.TButton", font=("Segoe UI", 10))
        style.configure("Hint.TLabel", font=("Segoe UI", 9), foreground="#4b5872")

        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(outer)
        top.pack(fill=tk.X)
        top_left = ttk.Frame(top)
        top_left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(top_left, text="PDFCompare Local", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            top_left,
            text="Локальное сравнение PDF · без облака",
            style="SubHeader.TLabel",
            foreground="#5f6d86",
        ).pack(anchor="w", pady=(1, 8))
        ttk.Button(top, text="⚙", style="Small.TButton", state=tk.DISABLED).pack(side=tk.RIGHT, padx=(8, 0))

        tabs = ttk.Notebook(outer)
        tabs.pack(fill=tk.BOTH, expand=True)
        compare_tab = ttk.Frame(tabs, padding=8)
        history_tab = ttk.Frame(tabs, padding=8)
        tabs.add(compare_tab, text="Сравнение")
        tabs.add(history_tab, text="История")

        self.drop_canvas = tk.Canvas(compare_tab, height=145, bg="#F0F4F8", highlightthickness=0)
        self.drop_canvas.pack(fill=tk.X, pady=(0, 8))
        self.drop_canvas.bind("<Configure>", lambda _e: self._draw_drop_zone())
        self._draw_drop_zone()

        ttk.Label(compare_tab, textvariable=self.drop_badges_var, style="Hint.TLabel").pack(anchor="w", pady=(0, 8))

        self._path_row(compare_tab, "● Старый PDF", self.old_pdf, self._pick_old_pdf)
        self._path_row(compare_tab, "● Новый PDF", self.new_pdf, self._pick_new_pdf)
        self._path_row(compare_tab, "Папка вывода", self.out_dir, self._pick_out_dir)

        options_wrap = ttk.Frame(compare_tab)
        options_wrap.pack(fill=tk.X, pady=(6, 6))
        self.options_toggle_btn = ttk.Button(
            options_wrap, text="Параметры ▾", style="Small.TButton", command=self._toggle_options
        )
        self.options_toggle_btn.pack(anchor="center", pady=(0, 4))

        self.options_body = ttk.LabelFrame(options_wrap, text="Параметры сравнения", padding=10)
        self.options_body.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(self.options_body, text="Разрешение (DPI):").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(self.options_body, from_=120, to=600, textvariable=self.dpi, width=8).grid(
            row=0, column=1, sticky="w", padx=(6, 16)
        )
        ttk.Label(self.options_body, text="Выше = точнее, но медленнее", style="Hint.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 8)
        )
        ttk.Label(self.options_body, text="Допуск штриха (px):").grid(row=0, column=2, sticky="w")
        ttk.Entry(self.options_body, textvariable=self.stroke_tol, width=8).grid(
            row=0, column=3, sticky="w", padx=(6, 0)
        )
        ttk.Label(
            self.options_body,
            text="Игнорирует различия тоньше указанного размера",
            style="Hint.TLabel",
        ).grid(row=1, column=2, columnspan=2, sticky="w", pady=(2, 8))
        self.options_body.columnconfigure(4, weight=1)
        self.options_body.pack_forget()

        actions = ttk.Frame(compare_tab)
        actions.pack(fill=tk.X, pady=(2, 2))
        self.run_btn = ttk.Button(actions, text="Сравнить (Enter)", style="Primary.TButton", command=self.start_compare)
        self.run_btn.pack(fill=tk.X, ipady=7)

        secondary = ttk.Frame(compare_tab)
        secondary.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(secondary, text="Очистить", style="Small.TButton", command=self._clear_inputs).pack(side=tk.LEFT)
        ttk.Button(secondary, text="Из истории", style="Small.TButton", command=self._restore_last_inputs).pack(side=tk.LEFT, padx=8)
        self.open_report_btn = ttk.Button(
            secondary, text="Открыть отчёт", style="Small.TButton", command=self._open_report, state=tk.DISABLED
        )
        self.open_report_btn.pack(side=tk.RIGHT)
        self.open_run_btn = ttk.Button(
            secondary, text="Открыть папку", style="Small.TButton", command=self._open_run_folder, state=tk.DISABLED
        )
        self.open_run_btn.pack(side=tk.RIGHT, padx=(0, 8))

        progress_row = ttk.Frame(compare_tab)
        progress_row.pack(fill=tk.X, pady=(10, 5))
        self.progress = ttk.Progressbar(progress_row, mode="determinate", maximum=100)
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(progress_row, textvariable=self.progress_pct, width=6, anchor="e").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(compare_tab, textvariable=self.status, style="Hint.TLabel", wraplength=860).pack(anchor="w")

        hist_tools = ttk.Frame(history_tab)
        hist_tools.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(hist_tools, text="Восстановить", style="Small.TButton", command=self._restore_selected_history).pack(side=tk.LEFT)
        ttk.Button(hist_tools, text="Сохранить снимок", style="Small.TButton", command=self._save_snapshot_to_history).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Button(hist_tools, text="Открыть папку", style="Small.TButton", command=self._open_selected_history_run).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Button(hist_tools, text="Обновить", style="Small.TButton", command=self._refresh_history_table).pack(side=tk.LEFT)

        cols = ("ts", "result", "old", "new", "out", "run")
        self.history_tree = ttk.Treeview(history_tab, columns=cols, show="headings", selectmode="browse")
        self.history_tree.heading("ts", text="Дата/время")
        self.history_tree.heading("result", text="Результат")
        self.history_tree.heading("old", text="Старый PDF")
        self.history_tree.heading("new", text="Новый PDF")
        self.history_tree.heading("out", text="Папка вывода")
        self.history_tree.heading("run", text="Папка запуска")
        self.history_tree.column("ts", width=150, anchor="w")
        self.history_tree.column("result", width=90, anchor="center")
        self.history_tree.column("old", width=190, anchor="w")
        self.history_tree.column("new", width=190, anchor="w")
        self.history_tree.column("out", width=150, anchor="w")
        self.history_tree.column("run", width=230, anchor="w")
        self.history_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        self.history_tree.bind("<Double-1>", self._on_history_double_click)

        hist_scroll = ttk.Scrollbar(history_tab, orient=tk.VERTICAL, command=self.history_tree.yview)
        hist_scroll.pack(fill=tk.Y, side=tk.RIGHT)
        self.history_tree.configure(yscrollcommand=hist_scroll.set)

        ttk.Label(
            history_tab,
            text="Двойной клик по строке восстанавливает файлы, папку вывода и параметры.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(8, 0))

    def _path_row(self, parent: ttk.Frame, title: str, var: tk.StringVar, pick_cmd: Callable[[], None]) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=title, width=20).pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Выбрать...", style="Small.TButton", command=pick_cmd).pack(side=tk.LEFT, padx=(8, 0))

    def _toggle_options(self) -> None:
        self.options_expanded = not self.options_expanded
        if self.options_body is not None and self.options_toggle_btn is not None:
            if self.options_expanded:
                self.options_body.pack(fill=tk.X, pady=(0, 10))
                self.options_toggle_btn.configure(text="Параметры ▴")
            else:
                self.options_body.pack_forget()
                self.options_toggle_btn.configure(text="Параметры ▾")

    def _draw_drop_zone(self) -> None:
        if self.drop_canvas is None:
            return
        c = self.drop_canvas
        c.delete("all")
        w = max(40, c.winfo_width())
        h = max(100, c.winfo_height())
        pad = 8
        c.create_rectangle(pad, pad, w - pad, h - pad, dash=(5, 3), outline="#9BB3CF", width=2, fill="#F3F7FC")
        c.create_text(w / 2, h / 2 - 16, text="📄+📄", font=("Segoe UI Emoji", 28), fill="#6b7f9a")
        c.create_text(
            w / 2,
            h / 2 + 14,
            text="Перетащите 2 файла PDF сюда",
            font=("Segoe UI", 15, "bold"),
            fill="#293648",
        )
        c.create_text(
            w / 2,
            h / 2 + 40,
            text="или используйте кнопки ниже",
            font=("Segoe UI", 10),
            fill="#5f6f87",
        )

    def _refresh_drop_badges(self) -> None:
        def short_name(p: str) -> str:
            if not p:
                return ""
            path = Path(p)
            return path.name if path.name else p

        old_name = short_name(self.old_pdf.get().strip())
        new_name = short_name(self.new_pdf.get().strip())
        if old_name or new_name:
            self.drop_badges_var.set(f"Старый: {old_name or 'не выбран'}   |   Новый: {new_name or 'не выбран'}")
        else:
            self.drop_badges_var.set("")

    def _bind_input_tracking(self) -> None:
        for var in (self.old_pdf, self.new_pdf, self.out_dir, self.dpi, self.stroke_tol):
            var.trace_add("write", self._on_inputs_changed)

    def _on_inputs_changed(self, *_: object) -> None:
        self.last_inputs = self._capture_inputs()
        self._refresh_drop_badges()
        self._update_run_availability()

    def _update_run_availability(self) -> None:
        if self.run_btn is None:
            return
        if self.running:
            self.run_btn.configure(state=tk.DISABLED)
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
        self.run_btn.configure(state=tk.NORMAL if ready else tk.DISABLED)

    def _capture_inputs(self) -> dict[str, Any]:
        return {
            "old_pdf": self.old_pdf.get().strip(),
            "new_pdf": self.new_pdf.get().strip(),
            "out_dir": self.out_dir.get().strip(),
            "dpi": self.dpi.get().strip(),
            "stroke_tol": self.stroke_tol.get().strip(),
            "last_run_dir": str(self.last_run_dir) if self.last_run_dir else "",
        }

    def _apply_inputs(self, data: dict[str, Any]) -> None:
        self.old_pdf.set(str(data.get("old_pdf") or ""))
        self.new_pdf.set(str(data.get("new_pdf") or ""))
        self.out_dir.set(str(data.get("out_dir") or ""))
        self.dpi.set(str(data.get("dpi") or "250"))
        self.stroke_tol.set(str(data.get("stroke_tol") or "2.0"))
        self.open_report_btn.configure(state=tk.DISABLED)
        self.open_run_btn.configure(state=tk.DISABLED)
        self.last_run_dir = None
        run_dir = str(data.get("last_run_dir") or "").strip()
        if run_dir:
            self.last_run_dir = Path(run_dir)
            if self.last_run_dir.exists():
                self.open_report_btn.configure(state=tk.NORMAL)
                self.open_run_btn.configure(state=tk.NORMAL)
        self.last_inputs = self._capture_inputs()
        self._refresh_drop_badges()

    def _load_state(self) -> None:
        try:
            if not self.state_path.exists():
                return
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                last_inputs = data.get("last_inputs")
                history = data.get("history")
                if isinstance(last_inputs, dict):
                    self.last_inputs = last_inputs
                if isinstance(history, list):
                    self.history_records = [h for h in history if isinstance(h, dict)][-300:]
        except Exception:
            self.last_inputs = {}
            self.history_records = []

    def _save_state(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_inputs": self._capture_inputs(),
            "history": self.history_records[-300:],
        }
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _restore_last_inputs(self, startup: bool = False) -> None:
        if not self.last_inputs:
            if not startup:
                self.status.set("Сохраненных данных пока нет.")
            return
        self._apply_inputs(self.last_inputs)
        if startup:
            self.status.set("Предыдущие параметры восстановлены из локальной истории.")
        else:
            self.status.set("Восстановлены последние сохраненные параметры.")

    def _refresh_history_table(self) -> None:
        self._history_by_iid.clear()
        for iid in self.history_tree.get_children():
            self.history_tree.delete(iid)

        for rec_idx in range(len(self.history_records) - 1, -1, -1):
            rec = self.history_records[rec_idx]
            iid = str(rec_idx)
            result = str(rec.get("result") or "").upper()
            if result == "DONE":
                result = "Готово"
            elif result == "ERROR":
                result = "Ошибка"
            elif result == "SNAPSHOT":
                result = "Снимок"
            else:
                result = "Готово" if result == "OK" else result
            old_name = Path(str(rec.get("old_pdf") or "")).name
            new_name = Path(str(rec.get("new_pdf") or "")).name
            out_name = Path(str(rec.get("out_dir") or "")).name
            self.history_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    rec.get("ts", ""),
                    result,
                    old_name,
                    new_name,
                    out_name,
                    rec.get("run_dir", ""),
                ),
            )
            self._history_by_iid[iid] = rec

    def _get_selected_history(self) -> dict[str, Any] | None:
        selected = self.history_tree.selection()
        if not selected:
            return None
        return self._history_by_iid.get(selected[0])

    def _restore_selected_history(self) -> None:
        rec = self._get_selected_history()
        if not rec:
            self.status.set("Сначала выберите строку в истории.")
            return
        data = dict(rec)
        data["last_run_dir"] = rec.get("run_dir", "")
        self._apply_inputs(data)
        old_ok = Path(self.old_pdf.get()).exists() if self.old_pdf.get() else False
        new_ok = Path(self.new_pdf.get()).exists() if self.new_pdf.get() else False
        msg = "Данные из истории восстановлены."
        if not old_ok or not new_ok:
            msg += " Внимание: один или оба PDF-файла не найдены."
        self.status.set(msg)

    def _open_selected_history_run(self) -> None:
        rec = self._get_selected_history()
        if not rec:
            self.status.set("Сначала выберите строку в истории.")
            return
        run_dir = str(rec.get("run_dir") or "").strip()
        if not run_dir:
            self.status.set("Для выбранной строки нет папки запуска.")
            return
        p = Path(run_dir)
        if p.exists():
            os.startfile(str(p))
        else:
            messagebox.showerror("Папка не найдена", f"Не найдено:\n{p}")

    def _on_history_double_click(self, event: tk.Event) -> None:
        self._restore_selected_history()

    def _save_snapshot_to_history(self) -> None:
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
                "run_dir": "",
            }
        )
        self.status.set("Текущие параметры сохранены в историю.")

    def _add_history_record(self, rec: dict[str, Any]) -> None:
        self.history_records.append(rec)
        if len(self.history_records) > 300:
            self.history_records = self.history_records[-300:]
        self._refresh_history_table()
        self._save_state()

    def _install_drop_hook(self) -> None:
        self.root.update_idletasks()
        try:
            self._drop_hook = WindowsDropHook(self.root, self._handle_dropped_files)
            self.status.set("Перетащите 2 PDF-файла и нажмите Enter для запуска.")
        except Exception as exc:
            self._drop_hook = None
            self.status.set(f"Перетаскивание недоступно ({exc}). Используйте кнопки «Выбрать...».")

    def _handle_dropped_files(self, paths: Iterable[Path]) -> None:
        pdfs = [p for p in paths if p.suffix.lower() == ".pdf"]
        if not pdfs:
            self.status.set("В перетаскиваемых элементах нет PDF-файлов.")
            return

        if len(pdfs) >= 2:
            self.old_pdf.set(str(pdfs[0]))
            self.new_pdf.set(str(pdfs[1]))
            self.status.set("Загружены 2 PDF-файла. Нажмите Enter для запуска.")
            self._save_state()
            return

        one = str(pdfs[0])
        if not self.old_pdf.get():
            self.old_pdf.set(one)
            self.status.set("Выбран старый PDF. Добавьте новый PDF или нажмите «Выбрать...».")
        elif not self.new_pdf.get():
            self.new_pdf.set(one)
            self.status.set("Выбран новый PDF. Нажмите Enter для запуска.")
        else:
            self.new_pdf.set(one)
            self.status.set("Новый PDF заменен. Нажмите Enter для запуска.")
        self._save_state()

    def _pick_old_pdf(self) -> None:
        p = filedialog.askopenfilename(title="Выберите старый PDF", filetypes=[("PDF", "*.pdf")])
        if p:
            self.old_pdf.set(p)
            self._save_state()

    def _pick_new_pdf(self) -> None:
        p = filedialog.askopenfilename(title="Выберите новый PDF", filetypes=[("PDF", "*.pdf")])
        if p:
            self.new_pdf.set(p)
            self._save_state()

    def _pick_out_dir(self) -> None:
        p = filedialog.askdirectory(title="Выберите папку вывода")
        if p:
            self.out_dir.set(p)
            self._save_state()

    def _clear_inputs(self) -> None:
        if self.running:
            return
        self.old_pdf.set("")
        self.new_pdf.set("")
        self.out_dir.set("")
        self.progress.configure(value=0.0)
        self.progress_pct.set("0%")
        self.last_run_dir = None
        self.open_report_btn.configure(state=tk.DISABLED)
        self.open_run_btn.configure(state=tk.DISABLED)
        self.status.set("Поля очищены.")
        self._save_state()

    def _on_enter(self, event: tk.Event) -> None:
        if not self.running:
            self.start_compare()

    def start_compare(self) -> None:
        if self.running:
            return

        old = Path(self.old_pdf.get().strip()) if self.old_pdf.get().strip() else None
        new = Path(self.new_pdf.get().strip()) if self.new_pdf.get().strip() else None
        if not old or not old.exists():
            messagebox.showerror("Файл не найден", "Выберите корректный старый PDF-файл.")
            return
        if not new or not new.exists():
            messagebox.showerror("Файл не найден", "Выберите корректный новый PDF-файл.")
            return
        if old.resolve() == new.resolve():
            messagebox.showerror("Некорректный ввод", "Старый и новый PDF-файлы должны отличаться.")
            return

        out = self.out_dir.get().strip()
        if not out:
            selected = filedialog.askdirectory(title="Выберите папку вывода")
            if not selected:
                self.status.set("Запуск отменен: не выбрана папка вывода.")
                return
            self.out_dir.set(selected)
            out = selected
        out_path = Path(out)
        out_path.mkdir(parents=True, exist_ok=True)

        try:
            dpi = int(self.dpi.get().strip())
            stroke_tol = float(self.stroke_tol.get().strip())
        except ValueError:
            messagebox.showerror("Некорректный параметр", "DPI должен быть целым числом, допуск штриха - числом.")
            return

        if dpi < 72:
            messagebox.showerror("Некорректный параметр", "DPI должен быть не меньше 72.")
            return
        if stroke_tol < 0:
            messagebox.showerror("Некорректный параметр", "Допуск штриха должен быть не меньше 0.")
            return

        self.last_inputs = self._capture_inputs()
        self._save_state()
        self._set_running(True)
        self.status.set("Сравнение запущено... Это может занять несколько минут.")
        t = threading.Thread(
            target=self._run_worker,
            args=(old, new, out_path, dpi, stroke_tol),
            daemon=True,
        )
        t.start()

    def _run_worker(self, old: Path, new: Path, out_path: Path, dpi: int, stroke_tol: float) -> None:
        try:
            def report_progress(pct: float, msg: str) -> None:
                self.worker_events.put(("progress", float(pct), str(msg)))

            run_dir = compare_pdfs(
                old,
                new,
                out_path,
                high_dpi=dpi,
                stroke_tol_px=stroke_tol,
                progress_cb=report_progress,
            )
            self.worker_events.put(("done", run_dir, old, new, out_path, dpi, stroke_tol))
        except Exception as exc:
            self.worker_events.put(("error", str(exc), traceback.format_exc(), old, new, out_path, dpi, stroke_tol))

    def _poll_worker_events(self) -> None:
        try:
            while True:
                event = self.worker_events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    pct = max(0.0, min(100.0, float(event[1])))
                    msg = str(event[2])
                    self.progress.configure(value=pct)
                    self.progress_pct.set(f"{pct:.0f}%")
                    if self.run_btn is not None:
                        self.run_btn.configure(text=f"Сравнение... {pct:.0f}%")
                    self.status.set(f"{msg} ({pct:.0f}%)")
                elif kind == "done":
                    run_dir: Path = event[1]
                    old, new, out_dir, dpi, stroke_tol = event[2], event[3], event[4], event[5], event[6]
                    self.last_run_dir = run_dir
                    self._set_running(False)
                    self.progress.configure(value=100.0)
                    self.progress_pct.set("100%")
                    self.open_report_btn.configure(state=tk.NORMAL)
                    self.open_run_btn.configure(state=tk.NORMAL)
                    self.status.set(f"Готово. Отчет: {run_dir / 'report_bundle' / 'index.html'}")
                    self._add_history_record(
                        {
                            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "result": "done",
                            "old_pdf": str(old),
                            "new_pdf": str(new),
                            "out_dir": str(out_dir),
                            "dpi": str(dpi),
                            "stroke_tol": str(stroke_tol),
                            "run_dir": str(run_dir),
                        }
                    )
                    messagebox.showinfo("Готово", f"Сравнение завершено.\n\nПапка запуска:\n{run_dir}")
                elif kind == "error":
                    self._set_running(False)
                    err = event[1]
                    tb = event[2]
                    old, new, out_dir, dpi, stroke_tol = event[3], event[4], event[5], event[6], event[7]
                    self.status.set(f"Ошибка: {err}")
                    self._add_history_record(
                        {
                            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "result": "error",
                            "old_pdf": str(old),
                            "new_pdf": str(new),
                            "out_dir": str(out_dir),
                            "dpi": str(dpi),
                            "stroke_tol": str(stroke_tol),
                            "run_dir": "",
                            "error": err,
                        }
                    )
                    messagebox.showerror("Ошибка", f"{err}\n\n{tb}")
        except queue.Empty:
            pass
        finally:
            self.root.after(150, self._poll_worker_events)

    def _set_running(self, running: bool) -> None:
        self.running = running
        if running:
            self.progress.configure(value=0.0)
            self.progress_pct.set("0%")
            self.run_btn.configure(state=tk.DISABLED)
            self.run_btn.configure(text="Сравнение... 0%")
            self.open_report_btn.configure(state=tk.DISABLED)
            self.open_run_btn.configure(state=tk.DISABLED)
        else:
            self.run_btn.configure(text="Сравнить (Enter)")
            self._update_run_availability()

    def _open_report(self) -> None:
        if not self.last_run_dir:
            return
        report_html = self.last_run_dir / "report_bundle" / "index.html"
        if report_html.exists():
            os.startfile(str(report_html))
        else:
            messagebox.showerror("Файл не найден", f"Не найдено:\n{report_html}")

    def _open_run_folder(self) -> None:
        if not self.last_run_dir:
            return
        if self.last_run_dir.exists():
            os.startfile(str(self.last_run_dir))
        else:
            messagebox.showerror("Папка не найдена", f"Не найдено:\n{self.last_run_dir}")

    def _on_close(self) -> None:
        self._save_state()
        if self._drop_hook is not None:
            try:
                self._drop_hook.close()
            except Exception:
                pass
        self.root.destroy()


def main() -> None:
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
    main()
