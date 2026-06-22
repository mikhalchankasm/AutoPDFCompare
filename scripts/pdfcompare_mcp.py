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
                "нужно ли исключить области из сравнения в формате процентов x,y,w,h, "
                "и какую строгость сравнения использовать: strict, normal или loose."
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
            "status_path": str(current_job_dir / "status.json"),
            "events_path": str(current_job_dir / "events.jsonl"),
            "worker_log": str(current_job_dir / "worker.log"),
            "next_step": "Вызови get_pdf_comparison_status с этим job_id, чтобы увидеть прогресс.",
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
