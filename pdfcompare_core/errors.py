"""User-facing errors, in both interface languages.

The engine used to raise Russian-only text, which the English interface then
showed verbatim — a bilingual app with monolingual failures. Errors a *user* can
trigger (bad DPI, a malformed zone, a missing report, a path outside the MCP
allowlist) now carry a key and their parameters, so the GUI/CLI/MCP can render
them in the language they are running in. ``str(exc)`` stays Russian, so anything
that just logs the exception — worker tracebacks, ``worker.log`` — behaves as
before, and existing diagnostics keep matching.

Internal invariants ("unsafe sheet path", "staging dir not built") are *not*
here on purpose: they mean the program is broken, not that the user did
something wrong, and translating them would only add churn.
"""

from __future__ import annotations

from typing import Any

ERROR_MESSAGES: dict[str, dict[str, str]] = {
    "ru": {
        # --- run name ---
        "run_name_empty": "Имя папки сравнения не может быть пустым",
        "run_name_not_a_name": "Имя папки сравнения должно быть одним именем, без пути: {name}",
        "run_name_trailing": "Имя папки сравнения не должно заканчиваться пробелом или точкой",
        "run_name_reserved": "Зарезервированное имя папки Windows: {name}",
        "run_name_too_long": "Имя папки сравнения не должно быть длиннее {limit} символов",
        # --- render settings ---
        "dpi_not_int": "DPI должен быть целым числом, получено: {value!r}",
        "dpi_out_of_range": "DPI должен быть в диапазоне {min}–{max}, получено: {value}",
        "dpi_not_positive": "DPI должен быть положительным: {value!r}",
        "strictness_invalid": "Некорректная строгость сравнения: {value!r}. Допустимо: {allowed}",
        # --- input files / run folder ---
        "input_pdf_count": "Ожидалось ровно 2 PDF-файла в {folder}, найдено {count}",
        "run_dir_exists": "Папка результата уже существует: {path}",
        "run_dir_create_failed": "Не удалось создать папку результата: {path}",
        # --- existing report (re-render) ---
        "summary_missing": "Не найден summary.json: {path}",
        "pages_dir_missing": "Не найдена папка pages: {path}",
        "source_pdfs_missing": "Исходные PDF из summary.json не найдены на диске",
        "summary_no_pages": "В summary.json нет данных по листам",
        "no_pages_selected": "Не выбраны листы для перегенерации",
        "no_page_settings": "Не переданы настройки страниц для перегенерации",
        "pages_not_in_report": "Не найдены листы в отчёте: {seqs}",
        "page_not_in_report": "Не найден лист в отчёте: {seq}",
        "page_seq_invalid": "Некорректный номер листа в summary.json: {value!r}",
        "page_settings_not_object": "Каждая настройка страницы должна быть объектом",
        "page_settings_no_seq": "В настройке страницы нет seq/seqs",
        "page_settings_bad_seq": "Некорректный номер строки отчёта: {value!r}",
        "page_settings_duplicate": "Повторная настройка для seq={seq}",
        # --- exclusion zones ---
        "zones_bad_json": "Некорректный JSON исключений: {error}",
        "zones_not_a_list": "Исключаемые области должны быть списком или строкой",
        "zone_bad_anchor": "Некорректная привязка исключаемой области: {anchor}",
        "zone_text_format": "Область #{idx}: нужен формат x,y,w,h в процентах",
        "zone_bad_shape": "Область #{idx}: нужен объект {{x,y,w,h}} или список из 4 чисел",
        "zone_not_numbers": "Область #{idx}: x,y,w,h должны быть числами",
        "zone_bad_unit": "Область #{idx}: неизвестная единица {unit!r}. Допустимо: percent, %, mm, px, ratio",
        "zone_negative": "Область #{idx}: x/y должны быть >= 0, w/h > 0",
        "zone_out_of_range": "Область #{idx}: координаты должны помещаться в диапазон {range}",
        # --- diff ---
        "raster_size_mismatch": "Разные размеры растра: A={a_w}x{a_h}, B={b_w}x{b_h}",
        # --- CLI ---
        "cli_old_new_together": "Укажите оба параметра --old и --new (либо ни одного, чтобы использовать --input-dir)",
        # --- MCP boundary ---
        "path_empty": "Путь не может быть пустым",
        "path_not_found": "Путь не найден: {path}",
        "path_outside_allowlist": "Путь вне разрешённых каталогов (PDFCOMPARE_MCP_ALLOWED_DIRS): {path}",
        "job_id_invalid": "Некорректный job_id: {job_id}",
        "job_not_found": "Задача не найдена: {job_id}",
        "job_limit_reached": "Достигнут лимит активных MCP-сравнений: {limit}",
        "job_not_running": "Задача уже не выполняется: {job_id}",
        "job_no_pid": "У задачи нет PID: {job_id}",
        "job_pid_foreign": "PID больше не похож на worker PDFCompare для задачи: {job_id}",
        "rerender_need_seqs": "Передайте seqs или page_settings",
        "page_settings_not_list": "page_settings должен быть списком объектов",
        "page_number_min": "page_number должен быть >= 1",
    },
    "en": {
        "run_name_empty": "The comparison folder name cannot be empty",
        "run_name_not_a_name": "The comparison folder name must be a single name, not a path: {name}",
        "run_name_trailing": "The comparison folder name must not end with a space or a dot",
        "run_name_reserved": "Reserved Windows folder name: {name}",
        "run_name_too_long": "The comparison folder name must not exceed {limit} characters",
        "dpi_not_int": "DPI must be an integer, got: {value!r}",
        "dpi_out_of_range": "DPI must be between {min} and {max}, got: {value}",
        "dpi_not_positive": "DPI must be positive: {value!r}",
        "strictness_invalid": "Invalid diff strictness: {value!r}. Allowed: {allowed}",
        "input_pdf_count": "Expected exactly 2 PDF files in {folder}, found {count}",
        "run_dir_exists": "The result folder already exists: {path}",
        "run_dir_create_failed": "Could not create the result folder: {path}",
        "summary_missing": "summary.json not found: {path}",
        "pages_dir_missing": "The pages folder was not found: {path}",
        "source_pdfs_missing": "The source PDFs listed in summary.json are missing from disk",
        "summary_no_pages": "summary.json contains no sheet data",
        "no_pages_selected": "No sheets selected for re-rendering",
        "no_page_settings": "No per-page settings were given for re-rendering",
        "pages_not_in_report": "Sheets not found in the report: {seqs}",
        "page_not_in_report": "Sheet not found in the report: {seq}",
        "page_seq_invalid": "Invalid sheet number in summary.json: {value!r}",
        "page_settings_not_object": "Every page setting must be an object",
        "page_settings_no_seq": "A page setting has no seq/seqs",
        "page_settings_bad_seq": "Invalid report row number: {value!r}",
        "page_settings_duplicate": "Duplicate settings for seq={seq}",
        "zones_bad_json": "Invalid exclusion JSON: {error}",
        "zones_not_a_list": "Exclusion regions must be a list or a string",
        "zone_bad_anchor": "Invalid exclusion region anchor: {anchor}",
        "zone_text_format": "Region #{idx}: expected x,y,w,h in percent",
        "zone_bad_shape": "Region #{idx}: expected an object {{x,y,w,h}} or a list of 4 numbers",
        "zone_not_numbers": "Region #{idx}: x,y,w,h must be numbers",
        "zone_bad_unit": "Region #{idx}: unknown unit {unit!r}. Allowed: percent, %, mm, px, ratio",
        "zone_negative": "Region #{idx}: x/y must be >= 0 and w/h > 0",
        "zone_out_of_range": "Region #{idx}: coordinates must fit within {range}",
        "raster_size_mismatch": "Raster sizes differ: A={a_w}x{a_h}, B={b_w}x{b_h}",
        "cli_old_new_together": "Pass both --old and --new (or neither, to use --input-dir)",
        "path_empty": "The path cannot be empty",
        "path_not_found": "Path not found: {path}",
        "path_outside_allowlist": "Path outside the allowed directories (PDFCOMPARE_MCP_ALLOWED_DIRS): {path}",
        "job_id_invalid": "Invalid job_id: {job_id}",
        "job_not_found": "Job not found: {job_id}",
        "job_limit_reached": "Active MCP comparison limit reached: {limit}",
        "job_not_running": "The job is no longer running: {job_id}",
        "job_no_pid": "The job has no PID: {job_id}",
        "job_pid_foreign": "The PID no longer looks like a PDFCompare worker for this job: {job_id}",
        "rerender_need_seqs": "Pass seqs or page_settings",
        "page_settings_not_list": "page_settings must be a list of objects",
        "page_number_min": "page_number must be >= 1",
    },
}

DEFAULT_LANG = "ru"


def _render(key: str, lang: str, params: dict[str, Any]) -> str:
    table = ERROR_MESSAGES.get(lang) or ERROR_MESSAGES[DEFAULT_LANG]
    template = table.get(key) or ERROR_MESSAGES[DEFAULT_LANG].get(key)
    if template is None:
        return key
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        return template


class PDFCompareError(Exception):
    """An error the user can act on, renderable in either language."""

    def __init__(self, key: str, **params: Any) -> None:
        self.key = key
        self.params = params
        super().__init__(_render(key, DEFAULT_LANG, params))

    def localized(self, lang: str) -> str:
        return _render(self.key, "en" if str(lang).lower().startswith("en") else "ru", self.params)


class InvalidInput(PDFCompareError, ValueError):
    """Bad value (DPI, strictness, a zone). Kept a ValueError: callers catch that."""


class RunFailed(PDFCompareError, RuntimeError):
    """The run cannot proceed (missing report, folder taken). Kept a RuntimeError."""


def localize_error(exc: BaseException, lang: str) -> str:
    """Message for the UI: translated when we own the error, str() otherwise."""
    if isinstance(exc, PDFCompareError):
        return exc.localized(lang)
    return str(exc)
