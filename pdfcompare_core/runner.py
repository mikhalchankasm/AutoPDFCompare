"""Top-level comparison orchestrator and worker plumbing."""

from __future__ import annotations

import concurrent.futures
import csv
import gc
import json
import multiprocessing
import os
import re
import shutil
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import cv2
import fitz
import numpy as np

from .alignment import align_ecc, align_pages_v1
from .classification import classify
from .constants import APP_NAME, APP_VERSION, LIVE_REPORT_EVENT_PREFIX, MAX_RENDER_DPI, MIN_RENDER_DPI
from .diff_engine import DIFF_STRICTNESS_CHOICES, compute_diff_detailed, harmonize_canvas
from .exclusions import ExcludeRegion, exclusion_regions_to_pixel_boxes, normalize_exclude_regions
from .errors import InvalidInput, RunFailed
from .html_report import generate_html_report
from .live_report import format_eta, write_live_detail_view, write_live_html_report
from .markdown_report import write_engineer_report_md, write_summary_md
from .models import MatchPair
from .pdf_io import (
    atomic_write_text,
    build_page_info,
    capped_render_dpi,
    find_pages_dir,
    find_summary_json_path,
    imwrite_compat,
    internal_dir,
    page_map_csv_path,
    render_page,
    report_pages_dir,
    summary_json_path,
)

INVALID_RUN_NAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')

# How often the parent wakes up while pages are running, to notice cancellation
# even when no page has finished yet.
CANCEL_POLL_SECONDS = 0.25
MAX_RUN_FOLDER_NAME_LEN = 80
WINDOWS_RESERVED_RUN_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def sanitize_run_folder_name(raw_name: str) -> str:
    raw = str(raw_name or "")
    name = raw.strip()
    if not name:
        raise InvalidInput("run_name_empty")
    if INVALID_RUN_NAME_CHARS_RE.search(name) or Path(name).name != name or Path(name).is_absolute():
        raise InvalidInput("run_name_not_a_name", name=raw_name)
    if name != name.rstrip(" ."):
        raise InvalidInput("run_name_trailing")

    name = re.sub(r"\s+", "_", name, flags=re.UNICODE)
    name = re.sub(r"_+", "_", name).strip(" ._")
    if not name:
        raise InvalidInput("run_name_empty")
    if name in {".", ".."}:
        raise InvalidInput("run_name_not_a_name", name=raw_name)
    if name.split(".")[0].upper() in WINDOWS_RESERVED_RUN_NAMES:
        raise InvalidInput("run_name_reserved", name=name)
    if len(name) > MAX_RUN_FOLDER_NAME_LEN:
        raise InvalidInput("run_name_too_long", limit=MAX_RUN_FOLDER_NAME_LEN)
    return name


def build_run_dir(out_dir: Path, report_lang: str, run_name: str | None = None) -> Path:
    if run_name is not None and str(run_name).strip():
        return out_dir / sanitize_run_folder_name(run_name)

    # Generate human-readable folder name based on language.
    # Add a unique suffix so multiple runs within the same second don't collide.
    now = datetime.now()
    unique_suffix = uuid4().hex[:4]
    if report_lang == "ru":
        date_str = now.strftime("%d-%m-%Y")
        time_str = now.strftime("%H-%M-%S")
        return out_dir / f"Сравнение_{date_str}_{time_str}_{unique_suffix}"

    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M-%S")
    return out_dir / f"Comparison_{date_str}_{time_str}_{unique_suffix}"


def _quarantine_failed_run(run_dir: Path) -> None:
    """Rename a partial run to <name>.failed-<suffix> (best effort: delete)."""
    try:
        if not run_dir.exists():
            return
        suffix = f"failed-{datetime.now().strftime('%H%M%S')}_{uuid4().hex[:4]}"
        run_dir.rename(run_dir.with_name(f"{run_dir.name}.{suffix}"))
    except OSError:
        shutil.rmtree(run_dir, ignore_errors=True)


def validate_render_dpi(value: object) -> int:
    """Uniform DPI validation for GUI, CLI, MCP, and re-render paths."""
    try:
        dpi = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise InvalidInput("dpi_not_int", value=value) from exc
    if not (MIN_RENDER_DPI <= dpi <= MAX_RENDER_DPI):
        raise InvalidInput("dpi_out_of_range", min=MIN_RENDER_DPI, max=MAX_RENDER_DPI, value=dpi)
    return dpi


class RunCancelled(RuntimeError):
    """The run was cancelled by the user.

    Raised inside a page worker when it sees the shared cancel flag, and by the
    sequential path between phases of a page. Callers treat it as "cancelled",
    not as a failure.
    """


class CancelFlag(Protocol):
    """What a page worker needs from a cancel flag.

    In production this is a spawn-context ``multiprocessing.Event`` inherited by
    the pool workers (see ``_init_pool_worker``); on the sequential path it is a
    ``_CallbackCancelFlag`` wrapping the caller's predicate.
    """

    def is_set(self) -> bool: ...


class _CallbackCancelFlag:
    """Adapts a plain predicate (e.g. ``threading.Event.is_set``) to CancelFlag."""

    def __init__(self, check: Callable[[], bool]) -> None:
        self._check = check

    def is_set(self) -> bool:
        return bool(self._check())


# Set once per pool worker by _init_pool_worker(). A multiprocessing.Event cannot
# be pickled as a submit() argument under spawn — it can only cross the process
# boundary by inheritance, which is exactly what the pool's initargs do. (A
# Manager().Event() would pickle fine, but it costs an extra server process,
# which is one more thing to go wrong inside the frozen EXE.)
_WORKER_CANCEL_FLAG: CancelFlag | None = None


def _init_pool_worker(cancel_event: CancelFlag) -> None:
    global _WORKER_CANCEL_FLAG
    _WORKER_CANCEL_FLAG = cancel_event


def _run_pair_tasks(
    tasks: Sequence[tuple],
    worker_count: int,
    on_row: Callable[[dict], None],
    tick: Callable[[], None],
    cancel_cb: Callable[[], bool] | None = None,
) -> None:
    """Run the page tasks and hand every finished row to ``on_row``.

    Cancellation used to be noticed only when a page finished, because the
    parent blocked in ``as_completed`` and the cancel check lives in the
    progress callback. Now the parent wakes up every ``CANCEL_POLL_SECONDS`` to
    call ``tick()``, and the pages already running poll a shared flag between
    their expensive phases — so "Отмена" stops the run instead of grinding to
    the end of every started page.
    """
    if worker_count <= 1:
        flag = _CallbackCancelFlag(cancel_cb) if cancel_cb is not None else None
        for task in tasks:
            if flag is not None and flag.is_set():
                raise RunCancelled("Сравнение отменено пользователем")
            on_row(process_pair_task(*task, cancel_event=flag))
        return

    ctx = multiprocessing.get_context("spawn")
    cancel_event = ctx.Event()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=worker_count,
        mp_context=ctx,
        initializer=_init_pool_worker,
        initargs=(cancel_event,),
    ) as executor:
        pending = {executor.submit(process_pair_task, *task) for task in tasks}
        try:
            while pending:
                if cancel_cb is not None and cancel_cb():
                    raise RunCancelled("Сравнение отменено пользователем")
                done, pending = concurrent.futures.wait(
                    pending,
                    timeout=CANCEL_POLL_SECONDS,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                if not done:
                    tick()
                    continue
                for future in done:
                    on_row(future.result())
        except BaseException:
            # Tell the running pages to stop at their next phase boundary, then
            # drop everything still queued.
            cancel_event.set()
            for future in pending:
                future.cancel()
            raise


def resolve_worker_count(requested: int | None, total_pairs: int) -> int:
    if total_pairs <= 1:
        return 1
    cpu_count = os.cpu_count() or 1
    if requested is not None and requested > 0:
        return max(1, min(int(requested), total_pairs, cpu_count))
    return max(1, min(total_pairs, max(1, cpu_count - 1), 4))


def process_pair_task(
    file_a: Path,
    file_b: Path,
    pages_dir: Path,
    seq: int,
    a_idx: int | None,
    b_idx: int | None,
    status: str,
    score: float,
    high_dpi: int,
    stroke_tol_px: float,
    keep_debug_images: bool,
    exclude_regions: list[ExcludeRegion] | None = None,
    diff_strictness: str = "normal",
    bbox_merge_gap_mm: float = 0.0,
    bbox_merge_max_area_ratio: float = 16.0,
    ignore_line_weight: bool = False,
    limit_cv_threads: bool = False,
    *,
    cancel_event: CancelFlag | None = None,
) -> dict:
    started = time.monotonic()

    # In a pool worker the flag arrives via the initializer, not as an argument.
    flag = cancel_event if cancel_event is not None else _WORKER_CANCEL_FLAG

    def check_cancelled() -> None:
        """Bail out between phases: a single page at high DPI takes tens of
        seconds, so a page that is already running must be interruptible too."""
        if flag is not None and flag.is_set():
            raise RunCancelled(f"Лист {seq}: сравнение отменено пользователем")

    def remember_shape(img: np.ndarray) -> None:
        h, w = img.shape[:2]
        entry["width_px"] = int(w)
        entry["height_px"] = int(h)
        entry["pixel_count"] = int(w * h)

    def finish() -> dict:
        entry["elapsed_sec"] = round(time.monotonic() - started, 3)
        return entry

    if limit_cv_threads:
        try:
            cv2.setNumThreads(1)
        except Exception:
            pass

    a_page = None if a_idx is None else a_idx + 1
    b_page = None if b_idx is None else b_idx + 1
    pair_name = f"{seq:03d}__A_{a_page or 'NA'}__B_{b_page or 'NA'}"
    pair_dir = pages_dir / pair_name
    pair_dir.mkdir(parents=True, exist_ok=True)

    entry = {
        "seq": seq,
        "a_page": a_page,
        "b_page": b_page,
        "pair_dir": pair_name,
        "status": status,
        "score": float(score),
        "diff_percent": None,
        "change_level": None,
        "bboxes_count": None,
        "excluded_regions_count": 0,
        "diff_strictness": diff_strictness,
        "high_dpi": int(high_dpi),
        "effective_dpi": None,
        "stroke_tol_px": float(stroke_tol_px),
        "bbox_merge_gap_mm": float(bbox_merge_gap_mm),
        "bbox_merge_max_area_ratio": float(bbox_merge_max_area_ratio),
        "ignore_line_weight": bool(ignore_line_weight),
        "ecc_failed": False,
        "width_px": None,
        "height_px": None,
        "pixel_count": None,
        "diff_area_px": None,
        "diff_area_mm2": None,
        "diff_foreground_percent": None,
        "foreground_px": None,
        "added_px": None,
        "removed_px": None,
        "added_area_mm2": None,
        "removed_area_mm2": None,
        "max_region_area_mm2": None,
        "foreground_sparse": None,
        "elapsed_sec": None,
    }

    with fitz.open(file_a) as doc_a, fitz.open(file_b) as doc_b:
        if status == "matched" and a_idx is not None and b_idx is not None:
            # Shared effective DPI for the pair: the megapixel cap is applied
            # BEFORE rendering, and every physical metric downstream (mm zones,
            # bbox gap, mm² areas) must use the DPI the rasters actually have —
            # not the requested one, which the cap may have reduced.
            effective_dpi = min(
                capped_render_dpi(doc_a[a_idx], high_dpi),
                capped_render_dpi(doc_b[b_idx], high_dpi),
            )
            entry["effective_dpi"] = round(float(effective_dpi), 2)
            check_cancelled()
            a_img = render_page(doc_a, a_idx, effective_dpi)
            check_cancelled()
            b_img = render_page(doc_b, b_idx, effective_dpi)
            check_cancelled()
            remember_shape(a_img)
            # Page matching has already established strong revision identity.
            # A drawing may be republished on a larger same-aspect sheet (for
            # example A1 -> A0), so normalize both rasters to the smaller one
            # before registration and diffing instead of reporting two sheets.
            harmonized = harmonize_canvas(a_img, b_img, allow_scale=True)
            if harmonized is None:
                entry["status"] = "size_mismatch"
                entry["change_level"] = "size_mismatch"
                imwrite_compat(pair_dir / "a.png", a_img)
                imwrite_compat(pair_dir / "b.png", b_img)
                return finish()

            a_h, b_h = harmonized
            b_aligned, ecc_ok = align_ecc(a_h, b_h)
            entry["ecc_failed"] = not ecc_ok
            check_cancelled()
            pixel_exclusions = exclusion_regions_to_pixel_boxes(
                exclude_regions or [], a_h.shape[1], a_h.shape[0], dpi=effective_dpi
            )
            bbox_merge_gap_px = int(round(max(0.0, float(bbox_merge_gap_mm)) * float(effective_dpi) / 25.4))
            mask, overlay, bboxes, metrics = compute_diff_detailed(
                a_h,
                b_aligned,
                stroke_tol_px=stroke_tol_px,
                exclude_regions=exclude_regions,
                diff_strictness=diff_strictness,
                render_dpi=effective_dpi,
                bbox_merge_gap_px=bbox_merge_gap_px,
                bbox_merge_max_area_ratio=bbox_merge_max_area_ratio,
                ignore_line_weight=ignore_line_weight,
            )
            diff_percent = float(metrics["diff_percent"])
            level = classify(
                diff_percent,
                len(bboxes),
                diff_foreground_percent=float(metrics["diff_foreground_percent"]),
                foreground_sparse=bool(metrics["foreground_sparse"]),
                max_region_area_mm2=float(metrics["max_region_area_mm2"]),
                diff_area_mm2=float(metrics["diff_area_mm2"]),
            )

            check_cancelled()
            imwrite_compat(pair_dir / "a.png", a_h)
            imwrite_compat(pair_dir / "b.png", b_aligned)
            if keep_debug_images:
                imwrite_compat(pair_dir / "b_raw.png", b_h)
                imwrite_compat(pair_dir / "b_aligned.png", b_aligned)
            imwrite_compat(pair_dir / "mask.png", mask)
            imwrite_compat(pair_dir / "overlay.png", overlay)
            (pair_dir / "bboxes.json").write_text(
                json.dumps([{"x": x, "y": y, "w": w, "h": h} for x, y, w, h in bboxes], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (pair_dir / "excluded_regions.json").write_text(
                json.dumps(
                    [{"x": x, "y": y, "w": w, "h": h} for x, y, w, h in pixel_exclusions],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            entry["diff_percent"] = float(diff_percent)
            entry["change_level"] = level
            entry["bboxes_count"] = len(bboxes)
            entry["excluded_regions_count"] = len(pixel_exclusions)
            entry["diff_area_px"] = int(metrics["changed_px"])
            entry["diff_area_mm2"] = float(metrics["diff_area_mm2"])
            entry["diff_foreground_percent"] = float(metrics["diff_foreground_percent"])
            entry["foreground_px"] = int(metrics["foreground_px"])
            entry["added_px"] = int(metrics["added_px"])
            entry["removed_px"] = int(metrics["removed_px"])
            entry["added_area_mm2"] = float(metrics["added_area_mm2"])
            entry["removed_area_mm2"] = float(metrics["removed_area_mm2"])
            entry["max_region_area_mm2"] = float(metrics["max_region_area_mm2"])
            entry["foreground_sparse"] = bool(metrics["foreground_sparse"])
            return finish()

        # Added/removed sheets are rendered too (full + preview), and on a large
        # sheet that is just as slow as a matched pair — so the same phase
        # boundaries get a cancel check.
        check_cancelled()
        if a_idx is not None:
            entry["effective_dpi"] = round(float(capped_render_dpi(doc_a[a_idx], high_dpi)), 2)
            a_full = render_page(doc_a, a_idx, high_dpi)
            check_cancelled()
            remember_shape(a_full)
            a_prev = render_page(doc_a, a_idx, 120)
            check_cancelled()
            imwrite_compat(pair_dir / "a.png", a_full)
            imwrite_compat(pair_dir / "a_preview.png", a_prev)
        if b_idx is not None:
            check_cancelled()
            if entry["effective_dpi"] is None:
                entry["effective_dpi"] = round(float(capped_render_dpi(doc_b[b_idx], high_dpi)), 2)
            b_full = render_page(doc_b, b_idx, high_dpi)
            check_cancelled()
            if entry["width_px"] is None:
                remember_shape(b_full)
            b_prev = render_page(doc_b, b_idx, 120)
            check_cancelled()
            imwrite_compat(pair_dir / "b.png", b_full)
            imwrite_compat(pair_dir / "b_preview.png", b_prev)
        return finish()


def _value_to_int(value: object) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    if not parsed.is_integer():
        return None
    return int(parsed)


def _page_value_to_idx(value: object) -> int | None:
    parsed = _value_to_int(value)
    if parsed is None:
        return None
    return parsed - 1


def _details_to_pairs(details: Sequence[dict]) -> list[MatchPair]:
    pairs: list[MatchPair] = []
    for row in details:
        status = str(row.get("status") or "matched")
        if status not in {"matched", "added", "removed"}:
            status = "matched"
        try:
            score = float(row.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        pairs.append(
            MatchPair(
                _page_value_to_idx(row.get("a_page")),
                _page_value_to_idx(row.get("b_page")),
                status,
                score,
            )
        )
    return pairs


def _write_run_summary_files(
    run_dir: Path,
    file_a: Path,
    file_b: Path,
    details: Sequence[dict],
    high_dpi: int,
    stroke_tol_px: float,
    report_lang: str,
    exclude_regions: list[ExcludeRegion] | None = None,
    diff_strictness: str = "normal",
    bbox_merge_gap_mm: float = 0.0,
    bbox_merge_max_area_ratio: float = 16.0,
    ignore_line_weight: bool = False,
) -> None:
    normalized_exclusions = normalize_exclude_regions(exclude_regions)
    pairs = _details_to_pairs(details)
    summary_json_path(run_dir).parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        summary_json_path(run_dir),
        json.dumps(
            {
                "file_a": str(file_a),
                "file_b": str(file_b),
                "app_name": APP_NAME,
                "app_version": APP_VERSION,
                "created_at": datetime.now().isoformat(),
                "high_dpi": int(high_dpi),
                "stroke_tol_px": float(stroke_tol_px),
                "diff_strictness": diff_strictness,
                "exclude_regions": normalized_exclusions,
                "bbox_merge_gap_mm": float(bbox_merge_gap_mm),
                "bbox_merge_max_area_ratio": float(bbox_merge_max_area_ratio),
                "ignore_line_weight": bool(ignore_line_weight),
                "pairs": list(details),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    csv_path = page_map_csv_path(run_dir)
    csv_tmp = csv_path.with_name(f".{csv_path.name}.{uuid4().hex}.tmp")
    with csv_tmp.open("w", newline="", encoding="utf-8") as f:
        csv_fields = [
            "seq",
            "a_page",
            "b_page",
            "status",
            "score",
            "diff_percent",
            "change_level",
            "bboxes_count",
            "excluded_regions_count",
            "diff_strictness",
            "high_dpi",
            "stroke_tol_px",
            "bbox_merge_gap_mm",
            "bbox_merge_max_area_ratio",
            "ignore_line_weight",
            "ecc_failed",
            "width_px",
            "height_px",
            "pixel_count",
            "diff_area_px",
            "diff_area_mm2",
            "diff_foreground_percent",
            "foreground_px",
            "added_px",
            "removed_px",
            "added_area_mm2",
            "removed_area_mm2",
            "max_region_area_mm2",
            "foreground_sparse",
            "elapsed_sec",
        ]
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        for row in details:
            w.writerow({k: row.get(k) for k in csv_fields})
    os.replace(csv_tmp, csv_path)

    write_summary_md(internal_dir(run_dir) / "summary.md", file_a, file_b, pairs, details, lang=report_lang)
    write_engineer_report_md(internal_dir(run_dir) / "engineer_report.md", file_a, file_b, details, lang=report_lang)


def _staging_pages_dir(run_dir: Path) -> Path:
    staging_root = internal_dir(run_dir) / f".rerender_{uuid4().hex}"
    pages_dir = staging_root / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    return pages_dir


class _RunUpdateTransaction:
    """Keeps page backups and pre-update copies of run metadata alive until the
    whole re-render (pages + summary/CSV/MD + HTML) has succeeded.

    The old implementation deleted the backups right after swapping the page
    directories, so a failure while writing summary.json or the HTML report
    left the run half-updated with no way back.
    """

    def __init__(self, staging_root: Path) -> None:
        self.staging_root = staging_root
        self.swapped: list[tuple[Path, Path]] = []  # (live_dir, backup_dir)
        self.installed: list[Path] = []
        self.preserved: list[tuple[Path, Path]] = []  # (original, backup_copy)
        # Files rollback() could not put back; their backups stay in staging.
        self.unrestored: list[Path] = []

    def preserve_file(self, path: Path) -> None:
        """Snapshot a metadata file so rollback() can restore its old content."""
        if not path.exists() or any(original == path for original, _copy in self.preserved):
            return
        backup_dir = self.staging_root / "backup_files"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{len(self.preserved):02d}_{path.name}"
        shutil.copy2(path, backup)
        self.preserved.append((path, backup))

    def commit(self) -> None:
        shutil.rmtree(self.staging_root, ignore_errors=True)

    def rollback(self) -> None:
        """Restore the pre-update state, and never destroy the last copy of it.

        If a restore fails (file locked by a viewer, disk error), the staging dir
        is deliberately kept: it holds the only remaining copy of those files, and
        deleting it would turn a recoverable failure into permanent data loss.
        """
        unrestored: list[Path] = []
        for dst in reversed(self.installed):
            shutil.rmtree(dst, ignore_errors=True)
        for dst, backup in reversed(self.swapped):
            if backup.exists() and not dst.exists():
                try:
                    backup.rename(dst)
                except OSError:
                    unrestored.append(dst)
        for original, backup in reversed(self.preserved):
            try:
                shutil.copy2(backup, original)
            except OSError:
                unrestored.append(original)

        if unrestored:
            self.unrestored = unrestored
            return  # keep staging: it is the last copy of these files
        shutil.rmtree(self.staging_root, ignore_errors=True)


def _replace_page_dirs_from_staging(
    run_dir: Path, live_pages_dir: Path, staging_pages_dir: Path, rows: Sequence[dict]
) -> _RunUpdateTransaction:
    """Swap freshly rendered page dirs into the live run.

    Returns an open transaction: the caller must finish the remaining run
    updates (summary, CSV, HTML) and then call ``commit()``, or ``rollback()``
    on failure to restore the pre-swap state.
    """
    live_root = live_pages_dir.resolve()
    txn = _RunUpdateTransaction(staging_pages_dir.parent)
    backup_root = txn.staging_root / "backup_pages"
    backup_root.mkdir(parents=True, exist_ok=True)
    try:
        for row in rows:
            pair_name = str(row.get("pair_dir") or "")
            if not pair_name:
                raise RuntimeError(f"Не найден pair_dir для seq={row.get('seq')}")
            src = staging_pages_dir / pair_name
            dst = (live_pages_dir / pair_name).resolve()
            if live_root not in dst.parents:
                raise RuntimeError(f"Небезопасный путь листа: {dst}")
            if not src.exists():
                raise RuntimeError(f"Не собран staging-каталог листа: {src}")
            backup = backup_root / pair_name
            if dst.exists():
                if backup.exists():
                    shutil.rmtree(backup)
                dst.rename(backup)
                txn.swapped.append((dst, backup))
            src.rename(dst)
            txn.installed.append(dst)
    except Exception:
        txn.rollback()
        raise
    return txn


def regenerate_report_pages(
    run_dir: Path,
    seqs: Iterable[int],
    high_dpi: int = 250,
    stroke_tol_px: float | None = None,
    report_lang: str = "ru",
    workers: int | None = None,
    exclude_regions: list[ExcludeRegion] | None = None,
    diff_strictness: str | None = None,
    bbox_merge_gap_mm: float | None = None,
    bbox_merge_max_area_ratio: float | None = None,
    ignore_line_weight: bool | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> Path:
    """Re-render selected mapped pages in an existing run and rebuild the report."""

    def emit(pct: float, msg: str) -> None:
        # Every stage is cancellable, not just the page tasks: a caller that
        # passes only cancel_cb (no raising progress_cb) can still stop the run
        # during alignment or report generation.
        if cancel_cb is not None and cancel_cb():
            raise RunCancelled("Операция отменена пользователем")
        if progress_cb is not None:
            progress_cb(float(max(0.0, min(100.0, pct))), msg)

    run_dir = Path(run_dir)
    summary_path = find_summary_json_path(run_dir)
    pages_dir = find_pages_dir(run_dir)
    if not summary_path.exists():
        raise RunFailed("summary_missing", path=summary_path)
    if not pages_dir.exists():
        raise RunFailed("pages_dir_missing", path=pages_dir)

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    file_a = Path(str(payload.get("file_a") or ""))
    file_b = Path(str(payload.get("file_b") or ""))
    if not file_a.exists() or not file_b.exists():
        raise RunFailed("source_pdfs_missing")

    details = [dict(row) for row in payload.get("pairs") or []]
    if not details:
        raise RunFailed("summary_no_pages")

    selected = {int(seq) for seq in seqs}
    if not selected:
        raise RunFailed("no_pages_selected")

    def required_seq(row: dict) -> int:
        seq = _value_to_int(row.get("seq"))
        if seq is None:
            raise RunFailed("page_seq_invalid", value=row.get("seq"))
        return seq

    by_seq = {required_seq(row): row for row in details}
    missing = sorted(selected.difference(by_seq))
    if missing:
        raise RunFailed("pages_not_in_report", seqs=", ".join(map(str, missing)))

    dpi = validate_render_dpi(high_dpi)
    tol = float(stroke_tol_px if stroke_tol_px is not None else payload.get("stroke_tol_px", 2.0))
    exclusions = normalize_exclude_regions(exclude_regions if exclude_regions is not None else payload.get("exclude_regions"))
    strictness = str(diff_strictness or payload.get("diff_strictness") or "normal")
    merge_gap_mm = float(
        bbox_merge_gap_mm if bbox_merge_gap_mm is not None else payload.get("bbox_merge_gap_mm", 0.0)
    )
    merge_max_area_ratio = float(
        bbox_merge_max_area_ratio
        if bbox_merge_max_area_ratio is not None
        else payload.get("bbox_merge_max_area_ratio", 16.0)
    )
    line_weight_mode = bool(
        ignore_line_weight if ignore_line_weight is not None else payload.get("ignore_line_weight", False)
    )
    worker_count = resolve_worker_count(workers, len(selected))
    pages_root_resolved = pages_dir.resolve()
    staging_pages = _staging_pages_dir(run_dir)

    tasks = []
    for seq in sorted(selected):
        row = by_seq[seq]
        status = str(row.get("status") or "matched")
        score = float(row.get("score") or 0.0)
        a_idx = _page_value_to_idx(row.get("a_page"))
        b_idx = _page_value_to_idx(row.get("b_page"))
        pair_name = str(
            row.get("pair_dir")
            or f"{seq:03d}__A_{row.get('a_page') or 'NA'}__B_{row.get('b_page') or 'NA'}"
        )
        pair_dir = (pages_dir / pair_name).resolve()
        if pair_dir.exists() and pages_root_resolved not in pair_dir.parents:
            raise RuntimeError(f"Небезопасный путь листа: {pair_dir}")
        tasks.append(
            (
                file_a,
                file_b,
                staging_pages,
                seq,
                a_idx,
                b_idx,
                status,
                score,
                dpi,
                tol,
                False,
                exclusions,
                strictness,
                merge_gap_mm,
                merge_max_area_ratio,
                line_weight_mode,
                worker_count > 1,
            )
        )

    completed = 0
    updated_rows: dict[int, dict] = {}

    def on_row(row: dict) -> None:
        nonlocal completed
        updated_rows[int(row["seq"])] = row
        completed += 1
        emit(5 + 65 * (completed / len(tasks)), f"Перегенерирован лист {row['seq']} ({completed}/{len(tasks)})")

    def tick() -> None:
        emit(5 + 65 * (completed / len(tasks)), f"Перегенерация листов: {completed}/{len(tasks)}")

    try:
        # Inside the try: a cancel raised by emit() must clean the staging dir too.
        emit(5, f"Перегенерация листов: {len(tasks)}, DPI {dpi}, процессов {worker_count}")
        _run_pair_tasks(tasks, worker_count, on_row, tick, cancel_cb)
    except BaseException:
        shutil.rmtree(staging_pages.parent, ignore_errors=True)
        raise

    txn = _replace_page_dirs_from_staging(run_dir, pages_dir, staging_pages, list(updated_rows.values()))
    try:
        # Snapshot metadata before overwriting so any failure below restores a
        # fully consistent run (pages + summary + reports).
        txn.preserve_file(find_summary_json_path(run_dir))
        txn.preserve_file(summary_json_path(run_dir))
        txn.preserve_file(page_map_csv_path(run_dir))
        txn.preserve_file(internal_dir(run_dir) / "summary.md")
        txn.preserve_file(internal_dir(run_dir) / "engineer_report.md")

        for idx, row in enumerate(details):
            seq = required_seq(row)
            if seq in updated_rows:
                details[idx] = updated_rows[seq]
        details.sort(key=required_seq)

        emit(75, "Обновление summary.json и CSV")
        _write_run_summary_files(
            run_dir,
            file_a,
            file_b,
            details,
            dpi,
            tol,
            report_lang,
            exclusions,
            strictness,
            merge_gap_mm,
            merge_max_area_ratio,
            line_weight_mode,
        )
        emit(82, "Пересборка HTML отчёта")
        generate_html_report(
            run_dir,
            file_a,
            file_b,
            details,
            high_dpi=dpi,
            stroke_tol_px=tol,
            report_lang=report_lang,
            progress_cb=lambda p, msg: emit(82 + 17 * (p / 100.0), msg),
        )
        txn.commit()
    except BaseException:
        txn.rollback()
        raise
    emit(100, "Готово")
    return run_dir


def _spec_seqs(spec: dict) -> list[int]:
    raw_seqs = spec.get("seqs")
    if raw_seqs is None:
        raw_seqs = [spec.get("seq")]
    if not isinstance(raw_seqs, (list, tuple)):
        raw_seqs = [raw_seqs]
    seqs: list[int] = []
    for raw_seq in raw_seqs:
        parsed = _value_to_int(raw_seq)
        if parsed is None or parsed <= 0:
            raise RunFailed("page_settings_bad_seq", value=raw_seq)
        seqs.append(parsed)
    if not seqs:
        raise RunFailed("page_settings_no_seq")
    return seqs


def regenerate_report_pages_mixed(
    run_dir: Path,
    page_settings: Sequence[dict],
    high_dpi: int = 250,
    stroke_tol_px: float | None = None,
    report_lang: str = "ru",
    workers: int | None = None,
    exclude_regions: list[ExcludeRegion] | None = None,
    diff_strictness: str | None = None,
    bbox_merge_gap_mm: float | None = None,
    bbox_merge_max_area_ratio: float | None = None,
    ignore_line_weight: bool | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> Path:
    """Re-render selected report rows with per-row settings and rebuild one report."""

    def emit(pct: float, msg: str) -> None:
        # Every stage is cancellable, not just the page tasks: a caller that
        # passes only cancel_cb (no raising progress_cb) can still stop the run
        # during alignment or report generation.
        if cancel_cb is not None and cancel_cb():
            raise RunCancelled("Операция отменена пользователем")
        if progress_cb is not None:
            progress_cb(float(max(0.0, min(100.0, pct))), msg)

    run_dir = Path(run_dir)
    summary_path = find_summary_json_path(run_dir)
    pages_dir = find_pages_dir(run_dir)
    if not summary_path.exists():
        raise RunFailed("summary_missing", path=summary_path)
    if not pages_dir.exists():
        raise RunFailed("pages_dir_missing", path=pages_dir)

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    file_a = Path(str(payload.get("file_a") or ""))
    file_b = Path(str(payload.get("file_b") or ""))
    if not file_a.exists() or not file_b.exists():
        raise RunFailed("source_pdfs_missing")

    details = [dict(row) for row in payload.get("pairs") or []]
    if not details:
        raise RunFailed("summary_no_pages")
    if not page_settings:
        raise RunFailed("no_page_settings")

    def required_seq(row: dict) -> int:
        seq = _value_to_int(row.get("seq"))
        if seq is None:
            raise RunFailed("page_seq_invalid", value=row.get("seq"))
        return seq

    by_seq = {required_seq(row): row for row in details}
    default_tol = float(stroke_tol_px if stroke_tol_px is not None else payload.get("stroke_tol_px", 2.0))
    default_exclusions = normalize_exclude_regions(
        exclude_regions if exclude_regions is not None else payload.get("exclude_regions")
    )
    default_strictness = str(diff_strictness or payload.get("diff_strictness") or "normal").strip().lower()
    if default_strictness not in DIFF_STRICTNESS_CHOICES:
        raise InvalidInput("strictness_invalid", value=default_strictness, allowed=", ".join(DIFF_STRICTNESS_CHOICES))
    default_merge_gap = float(
        bbox_merge_gap_mm if bbox_merge_gap_mm is not None else payload.get("bbox_merge_gap_mm", 0.0)
    )
    default_merge_ratio = float(
        bbox_merge_max_area_ratio
        if bbox_merge_max_area_ratio is not None
        else payload.get("bbox_merge_max_area_ratio", 16.0)
    )
    default_line_weight_mode = bool(
        ignore_line_weight if ignore_line_weight is not None else payload.get("ignore_line_weight", False)
    )

    tasks = []
    settings_by_seq: dict[int, dict] = {}
    pages_root_resolved = pages_dir.resolve()
    for spec in page_settings:
        if not isinstance(spec, dict):
            raise RunFailed("page_settings_not_object")
        spec_dpi = validate_render_dpi(spec.get("dpi", spec.get("high_dpi", high_dpi)))
        spec_tol = float(spec.get("stroke_tol", spec.get("stroke_tol_px", default_tol)))
        spec_strictness = str(spec.get("diff_strictness", default_strictness)).strip().lower()
        if spec_strictness not in DIFF_STRICTNESS_CHOICES:
            raise InvalidInput("strictness_invalid", value=spec_strictness, allowed=", ".join(DIFF_STRICTNESS_CHOICES))
        spec_exclusions = normalize_exclude_regions(
            spec.get("exclude_regions") if "exclude_regions" in spec else default_exclusions
        )
        spec_merge_gap = float(spec.get("bbox_merge_gap_mm", default_merge_gap))
        spec_merge_ratio = float(spec.get("bbox_merge_max_area_ratio", default_merge_ratio))
        spec_line_weight_mode = bool(spec.get("ignore_line_weight", default_line_weight_mode))

        for seq in _spec_seqs(spec):
            if seq in settings_by_seq:
                raise RunFailed("page_settings_duplicate", seq=seq)
            if seq not in by_seq:
                raise RunFailed("page_not_in_report", seq=seq)
            settings_by_seq[seq] = {
                "dpi": spec_dpi,
                "stroke_tol_px": spec_tol,
                "diff_strictness": spec_strictness,
                "exclude_regions": spec_exclusions,
                "bbox_merge_gap_mm": spec_merge_gap,
                "bbox_merge_max_area_ratio": spec_merge_ratio,
                "ignore_line_weight": spec_line_weight_mode,
            }

    staging_pages = _staging_pages_dir(run_dir)
    for seq, setting in sorted(settings_by_seq.items()):
        row = by_seq[seq]
        status = str(row.get("status") or "matched")
        score = float(row.get("score") or 0.0)
        a_idx = _page_value_to_idx(row.get("a_page"))
        b_idx = _page_value_to_idx(row.get("b_page"))
        pair_name = str(row.get("pair_dir") or f"{seq:03d}__A_{row.get('a_page') or 'NA'}__B_{row.get('b_page') or 'NA'}")
        pair_dir = (pages_dir / pair_name).resolve()
        if pair_dir.exists() and pages_root_resolved not in pair_dir.parents:
            raise RuntimeError(f"Небезопасный путь листа: {pair_dir}")
        tasks.append(
            (
                file_a,
                file_b,
                staging_pages,
                seq,
                a_idx,
                b_idx,
                status,
                score,
                int(setting["dpi"]),
                float(setting["stroke_tol_px"]),
                False,
                setting["exclude_regions"],
                str(setting["diff_strictness"]),
                float(setting["bbox_merge_gap_mm"]),
                float(setting["bbox_merge_max_area_ratio"]),
                bool(setting["ignore_line_weight"]),
                False,
            )
        )

    worker_count = resolve_worker_count(workers, len(tasks))
    if worker_count > 1:
        tasks = [(*task[:-1], True) for task in tasks]

    completed = 0
    updated_rows: dict[int, dict] = {}

    def on_row(row: dict) -> None:
        nonlocal completed
        row["mixed_settings"] = settings_by_seq[int(row["seq"])]
        updated_rows[int(row["seq"])] = row
        completed += 1
        emit(5 + 65 * (completed / len(tasks)), f"Перегенерирован лист {row['seq']} ({completed}/{len(tasks)})")

    def tick() -> None:
        emit(5 + 65 * (completed / len(tasks)), f"Перегенерация листов: {completed}/{len(tasks)}")

    try:
        # Inside the try: a cancel raised by emit() must clean the staging dir too.
        emit(5, f"Перегенерация листов со смешанными настройками: {len(tasks)}, процессов {worker_count}")
        _run_pair_tasks(tasks, worker_count, on_row, tick, cancel_cb)
    except BaseException:
        shutil.rmtree(staging_pages.parent, ignore_errors=True)
        raise

    txn = _replace_page_dirs_from_staging(run_dir, pages_dir, staging_pages, list(updated_rows.values()))
    try:
        txn.preserve_file(find_summary_json_path(run_dir))
        txn.preserve_file(summary_json_path(run_dir))
        txn.preserve_file(page_map_csv_path(run_dir))
        txn.preserve_file(internal_dir(run_dir) / "summary.md")
        txn.preserve_file(internal_dir(run_dir) / "engineer_report.md")

        for idx, row in enumerate(details):
            seq = required_seq(row)
            if seq in updated_rows:
                details[idx] = updated_rows[seq]
        details.sort(key=required_seq)

        emit(75, "Обновление summary.json и CSV")
        _write_run_summary_files(
            run_dir,
            file_a,
            file_b,
            details,
            int(high_dpi),
            float(default_tol),
            report_lang,
            default_exclusions,
            default_strictness,
            default_merge_gap,
            default_merge_ratio,
            default_line_weight_mode,
        )
        summary_payload = json.loads(summary_json_path(run_dir).read_text(encoding="utf-8"))
        summary_payload["mixed_page_settings"] = [
            {"seq": seq, **setting} for seq, setting in sorted(settings_by_seq.items())
        ]
        summary_payload["is_mixed_precision"] = True
        summary_payload["mixed_precision_seqs"] = sorted(settings_by_seq)
        atomic_write_text(summary_json_path(run_dir), json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        emit(82, "Пересборка HTML отчёта")
        generate_html_report(
            run_dir,
            file_a,
            file_b,
            details,
            high_dpi=int(high_dpi),
            stroke_tol_px=float(default_tol),
            report_lang=report_lang,
            progress_cb=lambda p, msg: emit(82 + 17 * (p / 100.0), msg),
        )
        txn.commit()
    except BaseException:
        txn.rollback()
        raise
    emit(100, "Готово")
    return run_dir


def compare_pdfs(
    file_a: Path,
    file_b: Path,
    out_dir: Path,
    high_dpi: int = 250,
    stroke_tol_px: float = 2.0,
    report_lang: str = "ru",
    run_name: str | None = None,
    keep_debug_images: bool = False,
    workers: int | None = None,
    exclude_regions: list[ExcludeRegion] | None = None,
    diff_strictness: str = "normal",
    bbox_merge_gap_mm: float = 0.0,
    bbox_merge_max_area_ratio: float = 16.0,
    ignore_line_weight: bool = False,
    progress_cb: Callable[[float, str], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> Path:
    def emit(pct: float, msg: str) -> None:
        # Every stage is cancellable, not just the page tasks: a caller that
        # passes only cancel_cb (no raising progress_cb) can still stop the run
        # during alignment or report generation.
        if cancel_cb is not None and cancel_cb():
            raise RunCancelled("Операция отменена пользователем")
        if progress_cb is not None:
            progress_cb(float(max(0.0, min(100.0, pct))), msg)

    run_dir = build_run_dir(out_dir, report_lang, run_name)
    high_dpi = validate_render_dpi(high_dpi)
    normalized_exclusions = normalize_exclude_regions(exclude_regions)
    strictness = str(diff_strictness or "normal").strip().lower()
    if strictness not in DIFF_STRICTNESS_CHOICES:
        raise InvalidInput("strictness_invalid", value=diff_strictness, allowed=", ".join(DIFF_STRICTNESS_CHOICES))
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise RunFailed("run_dir_exists", path=run_dir) from None
    except OSError as exc:
        raise RunFailed("run_dir_create_failed", path=run_dir) from exc
    pages_dir = report_pages_dir(run_dir)
    pages_dir.mkdir(parents=True, exist_ok=True)

    try:
        emit(1, f"Чтение страниц старого документа: {file_a.name}")
        pages_a = build_page_info(
            file_a,
            progress_cb=lambda done, total, label: emit(1 + 17 * (done / max(1, total)), f"{label}: {done}/{total}"),
            label="старый",
        )
        emit(18, f"Чтение страниц нового документа: {file_b.name}")
        pages_b = build_page_info(
            file_b,
            progress_cb=lambda done, total, label: emit(18 + 17 * (done / max(1, total)), f"{label}: {done}/{total}"),
            label="новый",
        )
        emit(36, "Сопоставление листов (v1: глобальное + проверка последовательности)")
        pairs = align_pages_v1(pages_a, pages_b)
        del pages_a, pages_b

        details: list[dict] = []

        total_pairs = max(1, len(pairs))
        worker_count = resolve_worker_count(workers, len(pairs))
        emit(37, f"Сравнение листов: процессов {worker_count}")
        tasks = [
            (
                file_a,
                file_b,
                pages_dir,
                idx,
                p.a_idx,
                p.b_idx,
                p.status,
                float(p.score),
                high_dpi,
                stroke_tol_px,
                keep_debug_images,
                normalized_exclusions,
                strictness,
                bbox_merge_gap_mm,
                bbox_merge_max_area_ratio,
                ignore_line_weight,
                worker_count > 1,
            )
            for idx, p in enumerate(pairs, start=1)
        ]
        write_live_html_report(run_dir, file_a, file_b, pairs, details, report_lang=report_lang, in_progress=True)
        emit(37, f"{LIVE_REPORT_EVENT_PREFIX}{run_dir}")
        completed = 0
        processing_started = time.monotonic()

        def compare_progress_message() -> str:
            elapsed = max(0.001, time.monotonic() - processing_started)
            remaining = (elapsed / max(1, completed)) * max(0, total_pairs - completed) if completed else None
            eta_text = format_eta(remaining)
            avg_page = elapsed / max(1, completed)
            return f"Сравнение листов {completed}/{total_pairs}, осталось ~{eta_text}, среднее {avg_page:.1f}с/лист"

        def on_row(row: dict) -> None:
            nonlocal completed
            details.append(row)
            completed += 1
            write_live_detail_view(run_dir, file_a, file_b, row, report_lang)
            write_live_html_report(
                run_dir,
                file_a,
                file_b,
                pairs,
                details,
                report_lang=report_lang,
                in_progress=True,
                write_detail_views=False,
            )
            if worker_count <= 1 and completed % 8 == 0:
                gc.collect()
            emit(38 + 48 * (completed / total_pairs), compare_progress_message())

        def tick() -> None:
            emit(38 + 48 * (completed / total_pairs), compare_progress_message())

        _run_pair_tasks(tasks, worker_count, on_row, tick, cancel_cb)
        details.sort(key=lambda row: int(row["seq"]))
        write_live_html_report(
            run_dir,
            file_a,
            file_b,
            pairs,
            details,
            report_lang=report_lang,
            in_progress=False,
            write_detail_views=False,
        )

        emit(87, "Подготовка сводки и CSV")
        _write_run_summary_files(
            run_dir,
            file_a,
            file_b,
            details,
            high_dpi,
            stroke_tol_px,
            report_lang,
            normalized_exclusions,
            strictness,
            bbox_merge_gap_mm,
            bbox_merge_max_area_ratio,
            ignore_line_weight,
        )
        emit(90, "Генерация HTML отчета")
        generate_html_report(
            run_dir,
            file_a,
            file_b,
            details,
            high_dpi=high_dpi,
            stroke_tol_px=stroke_tol_px,
            report_lang=report_lang,
            progress_cb=lambda p, msg: emit(90 + 9 * (p / 100.0), msg),
        )
        emit(100, "Готово")
        return run_dir
    except Exception as exc:
        # Cancellation is cooperative and may happen mid-run; drop partial artifacts.
        if isinstance(exc, RunCancelled) or str(exc) == "__CANCELLED__":
            shutil.rmtree(run_dir, ignore_errors=True)
        else:
            # Move the partial run aside so retrying with the same run_name
            # isn't blocked by a half-written folder; keep it for debugging.
            _quarantine_failed_run(run_dir)
        raise
