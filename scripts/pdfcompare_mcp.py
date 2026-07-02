from __future__ import annotations

import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
import ctypes
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import fitz
from mcp.server.fastmcp import FastMCP

from compare_pdfs import (
    DIFF_STRICTNESS_CHOICES,
    MAX_RUN_FOLDER_NAME_LEN,
    START_REPORT_FILE,
    find_summary_json_path,
    normalize_exclude_regions,
    sanitize_run_folder_name,
)


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got: {raw}") from exc


mcp = FastMCP(
    "pdfcompare-local",
    host=os.getenv("PDFCOMPARE_MCP_HOST", "127.0.0.1"),
    port=env_int("PDFCOMPARE_MCP_PORT", 8000),
    streamable_http_path=os.getenv("PDFCOMPARE_MCP_PATH", "/mcp"),
    sse_path=os.getenv("PDFCOMPARE_MCP_SSE_PATH", "/sse"),
    message_path=os.getenv("PDFCOMPARE_MCP_MESSAGE_PATH", "/messages/"),
)
STATE_ROOT = REPO_ROOT / ".pdfcompare_mcp"
JOBS_ROOT = STATE_ROOT / "jobs"
JOB_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9]+")
ACTIVE_JOB_STATES = {"queued", "running"}
LAST_CLEANUP_AT = 0.0


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(path_text: str, *, must_exist: bool = False) -> Path:
    raw = str(path_text or "").strip()
    if not raw:
        raise ValueError("Путь не может быть пустым")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    resolved = path.resolve(strict=False)
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Путь не найден: {resolved}")
    return resolved


def count_pdf_pages(path: Path) -> int:
    with fitz.open(path) as doc:
        return int(doc.page_count)


def normalize_for_compare(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=False)))


def summary_path_candidates(run_dir: Path) -> list[Path]:
    return [run_dir / "_pdfcompare" / "summary.json", run_dir / "summary.json"]


def report_path_for_run(run_dir: Path) -> Path | None:
    candidates = [
        run_dir / START_REPORT_FILE,
        run_dir / "_pdfcompare" / "report" / "index.html",
        run_dir / "report_bundle" / "index.html",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def resolve_summary_pdf_path(raw_path: str, run_dir: Path) -> list[Path]:
    path = Path(str(raw_path or ""))
    if path.is_absolute():
        return [path.resolve(strict=False)]
    return [(REPO_ROOT / path).resolve(strict=False), (run_dir / path).resolve(strict=False)]


def summarize_pairs(pairs: list[dict[str, Any]]) -> dict[str, int]:
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
    return counts


def path_matches_any(path: Path, candidates: list[Path]) -> bool:
    target = normalize_for_compare(path)
    return any(normalize_for_compare(candidate) == target for candidate in candidates)


def combined_name_similarity(old_a: str, new_a: str, old_b: str, new_b: str) -> float:
    direct = SequenceMatcher(None, f"{old_a} {new_a}".casefold(), f"{old_b} {new_b}".casefold()).ratio()
    reversed_score = SequenceMatcher(None, f"{old_a} {new_a}".casefold(), f"{new_b} {old_b}".casefold()).ratio()
    return max(direct, reversed_score)


def classify_similarity(payload: dict[str, Any], run_dir: Path, old_path: Path | None, new_path: Path | None) -> tuple[float, list[str]]:
    file_a = str(payload.get("file_a") or "")
    file_b = str(payload.get("file_b") or "")
    existing_a = resolve_summary_pdf_path(file_a, run_dir)
    existing_b = resolve_summary_pdf_path(file_b, run_dir)
    reasons: list[str] = []
    score = 0.0

    if old_path is not None and new_path is not None:
        direct_paths = path_matches_any(old_path, existing_a) and path_matches_any(new_path, existing_b)
        reversed_paths = path_matches_any(old_path, existing_b) and path_matches_any(new_path, existing_a)
        if direct_paths:
            return 1.0, ["exact_paths"]
        if reversed_paths:
            return 0.98, ["exact_paths_reversed"]

        old_name = old_path.name.casefold()
        new_name = new_path.name.casefold()
        old_stem = old_path.stem
        new_stem = new_path.stem
        existing_a_name = Path(file_a).name.casefold()
        existing_b_name = Path(file_b).name.casefold()
        if old_name == existing_a_name and new_name == existing_b_name:
            return 0.95, ["exact_file_names"]
        if old_name == existing_b_name and new_name == existing_a_name:
            return 0.93, ["exact_file_names_reversed"]

        existing_a_stem = Path(file_a).stem
        existing_b_stem = Path(file_b).stem
        name_score = combined_name_similarity(old_stem, new_stem, existing_a_stem, existing_b_stem)
        if name_score >= 0.72:
            score = name_score
            reasons.append("similar_file_names")

    return score, reasons


def read_existing_run(run_dir: Path, old_path: Path | None = None, new_path: Path | None = None) -> dict[str, Any] | None:
    summary_path = next((path for path in summary_path_candidates(run_dir) if path.exists()), None)
    if summary_path is None:
        return None
    try:
        payload = load_json(summary_path)
    except (OSError, json.JSONDecodeError):
        return None

    score, reasons = classify_similarity(payload, run_dir, old_path, new_path)
    pairs = payload.get("pairs") or []
    report_path = report_path_for_run(run_dir)
    return {
        "run_dir": str(run_dir),
        "run_name": run_dir.name,
        "summary_path": str(summary_path),
        "report_path": str(report_path) if report_path else None,
        "created_at": payload.get("created_at"),
        "file_a": payload.get("file_a"),
        "file_b": payload.get("file_b"),
        "similarity": round(score, 3),
        "match_reasons": reasons,
        "counts": summarize_pairs(pairs if isinstance(pairs, list) else []),
    }


def find_existing_comparisons(out_dir: Path, old_path: Path | None = None, new_path: Path | None = None, *, limit: int = 10) -> list[dict[str, Any]]:
    if not out_dir.exists():
        return []
    scan_limit = max(1, env_int("PDFCOMPARE_MCP_SCAN_LIMIT", 300))
    candidates = [child for child in out_dir.iterdir() if child.is_dir()]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    runs: list[dict[str, Any]] = []
    for child in candidates[:scan_limit]:
        item = read_existing_run(child, old_path, new_path)
        if item is None:
            continue
        if old_path is None or new_path is None or item["similarity"] >= 0.72:
            runs.append(item)
    runs.sort(key=lambda row: (float(row.get("similarity") or 0.0), str(row.get("created_at") or "")), reverse=True)
    return runs[:limit]


def extract_revision(stem: str) -> str | None:
    patterns = [
        r"(?i)(?:^|[^A-Za-zА-Яа-я0-9])(?:rev(?:ision)?|r)[-_ ]*([A-Za-zА-Яа-я]*\d+[A-Za-zА-Яа-я]*)\b",
        r"(?i)([A-Za-zА-Яа-я]{1,3}\d{1,4}[A-Za-zА-Яа-я]{0,2})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, stem)
        if match:
            return match.group(1).upper()
    return None


def common_prefix_tokens(left: str, right: str) -> list[str]:
    left_tokens = TOKEN_RE.findall(left)
    right_tokens = TOKEN_RE.findall(right)
    common: list[str] = []
    for left_token, right_token in zip(left_tokens, right_tokens, strict=False):
        if left_token.casefold() != right_token.casefold():
            break
        common.append(left_token)
    return common


def compact_name(name: str, max_len: int = 70) -> str:
    normalized = re.sub(r"\s+", "_", str(name or "").strip(), flags=re.UNICODE)
    normalized = re.sub(r"_+", "_", normalized).strip(" ._")
    if not normalized:
        normalized = "Comparison"
    if len(normalized) > max_len:
        normalized = normalized[:max_len].rstrip(" ._")
    return sanitize_run_folder_name(normalized)


def available_folder_name(out_dir: Path, raw_name: str) -> str:
    base = compact_name(raw_name, MAX_RUN_FOLDER_NAME_LEN)
    candidate = base
    index = 2
    while (out_dir / candidate).exists():
        suffix = f"_{index}"
        candidate = sanitize_run_folder_name(f"{base[: max(1, MAX_RUN_FOLDER_NAME_LEN - len(suffix))]}{suffix}")
        index += 1
    return sanitize_run_folder_name(candidate)


def suggest_folder_names(old_path: Path, new_path: Path, out_dir: Path) -> list[dict[str, str]]:
    old_stem = old_path.stem
    new_stem = new_path.stem
    old_rev = extract_revision(old_stem)
    new_rev = extract_revision(new_stem)
    common = common_prefix_tokens(old_stem, new_stem)
    if common:
        base = compact_name("_".join(common[:8]), max_len=60)
    else:
        prefix = os.path.commonprefix([old_stem, new_stem]).strip(" ._-")
        base = compact_name(prefix or old_stem[:36], max_len=60)

    today = datetime.now().strftime("%Y-%m-%d")
    raw_suggestions: list[tuple[str, str]] = []
    if old_rev and new_rev:
        raw_suggestions.append((f"{base}_{old_rev}_vs_{new_rev}", "общая часть имени + найденные ревизии"))
    raw_suggestions.extend(
        [
            (f"{base}_old_vs_new", "нейтральное имя для пары старый/новый"),
            (f"{compact_name(old_stem, 36)}_vs_{compact_name(new_stem, 36)}", "полные имена обоих PDF"),
            (f"Comparison_{today}_{base}", "дата запуска + общий идентификатор документов"),
        ]
    )

    seen: set[str] = set()
    suggestions: list[dict[str, str]] = []
    for raw_name, reason in raw_suggestions:
        try:
            name = available_folder_name(out_dir, raw_name)
        except ValueError:
            continue
        if name.casefold() in seen:
            continue
        seen.add(name.casefold())
        suggestions.append({"name": name, "reason": reason})
        if len(suggestions) >= 4:
            break
    return suggestions


def job_dir(job_id: str) -> Path:
    if not JOB_ID_RE.match(job_id):
        raise ValueError(f"Некорректный job_id: {job_id}")
    return JOBS_ROOT / job_id


def load_status(job_id: str) -> dict[str, Any]:
    path = job_dir(job_id) / "status.json"
    if not path.exists():
        raise FileNotFoundError(f"Задача не найдена: {job_id}")
    status = load_json(path)
    run_dir = status.get("run_dir")
    if run_dir and not status.get("summary") and str(status.get("state")) == "completed":
        summary_path = find_summary_json_path(Path(run_dir))
        if summary_path.exists():
            payload = load_json(summary_path)
            pairs = payload.get("pairs") or []
            status["summary"] = {"summary_path": str(summary_path), "counts": summarize_pairs(pairs if isinstance(pairs, list) else [])}
    return status


def list_statuses() -> list[dict[str, Any]]:
    if not JOBS_ROOT.exists():
        return []
    statuses: list[dict[str, Any]] = []
    for child in JOBS_ROOT.iterdir():
        if not child.is_dir():
            continue
        status_path = child / "status.json"
        if not status_path.exists():
            continue
        try:
            statuses.append(load_json(status_path))
        except (OSError, json.JSONDecodeError):
            continue
    statuses.sort(key=lambda row: str(row.get("created_at") or row.get("started_at") or ""), reverse=True)
    return statuses


def get_process_command_line(pid: int) -> str:
    if pid <= 0:
        return ""
    if os.name == "nt":
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\").CommandLine",
        ]
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout.strip()

    proc_cmdline = Path("/proc") / str(pid) / "cmdline"
    if proc_cmdline.exists():
        return proc_cmdline.read_text(encoding="utf-8", errors="ignore").replace("\x00", " ").strip()
    return ""


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        # Access denied still means the PID exists; be conservative for cleanup.
        return ctypes.windll.kernel32.GetLastError() == 5

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_matches_worker_job(pid: int, job_id: str) -> bool:
    if not pid_exists(pid):
        return False
    command_line = get_process_command_line(pid)
    if not command_line:
        return False
    normalized = command_line.replace("\\", "/")
    return "pdfcompare_worker.py" in normalized and job_id in normalized


def active_job_statuses() -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    running_stale_sec = max(60, env_int("PDFCOMPARE_MCP_RUNNING_STALE_SEC", 21600))
    for status in list_statuses():
        job_id = str(status.get("job_id") or "")
        state = str(status.get("state") or "")
        pid = int(status.get("pid") or 0)
        status_path = job_dir(job_id) / "status.json" if JOB_ID_RE.match(job_id) else None
        status_age_sec = max(0.0, time.time() - status_path.stat().st_mtime) if status_path and status_path.exists() else 0.0
        if state == "queued" and job_id and not pid:
            active.append(status)
        elif state in ACTIVE_JOB_STATES and job_id and pid_exists(pid) and status_age_sec < running_stale_sec:
            active.append(status)
    return active


def cleanup_stale_job_artifacts() -> None:
    global LAST_CLEANUP_AT
    cleanup_interval_sec = max(1, env_int("PDFCOMPARE_MCP_CLEANUP_INTERVAL_SEC", 10))
    now = time.time()
    if now - LAST_CLEANUP_AT < cleanup_interval_sec:
        return
    LAST_CLEANUP_AT = now

    if not JOBS_ROOT.exists():
        return

    retention_days = max(1, env_int("PDFCOMPARE_MCP_JOBS_RETENTION_DAYS", 30))
    cutoff = time.time() - retention_days * 24 * 60 * 60
    max_retained_jobs = max(1, env_int("PDFCOMPARE_MCP_MAX_RETAINED_JOBS", 50))
    running_stale_sec = max(60, env_int("PDFCOMPARE_MCP_RUNNING_STALE_SEC", 21600))
    inactive_job_dirs: list[Path] = []
    for child in JOBS_ROOT.iterdir():
        if not child.is_dir():
            continue
        status_path = child / "status.json"
        if not status_path.exists():
            continue
        try:
            status = load_json(status_path)
            job_id = str(status.get("job_id") or child.name)
            if not JOB_ID_RE.match(job_id):
                continue
            state = str(status.get("state") or "")
            pid = int(status.get("pid") or 0)
            status_age_sec = max(0.0, time.time() - status_path.stat().st_mtime)
            if state == "queued" and not pid:
                is_active = status_age_sec < 60
            else:
                is_active = state in ACTIVE_JOB_STATES and pid_exists(pid) and status_age_sec < running_stale_sec

            out_dir = status.get("out_dir")
            if not is_active and out_dir:
                shutil.rmtree(Path(str(out_dir)) / f".pdfcompare_mcp_{job_id}", ignore_errors=True)
                inactive_job_dirs.append(child)

            if state in ACTIVE_JOB_STATES and not is_active:
                status.update(
                    {
                        "state": "failed",
                        "message": "Worker process is no longer running",
                        "error": "stale worker process",
                        "completed_at": now_iso(),
                        "updated_at": now_iso(),
                    }
                )
                atomic_write_json(status_path, status)

            if not is_active and child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
        except Exception:
            continue

    inactive_job_dirs = [path for path in inactive_job_dirs if path.exists()]
    inactive_job_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for child in inactive_job_dirs[max_retained_jobs:]:
        shutil.rmtree(child, ignore_errors=True)


@mcp.tool()
def prepare_pdf_comparison(old_path: str, new_path: str, out_dir: str = "runs", lang: str = "ru") -> dict[str, Any]:
    """Validate two PDFs, count pages, find similar previous runs, and suggest result folder names."""
    try:
        cleanup_stale_job_artifacts()
        old_pdf = resolve_path(old_path, must_exist=True)
        new_pdf = resolve_path(new_path, must_exist=True)
        output_dir = resolve_path(out_dir, must_exist=False)
        old_pages = count_pdf_pages(old_pdf)
        new_pages = count_pdf_pages(new_pdf)
        existing = find_existing_comparisons(output_dir, old_pdf, new_pdf)
        suggestions = suggest_folder_names(old_pdf, new_pdf, output_dir)
        return {
            "ok": True,
            "old_path": str(old_pdf),
            "new_path": str(new_pdf),
            "out_dir": str(output_dir),
            "page_counts": {"old": old_pages, "new": new_pages, "delta": new_pages - old_pages},
            "existing_similar_comparisons": existing,
            "suggested_run_names": suggestions,
            "requires_user_choice": True,
            "prompt_for_agent": (
                "Скажи пользователю количество листов и найденные похожие сравнения. "
                "Затем предложи варианты из suggested_run_names, спроси имя папки результата, "
                "нужно ли исключить области из сравнения в формате процентов x,y,w,h или через pick_pdf_exclude_region, "
                "какую строгость сравнения использовать: strict, normal или loose, "
                "и нужно ли включать экспериментальное объединение близких bbox. Если пользователь не сказал про объединение, "
                "спроси явно и рекомендуй оставить выключенным; по умолчанию объединение выключено: bbox_merge_gap_mm=0. "
                "Для пробного объединения обычно предлагай bbox_merge_gap_mm=5; "
                "bbox_merge_max_area_ratio=16, page-area guard и sparse-fill guard защищают от огромных пустых прямоугольников."
            ),
            "lang": lang,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def start_pdf_comparison(
    old_path: str,
    new_path: str,
    out_dir: str,
    run_name: str,
    dpi: int = 250,
    stroke_tol: float = 2.0,
    diff_strictness: str = "normal",
    exclude_regions: list[dict[str, Any]] | None = None,
    bbox_merge_gap_mm: float = 0.0,
    bbox_merge_max_area_ratio: float = 16.0,
    workers: int = 0,
    lang: str = "ru",
    keep_debug_images: bool = False,
) -> dict[str, Any]:
    """Start a PDF comparison in the background and return a job id for status polling."""
    try:
        cleanup_stale_job_artifacts()
        max_active_jobs = max(1, env_int("PDFCOMPARE_MCP_MAX_JOBS", 1))
        active_jobs = active_job_statuses()
        if len(active_jobs) >= max_active_jobs:
            return {
                "ok": False,
                "error": f"Достигнут лимит активных MCP-сравнений: {max_active_jobs}",
                "active_jobs": active_jobs,
            }

        old_pdf = resolve_path(old_path, must_exist=True)
        new_pdf = resolve_path(new_path, must_exist=True)
        output_dir = resolve_path(out_dir, must_exist=False)
        safe_run_name = sanitize_run_folder_name(run_name)
        strictness = str(diff_strictness or "normal").strip().lower()
        if strictness not in DIFF_STRICTNESS_CHOICES:
            return {"ok": False, "error": f"Некорректная строгость сравнения: {diff_strictness}"}
        normalized_exclusions = normalize_exclude_regions(exclude_regions)
        run_dir = output_dir / safe_run_name
        if run_dir.exists():
            return {"ok": False, "error": f"Папка результата уже существует: {run_dir}"}

        job_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        current_job_dir = job_dir(job_id)
        request = {
            "job_id": job_id,
            "created_at": now_iso(),
            "old_path": str(old_pdf),
            "new_path": str(new_pdf),
            "out_dir": str(output_dir),
            "run_name": safe_run_name,
            "dpi": int(dpi),
            "stroke_tol": float(stroke_tol),
            "diff_strictness": strictness,
            "exclude_regions": normalized_exclusions,
            "bbox_merge_gap_mm": float(bbox_merge_gap_mm),
            "bbox_merge_max_area_ratio": float(bbox_merge_max_area_ratio),
            "workers": int(workers),
            "lang": lang,
            "keep_debug_images": bool(keep_debug_images),
        }
        current_job_dir.mkdir(parents=True, exist_ok=False)
        atomic_write_json(current_job_dir / "request.json", request)
        status_payload = {
            "job_id": job_id,
            "state": "queued",
            "progress": 0.0,
            "message": "Ожидает запуска worker-а",
            "created_at": request["created_at"],
            "old_path": str(old_pdf),
            "new_path": str(new_pdf),
            "out_dir": str(output_dir),
            "run_name": safe_run_name,
            "run_dir": str(run_dir),
            "report_path": str(run_dir / START_REPORT_FILE),
            "diff_strictness": strictness,
            "exclude_regions": normalized_exclusions,
            "bbox_merge_gap_mm": float(bbox_merge_gap_mm),
            "bbox_merge_max_area_ratio": float(bbox_merge_max_area_ratio),
        }
        atomic_write_json(current_job_dir / "status.json", status_payload)

        command = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pdfcompare_worker.py"),
            "--request",
            str(current_job_dir / "request.json"),
            "--status",
            str(current_job_dir / "status.json"),
            "--events",
            str(current_job_dir / "events.jsonl"),
        ]
        creationflags = 0
        if os.name == "nt":
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
            creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        popen_kwargs: dict[str, Any] = {"creationflags": creationflags}
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        with (current_job_dir / "worker.log").open("ab") as log_handle:
            process = subprocess.Popen(
                command,
                cwd=str(REPO_ROOT),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                **popen_kwargs,
            )
        status_payload.update(
            {
                "state": "running",
                "pid": process.pid,
                "message": "Worker process launched",
                "started_at": now_iso(),
                "updated_at": now_iso(),
            }
        )
        atomic_write_json(current_job_dir / "status.json", status_payload)

        return {
            "ok": True,
            "job_id": job_id,
            "pid": process.pid,
            "run_dir": str(run_dir),
            "report_path": str(run_dir / START_REPORT_FILE),
            "diff_strictness": strictness,
            "exclude_regions": normalized_exclusions,
            "bbox_merge_gap_mm": float(bbox_merge_gap_mm),
            "bbox_merge_max_area_ratio": float(bbox_merge_max_area_ratio),
            "status_path": str(current_job_dir / "status.json"),
            "events_path": str(current_job_dir / "events.jsonl"),
            "worker_log": str(current_job_dir / "worker.log"),
            "next_step": "Вызови get_pdf_comparison_status с этим job_id, чтобы увидеть прогресс.",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def rerender_pdf_comparison_pages(
    run_dir: str,
    seqs: list[int] | None = None,
    page_settings: list[dict[str, Any]] | None = None,
    dpi: int = 250,
    stroke_tol: float | None = None,
    diff_strictness: str | None = None,
    exclude_regions: list[dict[str, Any]] | None = None,
    bbox_merge_gap_mm: float | None = None,
    bbox_merge_max_area_ratio: float | None = None,
    workers: int = 0,
    lang: str = "ru",
) -> dict[str, Any]:
    """Re-render selected rows of an existing report with new precision and rebuild the same report."""
    try:
        cleanup_stale_job_artifacts()
        max_active_jobs = max(1, env_int("PDFCOMPARE_MCP_MAX_JOBS", 1))
        active_jobs = active_job_statuses()
        if len(active_jobs) >= max_active_jobs:
            return {
                "ok": False,
                "error": f"Достигнут лимит активных MCP-сравнений: {max_active_jobs}",
                "active_jobs": active_jobs,
            }

        report_dir = resolve_path(run_dir, must_exist=True)
        summary_path = find_summary_json_path(report_dir)
        if not summary_path.exists():
            return {"ok": False, "error": f"Не найден summary.json в отчёте: {report_dir}"}
        summary = load_json(summary_path)

        settings = page_settings
        if settings is None:
            settings = []
        if not settings:
            if not seqs:
                return {"ok": False, "error": "Передайте seqs или page_settings"}
            settings = [{"seqs": [int(seq) for seq in seqs]}]
        if not isinstance(settings, list):
            return {"ok": False, "error": "page_settings должен быть списком объектов"}

        strictness = None
        if diff_strictness is not None:
            strictness = str(diff_strictness or "").strip().lower()
            if strictness not in DIFF_STRICTNESS_CHOICES:
                return {"ok": False, "error": f"Некорректная строгость сравнения: {diff_strictness}"}
        normalized_exclusions = normalize_exclude_regions(exclude_regions) if exclude_regions is not None else None

        job_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        current_job_dir = job_dir(job_id)
        request = {
            "operation": "rerender",
            "job_id": job_id,
            "created_at": now_iso(),
            "run_dir": str(report_dir),
            "old_path": summary.get("file_a"),
            "new_path": summary.get("file_b"),
            "page_settings": settings,
            "dpi": int(dpi),
            "stroke_tol": None if stroke_tol is None else float(stroke_tol),
            "diff_strictness": strictness,
            "exclude_regions": normalized_exclusions,
            "bbox_merge_gap_mm": None if bbox_merge_gap_mm is None else float(bbox_merge_gap_mm),
            "bbox_merge_max_area_ratio": (
                None if bbox_merge_max_area_ratio is None else float(bbox_merge_max_area_ratio)
            ),
            "workers": int(workers),
            "lang": lang,
        }
        current_job_dir.mkdir(parents=True, exist_ok=False)
        atomic_write_json(current_job_dir / "request.json", request)
        status_payload = {
            "job_id": job_id,
            "operation": "rerender",
            "state": "queued",
            "progress": 0.0,
            "message": "Ожидает запуска worker-а",
            "created_at": request["created_at"],
            "old_path": summary.get("file_a"),
            "new_path": summary.get("file_b"),
            "out_dir": str(report_dir.parent),
            "run_name": report_dir.name,
            "run_dir": str(report_dir),
            "report_path": str(report_dir / START_REPORT_FILE),
            "page_settings": settings,
        }
        atomic_write_json(current_job_dir / "status.json", status_payload)

        command = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pdfcompare_worker.py"),
            "--request",
            str(current_job_dir / "request.json"),
            "--status",
            str(current_job_dir / "status.json"),
            "--events",
            str(current_job_dir / "events.jsonl"),
        ]
        creationflags = 0
        if os.name == "nt":
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
            creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        popen_kwargs: dict[str, Any] = {"creationflags": creationflags}
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        with (current_job_dir / "worker.log").open("ab") as log_handle:
            process = subprocess.Popen(
                command,
                cwd=str(REPO_ROOT),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                **popen_kwargs,
            )
        status_payload.update(
            {
                "state": "running",
                "pid": process.pid,
                "message": "Worker process launched",
                "started_at": now_iso(),
                "updated_at": now_iso(),
            }
        )
        atomic_write_json(current_job_dir / "status.json", status_payload)

        return {
            "ok": True,
            "job_id": job_id,
            "pid": process.pid,
            "run_dir": str(report_dir),
            "report_path": str(report_dir / START_REPORT_FILE),
            "page_settings": settings,
            "status_path": str(current_job_dir / "status.json"),
            "events_path": str(current_job_dir / "events.jsonl"),
            "worker_log": str(current_job_dir / "worker.log"),
            "next_step": "Вызови get_pdf_comparison_status с этим job_id, чтобы увидеть прогресс.",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def pick_pdf_exclude_region(
    pdf_path: str,
    page_number: int = 1,
    dpi: int = 120,
    unit: str = "percent",
    anchor: str = "top_left",
    label: str = "exclude_region",
) -> dict[str, Any]:
    """Open a local window to select one rectangular exclude region on a PDF page."""
    try:
        import tempfile
        import tkinter as tk
        from tkinter import messagebox

        pdf = resolve_path(pdf_path, must_exist=True)
        page_index = int(page_number) - 1
        if page_index < 0:
            return {"ok": False, "error": "page_number должен быть >= 1"}

        with fitz.open(pdf) as doc:
            if page_index >= doc.page_count:
                return {"ok": False, "error": f"В PDF только {doc.page_count} листов"}
            page = doc[page_index]
            pix = page.get_pixmap(matrix=fitz.Matrix(float(dpi) / 72.0, float(dpi) / 72.0), alpha=False)
            image_width = int(pix.width)
            image_height = int(pix.height)
            tmp_dir = Path(tempfile.mkdtemp(prefix="pdfcompare_region_"))
            image_path = tmp_dir / "page.png"
            pix.save(image_path)

        result: dict[str, Any] = {}
        root = tk.Tk()
        root.title("PDFCompare: выбрать исключаемую область")
        root.geometry("1200x860")

        info = tk.Label(
            root,
            text=(
                "Выделите область мышкой и нажмите OK. "
                "Esc - отмена. Координаты вернутся агенту как exclude_region."
            ),
            anchor="w",
        )
        info.pack(fill="x", padx=8, pady=(8, 4))

        image = tk.PhotoImage(file=str(image_path))
        max_w, max_h = 1160, 760
        scale = min(max_w / image_width, max_h / image_height, 1.0)
        display_w = max(1, int(image_width * scale))
        display_h = max(1, int(image_height * scale))
        canvas = tk.Canvas(root, width=display_w, height=display_h, bg="white", cursor="crosshair")
        canvas.pack(padx=8, pady=4)
        if scale < 1.0:
            subsample = max(1, round(1.0 / scale))
            display_image = image.subsample(subsample, subsample)
            scale = display_image.width() / image_width
            canvas.configure(width=display_image.width(), height=display_image.height())
        else:
            display_image = image
        canvas.create_image(0, 0, image=display_image, anchor="nw")

        selection = {"start": None, "rect_id": None, "coords": None}

        def clamp(value: float, low: float, high: float) -> float:
            return max(low, min(high, value))

        def on_press(event: tk.Event) -> None:
            selection["start"] = (clamp(event.x, 0, display_image.width()), clamp(event.y, 0, display_image.height()))
            if selection["rect_id"] is not None:
                canvas.delete(selection["rect_id"])
            selection["rect_id"] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#ff2d2d", width=2)

        def on_drag(event: tk.Event) -> None:
            if selection["start"] is None or selection["rect_id"] is None:
                return
            x0, y0 = selection["start"]
            x1 = clamp(event.x, 0, display_image.width())
            y1 = clamp(event.y, 0, display_image.height())
            canvas.coords(selection["rect_id"], x0, y0, x1, y1)

        def on_release(event: tk.Event) -> None:
            if selection["start"] is None:
                return
            x0, y0 = selection["start"]
            x1 = clamp(event.x, 0, display_image.width())
            y1 = clamp(event.y, 0, display_image.height())
            left, right = sorted((x0, x1))
            top, bottom = sorted((y0, y1))
            selection["coords"] = (left / scale, top / scale, right / scale, bottom / scale)

        def convert_region() -> dict[str, Any] | None:
            coords = selection.get("coords")
            if coords is None:
                messagebox.showwarning("PDFCompare", "Сначала выделите область.")
                return None
            left, top, right, bottom = (float(value) for value in coords)
            if right - left < 2 or bottom - top < 2:
                messagebox.showwarning("PDFCompare", "Область слишком маленькая.")
                return None

            normalized_unit = str(unit or "percent").strip().lower()
            normalized_anchor = str(anchor or "top_left").strip().lower().replace("-", "_")
            if normalized_anchor in {"top_left", "left_top", "tl"}:
                x_raw, y_raw = left, top
            elif normalized_anchor in {"top_right", "right_top", "tr"}:
                x_raw, y_raw = image_width - right, top
            elif normalized_anchor in {"bottom_left", "left_bottom", "bl"}:
                x_raw, y_raw = left, image_height - bottom
            elif normalized_anchor in {"bottom_right", "right_bottom", "br"}:
                x_raw, y_raw = image_width - right, image_height - bottom
            else:
                raise ValueError(f"Некорректная anchor: {anchor}")

            w_raw = right - left
            h_raw = bottom - top
            if normalized_unit in {"px", "pixel", "pixels"}:
                x, y, w, h = x_raw, y_raw, w_raw, h_raw
                out_unit = "px"
            elif normalized_unit in {"mm", "millimeter", "millimeters"}:
                px_per_mm = float(dpi) / 25.4
                x, y, w, h = x_raw / px_per_mm, y_raw / px_per_mm, w_raw / px_per_mm, h_raw / px_per_mm
                out_unit = "mm"
            else:
                x, y, w, h = (
                    x_raw / image_width * 100.0,
                    y_raw / image_height * 100.0,
                    w_raw / image_width * 100.0,
                    h_raw / image_height * 100.0,
                )
                out_unit = "percent"

            return {
                "x": round(x, 4),
                "y": round(y, 4),
                "w": round(w, 4),
                "h": round(h, 4),
                "unit": out_unit,
                "anchor": normalized_anchor,
                "label": str(label or "exclude_region"),
            }

        def accept() -> None:
            region = convert_region()
            if region is None:
                return
            result["region"] = region
            root.destroy()

        def cancel(_event: tk.Event | None = None) -> None:
            result["cancelled"] = True
            root.destroy()

        buttons = tk.Frame(root)
        buttons.pack(fill="x", padx=8, pady=(4, 8))
        tk.Button(buttons, text="OK", command=accept, width=12).pack(side="right", padx=(6, 0))
        tk.Button(buttons, text="Отмена", command=cancel, width=12).pack(side="right")

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        root.bind("<Escape>", cancel)
        root.mainloop()

        shutil.rmtree(tmp_dir, ignore_errors=True)
        if result.get("cancelled"):
            return {"ok": False, "cancelled": True}
        region = result.get("region")
        if not region:
            return {"ok": False, "error": "Область не выбрана"}
        return {
            "ok": True,
            "pdf_path": str(pdf),
            "page_number": int(page_number),
            "dpi": int(dpi),
            "exclude_region": region,
            "usage": "Передай exclude_region в start_pdf_comparison.exclude_regions или rerender_pdf_comparison_pages.exclude_regions.",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_pdf_comparison_status(job_id: str = "") -> dict[str, Any]:
    """Return one comparison job status, or recent background jobs when job_id is omitted."""
    try:
        cleanup_stale_job_artifacts()
        if str(job_id or "").strip():
            return {"ok": True, "job": load_status(job_id.strip())}
        return {"ok": True, "jobs": list_statuses()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def list_pdf_comparisons(out_dir: str = "runs", old_path: str = "", new_path: str = "", limit: int = 20) -> dict[str, Any]:
    """List completed comparison folders, optionally filtered by two input PDFs."""
    try:
        cleanup_stale_job_artifacts()
        output_dir = resolve_path(out_dir, must_exist=False)
        old_pdf = resolve_path(old_path, must_exist=True) if str(old_path or "").strip() else None
        new_pdf = resolve_path(new_path, must_exist=True) if str(new_path or "").strip() else None
        return {
            "ok": True,
            "out_dir": str(output_dir),
            "comparisons": find_existing_comparisons(output_dir, old_pdf, new_pdf, limit=max(1, int(limit))),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def cancel_pdf_comparison(job_id: str) -> dict[str, Any]:
    """Terminate a running background comparison job."""
    try:
        status = load_status(job_id)
        if str(status.get("state") or "") not in {"queued", "running"}:
            return {"ok": False, "error": f"Задача уже не выполняется: {job_id}", "job": status}
        pid = int(status.get("pid") or 0)
        if not pid:
            return {"ok": False, "error": f"У задачи нет PID: {job_id}"}
        if not process_matches_worker_job(pid, job_id):
            return {
                "ok": False,
                "error": f"PID больше не похож на worker PDFCompare для задачи: {job_id}",
                "job": status,
            }

        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)

        out_dir = status.get("out_dir")
        if out_dir:
            shutil.rmtree(Path(str(out_dir)) / f".pdfcompare_mcp_{job_id}", ignore_errors=True)

        status.update({"state": "cancelled", "message": "Задача остановлена пользователем", "updated_at": now_iso()})
        atomic_write_json(job_dir(job_id) / "status.json", status)
        return {"ok": True, "job": status}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def main() -> None:
    transport = os.getenv("PDFCOMPARE_MCP_TRANSPORT", "stdio")
    if transport != "stdio" and os.getenv("PDFCOMPARE_MCP_ALLOW_NETWORK") != "1":
        raise SystemExit(
            "Non-stdio MCP transport requires PDFCOMPARE_MCP_ALLOW_NETWORK=1 "
            "and an environment-specific path allowlist."
        )
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
