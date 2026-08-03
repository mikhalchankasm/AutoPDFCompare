from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.process_identity import self_identity


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def publish_identity() -> None:
    """Say which process we are — before anything slow happens.

    The PID the server got back from Popen belongs to the venv's ``python.exe``
    launcher, not to us, so it waits on this file to learn the real one. That wait
    has to be short, and importing OpenCV and PyMuPDF below takes *seconds* — which
    is why this is a raw argv scan up here instead of a tidy argparse down in main().
    """
    if "--identity" not in sys.argv:
        return
    index = sys.argv.index("--identity") + 1
    if index >= len(sys.argv):
        return
    atomic_write_json(Path(sys.argv[index]), {**self_identity(), "recorded_at": now_iso()})


publish_identity()

from compare_pdfs import (  # noqa: E402  (deliberate: the identity must land first)
    LIVE_REPORT_EVENT_PREFIX,
    START_REPORT_FILE,
    RunCancelled,
    compare_pdfs,
    find_summary_json_path,
    localize_error,
    regenerate_report_pages_mixed,
    sanitize_run_folder_name,
)
from pdfcompare_core.history_index import append_mcp_record  # noqa: E402

HEARTBEAT_INTERVAL_SEC = 2.0


def start_heartbeat(path: Path) -> threading.Event:
    """Touch a file every couple of seconds for as long as this process runs.

    Without it the MCP server cannot tell a worker that is *slow* from one that is
    *stuck*: a single A0 sheet at 600 DPI renders for longer than any sensible
    cancel grace, and killing it there aborts the re-render transaction halfway.
    The heartbeat is what buys a long, healthy phase the time it needs.
    """
    stop = threading.Event()

    def beat() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        while not stop.is_set():
            try:
                path.write_text(now_iso(), encoding="utf-8")
            except OSError:
                pass  # a heartbeat that cannot be written must not kill the run
            stop.wait(HEARTBEAT_INTERVAL_SEC)

    threading.Thread(target=beat, name="pdfcompare-heartbeat", daemon=True).start()
    return stop


def append_event(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_run(run_dir: Path) -> dict[str, Any]:
    summary_path = find_summary_json_path(run_dir)
    if not summary_path.exists():
        return {}

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    pairs = payload.get("pairs") or []
    counts = {
        "total": len(pairs),
        "matched": 0,
        "added": 0,
        "removed": 0,
        "unchanged": 0,
        "minor": 0,
        "moderate": 0,
        "major": 0,
    }
    for row in pairs:
        status = str(row.get("status") or "")
        if status in counts:
            counts[status] += 1
        level = str(row.get("change_level") or "")
        if level in counts:
            counts[level] += 1
    return {"summary_path": str(summary_path), "counts": counts}


def record_mcp_history(
    request: dict[str, Any], run_dir: Path | str, result: str, summary: dict[str, Any] | None = None
) -> None:
    """Append this comparison to the global, install-independent MCP history.

    The store lives in ~/.pdfcompare_local/ (see history_index), so it outlives a
    fresh MCP clone. A re-render edits an existing run in place rather than being a
    new comparison, so it is skipped. Best-effort by design: history is a
    convenience and must never turn a finished run into a failed one, so every
    error here is swallowed — the same stance the GUI takes in _save_state().
    """
    if str(request.get("operation") or "compare") != "compare":
        return
    try:
        counts = summary.get("counts") if isinstance(summary, dict) else None
        append_mcp_record(
            {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "result": result,
                "job_id": str(request.get("job_id") or ""),
                "old_pdf": str(request.get("old_path") or ""),
                "new_pdf": str(request.get("new_path") or ""),
                "out_dir": str(request.get("out_dir") or ""),
                "run_name": str(request.get("run_name") or ""),
                "run_dir": str(run_dir or ""),
                "dpi": request.get("dpi"),
                "stroke_tol": request.get("stroke_tol"),
                "diff_strictness": request.get("diff_strictness"),
                "exclude_regions": request.get("exclude_regions"),
                "bbox_merge_gap_mm": request.get("bbox_merge_gap_mm"),
                "bbox_merge_max_area_ratio": request.get("bbox_merge_max_area_ratio"),
                "keep_debug_images": request.get("keep_debug_images"),
                "ignore_line_weight": request.get("ignore_line_weight"),
                "created_at": request.get("created_at"),
                "completed_at": now_iso(),
                "counts": counts,
            }
        )
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Background PDFCompare worker")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--cancel", type=Path, required=False)
    parser.add_argument("--heartbeat", type=Path, required=False)
    parser.add_argument("--identity", type=Path, required=False)
    args = parser.parse_args()  # --identity was already acted on: see publish_identity()

    request = load_json(args.request)
    job_id = str(request["job_id"])
    lang = str(request.get("lang") or "ru")
    operation = str(request.get("operation") or "compare")
    if operation == "rerender":
        expected_run_dir = Path(str(request["run_dir"]))
        run_name = expected_run_dir.name
        output_dir = expected_run_dir.parent
        work_out_dir = output_dir / f".pdfcompare_mcp_{job_id}"
        old_path = str(request.get("old_path") or "")
        new_path = str(request.get("new_path") or "")
    else:
        run_name = sanitize_run_folder_name(str(request["run_name"]))
        output_dir = Path(request["out_dir"])
        expected_run_dir = output_dir / run_name
        work_out_dir = output_dir / f".pdfcompare_mcp_{job_id}"
        old_path = str(request["old_path"])
        new_path = str(request["new_path"])
    status: dict[str, Any] = {
        "job_id": job_id,
        "state": "running",
        "pid": os.getpid(),
        "progress": 0.0,
        "message": "Запуск перегенерации листов" if operation == "rerender" else "Запуск сравнения",
        "operation": operation,
        "old_path": old_path,
        "new_path": new_path,
        "out_dir": str(output_dir),
        "run_name": run_name,
        "created_at": request.get("created_at"),
        "started_at": now_iso(),
        "updated_at": now_iso(),
        "report_path": str(expected_run_dir / START_REPORT_FILE),
        "run_dir": str(expected_run_dir),
        "completed_pages": 0,
        "total_pages": None,
    }
    atomic_write_json(args.status, status)
    append_event(args.events, {"at": now_iso(), "state": "running", "message": status["message"]})

    if args.heartbeat:
        start_heartbeat(args.heartbeat)

    def is_cancelled() -> bool:
        """Cooperative cancel: the MCP server drops a marker file here.

        Killing the process outright would abort a re-render mid-transaction —
        after the new pages are swapped in but before summary/report are written —
        leaving the run inconsistent with no rollback. Polling a file lets the
        transaction unwind properly.

        Seeing the marker is also acknowledged in the status, so the server knows
        the cooperative path has engaged and that what follows is a rollback, not a
        hang. That is the difference between waiting and force-killing.
        """
        if not (args.cancel and args.cancel.exists()):
            return False
        if not status.get("cancel_acknowledged_at"):
            status["cancel_acknowledged_at"] = now_iso()
            status["message"] = "Отмена принята, откат изменений"
            status["updated_at"] = now_iso()
            atomic_write_json(args.status, status)
            append_event(
                args.events,
                {"at": status["updated_at"], "state": "cancelling", "message": status["message"]},
            )
        return True

    def update_progress(progress: float, message: str) -> None:
        display_message = message
        if message.startswith(LIVE_REPORT_EVENT_PREFIX):
            run_dir_text = message[len(LIVE_REPORT_EVENT_PREFIX) :]
            status["live_run_dir"] = run_dir_text
            status["live_report_path"] = str(Path(run_dir_text) / START_REPORT_FILE)
            status["report_path"] = status["live_report_path"]
            display_message = "Live-отчет создан"

        match = re.search(r"(\d+)\s*/\s*(\d+)", display_message)
        if match:
            status["completed_pages"] = int(match.group(1))
            status["total_pages"] = int(match.group(2))

        status["progress"] = round(float(progress), 2)
        status["message"] = display_message
        status["updated_at"] = now_iso()
        atomic_write_json(args.status, status)
        append_event(
            args.events,
            {
                "at": status["updated_at"],
                "state": status["state"],
                "progress": status["progress"],
                "message": display_message,
                "run_dir": status.get("run_dir"),
                "report_path": status.get("report_path"),
                "completed_pages": status.get("completed_pages"),
                "total_pages": status.get("total_pages"),
            },
        )

    try:
        if operation == "rerender":
            run_dir = regenerate_report_pages_mixed(
                expected_run_dir,
                request.get("page_settings") or [],
                high_dpi=int(request.get("dpi", 500)),
                stroke_tol_px=float(request["stroke_tol"]) if request.get("stroke_tol") is not None else None,
                diff_strictness=request.get("diff_strictness"),
                exclude_regions=request.get("exclude_regions"),
                bbox_merge_gap_mm=(
                    float(request["bbox_merge_gap_mm"]) if request.get("bbox_merge_gap_mm") is not None else None
                ),
                bbox_merge_max_area_ratio=(
                    float(request["bbox_merge_max_area_ratio"])
                    if request.get("bbox_merge_max_area_ratio") is not None
                    else None
                ),
                ignore_line_weight=request.get("ignore_line_weight"),
                report_lang=str(request.get("lang", "ru")),
                workers=int(request.get("workers", 0)),
                progress_cb=update_progress,
                cancel_cb=is_cancelled,
            )
        else:
            run_dir = compare_pdfs(
                Path(request["old_path"]),
                Path(request["new_path"]),
                work_out_dir,
                high_dpi=int(request.get("dpi", 250)),
                stroke_tol_px=float(request.get("stroke_tol", 2.0)),
                diff_strictness=str(request.get("diff_strictness") or "normal"),
                exclude_regions=request.get("exclude_regions") or [],
                report_lang=str(request.get("lang", "ru")),
                run_name=run_name,
                keep_debug_images=bool(request.get("keep_debug_images", False)),
                ignore_line_weight=bool(request.get("ignore_line_weight", False)),
                workers=int(request.get("workers", 0)),
                bbox_merge_gap_mm=float(request.get("bbox_merge_gap_mm", 0.0)),
                bbox_merge_max_area_ratio=float(request.get("bbox_merge_max_area_ratio", 16.0)),
                progress_cb=update_progress,
                cancel_cb=is_cancelled,
            )
            expected_run_dir.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(run_dir, expected_run_dir)
            except FileExistsError as exc:
                raise RuntimeError(f"Папка результата уже существует: {expected_run_dir}") from exc
            except OSError as exc:
                if expected_run_dir.exists():
                    raise RuntimeError(f"Папка результата уже существует: {expected_run_dir}") from exc
                raise
            try:
                work_out_dir.rmdir()
            except OSError:
                pass
            run_dir = expected_run_dir
        status.update(
            {
                "state": "completed",
                "progress": 100.0,
                "message": "Готово",
                "run_dir": str(run_dir),
                "report_path": str(run_dir / START_REPORT_FILE),
                "completed_at": now_iso(),
                "updated_at": now_iso(),
                "summary": summarize_run(run_dir),
            }
        )
        atomic_write_json(args.status, status)
        append_event(args.events, {"at": status["updated_at"], "state": "completed", "message": "Готово"})
        record_mcp_history(request, run_dir, "completed", status.get("summary"))
        return 0
    except RunCancelled:
        # The run rolled itself back; nothing half-applied is left behind.
        shutil.rmtree(work_out_dir, ignore_errors=True)
        status.update(
            {
                "state": "cancelled",
                "message": "Задача остановлена пользователем",
                "completed_at": now_iso(),
                "updated_at": now_iso(),
            }
        )
        atomic_write_json(args.status, status)
        append_event(args.events, {"at": status["updated_at"], "state": "cancelled", "message": status["message"]})
        record_mcp_history(request, "", "cancelled")
        return 0
    except Exception as exc:
        shutil.rmtree(work_out_dir, ignore_errors=True)
        # What the user reads is in the language they asked for; what a maintainer
        # reads — error_detail and the traceback — stays the original Russian text,
        # so existing log matching and diagnostics keep working.
        message = localize_error(exc, lang)
        status.update(
            {
                "state": "failed",
                "progress": status.get("progress", 0.0),
                "message": message,
                "error": message,
                "error_detail": str(exc),
                "traceback": traceback.format_exc(),
                "completed_at": now_iso(),
                "updated_at": now_iso(),
            }
        )
        atomic_write_json(args.status, status)
        append_event(
            args.events,
            {
                "at": status["updated_at"],
                "state": "failed",
                "message": message,
                "error_detail": str(exc),
            },
        )
        record_mcp_history(request, "", "failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
