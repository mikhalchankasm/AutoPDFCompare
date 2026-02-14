from __future__ import annotations

import ctypes
import json
import os
import queue
import threading
import time
import traceback
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Iterable

from compare_pdfs import compare_pdfs

# Try to import tkinterdnd2 for drag & drop support
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_TKDND = True
except ImportError:
    HAS_TKDND = False
    TkinterDnD = None
    DND_FILES = None


I18N: dict[str, dict[str, str]] = {
    "ru": {
        "window_title": "PDFCompare Local",
        "app_title": "PDFCompare Local",
        "app_subtitle": "Локальное сравнение PDF · без облака",
        "tab_compare": "Сравнение",
        "tab_history": "История",
        "drop_primary": "Перетащите 2 файла PDF сюда",
        "drop_secondary": "или используйте кнопки ниже",
        "path_old": "● Старый PDF",
        "path_new": "● Новый PDF",
        "path_out": "Папка вывода",
        "btn_select": "Выбрать...",
        "btn_swap": "⇅ Поменять местами",
        "opts_collapsed": "Параметры ▾",
        "opts_expanded": "Параметры ▴",
        "opts_group": "Параметры сравнения",
        "opts_dpi": "Разрешение (DPI):",
        "opts_dpi_hint": "Выше = точнее, но медленнее",
        "opts_stroke": "Допуск штриха (px):",
        "opts_stroke_hint": "Игнорирует различия тоньше указанного размера",
        "btn_run": "Сравнить (Enter)",
        "btn_cancel": "Отменить",
        "btn_cancelling": "Отмена...",
        "btn_clear": "Очистить",
        "btn_from_history": "Из истории",
        "btn_open_report": "Открыть отчёт",
        "btn_open_folder": "Открыть папку",
        "hist_restore": "Восстановить",
        "hist_snapshot": "Сохранить снимок",
        "hist_open_folder": "Открыть папку",
        "hist_refresh": "Обновить",
        "hist_col_time": "Дата/время",
        "hist_col_duration": "Время",
        "hist_col_pages": "Страницы",
        "hist_col_result": "Результат",
        "hist_col_old": "Старый PDF",
        "hist_col_new": "Новый PDF",
        "hist_col_out": "Папка вывода",
        "hist_col_run": "Папка запуска",
        "hist_hint": "Двойной клик по строке восстанавливает файлы, папку вывода и параметры.",
        "badge_old": "Старый",
        "badge_new": "Новый",
        "badge_not_selected": "не выбран",
        "status_initial": "Перетащите 2 PDF-файла и нажмите Enter для запуска.",
        "status_no_saved": "Сохраненных данных пока нет.",
        "status_restored_startup": "Предыдущие параметры восстановлены из локальной истории.",
        "status_restored": "Восстановлены последние сохраненные параметры.",
        "status_select_history_first": "Сначала выберите строку в истории.",
        "status_history_restored": "Данные из истории восстановлены.",
        "status_history_missing_files": "Внимание: один или оба PDF-файла не найдены.",
        "status_history_no_run": "Для выбранной строки нет папки запуска.",
        "status_snapshot_saved": "Текущие параметры сохранены в историю.",
        "status_drag_unavailable": "Перетаскивание недоступно ({error}). Используйте кнопки «Выбрать...».",
        "status_drop_no_pdf": "В перетаскиваемых элементах нет PDF-файлов.",
        "status_drop_loaded_two": "Загружены 2 PDF-файла. Нажмите Enter для запуска.",
        "status_drop_set_old": "Выбран старый PDF. Добавьте новый PDF или нажмите «Выбрать...».",
        "status_drop_set_new": "Выбран новый PDF. Нажмите Enter для запуска.",
        "status_drop_replaced_new": "Новый PDF заменен. Нажмите Enter для запуска.",
        "dlg_pick_old": "Выберите старый PDF",
        "dlg_pick_new": "Выберите новый PDF",
        "dlg_pick_out": "Выберите папку вывода",
        "status_cleared": "Поля очищены.",
        "err_file_missing_title": "Файл не найден",
        "err_old_missing": "Выберите корректный старый PDF-файл.",
        "err_new_missing": "Выберите корректный новый PDF-файл.",
        "err_invalid_input_title": "Некорректный ввод",
        "err_same_files": "Старый и новый PDF-файлы должны отличаться.",
        "status_run_cancel_no_out": "Запуск отменен: не выбрана папка вывода.",
        "err_invalid_option_title": "Некорректный параметр",
        "err_invalid_option_parse": "DPI должен быть целым числом, допуск штриха - числом.",
        "err_invalid_option_dpi": "DPI должен быть не меньше 72.",
        "err_invalid_option_stroke": "Допуск штриха должен быть не меньше 0.",
        "status_running": "Сравнение запущено... Это может занять несколько минут.",
        "status_cancel_requested": "Запрошена отмена. Ожидайте завершения текущего шага...",
        "status_cancelled": "Сравнение отменено пользователем.",
        "btn_running": "Сравнение... {pct:.0f}%",
        "status_done": "Готово. Отчет: {path}",
        "dlg_done_title": "Готово",
        "dlg_done_body": "Сравнение завершено.\n\nПапка запуска:\n{run_dir}",
        "status_error": "Ошибка: {error}",
        "dlg_error_title": "Ошибка",
        "err_folder_missing_title": "Папка не найдена",
        "err_not_found": "Не найдено:\n{path}",
        "hist_result_done": "Готово",
        "hist_result_error": "Ошибка",
        "hist_result_snapshot": "Снимок",
        "hist_result_cancelled": "Отменено",
        "lang_ru": "Русский",
        "lang_en": "English",
    },
    "en": {
        "window_title": "PDFCompare Local",
        "app_title": "PDFCompare Local",
        "app_subtitle": "Local PDF comparison · no cloud",
        "tab_compare": "Compare",
        "tab_history": "History",
        "drop_primary": "Drop 2 PDF files here",
        "drop_secondary": "or use the buttons below",
        "path_old": "● Old PDF",
        "path_new": "● New PDF",
        "path_out": "Output folder",
        "btn_select": "Select...",
        "btn_swap": "⇅ Swap files",
        "opts_collapsed": "Options ▾",
        "opts_expanded": "Options ▴",
        "opts_group": "Comparison options",
        "opts_dpi": "Resolution (DPI):",
        "opts_dpi_hint": "Higher = more precise but slower",
        "opts_stroke": "Stroke tolerance (px):",
        "opts_stroke_hint": "Ignores differences thinner than this threshold",
        "btn_run": "Compare (Enter)",
        "btn_cancel": "Cancel",
        "btn_cancelling": "Cancelling...",
        "btn_clear": "Clear",
        "btn_from_history": "From history",
        "btn_open_report": "Open report",
        "btn_open_folder": "Open folder",
        "hist_restore": "Restore",
        "hist_snapshot": "Save snapshot",
        "hist_open_folder": "Open folder",
        "hist_refresh": "Refresh",
        "hist_col_time": "Date/time",
        "hist_col_duration": "Duration",
        "hist_col_pages": "Pages",
        "hist_col_result": "Result",
        "hist_col_old": "Old PDF",
        "hist_col_new": "New PDF",
        "hist_col_out": "Output folder",
        "hist_col_run": "Run folder",
        "hist_hint": "Double-click a row to restore files, output folder, and options.",
        "badge_old": "Old",
        "badge_new": "New",
        "badge_not_selected": "not selected",
        "status_initial": "Drop 2 PDF files and press Enter to start.",
        "status_no_saved": "No saved values yet.",
        "status_restored_startup": "Previous settings restored from local history.",
        "status_restored": "Last saved settings restored.",
        "status_select_history_first": "Select a history row first.",
        "status_history_restored": "History row restored.",
        "status_history_missing_files": "Warning: one or both PDF files are missing.",
        "status_history_no_run": "Selected row has no run folder.",
        "status_snapshot_saved": "Current settings saved to history.",
        "status_drag_unavailable": "Drag-and-drop unavailable ({error}). Use Select buttons.",
        "status_drop_no_pdf": "Dropped items contain no PDF files.",
        "status_drop_loaded_two": "Loaded 2 PDFs. Press Enter to start.",
        "status_drop_set_old": "Old PDF set. Add new PDF or click Select...",
        "status_drop_set_new": "New PDF set. Press Enter to start.",
        "status_drop_replaced_new": "New PDF replaced. Press Enter to start.",
        "dlg_pick_old": "Select old PDF",
        "dlg_pick_new": "Select new PDF",
        "dlg_pick_out": "Select output folder",
        "status_cleared": "Inputs cleared.",
        "err_file_missing_title": "Missing file",
        "err_old_missing": "Select a valid old PDF file.",
        "err_new_missing": "Select a valid new PDF file.",
        "err_invalid_input_title": "Invalid input",
        "err_same_files": "Old and new PDF files must be different.",
        "status_run_cancel_no_out": "Run canceled: output folder not selected.",
        "err_invalid_option_title": "Invalid option",
        "err_invalid_option_parse": "DPI must be integer and stroke tolerance must be numeric.",
        "err_invalid_option_dpi": "DPI must be >= 72.",
        "err_invalid_option_stroke": "Stroke tolerance must be >= 0.",
        "status_running": "Comparison started... This may take a few minutes.",
        "status_cancel_requested": "Cancellation requested. Waiting for current step to finish...",
        "status_cancelled": "Comparison cancelled by user.",
        "btn_running": "Comparing... {pct:.0f}%",
        "status_done": "Done. Report: {path}",
        "dlg_done_title": "Done",
        "dlg_done_body": "Comparison complete.\n\nRun folder:\n{run_dir}",
        "status_error": "Error: {error}",
        "dlg_error_title": "Error",
        "err_folder_missing_title": "Missing folder",
        "err_not_found": "Not found:\n{path}",
        "hist_result_done": "Done",
        "hist_result_error": "Error",
        "hist_result_snapshot": "Snapshot",
        "hist_result_cancelled": "Cancelled",
        "lang_ru": "Russian",
        "lang_en": "English",
    },
}



class PDFCompareApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.lang = tk.StringVar(value="ru")
        self.root.title(I18N["ru"]["window_title"])
        self.root.geometry("900x700")
        self.root.minsize(800, 620)

        self.old_pdf = tk.StringVar()
        self.new_pdf = tk.StringVar()
        self.out_dir = tk.StringVar()
        self.dpi = tk.StringVar(value="250")
        self.stroke_tol = tk.StringVar(value="2.0")
        self.status = tk.StringVar(value="")
        self.progress_pct = tk.StringVar(value="0%")
        self.elapsed = tk.StringVar(value="00:00")
        self.drop_badges_var = tk.StringVar(value="")
        self.options_expanded = False

        self.worker_events: queue.Queue[tuple] = queue.Queue()
        self.running = False
        self.cancel_requested = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self._run_started_monotonic = 0.0
        self._timer_job: str | None = None
        self.last_run_dir: Path | None = None
        self._drop_hook: WindowsDropHook | None = None
        self._history_by_iid: dict[str, dict[str, Any]] = {}
        self.run_btn: ttk.Button | None = None
        self.open_report_btn: ttk.Button | None = None
        self.open_run_btn: ttk.Button | None = None
        self.options_body: ttk.Frame | None = None
        self.options_toggle_btn: ttk.Button | None = None
        self.drop_canvas: tk.Canvas | None = None
        self.lang_ru_btn: ttk.Button | None = None
        self.lang_en_btn: ttk.Button | None = None
        self.subtitle_label: ttk.Label | None = None
        self.tabs: ttk.Notebook | None = None
        self.compare_tab: ttk.Frame | None = None
        self.history_tab: ttk.Frame | None = None
        self.old_label: ttk.Label | None = None
        self.new_label: ttk.Label | None = None
        self.out_label: ttk.Label | None = None
        self.old_entry: ttk.Entry | None = None
        self.new_entry: ttk.Entry | None = None
        self.out_entry: ttk.Entry | None = None
        self.old_pick_btn: ttk.Button | None = None
        self.new_pick_btn: ttk.Button | None = None
        self.out_pick_btn: ttk.Button | None = None
        self.options_dpi_label: ttk.Label | None = None
        self.options_dpi_hint_label: ttk.Label | None = None
        self.options_stroke_label: ttk.Label | None = None
        self.options_stroke_hint_label: ttk.Label | None = None
        self.clear_btn: ttk.Button | None = None
        self.from_history_btn: ttk.Button | None = None
        self.hist_restore_btn: ttk.Button | None = None
        self.hist_snapshot_btn: ttk.Button | None = None
        self.hist_open_btn: ttk.Button | None = None
        self.hist_refresh_btn: ttk.Button | None = None
        self.history_hint_label: ttk.Label | None = None

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

    def _tr(self, key: str, **kwargs: object) -> str:
        lang = self.lang.get() if self.lang.get() in I18N else "ru"
        template = I18N.get(lang, I18N["ru"]).get(key, I18N["ru"].get(key, key))
        return template.format(**kwargs)

    def _set_status(self, key: str, **kwargs: object) -> None:
        self.status.set(self._tr(key, **kwargs))

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
        if current == "ru":
            self.lang_ru_btn.configure(style="Primary.TButton")
            self.lang_en_btn.configure(style="Small.TButton")
        else:
            self.lang_ru_btn.configure(style="Small.TButton")
            self.lang_en_btn.configure(style="Primary.TButton")

    def _apply_locale(self) -> None:
        self.root.title(self._tr("window_title"))
        if self.subtitle_label is not None:
            self.subtitle_label.configure(text=self._tr("app_subtitle"))
        if self.tabs is not None:
            self.tabs.tab(0, text=self._tr("tab_compare"))
            self.tabs.tab(1, text=self._tr("tab_history"))
        if self.old_label is not None:
            self.old_label.configure(text=self._tr("path_old"))
        if self.new_label is not None:
            self.new_label.configure(text=self._tr("path_new"))
        if self.out_label is not None:
            self.out_label.configure(text=self._tr("path_out"))
        if self.old_pick_btn is not None:
            self.old_pick_btn.configure(text=self._tr("btn_select"))
        if self.swap_btn is not None:
            self.swap_btn.configure(text=self._tr("btn_swap"))
        if self.new_pick_btn is not None:
            self.new_pick_btn.configure(text=self._tr("btn_select"))
        if self.out_pick_btn is not None:
            self.out_pick_btn.configure(text=self._tr("btn_select"))
        if self.options_body is not None:
            self.options_body.configure(text=self._tr("opts_group"))
        if self.options_dpi_label is not None:
            self.options_dpi_label.configure(text=self._tr("opts_dpi"))
        if self.options_dpi_hint_label is not None:
            self.options_dpi_hint_label.configure(text=self._tr("opts_dpi_hint"))
        if self.options_stroke_label is not None:
            self.options_stroke_label.configure(text=self._tr("opts_stroke"))
        if self.options_stroke_hint_label is not None:
            self.options_stroke_hint_label.configure(text=self._tr("opts_stroke_hint"))
        if self.run_btn is not None:
            if self.running:
                self.run_btn.configure(text=self._tr("btn_cancelling" if self.cancel_requested.is_set() else "btn_cancel"))
            else:
                self.run_btn.configure(text=self._tr("btn_run"))
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
            self.hist_refresh_btn.configure(text=self._tr("hist_refresh"))
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
        self._update_lang_buttons()
        self._draw_drop_zone()
        self._refresh_drop_badges()
        self._refresh_history_table()

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("SubHeader.TLabel", font=("Segoe UI", 11))
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"))
        style.configure("Small.TButton", font=("Segoe UI", 10))
        style.configure("Hint.TLabel", font=("Segoe UI", 9), foreground="#4b5872")
        style.configure("Red.TLabel", font=("Segoe UI", 10, "bold"), foreground="#d32f2f")  # Red bold for old PDF
        style.configure("Green.TLabel", font=("Segoe UI", 10, "bold"), foreground="#388e3c")  # Green bold for new PDF

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
            foreground="#5f6d86",
        )
        self.subtitle_label.pack(anchor="w", pady=(1, 8))

        right_top = ttk.Frame(top)
        right_top.pack(side=tk.RIGHT)

        # Language switcher - two buttons instead of combobox
        lang_frame = ttk.Frame(right_top)
        lang_frame.pack(side=tk.RIGHT)
        self.lang_ru_btn = ttk.Button(lang_frame, text="RU", width=4, command=lambda: self._set_language("ru"))
        self.lang_ru_btn.pack(side=tk.LEFT, padx=2)
        self.lang_en_btn = ttk.Button(lang_frame, text="EN", width=4, command=lambda: self._set_language("en"))
        self.lang_en_btn.pack(side=tk.LEFT)

        ttk.Button(right_top, text="⚙", style="Small.TButton", state=tk.DISABLED).pack(side=tk.RIGHT, padx=(8, 6))

        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill=tk.BOTH, expand=True)
        self.compare_tab = ttk.Frame(self.tabs, padding=8)
        self.history_tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(self.compare_tab, text=self._tr("tab_compare"))
        self.tabs.add(self.history_tab, text=self._tr("tab_history"))

        self.drop_canvas = tk.Canvas(self.compare_tab, height=145, bg="#F0F4F8", highlightthickness=0)
        self.drop_canvas.pack(fill=tk.X, pady=(0, 8))
        self.drop_canvas.bind("<Configure>", lambda _e: self._draw_drop_zone())
        self._draw_drop_zone()

        ttk.Label(self.compare_tab, textvariable=self.drop_badges_var, style="Hint.TLabel").pack(anchor="w", pady=(0, 8))

        self.old_label, self.old_entry, self.old_pick_btn = self._path_row(self.compare_tab, self.old_pdf, self._pick_old_pdf, "Red.TLabel")

        # Swap button between old and new PDF
        swap_frame = ttk.Frame(self.compare_tab)
        swap_frame.pack(fill=tk.X, pady=2)
        self.swap_btn = ttk.Button(swap_frame, text=self._tr("btn_swap"), style="Small.TButton", command=self._swap_files)
        self.swap_btn.pack(anchor="center")

        self.new_label, self.new_entry, self.new_pick_btn = self._path_row(self.compare_tab, self.new_pdf, self._pick_new_pdf, "Green.TLabel")
        self.out_label, self.out_entry, self.out_pick_btn = self._path_row(self.compare_tab, self.out_dir, self._pick_out_dir)

        options_wrap = ttk.Frame(self.compare_tab)
        options_wrap.pack(fill=tk.X, pady=(6, 6))

        # Options always visible (no toggle button)
        self.options_body = ttk.LabelFrame(options_wrap, text=self._tr("opts_group"), padding=10)
        self.options_body.pack(fill=tk.X, pady=(0, 10))
        self.options_dpi_label = ttk.Label(self.options_body, text=self._tr("opts_dpi"))
        self.options_dpi_label.grid(row=0, column=0, sticky="w")
        ttk.Spinbox(self.options_body, from_=120, to=600, textvariable=self.dpi, width=8).grid(
            row=0, column=1, sticky="w", padx=(6, 16)
        )
        self.options_dpi_hint_label = ttk.Label(self.options_body, text=self._tr("opts_dpi_hint"), style="Hint.TLabel")
        self.options_dpi_hint_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 8))
        self.options_stroke_label = ttk.Label(self.options_body, text=self._tr("opts_stroke"))
        self.options_stroke_label.grid(row=0, column=2, sticky="w")
        ttk.Entry(self.options_body, textvariable=self.stroke_tol, width=8).grid(row=0, column=3, sticky="w", padx=(6, 0))
        self.options_stroke_hint_label = ttk.Label(self.options_body, text=self._tr("opts_stroke_hint"), style="Hint.TLabel")
        self.options_stroke_hint_label.grid(row=1, column=2, columnspan=2, sticky="w", pady=(2, 8))
        self.options_body.columnconfigure(4, weight=1)
        # Options always visible - no pack_forget()

        actions = ttk.Frame(self.compare_tab)
        actions.pack(fill=tk.X, pady=(2, 2))
        self.run_btn = ttk.Button(actions, text=self._tr("btn_run"), style="Primary.TButton", command=self.start_compare)
        self.run_btn.pack(fill=tk.X, ipady=7)

        secondary = ttk.Frame(self.compare_tab)
        secondary.pack(fill=tk.X, pady=(8, 0))
        self.clear_btn = ttk.Button(secondary, text=self._tr("btn_clear"), style="Small.TButton", command=self._clear_inputs)
        self.clear_btn.pack(side=tk.LEFT)
        self.from_history_btn = ttk.Button(
            secondary, text=self._tr("btn_from_history"), style="Small.TButton", command=self._restore_last_inputs
        )
        self.from_history_btn.pack(side=tk.LEFT, padx=8)
        self.open_report_btn = ttk.Button(
            secondary, text=self._tr("btn_open_report"), style="Small.TButton", command=self._open_report, state=tk.DISABLED
        )
        self.open_report_btn.pack(side=tk.RIGHT)
        self.open_run_btn = ttk.Button(
            secondary, text=self._tr("btn_open_folder"), style="Small.TButton", command=self._open_run_folder, state=tk.DISABLED
        )
        self.open_run_btn.pack(side=tk.RIGHT, padx=(0, 8))

        progress_row = ttk.Frame(self.compare_tab)
        progress_row.pack(fill=tk.X, pady=(10, 5))
        self.progress = ttk.Progressbar(progress_row, mode="determinate", maximum=100)
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(progress_row, textvariable=self.elapsed, width=7, anchor="e").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(progress_row, textvariable=self.progress_pct, width=6, anchor="e").pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(self.compare_tab, textvariable=self.status, style="Hint.TLabel", wraplength=860).pack(anchor="w")

        hist_tools = ttk.Frame(self.history_tab)
        hist_tools.pack(fill=tk.X, pady=(0, 8))
        self.hist_restore_btn = ttk.Button(
            hist_tools, text=self._tr("hist_restore"), style="Small.TButton", command=self._restore_selected_history
        )
        self.hist_restore_btn.pack(side=tk.LEFT)
        self.hist_snapshot_btn = ttk.Button(
            hist_tools, text=self._tr("hist_snapshot"), style="Small.TButton", command=self._save_snapshot_to_history
        )
        self.hist_snapshot_btn.pack(side=tk.LEFT, padx=8)
        self.hist_open_btn = ttk.Button(
            hist_tools, text=self._tr("hist_open_folder"), style="Small.TButton", command=self._open_selected_history_run
        )
        self.hist_open_btn.pack(side=tk.LEFT, padx=8)
        self.hist_refresh_btn = ttk.Button(
            hist_tools, text=self._tr("hist_refresh"), style="Small.TButton", command=self._refresh_history_table
        )
        self.hist_refresh_btn.pack(side=tk.LEFT)

        # Create container for table and scrollbar
        tree_container = ttk.Frame(self.history_tab)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ("ts", "duration", "pages", "result", "old", "new", "out", "run")
        self.history_tree = ttk.Treeview(tree_container, columns=cols, show="headings", selectmode="browse")
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

        hist_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.history_tree.yview)
        hist_scroll.pack(fill=tk.Y, side=tk.RIGHT)
        self.history_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        self.history_tree.configure(yscrollcommand=hist_scroll.set)
        self.history_tree.bind("<Double-1>", self._on_history_double_click)

        self.history_hint_label = ttk.Label(self.history_tab, text=self._tr("hist_hint"), style="Hint.TLabel")
        self.history_hint_label.pack(anchor="w", pady=(8, 0))

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

    # Options are now always visible - toggle removed

    def _format_duration(self, seconds: float) -> str:
        """Format duration as MM:SS"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def _get_pages_str(self, old_pdf: Path, new_pdf: Path) -> str:
        """Get page counts from PDFs as 'old/new' format"""
        try:
            import fitz  # PyMuPDF
            old_count = 0
            new_count = 0
            try:
                with fitz.open(old_pdf) as doc:
                    old_count = len(doc)
            except Exception:
                pass
            try:
                with fitz.open(new_pdf) as doc:
                    new_count = len(doc)
            except Exception:
                pass
            return f"{old_count}/{new_count}"
        except ImportError:
            return ""

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
            text=self._tr("drop_primary"),
            font=("Segoe UI", 15, "bold"),
            fill="#293648",
        )
        c.create_text(
            w / 2,
            h / 2 + 40,
            text=self._tr("drop_secondary"),
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
            self.drop_badges_var.set(
                f"{self._tr('badge_old')}: {old_name or self._tr('badge_not_selected')}   |   "
                f"{self._tr('badge_new')}: {new_name or self._tr('badge_not_selected')}"
            )
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
            self.run_btn.configure(state=tk.DISABLED if self.cancel_requested.is_set() else tk.NORMAL)
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

    def _save_state(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "language": self.lang.get(),
            "last_inputs": self._capture_inputs(),
            "history": self.history_records[-300:],
        }
        tmp_path = self.state_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.state_path)

    def _restore_last_inputs(self, startup: bool = False) -> None:
        if not self.last_inputs:
            if not startup:
                self._set_status("status_no_saved")
            return
        self._apply_inputs(self.last_inputs)
        if startup:
            self._set_status("status_restored_startup")
        else:
            self._set_status("status_restored")

    def _refresh_history_table(self) -> None:
        self._history_by_iid.clear()
        for iid in self.history_tree.get_children():
            self.history_tree.delete(iid)

        for rec_idx in range(len(self.history_records) - 1, -1, -1):
            rec = self.history_records[rec_idx]
            iid = str(rec_idx)
            result = str(rec.get("result") or "").upper()
            if result == "DONE":
                result = self._tr("hist_result_done")
            elif result == "ERROR":
                result = self._tr("hist_result_error")
            elif result == "SNAPSHOT":
                result = self._tr("hist_result_snapshot")
            elif result == "CANCELLED":
                result = self._tr("hist_result_cancelled")
            else:
                result = self._tr("hist_result_done") if result == "OK" else result
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

    def _open_selected_history_run(self) -> None:
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
        self._set_status("status_snapshot_saved")

    def _add_history_record(self, rec: dict[str, Any]) -> None:
        self.history_records.append(rec)
        if len(self.history_records) > 300:
            self.history_records = self.history_records[-300:]
        self._refresh_history_table()
        self._save_state()

    def _install_drop_hook(self) -> None:
        self.root.update_idletasks()
        try:
            if HAS_TKDND and DND_FILES is not None:
                # Use tkinterdnd2 for drag & drop (Python 3.12+ compatible)
                # Main drop canvas
                if self.drop_canvas:
                    self.drop_canvas.drop_target_register(DND_FILES)
                    self.drop_canvas.dnd_bind('<<Drop>>', self._on_tkdnd_drop)

                # Individual path entry fields
                if self.old_entry:
                    self.old_entry.drop_target_register(DND_FILES)
                    self.old_entry.dnd_bind('<<Drop>>', self._on_tkdnd_drop_old)
                if self.new_entry:
                    self.new_entry.drop_target_register(DND_FILES)
                    self.new_entry.dnd_bind('<<Drop>>', self._on_tkdnd_drop_new)
                if self.out_entry:
                    self.out_entry.drop_target_register(DND_FILES)
                    self.out_entry.dnd_bind('<<Drop>>', self._on_tkdnd_drop_out)

                self._set_status("status_initial")
            else:
                # Fallback: drag & drop not available
                self._set_status("status_drag_unavailable", error="tkinterdnd2 not installed")
        except Exception as exc:
            self._set_status("status_drag_unavailable", error=str(exc))

    def _on_tkdnd_drop(self, event) -> None:
        """Handle drop event from tkinterdnd2 (main canvas)"""
        try:
            files = self.root.tk.splitlist(event.data)
            paths = [Path(f) for f in files if Path(f).exists()]
            self._handle_dropped_files(paths)
        except Exception:
            pass
        return event.action

    def _on_tkdnd_drop_old(self, event) -> None:
        """Handle drop to Old PDF field"""
        try:
            files = self.root.tk.splitlist(event.data)
            if files:
                path = Path(files[0])
                if path.exists() and path.suffix.lower() == '.pdf':
                    self.old_pdf.set(str(path))
                    self._save_state()
        except Exception:
            pass
        return event.action

    def _on_tkdnd_drop_new(self, event) -> None:
        """Handle drop to New PDF field"""
        try:
            files = self.root.tk.splitlist(event.data)
            if files:
                path = Path(files[0])
                if path.exists() and path.suffix.lower() == '.pdf':
                    self.new_pdf.set(str(path))
                    self._save_state()
        except Exception:
            pass
        return event.action

    def _on_tkdnd_drop_out(self, event) -> None:
        """Handle drop to Output folder field"""
        try:
            files = self.root.tk.splitlist(event.data)
            if files:
                path = Path(files[0])
                # Accept both folders and files (use parent folder if file dropped)
                if path.exists():
                    if path.is_dir():
                        self.out_dir.set(str(path))
                    else:
                        self.out_dir.set(str(path.parent))
                    self._save_state()
        except Exception:
            pass
        return event.action

    def _handle_dropped_files(self, paths: Iterable[Path]) -> None:
        pdfs = [p for p in paths if p.suffix.lower() == ".pdf"]
        if not pdfs:
            self._set_status("status_drop_no_pdf")
            return

        if len(pdfs) >= 2:
            self.old_pdf.set(str(pdfs[0]))
            self.new_pdf.set(str(pdfs[1]))
            self._set_status("status_drop_loaded_two")
            self._save_state()
            return

        one = str(pdfs[0])
        if not self.old_pdf.get():
            self.old_pdf.set(one)
            self._set_status("status_drop_set_old")
        elif not self.new_pdf.get():
            self.new_pdf.set(one)
            self._set_status("status_drop_set_new")
        else:
            self.new_pdf.set(one)
            self._set_status("status_drop_replaced_new")
        self._save_state()

    def _pick_old_pdf(self) -> None:
        p = filedialog.askopenfilename(title=self._tr("dlg_pick_old"), filetypes=[("PDF", "*.pdf")])
        if p:
            self.old_pdf.set(p)
            self._save_state()

    def _pick_new_pdf(self) -> None:
        p = filedialog.askopenfilename(title=self._tr("dlg_pick_new"), filetypes=[("PDF", "*.pdf")])
        if p:
            self.new_pdf.set(p)
            self._save_state()

    def _pick_out_dir(self) -> None:
        p = filedialog.askdirectory(title=self._tr("dlg_pick_out"))
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
        self.progress.configure(value=0.0)
        self.progress_pct.set("0%")
        self.last_run_dir = None
        self.open_report_btn.configure(state=tk.DISABLED)
        self.open_run_btn.configure(state=tk.DISABLED)
        self._set_status("status_cleared")
        self._save_state()

    def _on_enter(self, event: tk.Event) -> None:
        if not self.running:
            self.start_compare()
        else:
            self._request_cancel()

    def _request_cancel(self) -> None:
        if not self.running:
            return
        self.cancel_requested.set()
        if self.run_btn is not None:
            self.run_btn.configure(state=tk.DISABLED, text=self._tr("btn_cancelling"))
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
            selected = filedialog.askdirectory(title=self._tr("dlg_pick_out"))
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
        except ValueError:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_parse"))
            return

        if dpi < 72:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_dpi"))
            return
        if stroke_tol < 0:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_stroke"))
            return

        self.last_inputs = self._capture_inputs()
        self._save_state()
        self.cancel_requested.clear()
        self._set_running(True)
        self._set_status("status_running")
        t = threading.Thread(
            target=self._run_worker,
            args=(old, new, out_path, dpi, stroke_tol, self.lang.get()),
            daemon=True,
        )
        self.worker_thread = t
        t.start()

    def _run_worker(self, old: Path, new: Path, out_path: Path, dpi: int, stroke_tol: float, report_lang: str) -> None:
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
                progress_cb=report_progress,
            )
            if self.cancel_requested.is_set():
                self.worker_events.put(("cancelled", old, new, out_path, dpi, stroke_tol))
                return
            self.worker_events.put(("done", run_dir, old, new, out_path, dpi, stroke_tol))
        except Exception as exc:
            if str(exc) == "__CANCELLED__":
                self.worker_events.put(("cancelled", old, new, out_path, dpi, stroke_tol))
                return
            self.worker_events.put(("error", str(exc), traceback.format_exc(), old, new, out_path, dpi, stroke_tol))

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
                    self.progress.configure(value=pct)
                    self.progress_pct.set(f"{pct:.0f}%")
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
                    self._set_status("status_done", path=run_dir / "report_bundle" / "index.html")

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
                            "run_dir": str(run_dir),
                        }
                    )
                    messagebox.showinfo(self._tr("dlg_done_title"), self._tr("dlg_done_body", run_dir=run_dir))
                elif kind == "cancelled":
                    old, new, out_dir, dpi, stroke_tol = event[1], event[2], event[3], event[4], event[5]
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
                            "run_dir": "",
                        }
                    )
                elif kind == "error":
                    self._set_running(False)
                    err = event[1]
                    tb = event[2]
                    old, new, out_dir, dpi, stroke_tol = event[3], event[4], event[5], event[6], event[7]
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
                            "run_dir": "",
                            "error": err,
                        }
                    )
                    messagebox.showerror(self._tr("dlg_error_title"), f"{err}\n\n{tb}")
            has_more = not self.worker_events.empty()
        except queue.Empty:
            pass
        finally:
            self.root.after(20 if has_more else 150, self._poll_worker_events)

    def _set_running(self, running: bool) -> None:
        self.running = running
        if running:
            self.progress.configure(value=0.0)
            self.progress_pct.set("0%")
            self.elapsed.set("00:00")
            self._run_started_monotonic = time.monotonic()
            self._start_timer()
            self.run_btn.configure(state=tk.NORMAL, command=self._request_cancel)
            self.run_btn.configure(text=self._tr("btn_cancel"))
            self.open_report_btn.configure(state=tk.DISABLED)
            self.open_run_btn.configure(state=tk.DISABLED)
        else:
            self._stop_timer()
            self.cancel_requested.clear()
            self.worker_thread = None
            self.run_btn.configure(command=self.start_compare)
            self.run_btn.configure(text=self._tr("btn_run"))
            self._update_run_availability()

    def _open_report(self) -> None:
        if not self.last_run_dir:
            return
        report_html = self.last_run_dir / "report_bundle" / "index.html"
        if report_html.exists():
            os.startfile(str(report_html))
        else:
            messagebox.showerror(self._tr("err_file_missing_title"), self._tr("err_not_found", path=report_html))

    def _open_run_folder(self) -> None:
        if not self.last_run_dir:
            return
        if self.last_run_dir.exists():
            os.startfile(str(self.last_run_dir))
        else:
            messagebox.showerror(self._tr("err_folder_missing_title"), self._tr("err_not_found", path=self.last_run_dir))

    def _on_close(self) -> None:
        if self.running:
            self.cancel_requested.set()
            self._set_status("status_cancel_requested")
            deadline = time.monotonic() + 3.0
            while True:
                worker = self.worker_thread
                if worker is None:
                    break
                worker.join(timeout=0.05)
                if not worker.is_alive():
                    break
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
    if HAS_TKDND and TkinterDnD is not None:
        root = TkinterDnD.Tk()
    else:
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
