from __future__ import annotations

import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import fitz
from mcp.server.fastmcp import FastMCP

from compare_pdfs import (
    APP_VERSION,
    DIFF_STRICTNESS_CHOICES,
    START_REPORT_FILE,
    InvalidInput,
    PDFCompareError,
    RunFailed,
    find_summary_json_path,
    localize_error,
    normalize_exclude_regions,
    sanitize_run_folder_name,
    validate_render_dpi,
)
from pdfcompare_core import history_index
from pdfcompare_core.run_names import suggest_folder_names
from pdfcompare_core.vision_analysis import (
    DEFAULT_DEEPSEEK_VISION_MODEL,
    DEFAULT_QWEN_VISION_MODEL,
    DeepSeekVisionClient,
    QwenVisionClient,
    VisionAnalysisCache,
    VisionAnalysisError,
    build_vision_evidence,
    create_vision_report,
    select_vision_rows,
    validate_qwen_base_url,
    vision_report_paths,
)
from pdfcompare_core.vision_pricing import (
    OPENROUTER_CREDIT_FEE_RATE,
    OPENROUTER_MINIMUM_CREDIT_PURCHASE_FEE_USD,
    estimate_deepseek_vision_cost,
)
from scripts.process_identity import pid_exists, process_create_time, same_process

TRANSPORTS: tuple[Literal["stdio", "sse", "streamable-http"], ...] = ("stdio", "sse", "streamable-http")


def error_result(exc: BaseException, lang: str = "ru") -> dict[str, Any]:
    """The failure an agent reads, in the language it asked for.

    ``str(exc)`` is deliberately Russian — worker logs and tracebacks are matched
    against it — so the translated text goes into ``error`` and the diagnostic
    original is kept beside it under ``error_detail``.
    """
    message = localize_error(exc, lang)
    payload: dict[str, Any] = {"ok": False, "error": message}
    if isinstance(exc, PDFCompareError):
        payload["error_key"] = exc.key
    detail = str(exc)
    if detail != message:
        payload["error_detail"] = detail
    return payload


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got: {raw}") from exc


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got: {raw}") from exc


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
ACTIVE_JOB_STATES = {"queued", "running"}
LAST_CLEANUP_AT = 0.0
CANCEL_POLL_SEC = 0.2


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
        raise InvalidInput("path_empty")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    resolved = path.resolve(strict=False)  # resolves symlinks/junctions before the check
    roots = allowed_roots()
    if roots and not any(resolved == root or root in resolved.parents for root in roots):
        raise InvalidInput("path_outside_allowlist", path=resolved)
    if must_exist and not resolved.exists():
        raise RunFailed("path_not_found", path=resolved)
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


def job_dir(job_id: str) -> Path:
    if not JOB_ID_RE.match(job_id):
        raise InvalidInput("job_id_invalid", job_id=job_id)
    return JOBS_ROOT / job_id


def cancel_marker_path(job_id: str) -> Path:
    """Marker the worker polls: its presence means "stop and roll back"."""
    return job_dir(job_id) / "cancel"


def heartbeat_path(job_id: str) -> Path:
    """File the worker touches while it is alive — how cancel tells slow from stuck."""
    return job_dir(job_id) / "heartbeat"


def load_status(job_id: str) -> dict[str, Any]:
    path = job_dir(job_id) / "status.json"
    if not path.exists():
        raise RunFailed("job_not_found", job_id=job_id)
    status = load_json(path)
    run_dir = status.get("run_dir")
    if run_dir and not status.get("summary") and str(status.get("state")) == "completed":
        summary_path = find_summary_json_path(Path(run_dir))
        if summary_path.exists():
            payload = load_json(summary_path)
            pairs = payload.get("pairs") or []
            status["summary"] = {"summary_path": str(summary_path), "counts": summarize_pairs(pairs if isinstance(pairs, list) else [])}
    return status


def load_status_or_empty(job_id: str) -> dict[str, Any]:
    """status.json as it is right now, or {} — used to see whether the worker owns it yet."""
    path = job_dir(job_id) / "status.json"
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


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
            # Generous: a cancel arrives precisely when every core is busy rendering,
            # and that is the worst moment to start a PowerShell. A timeout here used
            # to read as "not our worker" and quietly refuse the cancel.
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout.strip()

    proc_cmdline = Path("/proc") / str(pid) / "cmdline"
    if proc_cmdline.exists():
        return proc_cmdline.read_text(encoding="utf-8", errors="ignore").replace("\x00", " ").strip()
    return ""


def worker_identity_path(job_id: str) -> Path:
    """What the worker records about itself: its real PID and its creation time."""
    return job_dir(job_id) / "worker.json"


def load_worker_identity(job_id: str) -> dict[str, Any]:
    path = worker_identity_path(job_id)
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


def await_worker_identity(job_id: str, process: subprocess.Popen[bytes], timeout_sec: float = 20.0) -> dict[str, Any]:
    """Wait for the worker to say which process it actually is.

    ``Popen.pid`` is not the worker's: in a virtualenv ``python.exe`` is a launcher
    that re-execs the real interpreter. Publishing that PID as the worker's is also a
    *race* — the worker writes its own, real PID into status.json within milliseconds,
    and the server's write would then stamp the launcher's back over it. A cancel a
    moment later would compare the wrong process and refuse with ``job_pid_foreign``.

    So the server does not guess. It waits for the worker to publish itself (which it
    does before its slow imports), and gives up early if the process dies first.
    """
    deadline = time.time() + max(0.0, timeout_sec)
    while time.time() < deadline:
        identity = load_worker_identity(job_id)
        if int(identity.get("pid") or 0) > 0:
            return identity
        if process.poll() is not None:
            return {}  # it died before it could say who it was
        time.sleep(0.05)
    return {}


def worker_pid_for_job(job_id: str, status: dict[str, Any]) -> int:
    """The worker's real PID: what it said about itself, then whatever status holds."""
    recorded = int(load_worker_identity(job_id).get("pid") or 0)
    return recorded or int(status.get("pid") or 0)


def worker_process_alive(pid: int, job_id: str) -> bool:
    """Cheap check: is *our* worker still running under this PID?

    Safe to call in a polling loop — a couple of syscalls, unlike the command-line
    lookup, which spawns a PowerShell.
    """
    return same_process(pid, load_worker_identity(job_id).get("create_time"))


def process_matches_worker_job(pid: int, job_id: str) -> bool:
    """The full check, run before anything is ever signalled.

    The creation time the worker recorded about itself is the authoritative answer:
    the PID exists *and* the process behind it started at the instant our worker
    did, which nothing else can claim. It costs two syscalls.

    The command line is only the fallback for a job started before the worker
    recorded itself — and it is a poor one, because reading it spawns a PowerShell,
    and a cancel arrives exactly when every core is busy rendering. A lookup that
    times out comes back empty, and the safe reading of "could not tell" is *do not
    kill*.
    """
    if not pid_exists(pid):
        return False

    recorded = load_worker_identity(job_id).get("create_time")
    if recorded is not None:
        current = process_create_time(pid)
        return current is not None and int(current) == int(recorded)

    command_line = get_process_command_line(pid)
    if not command_line:
        return False
    normalized = command_line.replace("\\", "/")
    return "pdfcompare_worker.py" in normalized and job_id in normalized


def worker_liveness(job_id: str) -> float:
    """Newest mtime of anything the worker writes — its proof of life."""
    newest = 0.0
    for name in ("heartbeat", "status.json"):
        try:
            newest = max(newest, (job_dir(job_id) / name).stat().st_mtime)
        except OSError:
            continue
    return newest


def cancel_acknowledged(job_id: str) -> bool:
    """Has the worker seen the marker and started unwinding?"""
    try:
        status = load_json(job_dir(job_id) / "status.json")
    except (OSError, json.JSONDecodeError):
        return False
    return bool(status.get("cancel_acknowledged_at"))


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
        return error_result(exc, lang)


def _resolve_comparison_settings(
    old_path: str,
    new_path: str,
    out_dir: str,
    run_name: str,
    dpi: int,
    stroke_tol: float,
    diff_strictness: str,
    exclude_regions: str | list[dict[str, Any]] | None,
    bbox_merge_gap_mm: float,
    bbox_merge_max_area_ratio: float,
    *,
    require_free_run_dir: bool = True,
) -> dict[str, Any]:
    """Validate and normalize the inputs shared by preview and start.

    Raises exactly the user-facing errors ``start_pdf_comparison`` would, so a
    preview never green-lights a run that start would then reject.
    """
    old_pdf = resolve_path(old_path, must_exist=True)
    new_pdf = resolve_path(new_path, must_exist=True)
    output_dir = resolve_path(out_dir, must_exist=False)
    safe_run_name = sanitize_run_folder_name(run_name)
    dpi_value = validate_render_dpi(dpi)
    strictness = str(diff_strictness or "normal").strip().lower()
    if strictness not in DIFF_STRICTNESS_CHOICES:
        raise InvalidInput("strictness_invalid", value=diff_strictness, allowed=", ".join(DIFF_STRICTNESS_CHOICES))
    normalized_exclusions = normalize_exclude_regions(exclude_regions)
    run_dir = output_dir / safe_run_name
    if require_free_run_dir and run_dir.exists():
        raise RunFailed("run_dir_exists", path=run_dir)
    return {
        "old_pdf": old_pdf,
        "new_pdf": new_pdf,
        "output_dir": output_dir,
        "safe_run_name": safe_run_name,
        "dpi": int(dpi_value),
        "stroke_tol": float(stroke_tol),
        "diff_strictness": strictness,
        "exclude_regions": normalized_exclusions,
        "bbox_merge_gap_mm": float(bbox_merge_gap_mm),
        "bbox_merge_max_area_ratio": float(bbox_merge_max_area_ratio),
        "run_dir": run_dir,
    }


def _exclusion_summary(regions: list[dict[str, Any]]) -> list[str]:
    """One human-readable line per exclusion zone for the pre-launch checklist."""
    lines: list[str] = []
    for idx, region in enumerate(regions, start=1):
        unit = str(region.get("unit") or "percent")
        anchor = str(region.get("anchor") or "top_left")
        label = str(region.get("label") or "").strip()
        suffix = f" — {label}" if label else ""
        lines.append(
            f"#{idx}: {region.get('w')}×{region.get('h')} {unit} @ "
            f"({region.get('x')},{region.get('y')}) from {anchor}{suffix}"
        )
    return lines


@mcp.tool()
def preview_pdf_comparison(
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
    ignore_line_weight: bool = False,
) -> dict[str, Any]:
    """Build the final pre-launch checklist for a comparison — WITHOUT starting it.

    Call this right before start_pdf_comparison, after the user has chosen the run
    name, strictness and exclusion zones. It validates and normalizes exactly what
    start_pdf_comparison would (paths, run-folder name, DPI, strictness, exclusion
    zones, output-folder collision), so it never green-lights a run that start
    would reject, and returns a ready-to-read checklist:

      - which old / new file, with page counts and the page delta;
      - the precision settings (DPI, stroke_tol, strictness) and whether each is
        still at its default;
      - whether any exclusion zones are set, and a one-line summary of each;
      - the bbox-merge setting;
      - where the report is saved (out_dir) and under what run name / run_dir.

    Show the checklist to the user, ask whether every line is correct or which one
    to change (files, tolerances, excluded zones, output folder/name), and only
    then call start_pdf_comparison with the confirmed values. Accepts the same
    arguments as start_pdf_comparison so the confirmed call is a straight copy.
    """
    try:
        settings = _resolve_comparison_settings(
            old_path,
            new_path,
            out_dir,
            run_name,
            dpi,
            stroke_tol,
            diff_strictness,
            exclude_regions,
            bbox_merge_gap_mm,
            bbox_merge_max_area_ratio,
        )
        old_pdf = settings["old_pdf"]
        new_pdf = settings["new_pdf"]
        old_pages = count_pdf_pages(old_pdf)
        new_pages = count_pdf_pages(new_pdf)
        regions = settings["exclude_regions"]
        strictness = settings["diff_strictness"]
        gap = settings["bbox_merge_gap_mm"]
        checklist = {
            "old_file": {"path": str(old_pdf), "name": old_pdf.name, "pages": old_pages},
            "new_file": {"path": str(new_pdf), "name": new_pdf.name, "pages": new_pages},
            "page_delta": new_pages - old_pages,
            "precision": {
                "dpi": settings["dpi"],
                "dpi_is_default": settings["dpi"] == 250,
                "stroke_tol": settings["stroke_tol"],
                "stroke_tol_is_default": abs(settings["stroke_tol"] - 2.0) < 1e-9,
                "diff_strictness": strictness,
                "diff_strictness_is_default": strictness == "normal",
            },
            "exclude_regions": {
                "count": len(regions),
                "items": _exclusion_summary(regions),
                "raw": regions,
            },
            "bbox_merge": {
                "gap_mm": gap,
                "enabled": gap > 0,
                "max_area_ratio": settings["bbox_merge_max_area_ratio"],
            },
            "alignment": {
                "enabled": True,
                "mode": "automatic_multiscale",
                "description": (
                    "Автоматически компенсирует небольшой сдвиг/поворот чертежа перед поиском изменений; "
                    "зоны исключения удаляются из области, по которой оценивается смещение."
                ),
            },
            "output": {
                "out_dir": str(settings["output_dir"]),
                "run_name": settings["safe_run_name"],
                "run_dir": str(settings["run_dir"]),
                "report_path": str(settings["run_dir"] / START_REPORT_FILE),
            },
            "keep_debug_images": bool(keep_debug_images),
            "ignore_line_weight": bool(ignore_line_weight),
            "workers": int(workers),
        }
        return {
            "ok": True,
            "requires_user_choice": True,
            "checklist": checklist,
            "next_step": (
                "Покажи пользователю чек-лист. Спроси, всё ли верно или какой пункт изменить "
                "(файлы, допуски/строгость, исключаемые зоны, папку и имя результата). После "
                "подтверждения вызови start_pdf_comparison с этими же значениями."
            ),
            "prompt_for_agent": (
                "Собери короткий чек-лист перед запуском и покажи пользователю:\n"
                "• Старый файл — имя и число листов;\n"
                "• Новый файл — имя и число листов;\n"
                "• Точность — DPI, stroke_tol, строгость (пометь, если по умолчанию);\n"
                "• Автовыравнивание — включено;\n"
                "• Исключаемые зоны — сколько и какие, либо «нет»;\n"
                "• Результат — папка и имя.\n"
                "Затем спроси: всё запускаем или что-то изменить?"
            ),
            "lang": lang,
        }
    except Exception as exc:
        return error_result(exc, lang)


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
    ignore_line_weight: bool = False,
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
            return error_result(RunFailed("job_limit_reached", limit=max_active_jobs), lang) | {
                "active_jobs": active_jobs
            }

        settings = _resolve_comparison_settings(
            old_path,
            new_path,
            out_dir,
            run_name,
            dpi,
            stroke_tol,
            diff_strictness,
            exclude_regions,
            bbox_merge_gap_mm,
            bbox_merge_max_area_ratio,
        )
        old_pdf = settings["old_pdf"]
        new_pdf = settings["new_pdf"]
        output_dir = settings["output_dir"]
        safe_run_name = settings["safe_run_name"]
        dpi = settings["dpi"]
        strictness = settings["diff_strictness"]
        normalized_exclusions = settings["exclude_regions"]
        run_dir = settings["run_dir"]

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
            "ignore_line_weight": bool(ignore_line_weight),
            "alignment_mode": "automatic_multiscale",
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
            "ignore_line_weight": bool(ignore_line_weight),
            "alignment_mode": "automatic_multiscale",
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
            "--heartbeat",
            str(heartbeat_path(job_id)),
            "--identity",
            str(worker_identity_path(job_id)),
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
        # Never publish Popen.pid as the worker's — see await_worker_identity().
        identity = await_worker_identity(job_id, process)
        worker_pid = int(identity.get("pid") or 0)
        status_payload.update(
            {
                "state": "running",
                "pid": worker_pid or process.pid,
                "launcher_pid": process.pid,
                "message": "Worker process launched",
                "started_at": now_iso(),
                "updated_at": now_iso(),
            }
        )
        # The worker owns status.json from the moment it starts writing to it; only
        # fill in the launch details if it has not taken over yet.
        current_status = load_status_or_empty(job_id)
        if str(current_status.get("state") or "queued") == "queued":
            atomic_write_json(current_job_dir / "status.json", status_payload)

        return {
            "ok": True,
            "job_id": job_id,
            "pid": worker_pid or process.pid,
            "run_dir": str(run_dir),
            "report_path": str(run_dir / START_REPORT_FILE),
            "diff_strictness": strictness,
            "exclude_regions": normalized_exclusions,
            "bbox_merge_gap_mm": float(bbox_merge_gap_mm),
            "bbox_merge_max_area_ratio": float(bbox_merge_max_area_ratio),
            "alignment_mode": "automatic_multiscale",
            "status_path": str(current_job_dir / "status.json"),
            "events_path": str(current_job_dir / "events.jsonl"),
            "worker_log": str(current_job_dir / "worker.log"),
            "next_step": "Вызови get_pdf_comparison_status с этим job_id, чтобы увидеть прогресс.",
        }
    except Exception as exc:
        return error_result(exc, lang)


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
    ignore_line_weight: bool | None = None,
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
            return error_result(RunFailed("job_limit_reached", limit=max_active_jobs), lang) | {
                "active_jobs": active_jobs
            }

        report_dir = resolve_path(run_dir, must_exist=True)
        dpi = validate_render_dpi(dpi)
        summary_path = find_summary_json_path(report_dir)
        if not summary_path.exists():
            raise RunFailed("summary_missing", path=summary_path)
        summary = load_json(summary_path)

        settings = page_settings
        if settings is None:
            settings = []
        if not settings:
            if not seqs:
                raise InvalidInput("rerender_need_seqs")
            settings = [{"seqs": [int(seq) for seq in seqs]}]
        if not isinstance(settings, list):
            raise InvalidInput("page_settings_not_list")

        strictness = None
        if diff_strictness is not None:
            strictness = str(diff_strictness or "").strip().lower()
            if strictness not in DIFF_STRICTNESS_CHOICES:
                raise InvalidInput(
                    "strictness_invalid", value=diff_strictness, allowed=", ".join(DIFF_STRICTNESS_CHOICES)
                )
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
            "ignore_line_weight": ignore_line_weight,
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
            "--heartbeat",
            str(heartbeat_path(job_id)),
            "--identity",
            str(worker_identity_path(job_id)),
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
        # Never publish Popen.pid as the worker's — see await_worker_identity().
        identity = await_worker_identity(job_id, process)
        worker_pid = int(identity.get("pid") or 0)
        status_payload.update(
            {
                "state": "running",
                "pid": worker_pid or process.pid,
                "launcher_pid": process.pid,
                "message": "Worker process launched",
                "started_at": now_iso(),
                "updated_at": now_iso(),
            }
        )
        # The worker owns status.json from the moment it starts writing to it; only
        # fill in the launch details if it has not taken over yet.
        current_status = load_status_or_empty(job_id)
        if str(current_status.get("state") or "queued") == "queued":
            atomic_write_json(current_job_dir / "status.json", status_payload)

        return {
            "ok": True,
            "job_id": job_id,
            "pid": worker_pid or process.pid,
            "run_dir": str(report_dir),
            "report_path": str(report_dir / START_REPORT_FILE),
            "page_settings": settings,
            "status_path": str(current_job_dir / "status.json"),
            "events_path": str(current_job_dir / "events.jsonl"),
            "worker_log": str(current_job_dir / "worker.log"),
            "next_step": "Вызови get_pdf_comparison_status с этим job_id, чтобы увидеть прогресс.",
        }
    except Exception as exc:
        return error_result(exc, lang)


@dataclass(frozen=True)
class VisionProviderConfig:
    key: str
    display_name: str
    api_key_env: str
    api_key: str
    base_url_env: str | None
    base_url: str
    model: str
    timeout_env: str
    timeout_sec: float
    max_tokens_env: str
    max_tokens: int


def _vision_provider(provider: str) -> str:
    value = str(provider or os.getenv("PDFCOMPARE_VISION_PROVIDER") or "deepseek").strip().lower()
    aliases = {"deepseek": "deepseek", "qwen": "qwen", "alibaba": "qwen", "modelstudio": "qwen"}
    if value not in aliases:
        raise ValueError("provider must be deepseek or qwen")
    return aliases[value]


def _vision_config(provider: str, model: str) -> VisionProviderConfig:
    key = _vision_provider(provider)
    if key == "qwen":
        return VisionProviderConfig(
            key=key,
            display_name="Qwen",
            api_key_env="QWEN_API_KEY",
            api_key=os.getenv("QWEN_API_KEY", "").strip(),
            base_url_env="QWEN_BASE_URL",
            base_url=os.getenv("QWEN_BASE_URL", "").strip().rstrip("/"),
            model=str(model or os.getenv("QWEN_MODEL") or DEFAULT_QWEN_VISION_MODEL).strip(),
            timeout_env="PDFCOMPARE_QWEN_TIMEOUT_SEC",
            timeout_sec=env_float("PDFCOMPARE_QWEN_TIMEOUT_SEC", 300.0),
            max_tokens_env="PDFCOMPARE_QWEN_MAX_TOKENS",
            max_tokens=env_int("PDFCOMPARE_QWEN_MAX_TOKENS", 3000),
        )
    return VisionProviderConfig(
        key=key,
        display_name="DeepSeek",
        api_key_env="DEEPSEEK_API_KEY",
        api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
        base_url_env=None,
        base_url="https://api.deepseek.com",
        model=str(
            model or os.getenv("PDFCOMPARE_DEEPSEEK_VISION_MODEL") or DEFAULT_DEEPSEEK_VISION_MODEL
        ).strip(),
        timeout_env="PDFCOMPARE_DEEPSEEK_TIMEOUT_SEC",
        timeout_sec=env_float("PDFCOMPARE_DEEPSEEK_TIMEOUT_SEC", 120.0),
        max_tokens_env="PDFCOMPARE_DEEPSEEK_MAX_TOKENS",
        max_tokens=env_int("PDFCOMPARE_DEEPSEEK_MAX_TOKENS", 1200),
    )


def _vision_key_setup(config: VisionProviderConfig, lang: str) -> dict[str, Any]:
    is_en = str(lang).lower().startswith("en")
    variables = [config.api_key_env]
    if config.base_url_env:
        variables.append(config.base_url_env)
    if is_en:
        message = (
            f"To use {config.display_name} model {config.model}, configure {', '.join(variables)} in the MCP "
            "process environment and restart the MCP client. Never paste an API key into chat or a tool argument."
        )
    else:
        message = (
            f"Для AI-проверки через {config.display_name}, модель {config.model}, задайте "
            f"{', '.join(variables)} в окружении MCP-процесса и перезапустите MCP-клиент. "
            "Не отправляйте API-ключ в чат и не передавайте его аргументом инструмента."
        )
    powershell = [f'$env:{config.api_key_env} = "<your key>"']
    if config.base_url_env:
        powershell.append(f'$env:{config.base_url_env} = "<Alibaba compatible-mode endpoint>"')
    return {
        "message": message,
        "required_environment_variables": variables,
        "powershell_current_session_examples": powershell,
        "restart_mcp_required": True,
        "security_note": (
            "Never paste the key into chat or tool arguments."
            if is_en
            else "Никогда не вставляйте ключ в чат или аргументы MCP-инструмента."
        ),
    }


def _vision_configuration_error_result(
    exc: VisionAnalysisError,
    provider: str,
    model: str,
    lang: str,
) -> dict[str, Any]:
    payload = _vision_error_result(exc, lang)
    if exc.key in {"api_key_missing", "qwen_base_url_missing", "qwen_base_url_invalid"}:
        config = _vision_config(provider, model)
        payload.update(
            {
                "provider": config.key,
                "provider_name": config.display_name,
                "model": config.model,
                "required_environment_variable": config.api_key_env,
                "key_setup": _vision_key_setup(config, lang),
            }
        )
    return payload


def _vision_error_result(exc: VisionAnalysisError, lang: str) -> dict[str, Any]:
    message = exc.localized(lang)
    payload: dict[str, Any] = {"ok": False, "error": message, "error_key": f"vision_{exc.key}"}
    detail = str(exc)
    if detail != message:
        payload["error_detail"] = detail
    return payload


def _vision_preview(
    run_dir: str,
    *,
    excluded_seqs: list[int] | None,
    max_sheets: int,
    model: str,
    provider: str,
    lang: str,
) -> tuple[dict[str, Any], Path, list[dict[str, Any]]]:
    report_dir = resolve_path(run_dir, must_exist=True)
    summary_path = find_summary_json_path(report_dir)
    if not summary_path.exists():
        raise RunFailed("summary_not_found", run_dir=report_dir)
    summary = load_json(summary_path)
    pairs = summary.get("pairs") or []
    if not isinstance(pairs, list):
        pairs = []
    selection = select_vision_rows(pairs, excluded_seqs or [])
    selected = selection.eligible[:max_sheets]
    config = _vision_config(provider, model)
    cache = VisionAnalysisCache(report_dir, config.model, lang=lang, provider=config.key)
    cached = set(cache.cached_sequences())
    artifacts = vision_report_paths(report_dir, config.model, lang=lang, provider=config.key)
    is_en = str(lang).lower().startswith("en")
    warning = (
        "After explicit confirmation, JPEG montages containing OLD, NEW, DIFF, and numbered change crops for the "
        f"listed sheets will be sent to the external {config.display_name} API. Source PDFs, added sheets, removed "
        "sheets, and one-sided rows will not be sent."
        if is_en
        else f"После явного подтверждения во внешний {config.display_name} API будут отправлены JPEG-монтажи "
        "OLD, NEW, DIFF и нумерованных зон только для перечисленных листов. Исходные PDF, добавленные, "
        "удалённые и односторонние листы отправляться не будут."
    )
    base_url_ready = not config.base_url_env
    base_url_error: str | None = None
    if config.base_url_env:
        try:
            validate_qwen_base_url(config.base_url)
            base_url_ready = True
        except VisionAnalysisError as exc:
            base_url_error = exc.localized(lang)
    configuration_ready = bool(config.api_key) and base_url_ready
    preview = {
        "ok": True,
        "run_dir": str(report_dir),
        "summary_path": str(summary_path),
        "provider": config.key,
        "provider_name": config.display_name,
        "model": config.model,
        "api_key_environment_variable": config.api_key_env,
        "api_key_configured": bool(config.api_key),
        "base_url_environment_variable": config.base_url_env,
        "base_url_configured": base_url_ready,
        "base_url_error": base_url_error,
        "configuration_ready": configuration_ready,
        "setup_required": not configuration_ready,
        "key_setup": _vision_key_setup(config, lang),
        "eligible_count": len(selection.eligible),
        "selected_count": len(selected),
        "max_sheets": max_sheets,
        "eligible_sheets": [
            {
                "seq": int(row["seq"]),
                "change_level": row.get("change_level"),
                "diff_percent": row.get("diff_percent"),
                "diff_foreground_percent": row.get("diff_foreground_percent"),
                "diff_area_mm2": row.get("diff_area_mm2"),
                "bboxes_count": row.get("bboxes_count"),
                "cached": int(row["seq"]) in cached,
            }
            for row in selected
        ],
        "skipped": {reason: {"count": len(seqs), "seqs": seqs} for reason, seqs in selection.skipped.items()},
        "cached_sequences": sorted(cached),
        "report_html_path": str(artifacts.html_path) if artifacts.html_path.is_file() else None,
        "report_markdown_path": str(artifacts.markdown_path) if artifacts.markdown_path.is_file() else None,
        "report_zip_path": str(artifacts.zip_path) if artifacts.zip_path.is_file() else None,
        "external_upload_warning": warning,
        "requires_external_upload_confirmation": bool(selected),
        "next_step": (
            "Show this exact sheet list and warning to the user. Call analyze_pdf_comparison_with_ai with "
            f"provider={config.key} and confirm_external_upload=true only after the user explicitly agrees."
            if is_en
            else "Покажи пользователю точный список листов и предупреждение. Вызывай "
            f"analyze_pdf_comparison_with_ai с provider={config.key} и confirm_external_upload=true только после "
            "явного согласия."
        ),
    }
    return preview, report_dir, selection.eligible


@mcp.tool()
def preview_pdf_vision_analysis(
    run_dir: str,
    excluded_seqs: list[int] | None = None,
    max_sheets: int = 12,
    model: str = "",
    provider: str = "",
    lang: str = "ru",
) -> dict[str, Any]:
    """Preview exactly which comparison sheets may be sent to DeepSeek or Qwen; never calls the network.

    Eligibility is deliberately strict: status must be ``matched``, both OLD and NEW pages must exist, the row must
    not be ``unchanged``, and machine diff metrics must be non-zero. Added, removed, one-sided, size-mismatch, and
    explicitly excluded rows are listed under ``skipped`` and are never uploaded or included in the AI report.

    The response includes the external-transfer warning, cache/report state, and the exact selected sheet numbers.
    An agent must show those details to the user before a confirmed analysis call.
    """
    try:
        limit = int(max_sheets)
        if not 1 <= limit <= 50:
            raise ValueError("max_sheets must be between 1 and 50")
        preview, _, _ = _vision_preview(
            run_dir,
            excluded_seqs=excluded_seqs,
            max_sheets=limit,
            model=model,
            provider=provider,
            lang=lang,
        )
        return preview
    except VisionAnalysisError as exc:
        return _vision_configuration_error_result(exc, provider, model, lang)
    except Exception as exc:
        return error_result(exc, lang)


def _analyze_pdf_comparison_with_ai(
    run_dir: str,
    *,
    provider: str,
    confirm_external_upload: bool = False,
    excluded_seqs: list[int] | None = None,
    seqs: list[int] | None = None,
    max_sheets: int = 12,
    max_zones: int = 8,
    model: str = "",
    lang: str = "ru",
) -> dict[str, Any]:
    try:
        sheet_limit = int(max_sheets)
        zone_limit = int(max_zones)
        if not 1 <= sheet_limit <= 50:
            raise ValueError("max_sheets must be between 1 and 50")
        if not 1 <= zone_limit <= 20:
            raise ValueError("max_zones must be between 1 and 20")
        preview, report_dir, all_eligible = _vision_preview(
            run_dir,
            excluded_seqs=excluded_seqs,
            max_sheets=sheet_limit,
            model=model,
            provider=provider,
            lang=lang,
        )
        if not confirm_external_upload:
            preview["analysis_started"] = False
            return preview
        if not all_eligible:
            raise VisionAnalysisError("no_eligible")

        requested = {int(seq) for seq in (seqs or [])}
        candidates = [row for row in all_eligible if not requested or int(row["seq"]) in requested]
        selected = candidates[:sheet_limit]
        if not selected:
            raise VisionAnalysisError("no_eligible")

        config = _vision_config(provider, model)
        if not 5 <= config.timeout_sec <= 600:
            raise ValueError(f"{config.timeout_env} must be between 5 and 600")
        if not 100 <= config.max_tokens <= 8000:
            raise ValueError(f"{config.max_tokens_env} must be between 100 and 8000")

        cache = VisionAnalysisCache(report_dir, config.model, lang=lang, provider=config.key)
        needs_network = any(cache.get(int(row["seq"])) is None for row in selected)
        if needs_network and not config.api_key:
            raise VisionAnalysisError(
                "api_key_missing",
                provider=config.display_name,
                env_var=config.api_key_env,
            )
        client: DeepSeekVisionClient | QwenVisionClient | None = None
        if needs_network and config.key == "qwen":
            client = QwenVisionClient(
                api_key=config.api_key,
                base_url=validate_qwen_base_url(config.base_url),
                model=config.model,
                timeout_sec=config.timeout_sec,
                max_tokens=config.max_tokens,
            )
        elif needs_network:
            client = DeepSeekVisionClient(
                api_key=config.api_key,
                model=config.model,
                timeout_sec=config.timeout_sec,
                max_tokens=config.max_tokens,
            )
        results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        prompt_tokens = 0
        completion_tokens = 0
        cached_prompt_tokens = 0
        for row in selected:
            seq = int(row["seq"])
            try:
                evidence = build_vision_evidence(report_dir, row, max_zones=zone_limit)
                analysis = cache.get(seq)
                if analysis is None:
                    assert client is not None
                    analysis = client.analyze(evidence, row, lang=lang)
                    cache.put(seq, analysis)
                    prompt_tokens += analysis.prompt_tokens
                    completion_tokens += analysis.completion_tokens
                    cached_prompt_tokens += analysis.cached_prompt_tokens
                results.append(
                    {
                        "seq": seq,
                        "description": analysis.text,
                        "cached": analysis.cached,
                        "evidence_path": str(evidence.path),
                    }
                )
            except VisionAnalysisError as exc:
                failures.append({"seq": seq, "error": exc.localized(lang), "error_key": f"vision_{exc.key}"})

        if not results and not cache.cached_sequences():
            return {
                "ok": False,
                "error": failures[0]["error"] if failures else VisionAnalysisError("no_analysis").localized(lang),
                "failures": failures,
            }
        artifacts = create_vision_report(
            report_dir,
            config.model,
            all_eligible,
            lang=lang,
            max_zones=zone_limit,
            provider=config.key,
        )
        payload: dict[str, Any] = {
            "ok": True,
            "run_dir": str(report_dir),
            "provider": config.key,
            "provider_name": config.display_name,
            "model": config.model,
            "processed_count": len(results),
            "cached_count": sum(1 for item in results if item["cached"]),
            "failed_count": len(failures),
            "results": results,
            "failures": failures,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cached_prompt_tokens": cached_prompt_tokens,
            "report_sheet_count": artifacts.sheet_count,
            "report_html_path": str(artifacts.html_path),
            "report_markdown_path": str(artifacts.markdown_path),
            "report_json_path": str(artifacts.json_path),
            "report_zip_path": str(artifacts.zip_path),
            "external_upload_confirmed": True,
        }
        if config.key == "deepseek":
            cost = estimate_deepseek_vision_cost(
                prompt_tokens,
                completion_tokens,
                cached_prompt_tokens=cached_prompt_tokens,
            )
            payload["cost_estimate"] = {
                "currency": "USD",
                "period": cost.period,
                "direct_deepseek_usd": cost.direct_deepseek_usd,
                "openrouter_inference_usd": cost.openrouter_inference_usd,
                "openrouter_effective_usd_with_proportional_credit_fee": cost.openrouter_effective_usd,
                "openrouter_credit_purchase_fee_rate": OPENROUTER_CREDIT_FEE_RATE,
                "openrouter_minimum_credit_purchase_fee_usd": OPENROUTER_MINIMUM_CREDIT_PURCHASE_FEE_USD,
                "off_peak_direct_usd": cost.off_peak_direct_usd,
                "peak_direct_usd": cost.peak_direct_usd,
                "pricing_last_verified": cost.pricing_last_verified,
            }
        else:
            payload["cost_estimate"] = None
            payload["cost_note"] = (
                "Qwen token usage is returned, but pricing is not estimated because regional Alibaba Model Studio "
                "tariffs are not embedded in PDFCompare."
                if str(lang).lower().startswith("en")
                else "Токены Qwen указаны, но стоимость не рассчитывается: региональные тарифы Alibaba Model "
                "Studio не зашиты в PDFCompare."
            )
        return payload
    except VisionAnalysisError as exc:
        return _vision_configuration_error_result(exc, provider, model, lang)
    except Exception as exc:
        return error_result(exc, lang)


@mcp.tool()
def analyze_pdf_comparison_with_ai(
    run_dir: str,
    provider: str = "",
    confirm_external_upload: bool = False,
    excluded_seqs: list[int] | None = None,
    seqs: list[int] | None = None,
    max_sheets: int = 12,
    max_zones: int = 8,
    model: str = "",
    lang: str = "ru",
) -> dict[str, Any]:
    """Describe two-sided PDF diffs through a user-configured DeepSeek or Qwen provider.

    The provider defaults to ``PDFCOMPARE_VISION_PROVIDER`` (or ``deepseek``). Credentials are read only from the
    MCP process environment: ``DEEPSEEK_API_KEY`` for DeepSeek, or ``QWEN_API_KEY`` plus the official Alibaba Model
    Studio ``QWEN_BASE_URL`` for Qwen. Never pass a key in a prompt or tool argument. Without explicit external-upload
    confirmation this returns a no-network preview, including safe setup guidance when configuration is missing.

    Only matched, changed OLD + NEW pairs are eligible. Successful results are cached separately by provider, model,
    language, and prompt version, and generate local interactive HTML, Markdown, JSON, and ZIP reports.
    """
    return _analyze_pdf_comparison_with_ai(
        run_dir,
        provider=provider,
        confirm_external_upload=confirm_external_upload,
        excluded_seqs=excluded_seqs,
        seqs=seqs,
        max_sheets=max_sheets,
        max_zones=max_zones,
        model=model,
        lang=lang,
    )


@mcp.tool()
def analyze_pdf_comparison_with_deepseek(
    run_dir: str,
    confirm_external_upload: bool = False,
    excluded_seqs: list[int] | None = None,
    seqs: list[int] | None = None,
    max_sheets: int = 12,
    max_zones: int = 8,
    model: str = "",
    lang: str = "ru",
) -> dict[str, Any]:
    """Backward-compatible DeepSeek-only alias for ``analyze_pdf_comparison_with_ai``."""
    return _analyze_pdf_comparison_with_ai(
        run_dir,
        provider="deepseek",
        confirm_external_upload=confirm_external_upload,
        excluded_seqs=excluded_seqs,
        seqs=seqs,
        max_sheets=max_sheets,
        max_zones=max_zones,
        model=model,
        lang=lang,
    )


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
            raise InvalidInput("page_number_min")
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
        return error_result(exc, lang)


@mcp.tool()
def get_pdf_comparison_status(job_id: str = "", lang: str = "ru") -> dict[str, Any]:
    """Return one comparison job status, or recent background jobs when job_id is omitted."""
    try:
        cleanup_stale_job_artifacts()
        if str(job_id or "").strip():
            return {"ok": True, "job": load_status(job_id.strip())}
        return {"ok": True, "jobs": list_statuses()}
    except Exception as exc:
        return error_result(exc, lang)


@mcp.tool()
def list_pdf_comparisons(
    out_dir: str = "runs", old_path: str = "", new_path: str = "", limit: int = 20, lang: str = "ru"
) -> dict[str, Any]:
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
        return error_result(exc, lang)


def _history_view(record: dict[str, Any]) -> dict[str, Any]:
    """The compact, agent-facing row: the number, date, origin and file names."""
    return {
        "index": record.get("index"),
        "id": record.get("id"),
        "source": record.get("source"),
        "date": record.get("date"),
        "result": record.get("result"),
        "old": Path(str(record.get("old_pdf") or "")).name,
        "new": Path(str(record.get("new_pdf") or "")).name,
        "out_dir": record.get("out_dir"),
        "run_dir": record.get("run_dir"),
    }


def _unique_restore_run_name(output_dir: Path, base: str) -> str:
    """A run-folder name under ``output_dir`` that does not collide with an existing run.

    Restore never overwrites the original: it always makes a new folder. The
    record's own name is tried first, then ``<name>_restore``, ``<name>_restore2``…
    """
    safe_base = sanitize_run_folder_name(base or "restore")
    if not (output_dir / safe_base).exists():
        return safe_base
    counter = 1
    while True:
        suffix = "_restore" if counter == 1 else f"_restore{counter}"
        candidate = sanitize_run_folder_name(f"{safe_base}{suffix}")
        if not (output_dir / candidate).exists():
            return candidate
        counter += 1


@mcp.tool()
def list_comparison_history(limit: int = 50, source: str = "", lang: str = "ru") -> dict[str, Any]:
    """List past comparisons from both the GUI and this MCP server as one numbered, dated log.

    Unlike list_pdf_comparisons (which scans a single out_dir on disk as it looks
    right now), this reads the persistent history under ~/.pdfcompare_local/ — the
    user's home, not this checkout — so it survives a fresh MCP clone or a GUI
    reinstall, and it lists runs no matter where their reports were written.

    Each row carries:
      - index: a position, newest = 1, for quick reference ("restore #5");
      - id: a stable handle ('mcp:<job>' / 'ui:<hash>') for an unambiguous restore;
      - source: 'ui' (GUI History tab) or 'mcp' (started via this server);
      - date, result, the two file names, out_dir and run_dir.

    Pass source='ui' or source='mcp' to see only one origin. The index is valid
    against the most recent listing; if another comparison finishes between listing
    and restore, prefer the id.
    """
    try:
        requested = str(source or "").strip().lower()
        source_filter = requested if requested in ("ui", "mcp") else None
        records = history_index.list_records(limit=max(1, int(limit)), source=source_filter)
        return {
            "ok": True,
            "history_dir": str(history_index.STATE_DIR),
            "source": source_filter or "all",
            "count": len(records),
            "comparisons": [_history_view(row) for row in records],
        }
    except Exception as exc:
        return error_result(exc, lang)


@mcp.tool()
def restore_comparison(
    ref: str,
    out_dir: str = "",
    run_name: str = "",
    confirm: bool = False,
    source: str = "",
    lang: str = "ru",
) -> dict[str, Any]:
    """Re-run a past comparison from history. Two steps by design.

    Step 1 (confirm=False, the default): resolve the record referenced by ``ref``
    — a position from the last list_comparison_history ('5' or '#5') or a stable
    id ('mcp:2026…', 'ui:ab12cd34') — and return its inputs and options for the
    user to confirm: which two PDFs, which settings, where the new report will go,
    and whether the source PDFs still exist on disk. Nothing runs yet.

    Step 2 (confirm=True): start a fresh comparison with those inputs. The original
    run folder is never touched — the result goes to a new folder. By default that
    is the record's out_dir with a non-colliding run name (shown as
    suggested_run_name in step 1); override with out_dir/run_name to place it
    elsewhere.
    """
    try:
        requested = str(source or "").strip().lower()
        source_filter = requested if requested in ("ui", "mcp") else None
        record = history_index.find_record(ref, source=source_filter)
        if record is None:
            raise RunFailed("history_record_not_found", ref=ref)

        replay = dict(record["replay"])
        old_path = str(record.get("old_pdf") or "")
        new_path = str(record.get("new_pdf") or "")
        old_exists = bool(old_path) and Path(old_path).exists()
        new_exists = bool(new_path) and Path(new_path).exists()

        target_out = str(out_dir or "").strip() or str(record.get("out_dir") or "") or "runs"
        output_dir = resolve_path(target_out, must_exist=False)
        base_name = str(record.get("run_name") or "") or Path(str(record.get("run_dir") or "")).name or "restore"
        suggested = _unique_restore_run_name(output_dir, base_name)

        if not confirm:
            return {
                "ok": True,
                "requires_user_choice": True,
                "record": _history_view(record),
                "inputs": {
                    "old_path": old_path,
                    "new_path": new_path,
                    "old_exists": old_exists,
                    "new_exists": new_exists,
                    **replay,
                },
                "target_out_dir": str(output_dir),
                "suggested_run_name": suggested,
                "files_missing": (not old_exists) or (not new_exists),
                "next_step": (
                    "Покажи пользователю параметры записи и спроси подтверждение. Затем вызови "
                    "restore_comparison ещё раз с confirm=true (при желании передай свои out_dir/run_name)."
                ),
                "lang": lang,
            }

        missing = [path for path, ok in ((old_path, old_exists), (new_path, new_exists)) if not ok]
        if missing:
            raise RunFailed("history_source_files_missing", paths="; ".join(missing))

        final_run_name = str(run_name or "").strip() or suggested
        return start_pdf_comparison(
            old_path=old_path,
            new_path=new_path,
            out_dir=str(output_dir),
            run_name=final_run_name,
            dpi=int(replay["dpi"]),
            stroke_tol=float(replay["stroke_tol"]),
            diff_strictness=str(replay["diff_strictness"]),
            exclude_regions=replay["exclude_regions"] or None,
            bbox_merge_gap_mm=float(replay["bbox_merge_gap_mm"]),
            bbox_merge_max_area_ratio=float(replay["bbox_merge_max_area_ratio"]),
            lang=lang,
            keep_debug_images=bool(replay["keep_debug_images"]),
            ignore_line_weight=bool(replay["ignore_line_weight"]),
        )
    except Exception as exc:
        return error_result(exc, lang)


@mcp.tool()
def cancel_pdf_comparison(
    job_id: str, grace_sec: float = 20.0, max_wait_sec: float = 300.0, lang: str = "ru"
) -> dict[str, Any]:
    """Stop a running background job. Asks first, kills only as a last resort.

    A re-render rewrites an existing report in place, so a worker killed between
    "new pages swapped in" and "summary/report written" leaves the run inconsistent
    with no rollback — the transaction only lives in the worker's memory. So we drop
    a cancel marker and let the worker unwind.

    ``grace_sec`` is *not* a deadline for finishing: it is how long the worker may
    stay **silent**. A worker that keeps its heartbeat going is working, not stuck —
    one heavy A0 sheet at 600 DPI outlasts any fixed grace — and a worker that has
    acknowledged the cancel is rolling back, which is the worst possible moment to
    kill it. Both are left alone until ``max_wait_sec``. Force-kill is reserved for
    a worker that has actually stopped responding; it comes back as ``forced=true``
    with the warning that the report may be inconsistent.

    The PID is re-verified (creation time, then command line) on every poll and once
    more immediately before the kill: Windows recycles PIDs within seconds, and a
    worker that exits mid-wait must not get a stranger killed in its place.
    """
    try:
        status = load_status(job_id)
        if str(status.get("state") or "") not in ACTIVE_JOB_STATES:
            return error_result(RunFailed("job_not_running", job_id=job_id), lang) | {"job": status}
        pid = worker_pid_for_job(job_id, status)
        if not pid:
            return error_result(RunFailed("job_no_pid", job_id=job_id), lang)
        if not process_matches_worker_job(pid, job_id):
            return error_result(RunFailed("job_pid_foreign", job_id=job_id), lang) | {"job": status}

        marker = cancel_marker_path(job_id)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(now_iso(), encoding="utf-8")

        started = time.time()
        hard_deadline = started + max(0.0, float(max_wait_sec))
        silence_limit = max(1.0, float(grace_sec))
        acknowledged = False
        forced = False
        reason = "exited"

        while worker_process_alive(pid, job_id):
            acknowledged = acknowledged or cancel_acknowledged(job_id)
            now = time.time()
            beat = worker_liveness(job_id)
            silent_for = now - beat if beat else now - started
            if now >= hard_deadline:
                reason = "max_wait"
                break
            if silent_for >= silence_limit:
                reason = "unresponsive"
                break
            time.sleep(CANCEL_POLL_SEC)

        # The worker may have exited during the last sleep and had its PID handed to
        # something else. Never signal a process we have not just re-confirmed.
        pid_reused = False
        if reason in {"max_wait", "unresponsive"}:
            if process_matches_worker_job(pid, job_id):
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
                else:
                    os.kill(pid, signal.SIGTERM)
                forced = True
            else:
                pid_reused = pid_exists(pid)
                reason = "exited"
        else:
            pid_reused = pid_exists(pid)

        out_dir = status.get("out_dir")
        if out_dir:
            shutil.rmtree(Path(str(out_dir)) / f".pdfcompare_mcp_{job_id}", ignore_errors=True)

        waited_sec = round(time.time() - started, 2)
        # The worker writes its own "cancelled" status when it unwinds cleanly; only
        # overwrite it when we killed it, or when it never got that far.
        status = load_status(job_id)
        if forced or str(status.get("state") or "") in ACTIVE_JOB_STATES:
            if forced:
                message = (
                    "Задача принудительно остановлена: worker перестал отвечать "
                    f"({reason}); отчёт мог остаться в промежуточном состоянии"
                )
            elif pid_reused:
                message = (
                    "Worker уже завершился сам; его PID успел занять другой процесс, "
                    "поэтому принудительное завершение не выполнялось"
                )
            else:
                message = "Задача остановлена пользователем"
            status.update(
                {
                    "state": "cancelled",
                    "message": message,
                    "forced": forced,
                    "cancel_acknowledged": acknowledged,
                    "cancel_reason": reason,
                    "pid_reused": pid_reused,
                    "waited_sec": waited_sec,
                    "updated_at": now_iso(),
                }
            )
            atomic_write_json(job_dir(job_id) / "status.json", status)
        return {
            "ok": True,
            "forced": forced,
            "cancel_acknowledged": acknowledged,
            "cancel_reason": reason,
            "pid_reused": pid_reused,
            "waited_sec": waited_sec,
            "job": status,
        }
    except Exception as exc:
        return error_result(exc, lang)


def resolve_transport(raw: str) -> Literal["stdio", "sse", "streamable-http"]:
    """Reject an unknown transport here, not inside FastMCP.

    A typo used to reach ``mcp.run()`` as a plain string and fail somewhere in the
    library — and, worse, it slipped past the non-stdio guard below, because
    anything that is not literally "stdio" was treated as a network transport.
    """
    wanted = str(raw or "stdio").strip().lower()
    for transport in TRANSPORTS:
        if wanted == transport:
            return transport
    raise SystemExit(f"Unknown PDFCOMPARE_MCP_TRANSPORT: {raw!r}. Allowed: {', '.join(TRANSPORTS)}.")


def main() -> None:
    transport = resolve_transport(os.getenv("PDFCOMPARE_MCP_TRANSPORT", "stdio"))
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
