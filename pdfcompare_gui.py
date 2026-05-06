from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import queue
import re
import threading
import time
import traceback
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Iterable

from compare_pdfs import (
    APP_NAME,
    APP_VERSION,
    LIVE_REPORT_EVENT_PREFIX,
    START_REPORT_FILE,
    compare_pdfs,
    find_summary_json_path,
    regenerate_report_pages,
)

BG_WINDOW = "#ECEBE5"
BG_CARD = "#FFFFFF"
BG_SOFT = "#F5F4EE"
BG_INFO = "#E6F1FB"
TEXT_PRIMARY = "#141413"
TEXT_SECONDARY = "#6E6D68"
TEXT_TERTIARY = "#999791"
BORDER_THIN = "#E0DFDB"
BORDER_STRONG = "#C9C8C2"
ACCENT = "#185FA5"
ACCENT_DARK = "#0C447C"
OLD_DOT = "#E24B4A"
OLD_BORDER = "#B5D4F4"
NEW_DOT = "#639922"
NEW_BORDER = "#C0DD97"
PILL_OK_BG = "#EAF3DE"
PILL_OK_TEXT = "#3B6D11"
PILL_CANCEL_BG = "#F1EFE8"
PILL_CANCEL_TEXT = "#5F5E5A"

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
        "tab_rerender": "Перегенерация",
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
        "opts_workers": "Процессы:",
        "opts_workers_hint": "0 = авто, 1 = без параллельной обработки",
        "opts_default": "по умолчанию",
        "workers_auto": "Авто",
        "drop_hint": "⤓  Перетащите 2 PDF-файла прямо сюда — они автоматически попадут в «Старый» и «Новый»",
        "file_not_selected": "Файл не выбран",
        "file_path_hint": "Выберите PDF или перетащите его в карточку",
        "btn_compare_short": "Сравнить ⏎",
        "status_ready": "Готово к запуску. Нажмите Enter, чтобы начать сравнение.",
        "status_live_report": "Live-отчёт уже доступен. Его можно открыть во время сравнения.",
        "status_open_report_link": "Открыть отчёт →",
        "status_open_folder_link": "Открыть папку →",
        "history_search_placeholder": "Поиск по имени файла, папке…",
        "hist_filter_all": "Все",
        "hist_filter_done": "Готово",
        "hist_filter_cancelled": "Отменено",
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
        "rerender_title": "Перегенерация выбранных листов с повышенным DPI",
        "rerender_hint": "Загрузите готовый отчёт, выделите строки и пересчитайте только эти листы. Карта соответствия PDF не меняется.",
        "rerender_run": "Папка отчёта",
        "rerender_load_current": "Текущий отчёт",
        "rerender_pick": "Выбрать папку...",
        "rerender_reload": "Загрузить",
        "rerender_dpi": "Новый DPI:",
        "rerender_workers": "Процессы:",
        "rerender_start": "Перегенерировать выбранные",
        "rerender_col_seq": "#",
        "rerender_col_a": "A",
        "rerender_col_b": "B",
        "rerender_col_level": "Статус",
        "rerender_col_diff": "Diff %",
        "rerender_col_boxes": "Bbox",
        "rerender_col_pixels": "Пиксели",
        "rerender_col_time": "Время",
        "status_rerender_loaded": "Загружено листов: {count}. Выделите нужные строки для перегенерации.",
        "status_rerender_empty": "В отчёте нет данных по листам.",
        "status_rerender_select": "Выделите один или несколько листов.",
        "status_rerender_running": "Перегенерация выбранных листов запущена...",
        "status_rerender_done": "Перегенерация завершена. Отчёт обновлён.",
        "dlg_rerender_done_body": "Перегенерация выбранных листов завершена.\n\nОтчёт обновлён:\n{report}",
        "err_rerender_busy": "Дождитесь завершения текущей операции.",
        "err_invalid_rerender_dpi": "DPI должен быть целым числом не меньше 72.",
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
        "err_invalid_option_parse": "DPI и процессы должны быть целыми числами, допуск штриха - числом.",
        "err_invalid_option_dpi": "DPI должен быть не меньше 72.",
        "err_invalid_option_stroke": "Допуск штриха должен быть не меньше 0.",
        "err_invalid_option_workers": "Количество процессов должно быть 0 или больше.",
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
        "tab_rerender": "Re-render",
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
        "opts_workers": "Workers:",
        "opts_workers_hint": "0 = auto, 1 = no parallel page processing",
        "opts_default": "default",
        "workers_auto": "Auto",
        "drop_hint": "⤓  Drop 2 PDF files here — they will be assigned to Old and New",
        "file_not_selected": "No file selected",
        "file_path_hint": "Select a PDF or drop it onto this card",
        "btn_compare_short": "Compare ⏎",
        "status_ready": "Ready. Press Enter to start comparison.",
        "status_live_report": "Live report is available. You can open it while comparison continues.",
        "status_open_report_link": "Open report →",
        "status_open_folder_link": "Open folder →",
        "history_search_placeholder": "Search by file name or folder…",
        "hist_filter_all": "All",
        "hist_filter_done": "Done",
        "hist_filter_cancelled": "Cancelled",
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
        "rerender_title": "Re-render selected pages with higher DPI",
        "rerender_hint": "Load a finished report, select rows, and recompute only those pages. PDF page mapping is preserved.",
        "rerender_run": "Report folder",
        "rerender_load_current": "Current report",
        "rerender_pick": "Select folder...",
        "rerender_reload": "Load",
        "rerender_dpi": "New DPI:",
        "rerender_workers": "Workers:",
        "rerender_start": "Re-render selected",
        "rerender_col_seq": "#",
        "rerender_col_a": "A",
        "rerender_col_b": "B",
        "rerender_col_level": "Status",
        "rerender_col_diff": "Diff %",
        "rerender_col_boxes": "Bbox",
        "rerender_col_pixels": "Pixels",
        "rerender_col_time": "Time",
        "status_rerender_loaded": "Loaded pages: {count}. Select rows to re-render.",
        "status_rerender_empty": "The report has no page details.",
        "status_rerender_select": "Select one or more pages.",
        "status_rerender_running": "Selected page re-rendering started...",
        "status_rerender_done": "Re-rendering finished. Report updated.",
        "dlg_rerender_done_body": "Selected page re-rendering is complete.\n\nReport updated:\n{report}",
        "err_rerender_busy": "Wait until the current operation is finished.",
        "err_invalid_rerender_dpi": "DPI must be an integer >= 72.",
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
        "err_invalid_option_parse": "DPI and workers must be integers; stroke tolerance must be numeric.",
        "err_invalid_option_dpi": "DPI must be >= 72.",
        "err_invalid_option_stroke": "Stroke tolerance must be >= 0.",
        "err_invalid_option_workers": "Workers must be 0 or greater.",
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
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1100x740")
        self.root.minsize(920, 640)
        self.root.configure(bg=BG_WINDOW)

        self.old_pdf = tk.StringVar()
        self.new_pdf = tk.StringVar()
        self.out_dir = tk.StringVar()
        self.dpi = tk.StringVar(value="250")
        self.stroke_tol = tk.StringVar(value="2.0")
        self.workers = tk.StringVar(value="0")
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

        self.worker_events: queue.Queue[tuple] = queue.Queue()
        self.running = False
        self.cancel_requested = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self._run_started_monotonic = 0.0
        self._timer_job: str | None = None
        self.last_run_dir: Path | None = None
        self._drop_hook: WindowsDropHook | None = None
        self._history_by_iid: dict[str, dict[str, Any]] = {}
        self.run_btn: tk.Button | None = None
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
        self.rerender_tab: ttk.Frame | None = None
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
        self.options_workers_label: ttk.Label | None = None
        self.options_workers_hint_label: ttk.Label | None = None
        self.clear_btn: ttk.Button | None = None
        self.from_history_btn: ttk.Button | None = None
        self.hist_restore_btn: tk.Button | None = None
        self.hist_snapshot_btn: ttk.Button | None = None
        self.hist_open_btn: ttk.Button | None = None
        self.hist_refresh_btn: ttk.Button | None = None
        self.history_hint_label: ttk.Label | None = None
        self.status_text_label: tk.Label | None = None
        self.status_report_link: tk.Label | None = None
        self.status_folder_link: tk.Label | None = None
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
        self.rerender_start_btn: ttk.Button | None = None
        self.rerender_open_report_btn: ttk.Button | None = None
        self.history_filter_buttons: dict[str, tk.Label] = {}
        self.worker_chips: dict[str, tk.Label] = {}
        self.rerender_by_iid: dict[str, dict[str, Any]] = {}
        self.rerender_running = False

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
        self._refresh_status_links()

    def _refresh_status_links(self) -> None:
        visible = bool(self.last_run_dir and self.last_run_dir.exists())
        for widget in (self.status_report_link, self.status_folder_link):
            if widget is None:
                continue
            if visible:
                widget.pack(side=tk.RIGHT, padx=(8, 0))
            else:
                widget.pack_forget()

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
        if self.options_workers_label is not None:
            self.options_workers_label.configure(text=self._tr("opts_workers"))
        if self.options_workers_hint_label is not None:
            self.options_workers_hint_label.configure(text=self._tr("opts_workers_hint"))
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
        if self.status_report_link is not None:
            self.status_report_link.configure(text=self._tr("status_open_report_link"))
        if self.status_folder_link is not None:
            self.status_folder_link.configure(text=self._tr("status_open_folder_link"))
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
        if "0" in self.worker_chips:
            self.worker_chips["0"].configure(text=self._tr("workers_auto"))
        self._update_lang_buttons()
        self._draw_drop_zone()
        self._refresh_drop_badges()
        self._refresh_file_cards()
        self._refresh_option_values()
        self._update_history_filter_buttons()
        self._refresh_status_links()
        self._refresh_history_table()

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.configure("TFrame", background=BG_WINDOW)
        style.configure("Header.TLabel", font=("Segoe UI", 18, "normal"), foreground=TEXT_PRIMARY, background=BG_WINDOW)
        style.configure("SubHeader.TLabel", font=("Segoe UI", 10), foreground=TEXT_SECONDARY, background=BG_WINDOW)
        style.configure("Hint.TLabel", font=("Segoe UI", 9), foreground=TEXT_TERTIARY, background=BG_WINDOW)
        style.configure("FileLabel.TLabel", font=("Segoe UI", 10, "bold"), foreground=TEXT_PRIMARY, background=BG_CARD)
        style.configure("Red.TLabel", font=("Segoe UI", 10, "bold"), foreground=OLD_DOT, background=BG_CARD)
        style.configure("Green.TLabel", font=("Segoe UI", 10, "bold"), foreground=NEW_DOT, background=BG_CARD)
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), foreground=BG_CARD, background=ACCENT, padding=(12, 8))
        style.configure("Small.TButton", font=("Segoe UI", 9), padding=(10, 5))
        style.configure("Pill.TLabel", font=("Segoe UI", 9, "bold"))
        style.configure("Path.TEntry", fieldbackground=BG_SOFT, borderwidth=0)
        style.configure("Horizontal.TProgressbar", troughcolor=BG_INFO, background=ACCENT, borderwidth=0)
        style.configure("TNotebook", background=BG_WINDOW, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            padding=(14, 8),
            font=("Segoe UI", 10),
            background=BG_WINDOW,
            foreground=TEXT_SECONDARY,
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG_WINDOW)],
            foreground=[("selected", TEXT_PRIMARY)],
            font=[("selected", ("Segoe UI", 10, "bold"))],
        )
        style.configure(
            "History.Treeview",
            background=BG_CARD,
            fieldbackground=BG_CARD,
            foreground=TEXT_PRIMARY,
            rowheight=44,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure(
            "History.Treeview.Heading",
            background=BG_WINDOW,
            foreground=TEXT_SECONDARY,
            font=("Segoe UI", 9),
            relief="flat",
            borderwidth=0,
        )
        style.map("History.Treeview", background=[("selected", BG_INFO)], foreground=[("selected", TEXT_PRIMARY)])

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

        tk.Label(
            right_top,
            text="⚙",
            width=3,
            height=1,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            relief="solid",
            bd=1,
            font=("Segoe UI", 12),
        ).pack(side=tk.RIGHT, padx=(8, 6))

        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill=tk.BOTH, expand=True)
        self.compare_tab = ttk.Frame(self.tabs, padding=14)
        self.history_tab = ttk.Frame(self.tabs, padding=0)
        self.rerender_tab = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(self.compare_tab, text=self._tr("tab_compare"))
        self.tabs.add(self.history_tab, text=self._history_tab_text())
        self.tabs.add(self.rerender_tab, text=self._tr("tab_rerender"))

        files_row = tk.Frame(self.compare_tab, bg=BG_WINDOW)
        files_row.pack(fill=tk.X, pady=(0, 12))
        files_row.columnconfigure(0, weight=1, uniform="files")
        files_row.columnconfigure(2, weight=1, uniform="files")
        self.old_entry = self._build_file_card(files_row, self.old_pdf, old=True)
        self.old_entry.grid(row=0, column=0, sticky="nsew")
        swap_box = tk.Frame(files_row, bg=BG_WINDOW, width=36)
        swap_box.grid(row=0, column=1, sticky="ns", padx=10)
        self.swap_btn = ttk.Button(swap_box, text="⇅", width=3, style="Small.TButton", command=self._swap_files)
        self.swap_btn.pack(expand=True)
        self.new_entry = self._build_file_card(files_row, self.new_pdf, old=False)
        self.new_entry.grid(row=0, column=2, sticky="nsew")

        self.drop_canvas = tk.Frame(self.compare_tab, bg=BG_WINDOW, highlightthickness=1, highlightbackground=BORDER_THIN)
        self.drop_canvas.pack(fill=tk.X, pady=(0, 14))
        ttk.Label(self.drop_canvas, text=self._tr("drop_hint"), style="Hint.TLabel").pack(anchor="w", padx=12, pady=8)

        out_wrap = tk.Frame(self.compare_tab, bg=BG_WINDOW)
        out_wrap.pack(fill=tk.X, pady=(0, 14))
        self.out_label = ttk.Label(out_wrap, text=self._tr("path_out"), style="SubHeader.TLabel")
        self.out_label.pack(anchor="w", pady=(0, 6))
        out_fields = tk.Frame(out_wrap, bg=BG_WINDOW)
        out_fields.pack(fill=tk.X)
        self.out_entry = ttk.Entry(out_fields, textvariable=self.out_dir, style="Path.TEntry")
        self.out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        self.out_pick_btn = ttk.Button(out_fields, text=self._tr("btn_select"), style="Small.TButton", command=self._pick_out_dir)
        self.out_pick_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.options_body = tk.Frame(self.compare_tab, bg=BG_SOFT, padx=14, pady=14)
        self.options_body.pack(fill=tk.X, pady=(0, 14))
        opts_head = tk.Frame(self.options_body, bg=BG_SOFT)
        opts_head.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(opts_head, text=self._tr("opts_group"), style="FileLabel.TLabel", background=BG_SOFT).pack(side=tk.LEFT)
        ttk.Label(opts_head, text=self._tr("opts_default"), style="Hint.TLabel", background=BG_SOFT).pack(side=tk.RIGHT)
        opts_grid = tk.Frame(self.options_body, bg=BG_SOFT)
        opts_grid.pack(fill=tk.X)
        for col in range(3):
            opts_grid.columnconfigure(col, weight=1, uniform="opts")
        self._build_scale_option(opts_grid, 0, "opts_dpi", self.dpi, self.dpi_value, 100, 400, 10)
        self._build_scale_option(opts_grid, 1, "opts_stroke", self.stroke_tol, self.stroke_value, 0, 10, 0.5)
        worker_frame = tk.Frame(opts_grid, bg=BG_SOFT)
        worker_frame.grid(row=0, column=2, sticky="ew", padx=(12, 0))
        self.options_workers_label = ttk.Label(worker_frame, text=self._tr("opts_workers"), style="SubHeader.TLabel", background=BG_SOFT)
        self.options_workers_label.pack(anchor="w", pady=(0, 6))
        chips = tk.Frame(worker_frame, bg=BG_SOFT)
        chips.pack(anchor="w")
        for value, label_key in (("0", "workers_auto"), ("1", None), ("4", None)):
            text = self._tr(label_key) if label_key else value
            chip = tk.Label(chips, text=text, padx=12, pady=4, bg=BG_CARD, fg=TEXT_SECONDARY, relief="solid", bd=1, cursor="hand2")
            chip.pack(side=tk.LEFT, padx=(0, 6))
            chip.bind("<Button-1>", lambda _e, v=value: self.workers.set(v))
            self.worker_chips[value] = chip
        self.options_workers_hint_label = ttk.Label(worker_frame, text=self._tr("opts_workers_hint"), style="Hint.TLabel", background=BG_SOFT)
        self.options_workers_hint_label.pack(anchor="w", pady=(8, 0))

        actions = tk.Frame(self.compare_tab, bg=BG_WINDOW)
        actions.pack(fill=tk.X, pady=(0, 14))
        self.run_btn = self._primary_button(actions, self._tr("btn_compare_short"), self.start_compare)
        self.run_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.from_history_btn = ttk.Button(
            actions, text=self._tr("btn_from_history"), style="Small.TButton", command=self._restore_last_inputs
        )
        self.from_history_btn.pack(side=tk.LEFT, padx=8)
        self.clear_btn = ttk.Button(actions, text=self._tr("btn_clear"), style="Small.TButton", command=self._clear_inputs)
        self.clear_btn.pack(side=tk.LEFT)
        self.open_report_btn = ttk.Button(
            actions,
            text=self._tr("btn_open_report"),
            style="Small.TButton",
            command=self._open_report,
            state=tk.DISABLED,
        )
        self.open_report_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.open_run_btn = ttk.Button(
            actions,
            text=self._tr("btn_open_folder"),
            style="Small.TButton",
            command=self._open_run_folder,
            state=tk.DISABLED,
        )
        self.open_run_btn.pack(side=tk.LEFT, padx=(8, 0))

        status_panel = tk.Frame(self.compare_tab, bg=BG_INFO, padx=12, pady=10)
        status_panel.pack(fill=tk.X)
        tk.Canvas(status_panel, width=8, height=8, bg=BG_INFO, highlightthickness=0).pack(side=tk.LEFT, padx=(0, 10))
        status_panel.children[list(status_panel.children.keys())[0]].create_oval(1, 1, 7, 7, fill=ACCENT, outline=ACCENT)
        self.status_text_label = tk.Label(status_panel, textvariable=self.status, bg=BG_INFO, fg=ACCENT_DARK, anchor="w", font=("Segoe UI", 9))
        self.status_text_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progress = ttk.Progressbar(status_panel, mode="determinate", maximum=100, style="Horizontal.TProgressbar")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        self.progress.pack_forget()
        ttk.Label(status_panel, textvariable=self.elapsed, width=7, anchor="e", background=BG_INFO).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(status_panel, textvariable=self.progress_pct, width=6, anchor="e", background=BG_INFO).pack(side=tk.LEFT, padx=(4, 0))
        self.status_report_link = tk.Label(status_panel, text=self._tr("status_open_report_link"), bg=BG_INFO, fg=ACCENT, cursor="hand2", font=("Segoe UI", 9))
        self.status_report_link.pack(side=tk.RIGHT, padx=(8, 0))
        self.status_report_link.bind("<Button-1>", lambda _e: self._open_report())
        self.status_folder_link = tk.Label(status_panel, text=self._tr("status_open_folder_link"), bg=BG_INFO, fg=ACCENT, cursor="hand2", font=("Segoe UI", 9))
        self.status_folder_link.pack(side=tk.RIGHT, padx=(8, 0))
        self.status_folder_link.bind("<Button-1>", lambda _e: self._open_run_folder())

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
            btn = tk.Label(hist_tools, text=self._tr(key), padx=12, pady=6, bg=BG_CARD, fg=TEXT_SECONDARY, relief="solid", bd=1, cursor="hand2")
            btn.pack(side=tk.LEFT, padx=(8, 0))
            btn.bind("<Button-1>", lambda _e, v=value: self._set_history_filter(v))
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

        self._build_rerender_tab()
        self._update_lang_buttons()
        self._apply_locale()

    def _build_rerender_tab(self) -> None:
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

    def _load_current_rerender_report(self) -> None:
        if self.last_run_dir:
            self.rerender_run_dir.set(str(self.last_run_dir))
        self._load_rerender_report()

    def _pick_rerender_run_dir(self) -> None:
        start_dir = self.rerender_run_dir.get().strip() or (str(self.last_run_dir) if self.last_run_dir else self.out_dir.get().strip())
        folder = filedialog.askdirectory(title=self._tr("rerender_run"), initialdir=start_dir if start_dir else None)
        if folder:
            self.rerender_run_dir.set(folder)
            self._load_rerender_report()

    def _load_rerender_report(self, run_dir: Path | None = None, quiet: bool = False) -> None:
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
            elapsed_text = f"{float(elapsed):.1f}s" if elapsed not in (None, "") else ""
            diff = row.get("diff_percent")
            diff_text = "" if diff in (None, "") else f"{float(diff):.3f}"
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

    def _start_rerender_selected(self) -> None:
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

    def _rerender_worker(self, run_dir: Path, seqs: list[int], dpi: int, workers: int) -> None:
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
        button.bind("<Enter>", lambda _e, w=button: self._set_primary_hover(w, True))
        button.bind("<Leave>", lambda _e, w=button: self._set_primary_hover(w, False))
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
        name = Path(path_text).name
        m = re.search(r"r[Cc](\d{2,3})", name)
        return f"v.C{m.group(1)}" if m else ""

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
            variable=var,
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

    def _update_worker_chips(self) -> None:
        current = self.workers.get().strip() or "0"
        for value, widget in self.worker_chips.items():
            active = value == current
            widget.configure(fg=ACCENT if active else TEXT_SECONDARY, relief="solid", bd=2 if active else 1)

    def _update_history_filter_buttons(self) -> None:
        current = self.history_filter.get()
        for value, widget in self.history_filter_buttons.items():
            active = value == current
            widget.configure(fg=ACCENT if active else TEXT_SECONDARY, bd=2 if active else 1)

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
        self._update_worker_chips()

    def _bind_input_tracking(self) -> None:
        for var in (self.old_pdf, self.new_pdf, self.out_dir, self.dpi, self.stroke_tol, self.workers):
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

    def _capture_inputs(self) -> dict[str, Any]:
        return {
            "old_pdf": self.old_pdf.get().strip(),
            "new_pdf": self.new_pdf.get().strip(),
            "out_dir": self.out_dir.get().strip(),
            "dpi": self.dpi.get().strip(),
            "stroke_tol": self.stroke_tol.get().strip(),
            "workers": self.workers.get().strip(),
            "last_run_dir": str(self.last_run_dir) if self.last_run_dir else "",
        }

    def _apply_inputs(self, data: dict[str, Any]) -> None:
        self.old_pdf.set(str(data.get("old_pdf") or ""))
        self.new_pdf.set(str(data.get("new_pdf") or ""))
        self.out_dir.set(str(data.get("out_dir") or ""))
        self.dpi.set(str(data.get("dpi") or "250"))
        self.stroke_tol.set(str(data.get("stroke_tol") or "2.0"))
        self.workers.set(str(data.get("workers") or "0"))
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
                "workers": snap.get("workers", ""),
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
        if self.open_report_btn is not None:
            self.open_report_btn.configure(state=tk.DISABLED)
        if self.open_run_btn is not None:
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
            workers = int(self.workers.get().strip() or "0")
        except ValueError:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_parse"))
            return

        if dpi < 72:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_dpi"))
            return
        # Guard against accidental huge values that can exhaust memory.
        if dpi > 1200:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_dpi"))
            return
        if stroke_tol < 0:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_stroke"))
            return
        if workers < 0:
            messagebox.showerror(self._tr("err_invalid_option_title"), self._tr("err_invalid_option_workers"))
            return

        self.last_inputs = self._capture_inputs()
        self._save_state()
        self.cancel_requested.clear()
        self.last_run_dir = None
        self._refresh_status_links()
        self._set_running(True)
        self._set_status("status_running")
        t = threading.Thread(
            target=self._run_worker,
            args=(old, new, out_path, dpi, stroke_tol, workers, self.lang.get()),
            daemon=True,
        )
        self.worker_thread = t
        t.start()

    def _run_worker(self, old: Path, new: Path, out_path: Path, dpi: int, stroke_tol: float, workers: int, report_lang: str) -> None:
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
                workers=workers,
                progress_cb=report_progress,
            )
            if self.cancel_requested.is_set():
                self.worker_events.put(("cancelled", old, new, out_path, dpi, stroke_tol, workers))
                return
            self.worker_events.put(("done", run_dir, old, new, out_path, dpi, stroke_tol, workers))
        except Exception as exc:
            if str(exc) == "__CANCELLED__":
                self.worker_events.put(("cancelled", old, new, out_path, dpi, stroke_tol, workers))
                return
            self.worker_events.put(("error", str(exc), traceback.format_exc(), old, new, out_path, dpi, stroke_tol, workers))

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
                        if self.open_report_btn is not None:
                            self.open_report_btn.configure(state=tk.NORMAL)
                        if self.open_run_btn is not None:
                            self.open_run_btn.configure(state=tk.NORMAL)
                        self._refresh_status_links()
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
                elif kind == "rerender_done":
                    run_dir: Path = event[1]
                    self.rerender_running = False
                    self.last_run_dir = run_dir
                    self.progress.configure(value=100.0)
                    self.progress_pct.set("100%")
                    if self.rerender_start_btn is not None:
                        self.rerender_start_btn.configure(state=tk.NORMAL)
                    if self.open_report_btn is not None:
                        self.open_report_btn.configure(state=tk.NORMAL)
                    if self.open_run_btn is not None:
                        self.open_run_btn.configure(state=tk.NORMAL)
                    self._load_rerender_report(run_dir, quiet=True)
                    self._set_status("status_rerender_done")
                    self._refresh_status_links()
                    messagebox.showinfo(
                        self._tr("dlg_done_title"),
                        self._tr("dlg_rerender_done_body", report=run_dir / START_REPORT_FILE),
                    )
                elif kind == "rerender_error":
                    self.rerender_running = False
                    if self.rerender_start_btn is not None:
                        self.rerender_start_btn.configure(state=tk.NORMAL)
                    err = event[1]
                    tb = event[2]
                    self._set_status("status_error", error=err)
                    messagebox.showerror(self._tr("dlg_error_title"), f"{err}\n\n{tb}")
                elif kind == "done":
                    run_dir: Path = event[1]
                    old, new, out_dir, dpi, stroke_tol, workers = event[2], event[3], event[4], event[5], event[6], event[7]
                    self.last_run_dir = run_dir
                    self._set_running(False)
                    self.progress.configure(value=100.0)
                    self.progress_pct.set("100%")
                    if self.open_report_btn is not None:
                        self.open_report_btn.configure(state=tk.NORMAL)
                    if self.open_run_btn is not None:
                        self.open_run_btn.configure(state=tk.NORMAL)
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
                            "workers": str(workers),
                            "run_dir": str(run_dir),
                        }
                    )
                    self._load_rerender_report(run_dir, quiet=True)
                    messagebox.showinfo(self._tr("dlg_done_title"), self._tr("dlg_done_body", run_dir=run_dir))
                elif kind == "cancelled":
                    old, new, out_dir, dpi, stroke_tol, workers = event[1], event[2], event[3], event[4], event[5], event[6]
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
                            "workers": str(workers),
                            "run_dir": "",
                        }
                    )
                elif kind == "error":
                    self._set_running(False)
                    err = event[1]
                    tb = event[2]
                    old, new, out_dir, dpi, stroke_tol, workers = event[3], event[4], event[5], event[6], event[7], event[8]
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
                            "workers": str(workers),
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
            self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
            self.progress_pct.set("0%")
            self.elapsed.set("00:00")
            self._run_started_monotonic = time.monotonic()
            self._start_timer()
            self._set_primary_state(self.run_btn, tk.NORMAL)
            self.run_btn.configure(command=self._request_cancel)
            self.run_btn.configure(text=self._tr("btn_cancel"))
            if self.open_report_btn is not None:
                self.open_report_btn.configure(state=tk.DISABLED)
            if self.open_run_btn is not None:
                self.open_run_btn.configure(state=tk.DISABLED)
        else:
            self._stop_timer()
            self.cancel_requested.clear()
            self.worker_thread = None
            self.progress.pack_forget()
            self.run_btn.configure(command=self.start_compare)
            self.run_btn.configure(text=self._tr("btn_compare_short"))
            self._update_run_availability()
        self._refresh_status_links()

    def _open_report(self) -> None:
        if not self.last_run_dir:
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
    multiprocessing.freeze_support()
    main()
