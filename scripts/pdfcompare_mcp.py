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
    APP_VERSION,
    DIFF_STRICTNESS_CHOICES,
    MAX_RUN_FOLDER_NAME_LEN,
    START_REPORT_FILE,
    find_summary_json_path,
    normalize_exclude_regions,
    sanitize_run_folder_name,
    validate_render_dpi,
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


def allowed_roots() -> list[Path]:
    """Directories the tools may touch, from PDFCOMPARE_MCP_ALLOWED_DIRS.

    Unset (the default for a local stdio server) means "anything this user can
    already read" — the agent runs as the user anyway. Set it to confine the
    server, which is what a non-stdio transport needs.
    """
    raw = os.getenv("PDFCOMPARE_MCP_ALLOWED_DIRS", "").strip()
    if not raw:
        return []
    roots = []
    for part in raw.split(os.pathsep):
        text = part.strip()
        if text:
            roots.append(Path(text).expanduser().resolve(strict=False))
    return roots


def resolve_path(path_text: str, *, must_exist: bool = False) -> Path:
    raw = str(path_text or "").strip()
    if not raw:
        raise ValueError("Путь не может быть пустым")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    resolved = path.resolve(strict=False)  # resolves symlinks/junctions before the check
    roots = allowed_roots()
    if roots and not any(resolved == root or root in resolved.parents for root in roots):
        raise ValueError(
            f"Путь вне разрешённых каталогов (PDFCOMPARE_MCP_ALLOWED_DIRS): {resolved}"
        )
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


def cancel_marker_path(job_id: str) -> Path:
    """Marker the worker polls: its presence means "stop and roll back"."""
    return job_dir(job_id) / "cancel"


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


def git_text(*args: str, timeout: float = 20.0) -> str | None:
    """Run git in the repo checkout; None if git is missing or the command fails."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


@mcp.tool()
def check_pdfcompare_update(fetch: bool = True) -> dict[str, Any]:
    """Check whether this PDFCompare checkout is behind the repository's master branch.

    The MCP server runs the code in its own checkout (usually
    %LOCALAPPDATA%\\PDFCompareMCP\\AutoPDFCompare), which is separate from the
    installed GUI: the GUI's auto-update does not touch it. The bootstrap script
    pulls master on every server start unless auto-update was turned off, so this
    tool mainly matters for a long-running server or a checkout with auto-update
    disabled.

    Set fetch=False to compare against the already-fetched refs without touching
    the network.
    """
    result: dict[str, Any] = {"ok": True, "version": APP_VERSION, "repo_root": str(REPO_ROOT)}
    if git_text("rev-parse", "--is-inside-work-tree") != "true":
        result.update(
            {
                "ok": False,
                "error": "Каталог MCP-сервера не является git-репозиторием — обновление через git недоступно.",
            }
        )
        return result

    if fetch:
        git_text("fetch", "--prune", "origin", timeout=60.0)

    branch = git_text("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    commit = git_text("rev-parse", "--short", "HEAD") or "unknown"
    dirty = bool(git_text("status", "--porcelain", "--untracked-files=no"))
    counts = git_text("rev-list", "--left-right", "--count", "HEAD...origin/master")
    behind = ahead = None
    if counts:
        parts = counts.split()
        if len(parts) == 2:
            ahead, behind = int(parts[0]), int(parts[1])

    update_available = bool(behind)
    result.update(
        {
            "branch": branch,
            "commit": commit,
            "dirty": dirty,
            "commits_behind_master": behind,
            "commits_ahead_of_master": ahead,
            "update_available": update_available,
        }
    )
    if update_available:
        blockers = []
        if branch != "master":
            blockers.append(f"текущая ветка '{branch}', а не master")
        if dirty:
            blockers.append("в рабочем дереве есть локальные изменения")
        result["message"] = (
            f"Доступно обновление: локальная копия отстаёт от origin/master на {behind} коммит(ов). "
            "Перезапуск MCP-клиента подтянет его автоматически, если автообновление включено."
        )
        result["update_command"] = f'git -C "{REPO_ROOT}" pull --ff-only origin master'
        if blockers:
            result["blockers"] = blockers
            result["message"] += " Автообновление будет пропущено: " + "; ".join(blockers) + "."
    else:
        result["message"] = "Локальная копия PDFCompare актуальна."
    return result


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
                "нужно ли исключить области из сравнения (штампы, рамки, подписи). Области можно задать текстом: "
                "проценты 'x,y,w,h;…' от верхнего-левого угла, либо JSON-объекты {x,y,w,h,unit,anchor} с unit "
                "percent/mm/px и anchor top_left/top_right/bottom_left/bottom_right (отступы считаются от этого угла — "
                "bottom_right удобен для штампа, одинаково работает на A4 и A0). Либо открой визуальный выбор через "
                "pick_pdf_exclude_region (сетка в мм, несколько областей, якоря; существующие области передай в existing). "
                "Спроси, какую строгость сравнения использовать: strict, normal или loose, "
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
    exclude_regions: str | list[dict[str, Any]] | None = None,
    bbox_merge_gap_mm: float = 0.0,
    bbox_merge_max_area_ratio: float = 16.0,
    workers: int = 0,
    lang: str = "ru",
    keep_debug_images: bool = False,
) -> dict[str, Any]:
    """Start a PDF comparison in the background and return a job id for status polling.

    exclude_regions accepts the same forms as the GUI field:
    - text "x,y,w,h; x2,y2,w2,h2" — percent of the page, top-left anchor;
    - JSON string or a list of objects {"x","y","w","h","unit","anchor","label"}:
      unit = "percent" (default) | "mm" | "px"; anchor = "top_left" (default) |
      "top_right" | "bottom_left" | "bottom_right" — x/y are offsets from that
      corner, so a bottom_right stamp zone stays in place on any sheet format;
    - a list of 4-number lists (percent, top-left).
    """
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
        dpi = validate_render_dpi(dpi)
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
            "--cancel",
            str(cancel_marker_path(job_id)),
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
    exclude_regions: str | list[dict[str, Any]] | None = None,
    bbox_merge_gap_mm: float | None = None,
    bbox_merge_max_area_ratio: float | None = None,
    workers: int = 0,
    lang: str = "ru",
) -> dict[str, Any]:
    """Re-render selected rows of an existing report with new precision and rebuild the same report.

    exclude_regions (uniform override for all selected seqs) accepts the same
    forms as start_pdf_comparison: percent text "x,y,w,h;…", a JSON string, or
    a list of {"x","y","w","h","unit","anchor"} objects (unit percent/mm/px,
    anchor top_left/top_right/bottom_left/bottom_right). Per-page overrides go
    into page_settings items as {"seqs":[…], "exclude_regions": <same forms>,
    "dpi", "stroke_tol", "diff_strictness", "bbox_merge_gap_mm"}.
    """
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
        dpi = validate_render_dpi(dpi)
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
        if isinstance(exclude_regions, str) and not exclude_regions.strip():
            exclude_regions = None  # empty text means "inherit", not "clear"
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
            "--cancel",
            str(cancel_marker_path(job_id)),
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
    existing: str | list[dict[str, Any]] | None = None,
    lang: str = "ru",
) -> dict[str, Any]:
    """Open the visual picker to draw/edit rectangular exclude regions on a PDF page.

    Same dialog as the GUI: sheet format A4..A0 with portrait/landscape preview,
    mm grid, several regions with move/resize handles, and a per-region corner
    anchor (top_left/top_right/bottom_left/bottom_right).

    Regions come back in **millimetres from their anchor corner**
    (`unit: "mm"`), which is what makes one zone valid on every sheet format: a
    185x55 mm title block anchored bottom_right stays 185x55 mm on A4 and on A0.
    (A percent region would scale with the sheet and cover far too much of a
    large one.) `anchor` preselects the anchor for newly drawn regions;
    `existing` accepts the same forms as start_pdf_comparison.exclude_regions and
    opens those zones for editing. `dpi` and `unit` are legacy knobs and ignored.

    Returns exclude_regions (list) ready to pass to start_pdf_comparison or
    rerender_pdf_comparison_pages; exclude_region keeps the first region for
    older callers.
    """
    try:
        import tkinter as tk

        from pdfcompare_ui.exclusion_picker import pick_exclude_regions

        del dpi, unit  # legacy knobs; the picker renders to fit and returns mm

        pdf = resolve_path(pdf_path, must_exist=True)
        if int(page_number) < 1:
            return {"ok": False, "error": "page_number должен быть >= 1"}
        existing_regions = normalize_exclude_regions(existing) if existing else []

        root = tk.Tk()
        root.withdraw()
        try:
            regions = pick_exclude_regions(
                root,
                pdf,
                page_number=int(page_number),
                existing=list(existing_regions),
                initial_anchor=anchor,
                lang=str(lang),
            )
        finally:
            root.destroy()

        if regions is None:
            return {"ok": False, "cancelled": True}
        if label and str(label).strip() and str(label).strip() != "exclude_region":
            for region in regions:
                region["label"] = str(label).strip()
        return {
            "ok": True,
            "pdf_path": str(pdf),
            "page_number": int(page_number),
            "exclude_regions": regions,
            "exclude_region": regions[0] if regions else None,
            "usage": (
                "Передай exclude_regions в start_pdf_comparison.exclude_regions или "
                "rerender_pdf_comparison_pages.exclude_regions. Пустой список означает, "
                "что пользователь удалил все области."
            ),
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
def cancel_pdf_comparison(job_id: str, grace_sec: float = 20.0) -> dict[str, Any]:
    """Stop a running background job.

    Asks first, kills second. A re-render updates an existing report in place, so
    a worker killed between "new pages swapped in" and "summary/report written"
    would leave the run inconsistent with no rollback — the transaction only
    exists in the worker's memory. So we drop a cancel marker, give the worker
    time to unwind its transaction, and only force-kill if it does not exit.
    """
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

        marker = cancel_marker_path(job_id)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(now_iso(), encoding="utf-8")

        deadline = time.time() + max(0.0, float(grace_sec))
        forced = False
        while pid_exists(pid):
            if time.time() >= deadline:
                # It is not stopping — an unresponsive worker is worse than an
                # inconsistent one; kill it and say so.
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
                else:
                    os.kill(pid, signal.SIGTERM)
                forced = True
                break
            time.sleep(0.2)

        out_dir = status.get("out_dir")
        if out_dir:
            shutil.rmtree(Path(str(out_dir)) / f".pdfcompare_mcp_{job_id}", ignore_errors=True)

        # The worker writes its own "cancelled" status when it unwinds cleanly;
        # only overwrite it when we had to kill it.
        status = load_status(job_id)
        if forced or str(status.get("state") or "") in {"queued", "running"}:
            status.update(
                {
                    "state": "cancelled",
                    "message": (
                        "Задача принудительно остановлена (worker не завершился за отведённое время); "
                        "отчёт мог остаться в промежуточном состоянии"
                        if forced
                        else "Задача остановлена пользователем"
                    ),
                    "forced": forced,
                    "updated_at": now_iso(),
                }
            )
            atomic_write_json(job_dir(job_id) / "status.json", status)
        return {"ok": True, "forced": forced, "job": status}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def main() -> None:
    transport = os.getenv("PDFCOMPARE_MCP_TRANSPORT", "stdio")
    if transport != "stdio":
        # The tools read any PDF and write results anywhere the user can. Over a
        # network transport that is a file-system service, so the allowlist is
        # now enforced, not merely advertised.
        if os.getenv("PDFCOMPARE_MCP_ALLOW_NETWORK") != "1":
            raise SystemExit("Non-stdio MCP transport requires PDFCOMPARE_MCP_ALLOW_NETWORK=1.")
        if not allowed_roots():
            raise SystemExit(
                "Non-stdio MCP transport also requires PDFCOMPARE_MCP_ALLOWED_DIRS: a list of "
                "directories the tools may read and write (separated by os.pathsep). Without it "
                "the server would expose the whole user profile."
            )
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
