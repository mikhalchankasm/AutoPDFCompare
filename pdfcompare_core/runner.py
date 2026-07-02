"""Top-level comparison orchestrator and worker plumbing."""

from __future__ import annotations

import concurrent.futures
import csv
import gc
import json
import os
import re
import shutil
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import cv2
import fitz
import numpy as np

from .alignment import align_ecc, align_pages_v1
from .classification import classify
from .constants import APP_NAME, APP_VERSION, LIVE_REPORT_EVENT_PREFIX
from .diff_engine import DIFF_STRICTNESS_CHOICES, compute_diff, harmonize_canvas
from .exclusions import ExcludeRegion, exclusion_regions_to_pixel_boxes, normalize_exclude_regions
from .html_report import generate_html_report
from .live_report import format_eta, write_live_detail_view, write_live_html_report
from .markdown_report import write_engineer_report_md, write_summary_md
from .models import MatchPair
from .pdf_io import (
    atomic_write_text,
    build_page_info,
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
        raise ValueError("Имя папки сравнения не может быть пустым")
    if INVALID_RUN_NAME_CHARS_RE.search(name) or Path(name).name != name or Path(name).is_absolute():
        raise ValueError(f"Имя папки сравнения должно быть одним именем, без пути: {raw_name}")
    if name != name.rstrip(" ."):
        raise ValueError("Имя папки сравнения не должно заканчиваться пробелом или точкой")

    name = re.sub(r"\s+", "_", name, flags=re.UNICODE)
    name = re.sub(r"_+", "_", name).strip(" ._")
    if not name:
        raise ValueError("Имя папки сравнения не может быть пустым")
    if name in {".", ".."}:
        raise ValueError(f"Имя папки сравнения должно быть одним именем, без пути: {raw_name}")
    if name.split(".")[0].upper() in WINDOWS_RESERVED_RUN_NAMES:
        raise ValueError(f"Зарезервированное имя папки Windows: {name}")
    if len(name) > MAX_RUN_FOLDER_NAME_LEN:
        raise ValueError(f"Имя папки сравнения не должно быть длиннее {MAX_RUN_FOLDER_NAME_LEN} символов")
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
    limit_cv_threads: bool = False,
) -> dict:
    started = time.monotonic()

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
        "stroke_tol_px": float(stroke_tol_px),
        "bbox_merge_gap_mm": float(bbox_merge_gap_mm),
        "bbox_merge_max_area_ratio": float(bbox_merge_max_area_ratio),
        "ecc_failed": False,
        "width_px": None,
        "height_px": None,
        "pixel_count": None,
        "diff_area_px": None,
        "elapsed_sec": None,
    }

    with fitz.open(file_a) as doc_a, fitz.open(file_b) as doc_b:
        if status == "matched" and a_idx is not None and b_idx is not None:
            a_img = render_page(doc_a, a_idx, high_dpi)
            b_img = render_page(doc_b, b_idx, high_dpi)
            remember_shape(a_img)
            harmonized = harmonize_canvas(a_img, b_img)
            if harmonized is None:
                entry["status"] = "size_mismatch"
                entry["change_level"] = "size_mismatch"
                imwrite_compat(pair_dir / "a.png", a_img)
                imwrite_compat(pair_dir / "b.png", b_img)
                return finish()

            a_h, b_h = harmonized
            b_aligned, ecc_ok = align_ecc(a_h, b_h)
            entry["ecc_failed"] = not ecc_ok
            pixel_exclusions = exclusion_regions_to_pixel_boxes(
                exclude_regions or [], a_h.shape[1], a_h.shape[0], dpi=high_dpi
            )
            bbox_merge_gap_px = int(round(max(0.0, float(bbox_merge_gap_mm)) * float(high_dpi) / 25.4))
            mask, overlay, bboxes, diff_percent = compute_diff(
                a_h,
                b_aligned,
                stroke_tol_px=stroke_tol_px,
                exclude_regions=exclude_regions,
                diff_strictness=diff_strictness,
                render_dpi=high_dpi,
                bbox_merge_gap_px=bbox_merge_gap_px,
                bbox_merge_max_area_ratio=bbox_merge_max_area_ratio,
            )
            level = classify(diff_percent, len(bboxes))

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
            entry["diff_area_px"] = int(cv2.countNonZero(mask))
            return finish()

        if a_idx is not None:
            a_full = render_page(doc_a, a_idx, high_dpi)
            remember_shape(a_full)
            a_prev = render_page(doc_a, a_idx, 120)
            imwrite_compat(pair_dir / "a.png", a_full)
            imwrite_compat(pair_dir / "a_preview.png", a_prev)
        if b_idx is not None:
            b_full = render_page(doc_b, b_idx, high_dpi)
            if entry["width_px"] is None:
                remember_shape(b_full)
            b_prev = render_page(doc_b, b_idx, 120)
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
            "ecc_failed",
            "width_px",
            "height_px",
            "pixel_count",
            "diff_area_px",
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


def _replace_page_dirs_from_staging(run_dir: Path, live_pages_dir: Path, staging_pages_dir: Path, rows: Sequence[dict]) -> None:
    live_root = live_pages_dir.resolve()
    backup_root = staging_pages_dir.parent / "backup_pages"
    backup_root.mkdir(parents=True, exist_ok=True)
    swapped: list[tuple[Path, Path]] = []
    installed: list[Path] = []
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
                swapped.append((dst, backup))
            src.rename(dst)
            installed.append(dst)
    except Exception:
        for dst in reversed(installed):
            if dst.exists():
                shutil.rmtree(dst)
        for dst, backup in reversed(swapped):
            if backup.exists() and not dst.exists():
                backup.rename(dst)
        raise
    finally:
        try:
            shutil.rmtree(staging_pages_dir.parent)
        except FileNotFoundError:
            pass


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
    progress_cb: Callable[[float, str], None] | None = None,
) -> Path:
    """Re-render selected mapped pages in an existing run and rebuild the report."""

    def emit(pct: float, msg: str) -> None:
        if progress_cb is not None:
            progress_cb(float(max(0.0, min(100.0, pct))), msg)

    run_dir = Path(run_dir)
    summary_path = find_summary_json_path(run_dir)
    pages_dir = find_pages_dir(run_dir)
    if not summary_path.exists():
        raise RuntimeError(f"Не найден summary.json: {summary_path}")
    if not pages_dir.exists():
        raise RuntimeError(f"Не найдена папка pages: {pages_dir}")

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    file_a = Path(str(payload.get("file_a") or ""))
    file_b = Path(str(payload.get("file_b") or ""))
    if not file_a.exists() or not file_b.exists():
        raise RuntimeError("Исходные PDF из summary.json не найдены на диске")

    details = [dict(row) for row in payload.get("pairs") or []]
    if not details:
        raise RuntimeError("В summary.json нет данных по листам")

    selected = {int(seq) for seq in seqs}
    if not selected:
        raise RuntimeError("Не выбраны листы для перегенерации")

    def required_seq(row: dict) -> int:
        seq = _value_to_int(row.get("seq"))
        if seq is None:
            raise RuntimeError(f"Некорректный номер листа в summary.json: {row.get('seq')!r}")
        return seq

    by_seq = {required_seq(row): row for row in details}
    missing = sorted(selected.difference(by_seq))
    if missing:
        raise RuntimeError(f"Не найдены листы в отчёте: {', '.join(map(str, missing))}")

    dpi = int(high_dpi)
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
                worker_count > 1,
            )
        )

    emit(5, f"Перегенерация листов: {len(tasks)}, DPI {dpi}, процессов {worker_count}")
    completed = 0
    updated_rows: dict[int, dict] = {}
    swapped_pages = False
    try:
        if worker_count <= 1:
            for task in tasks:
                row = process_pair_task(*task)
                updated_rows[int(row["seq"])] = row
                completed += 1
                emit(5 + 65 * (completed / len(tasks)), f"Перегенерирован лист {row['seq']} ({completed}/{len(tasks)})")
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
                future_map = {executor.submit(process_pair_task, *task): task[3] for task in tasks}
                for future in concurrent.futures.as_completed(future_map):
                    row = future.result()
                    updated_rows[int(row["seq"])] = row
                    completed += 1
                    emit(
                        5 + 65 * (completed / len(tasks)),
                        f"Перегенерирован лист {row['seq']} ({completed}/{len(tasks)})",
                    )
        _replace_page_dirs_from_staging(run_dir, pages_dir, staging_pages, list(updated_rows.values()))
        swapped_pages = True
    finally:
        if not swapped_pages:
            shutil.rmtree(staging_pages.parent, ignore_errors=True)

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
            raise RuntimeError(f"Некорректный номер строки отчёта: {raw_seq!r}")
        seqs.append(parsed)
    if not seqs:
        raise RuntimeError("В настройке страницы нет seq/seqs")
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
    progress_cb: Callable[[float, str], None] | None = None,
) -> Path:
    """Re-render selected report rows with per-row settings and rebuild one report."""

    def emit(pct: float, msg: str) -> None:
        if progress_cb is not None:
            progress_cb(float(max(0.0, min(100.0, pct))), msg)

    run_dir = Path(run_dir)
    summary_path = find_summary_json_path(run_dir)
    pages_dir = find_pages_dir(run_dir)
    if not summary_path.exists():
        raise RuntimeError(f"Не найден summary.json: {summary_path}")
    if not pages_dir.exists():
        raise RuntimeError(f"Не найдена папка pages: {pages_dir}")

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    file_a = Path(str(payload.get("file_a") or ""))
    file_b = Path(str(payload.get("file_b") or ""))
    if not file_a.exists() or not file_b.exists():
        raise RuntimeError("Исходные PDF из summary.json не найдены на диске")

    details = [dict(row) for row in payload.get("pairs") or []]
    if not details:
        raise RuntimeError("В summary.json нет данных по листам")
    if not page_settings:
        raise RuntimeError("Не переданы настройки страниц для перегенерации")

    def required_seq(row: dict) -> int:
        seq = _value_to_int(row.get("seq"))
        if seq is None:
            raise RuntimeError(f"Некорректный номер листа в summary.json: {row.get('seq')!r}")
        return seq

    by_seq = {required_seq(row): row for row in details}
    default_tol = float(stroke_tol_px if stroke_tol_px is not None else payload.get("stroke_tol_px", 2.0))
    default_exclusions = normalize_exclude_regions(
        exclude_regions if exclude_regions is not None else payload.get("exclude_regions")
    )
    default_strictness = str(diff_strictness or payload.get("diff_strictness") or "normal").strip().lower()
    if default_strictness not in DIFF_STRICTNESS_CHOICES:
        raise RuntimeError(f"Некорректная строгость сравнения: {default_strictness}")
    default_merge_gap = float(
        bbox_merge_gap_mm if bbox_merge_gap_mm is not None else payload.get("bbox_merge_gap_mm", 0.0)
    )
    default_merge_ratio = float(
        bbox_merge_max_area_ratio
        if bbox_merge_max_area_ratio is not None
        else payload.get("bbox_merge_max_area_ratio", 16.0)
    )

    tasks = []
    settings_by_seq: dict[int, dict] = {}
    pages_root_resolved = pages_dir.resolve()
    for spec in page_settings:
        if not isinstance(spec, dict):
            raise RuntimeError("Каждая настройка страницы должна быть объектом")
        spec_dpi = int(spec.get("dpi", spec.get("high_dpi", high_dpi)))
        spec_tol = float(spec.get("stroke_tol", spec.get("stroke_tol_px", default_tol)))
        spec_strictness = str(spec.get("diff_strictness", default_strictness)).strip().lower()
        if spec_strictness not in DIFF_STRICTNESS_CHOICES:
            raise RuntimeError(f"Некорректная строгость сравнения: {spec_strictness}")
        spec_exclusions = normalize_exclude_regions(
            spec.get("exclude_regions") if "exclude_regions" in spec else default_exclusions
        )
        spec_merge_gap = float(spec.get("bbox_merge_gap_mm", default_merge_gap))
        spec_merge_ratio = float(spec.get("bbox_merge_max_area_ratio", default_merge_ratio))

        for seq in _spec_seqs(spec):
            if seq in settings_by_seq:
                raise RuntimeError(f"Повторная настройка для seq={seq}")
            if seq not in by_seq:
                raise RuntimeError(f"Не найден лист в отчёте: {seq}")
            settings_by_seq[seq] = {
                "dpi": spec_dpi,
                "stroke_tol_px": spec_tol,
                "diff_strictness": spec_strictness,
                "exclude_regions": spec_exclusions,
                "bbox_merge_gap_mm": spec_merge_gap,
                "bbox_merge_max_area_ratio": spec_merge_ratio,
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
                False,
            )
        )

    worker_count = resolve_worker_count(workers, len(tasks))
    if worker_count > 1:
        tasks = [(*task[:-1], True) for task in tasks]

    emit(5, f"Перегенерация листов со смешанными настройками: {len(tasks)}, процессов {worker_count}")
    completed = 0
    updated_rows: dict[int, dict] = {}
    swapped_pages = False
    try:
        if worker_count <= 1:
            for task in tasks:
                row = process_pair_task(*task)
                row["mixed_settings"] = settings_by_seq[int(row["seq"])]
                updated_rows[int(row["seq"])] = row
                completed += 1
                emit(5 + 65 * (completed / len(tasks)), f"Перегенерирован лист {row['seq']} ({completed}/{len(tasks)})")
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
                future_map = {executor.submit(process_pair_task, *task): task[3] for task in tasks}
                for future in concurrent.futures.as_completed(future_map):
                    row = future.result()
                    row["mixed_settings"] = settings_by_seq[int(row["seq"])]
                    updated_rows[int(row["seq"])] = row
                    completed += 1
                    emit(
                        5 + 65 * (completed / len(tasks)),
                        f"Перегенерирован лист {row['seq']} ({completed}/{len(tasks)})",
                    )
        _replace_page_dirs_from_staging(run_dir, pages_dir, staging_pages, list(updated_rows.values()))
        swapped_pages = True
    finally:
        if not swapped_pages:
            shutil.rmtree(staging_pages.parent, ignore_errors=True)

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
    progress_cb: Callable[[float, str], None] | None = None,
) -> Path:
    def emit(pct: float, msg: str) -> None:
        if progress_cb is not None:
            progress_cb(float(max(0.0, min(100.0, pct))), msg)

    run_dir = build_run_dir(out_dir, report_lang, run_name)
    normalized_exclusions = normalize_exclude_regions(exclude_regions)
    strictness = str(diff_strictness or "normal").strip().lower()
    if strictness not in DIFF_STRICTNESS_CHOICES:
        raise ValueError(f"Некорректная строгость сравнения: {diff_strictness}")
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise RuntimeError(f"Папка результата уже существует: {run_dir}") from None
    except OSError as exc:
        raise RuntimeError(f"Не удалось создать папку результата: {run_dir}") from exc
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

        if worker_count <= 1:
            for task in tasks:
                row = process_pair_task(*task)
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
                if completed % 8 == 0:
                    gc.collect()
                emit(38 + 48 * (completed / total_pairs), compare_progress_message())
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
                future_map = {executor.submit(process_pair_task, *task): task[3] for task in tasks}
                for future in concurrent.futures.as_completed(future_map):
                    row = future.result()
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
                    emit(38 + 48 * (completed / total_pairs), compare_progress_message())
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
        if str(exc) == "__CANCELLED__":
            shutil.rmtree(run_dir, ignore_errors=True)
        raise
