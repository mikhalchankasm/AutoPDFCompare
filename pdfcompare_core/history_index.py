"""Global, install-independent comparison history shared by the GUI and the MCP server.

Both stores live under ``~/.pdfcompare_local/`` — the user's home, never inside
a repo checkout — so a fresh MCP clone or a GUI reinstall keeps the whole record.
The GUI already owns ``state.json`` (its History tab); the MCP server appends to
``mcp_history.json`` right beside it. :func:`list_records` merges the two into one
chronological, numbered view, and every row carries enough of the original inputs
to be re-run (see :func:`restore params <normalize_record>`).

Why a separate MCP file instead of writing into the GUI's ``state.json``: the GUI
rewrites that file wholesale on every input change, so a second writer would race
it and lose records. Keeping the MCP log in its own file makes each side an
append-only owner of its own data; merging happens only on read.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

STATE_DIR = Path.home() / ".pdfcompare_local"
UI_STATE_PATH = STATE_DIR / "state.json"
MCP_HISTORY_PATH = STATE_DIR / "mcp_history.json"

# The GUI caps its own history at 300 (pdfcompare_ui/state_persistence.py); match
# it so neither file grows without bound.
MAX_MCP_RECORDS = 300

_TRUE_STRINGS = {"on", "1", "true", "yes", "да"}
# Canonical result labels. The GUI writes "ok"/"error"/"snapshot"; the worker
# writes "completed"/"failed". Everything is folded onto these four.
_RESULT_ALIASES = {
    "ok": "done",
    "done": "done",
    "completed": "done",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "error": "failed",
    "failed": "failed",
    "snapshot": "snapshot",
}


def _as_float(value: Any, default: float) -> float:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in _TRUE_STRINGS


def _load_history(path: Path, key: str | None) -> list[dict[str, Any]]:
    """Read a history list from ``path``.

    ``key`` selects a field inside a top-level object (the GUI's ``state.json``
    keeps history under ``"history"``); ``None`` means the file itself is the
    ``{"history": [...]}`` object we write. Any read/parse failure yields ``[]`` —
    history is a convenience, never a hard dependency.
    """
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if key is not None:
        container = data.get(key) if isinstance(data, dict) else None
    else:
        container = data.get("history") if isinstance(data, dict) else data
    if not isinstance(container, list):
        return []
    return [row for row in container if isinstance(row, dict)]


def read_ui_records() -> list[dict[str, Any]]:
    """Raw history rows the GUI persisted to ``state.json``."""
    return _load_history(UI_STATE_PATH, key="history")


def read_mcp_records() -> list[dict[str, Any]]:
    """Raw history rows the MCP worker appended to ``mcp_history.json``."""
    return _load_history(MCP_HISTORY_PATH, key="history")


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # os.replace can transiently fail on Windows with PermissionError when an
    # antivirus or the search indexer holds the destination open for a moment;
    # a few short retries clear it. On final failure drop the temp file rather
    # than leave litter, and re-raise for the caller's best-effort handling.
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 4:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05 * (attempt + 1))


def append_mcp_record(record: dict[str, Any]) -> None:
    """Append one comparison to the global MCP history (read-modify-write, atomic).

    Callers must treat this as best-effort: it is invoked from the worker's
    terminal path, where an I/O error must never mask the run's real outcome, so
    wrap the call in a ``try/except`` there.
    """
    history = read_mcp_records()
    history.append(record)
    if len(history) > MAX_MCP_RECORDS:
        history = history[-MAX_MCP_RECORDS:]
    _atomic_write(MCP_HISTORY_PATH, {"history": history})


def _stable_id(source: str, record: dict[str, Any]) -> str:
    """A short id that stays the same across listings.

    MCP rows already own a unique ``job_id`` (timestamp + uuid); reuse it. GUI
    rows have none, so hash the fields that identify the run — a re-listing of the
    same record always produces the same id, which is what ``restore`` keys on.
    """
    if source == "mcp":
        job_id = str(record.get("job_id") or "").strip()
        if job_id:
            return f"mcp:{job_id}"
    seed = "|".join(
        str(record.get(field) or "")
        for field in ("ts", "old_pdf", "new_pdf", "out_dir", "run_dir", "result")
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]  # noqa: S324 — id, not a security hash
    return f"{source}:{digest}"


def _replay_params(source: str, record: dict[str, Any]) -> dict[str, Any]:
    """The inputs needed to re-run a comparison, in start_pdf_comparison's shape.

    The GUI and the MCP server store the same settings under different names and
    types (the GUI keeps a bbox_merge on/off toggle plus a gap; the server keeps a
    single gap where 0 means off), so each source is mapped explicitly.
    """
    if source == "ui":
        merge_on = _as_bool(record.get("bbox_merge"))
        gap = _as_float(record.get("bbox_merge_gap"), 5.0) if merge_on else 0.0
        return {
            "dpi": _as_int(record.get("dpi"), 250),
            "stroke_tol": _as_float(record.get("stroke_tol"), 2.0),
            "diff_strictness": str(record.get("diff_strictness") or "normal"),
            "exclude_regions": record.get("exclude_regions") or "",
            "bbox_merge_gap_mm": gap,
            "bbox_merge_max_area_ratio": _as_float(record.get("bbox_merge_max_ratio"), 16.0),
            "keep_debug_images": _as_bool(record.get("keep_debug")),
            "ignore_line_weight": _as_bool(record.get("ignore_line_weight")),
        }
    return {
        "dpi": _as_int(record.get("dpi"), 250),
        "stroke_tol": _as_float(record.get("stroke_tol"), 2.0),
        "diff_strictness": str(record.get("diff_strictness") or "normal"),
        "exclude_regions": record.get("exclude_regions") or "",
        "bbox_merge_gap_mm": _as_float(record.get("bbox_merge_gap_mm"), 0.0),
        "bbox_merge_max_area_ratio": _as_float(record.get("bbox_merge_max_area_ratio"), 16.0),
        "keep_debug_images": _as_bool(record.get("keep_debug_images")),
        "ignore_line_weight": _as_bool(record.get("ignore_line_weight")),
    }


def normalize_record(source: str, record: dict[str, Any]) -> dict[str, Any]:
    """One raw GUI/MCP row → the common, self-describing shape used everywhere."""
    raw_result = str(record.get("result") or "").strip().lower()
    return {
        "id": _stable_id(source, record),
        "source": source,
        "date": str(record.get("ts") or ""),
        "result": _RESULT_ALIASES.get(raw_result, raw_result or "unknown"),
        "old_pdf": str(record.get("old_pdf") or ""),
        "new_pdf": str(record.get("new_pdf") or ""),
        "out_dir": str(record.get("out_dir") or ""),
        "run_dir": str(record.get("run_dir") or ""),
        "run_name": str(record.get("run_name") or Path(str(record.get("run_dir") or "")).name),
        "replay": _replay_params(source, record),
    }


def list_records(limit: int = 50, source: str | None = None) -> list[dict[str, Any]]:
    """Merged GUI+MCP history, newest first, each row numbered from 1.

    The positional ``index`` is assigned over the *full* sorted list before any
    ``limit`` slice, so "#5" means the same record whether the caller asked for 5
    rows or 500 — as long as no new comparison has landed in between. ``source``
    ('ui'/'mcp') restricts the view to one origin.
    """
    merged: list[dict[str, Any]] = []
    if source in (None, "ui"):
        merged.extend(normalize_record("ui", row) for row in read_ui_records())
    if source in (None, "mcp"):
        merged.extend(normalize_record("mcp", row) for row in read_mcp_records())
    merged.sort(key=lambda row: row.get("date") or "", reverse=True)
    for position, row in enumerate(merged, start=1):
        row["index"] = position
    if limit and limit > 0:
        return merged[:limit]
    return merged


def find_record(ref: str | int, source: str | None = None) -> dict[str, Any] | None:
    """Resolve a reference to a history row: a stable id, or a positional '#N'.

    Id wins over number, so an unambiguous id is never shadowed by a stale index.
    """
    records = list_records(limit=0, source=source)
    ref_text = str(ref).strip()
    if not ref_text:
        return None
    for row in records:
        if row["id"] == ref_text:
            return row
    number = ref_text.lstrip("#").strip()
    if number.isdigit():
        wanted = int(number)
        for row in records:
            if row["index"] == wanted:
                return row
    return None
