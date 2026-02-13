from __future__ import annotations

import argparse
import csv
import gc
import html
import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Sequence, Tuple
from uuid import uuid4

import cv2
import fitz
import numpy as np


TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9]{3,}")
SHEET_RU_RE = re.compile(
    r"(?:\bЛИСТ(?:\s*№)?|\bЛ\.)\s*[:№#-]?\s*([A-ZА-Я]{0,3}\d{1,4}[A-ZА-Я]{0,3})",
    re.IGNORECASE,
)
SHEET_EN_RE = re.compile(
    r"\bSHEET\s*[:#-]?\s*([A-Z]{0,3}\d{1,4}[A-Z]{0,3})\b",
    re.IGNORECASE,
)
SHEET_FRACTION_RE = re.compile(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b")


@dataclass
class PageInfo:
    index: int
    thumb: np.ndarray
    text_tokens: set[str]
    width_pt: float
    height_pt: float
    sheet_mark: str | None


@dataclass
class MatchPair:
    a_idx: int | None
    b_idx: int | None
    status: str  # matched | added | removed
    score: float


def render_page(doc: fitz.Document, page_index: int, dpi: int) -> np.ndarray:
    page = doc[page_index]
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
    return arr


def page_tokens(text: str) -> set[str]:
    return {m.group(0).upper() for m in TOKEN_RE.finditer(text)}


def normalize_sheet_mark(raw: str) -> str:
    mark = raw.strip().upper()
    mark = re.sub(r"[\s_]+", "", mark)
    mark = mark.replace("№", "")
    return mark


def extract_sheet_mark(text: str) -> str | None:
    for rx in (SHEET_RU_RE, SHEET_EN_RE):
        m = rx.search(text)
        if m:
            return normalize_sheet_mark(m.group(1))
    m_frac = SHEET_FRACTION_RE.search(text)
    if m_frac:
        return normalize_sheet_mark(m_frac.group(1))
    return None


def imread_compat(path: Path, flags: int = cv2.IMREAD_UNCHANGED) -> np.ndarray | None:
    """Unicode-safe image read for Windows paths."""
    try:
        raw = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if raw.size == 0:
        return None
    return cv2.imdecode(raw, flags)


def imwrite_compat(path: Path, img: np.ndarray) -> None:
    """Unicode-safe image write for Windows paths."""
    ext = path.suffix.lower() or ".png"
    ok, encoded = cv2.imencode(ext, img)
    if not ok:
        raise RuntimeError(f"Не удалось закодировать изображение для {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(str(path))


def build_page_info(
    doc_path: Path,
    thumb_dpi: int = 96,
    progress_cb: Callable[[int, int, str], None] | None = None,
    label: str = "",
) -> List[PageInfo]:
    infos: List[PageInfo] = []
    with fitz.open(doc_path) as doc:
        total = len(doc)
        for i in range(total):
            img = render_page(doc, i, thumb_dpi)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            thumb = cv2.resize(gray, (160, 160), interpolation=cv2.INTER_AREA)
            text = doc[i].get_text("text") or ""
            rect = doc[i].rect
            infos.append(
                PageInfo(
                    index=i,
                    thumb=thumb,
                    text_tokens=page_tokens(text),
                    width_pt=float(rect.width),
                    height_pt=float(rect.height),
                    sheet_mark=extract_sheet_mark(text),
                )
            )
            if progress_cb is not None:
                progress_cb(i + 1, total, label)
    return infos


def visual_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return 0.0
    # Robust to brightness shifts: compare normalized images.
    a_n = cv2.normalize(a, None, 0, 255, cv2.NORM_MINMAX)
    b_n = cv2.normalize(b, None, 0, 255, cv2.NORM_MINMAX)
    mse = float(np.mean((a_n.astype(np.float32) - b_n.astype(np.float32)) ** 2))
    return max(0.0, 1.0 - mse / (255.0 * 255.0))


def text_similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def sheet_mark_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    da = "".join(ch for ch in a if ch.isdigit())
    db = "".join(ch for ch in b if ch.isdigit())
    if da and db and da == db:
        return 0.65
    return 0.0


def size_compatible(a: PageInfo, b: PageInfo) -> bool:
    area_a = a.width_pt * a.height_pt
    area_b = b.width_pt * b.height_pt
    if area_a <= 0 or area_b <= 0:
        return False
    area_ratio = min(area_a, area_b) / max(area_a, area_b)
    aspect_a = a.width_pt / a.height_pt
    aspect_b = b.width_pt / b.height_pt
    aspect_delta = abs(aspect_a - aspect_b) / max(aspect_a, aspect_b)
    # Hard gate: different paper format should not be matched.
    return area_ratio >= 0.96 and aspect_delta <= 0.015


def pair_similarity(a: PageInfo, b: PageInfo) -> float:
    if not size_compatible(a, b):
        return 0.0
    v = visual_similarity(a.thumb, b.thumb)
    t = text_similarity(a.text_tokens, b.text_tokens)
    base = 0.72 * v + 0.28 * t if (a.text_tokens or b.text_tokens) else v
    sm = sheet_mark_similarity(a.sheet_mark, b.sheet_mark)
    if a.sheet_mark and b.sheet_mark:
        if sm >= 0.99:
            base += 0.20
        elif sm >= 0.60:
            base += 0.08
        else:
            base -= 0.22
    return float(max(0.0, min(1.0, base)))


def linear_sum_assignment(cost: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    c = np.asarray(cost, dtype=np.float64)
    if c.ndim != 2:
        raise ValueError("Матрица стоимости должна быть двумерной")
    n_rows, n_cols = c.shape
    transposed = False
    if n_rows > n_cols:
        c = c.T
        n_rows, n_cols = c.shape
        transposed = True
    u = np.zeros(n_rows + 1, dtype=np.float64)
    v = np.zeros(n_cols + 1, dtype=np.float64)
    p = np.zeros(n_cols + 1, dtype=np.int32)
    way = np.zeros(n_cols + 1, dtype=np.int32)
    for i in range(1, n_rows + 1):
        p[0] = i
        j0 = 0
        minv = np.full(n_cols + 1, np.inf, dtype=np.float64)
        used = np.zeros(n_cols + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = np.inf
            j1 = 0
            for j in range(1, n_cols + 1):
                if used[j]:
                    continue
                cur = c[i0 - 1, j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(0, n_cols + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = np.full(n_rows, -1, dtype=np.int32)
    for j in range(1, n_cols + 1):
        if p[j] != 0:
            assignment[p[j] - 1] = j - 1
    row_ind = np.arange(n_rows, dtype=np.int32)
    col_ind = assignment
    keep = col_ind >= 0
    row_ind = row_ind[keep]
    col_ind = col_ind[keep]
    if transposed:
        orig_row = col_ind.astype(np.int32)
        orig_col = row_ind.astype(np.int32)
        order = np.argsort(orig_row)
        return orig_row[order], orig_col[order]
    order = np.argsort(row_ind)
    return row_ind[order], col_ind[order]


def align_pages_hungarian(pages_a: Sequence[PageInfo], pages_b: Sequence[PageInfo]) -> List[MatchPair]:
    n, m = len(pages_a), len(pages_b)
    k = max(n, m)
    unmatched_cost = 0.35
    incompatible_cost = 1.20
    match_threshold = 0.55
    cost = np.full((k, k), unmatched_cost, dtype=np.float64)
    sims = np.zeros((n, m), dtype=np.float64)
    for i in range(n):
        for j in range(m):
            if size_compatible(pages_a[i], pages_b[j]):
                sim = pair_similarity(pages_a[i], pages_b[j])
                sims[i, j] = sim
                cost[i, j] = 1.0 - sim
            else:
                cost[i, j] = incompatible_cost
    if k > n and k > m:
        cost[n:, m:] = 0.0
    rows, cols = linear_sum_assignment(cost)
    matched_by_a: dict[int, tuple[int, float]] = {}
    removed: set[int] = set()
    added: set[int] = set()
    for i, j in zip(rows, cols):
        if i < n and j < m:
            sim = float(sims[i, j])
            if sim >= match_threshold and size_compatible(pages_a[i], pages_b[j]):
                matched_by_a[int(i)] = (int(j), sim)
            else:
                removed.add(int(i))
                added.add(int(j))
        elif i < n and j >= m:
            removed.add(int(i))
        elif i >= n and j < m:
            added.add(int(j))
    out: List[MatchPair] = []
    emitted_added: set[int] = set()
    for a_idx in range(n):
        if a_idx in matched_by_a:
            b_idx, sim = matched_by_a[a_idx]
            for add_idx in sorted(x for x in added if x < b_idx and x not in emitted_added):
                out.append(MatchPair(None, add_idx, "added", 0.0))
                emitted_added.add(add_idx)
            out.append(MatchPair(a_idx, b_idx, "matched", sim))
        else:
            out.append(MatchPair(a_idx, None, "removed", 0.0))
    for add_idx in sorted(x for x in added if x not in emitted_added):
        out.append(MatchPair(None, add_idx, "added", 0.0))
    return out


def align_pages_monotonic(pages_a: Sequence[PageInfo], pages_b: Sequence[PageInfo]) -> List[MatchPair]:
    """
    Sequence-preserving page mapping.
    Guarantees non-crossing links: page order in A and B remains monotonic.
    """
    n, m = len(pages_a), len(pages_b)
    gap_cost = 0.43
    mismatch_penalty = 0.45
    match_threshold = 0.58

    sims = np.zeros((n, m), dtype=np.float64)
    compatible = np.zeros((n, m), dtype=bool)
    for i in range(n):
        for j in range(m):
            ok = size_compatible(pages_a[i], pages_b[j])
            compatible[i, j] = ok
            if ok:
                sims[i, j] = pair_similarity(pages_a[i], pages_b[j])

    dp = np.full((n + 1, m + 1), np.inf, dtype=np.float64)
    act = np.zeros((n + 1, m + 1), dtype=np.int8)  # 1=match, 2=remove, 3=add
    dp[0, 0] = 0.0

    for i in range(1, n + 1):
        dp[i, 0] = dp[i - 1, 0] + gap_cost
        act[i, 0] = 2
    for j in range(1, m + 1):
        dp[0, j] = dp[0, j - 1] + gap_cost
        act[0, j] = 3

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = dp[i - 1, j] + gap_cost
            action = 2

            add_val = dp[i, j - 1] + gap_cost
            if add_val < best:
                best = add_val
                action = 3

            sim = float(sims[i - 1, j - 1])
            match_cost = 1.0 - sim
            if not compatible[i - 1, j - 1]:
                match_cost += 1.5
            elif sim < match_threshold:
                match_cost += mismatch_penalty
            match_val = dp[i - 1, j - 1] + match_cost
            if match_val < best:
                best = match_val
                action = 1

            dp[i, j] = best
            act[i, j] = action

    rev_ops: list[tuple[str, int | None, int | None, float]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and act[i, j] == 1:
            sim = float(sims[i - 1, j - 1])
            if compatible[i - 1, j - 1] and sim >= match_threshold:
                rev_ops.append(("M", i - 1, j - 1, sim))
            else:
                rev_ops.append(("A", None, j - 1, 0.0))
                rev_ops.append(("R", i - 1, None, 0.0))
            i -= 1
            j -= 1
        elif i > 0 and (j == 0 or act[i, j] == 2):
            rev_ops.append(("R", i - 1, None, 0.0))
            i -= 1
        else:
            rev_ops.append(("A", None, j - 1, 0.0))
            j -= 1

    out: List[MatchPair] = []
    for op, a_idx, b_idx, sim in reversed(rev_ops):
        if op == "M":
            out.append(MatchPair(a_idx, b_idx, "matched", sim))
        elif op == "R":
            out.append(MatchPair(a_idx, None, "removed", 0.0))
        else:
            out.append(MatchPair(None, b_idx, "added", 0.0))
    return out


def alignment_quality(pairs: Sequence[MatchPair], n_a: int, n_b: int) -> float:
    matched = [p for p in pairs if p.status == "matched" and p.a_idx is not None and p.b_idx is not None]
    if matched:
        sim_avg = float(sum(float(p.score) for p in matched) / len(matched))
    else:
        sim_avg = 0.0
    gap_count = sum(1 for p in pairs if p.status in {"added", "removed"})
    gap_ratio = gap_count / max(1, n_a + n_b)
    b_seq = [int(p.b_idx) for p in matched]
    inv = 0
    total = 0
    for i in range(len(b_seq)):
        for j in range(i + 1, len(b_seq)):
            total += 1
            if b_seq[i] > b_seq[j]:
                inv += 1
    cross_ratio = (inv / total) if total else 0.0
    return sim_avg - 0.38 * gap_ratio - 0.10 * cross_ratio


def align_pages_v1(pages_a: Sequence[PageInfo], pages_b: Sequence[PageInfo]) -> List[MatchPair]:
    global_map = align_pages_hungarian(pages_a, pages_b)
    mono_map = align_pages_monotonic(pages_a, pages_b)
    q_global = alignment_quality(global_map, len(pages_a), len(pages_b))
    q_mono = alignment_quality(mono_map, len(pages_a), len(pages_b))
    # Use monotonic only when its quality is close enough or better.
    if q_mono >= q_global - 0.04:
        return mono_map
    return global_map


def align_ecc(base_bgr: np.ndarray, moving_bgr: np.ndarray) -> Tuple[np.ndarray, bool]:
    base_gray = cv2.cvtColor(base_bgr, cv2.COLOR_BGR2GRAY)
    moving_gray = cv2.cvtColor(moving_bgr, cv2.COLOR_BGR2GRAY)
    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-6)
    try:
        cv2.findTransformECC(base_gray, moving_gray, warp, cv2.MOTION_AFFINE, criteria, None, 5)
        aligned = cv2.warpAffine(
            moving_bgr,
            warp,
            (base_bgr.shape[1], base_bgr.shape[0]),
            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return aligned, True
    except cv2.error:
        return moving_bgr, False


def harmonize_canvas(a_bgr: np.ndarray, b_bgr: np.ndarray, max_delta: int = 3) -> Tuple[np.ndarray, np.ndarray] | None:
    ha, wa = a_bgr.shape[:2]
    hb, wb = b_bgr.shape[:2]
    if abs(ha - hb) > max_delta or abs(wa - wb) > max_delta:
        return None
    h = max(ha, hb)
    w = max(wa, wb)
    if ha != h or wa != w:
        a_bgr = cv2.copyMakeBorder(a_bgr, 0, h - ha, 0, w - wa, cv2.BORDER_REPLICATE)
    if hb != h or wb != w:
        b_bgr = cv2.copyMakeBorder(b_bgr, 0, h - hb, 0, w - wb, cv2.BORDER_REPLICATE)
    return a_bgr, b_bgr


def compute_diff(
    a_bgr: np.ndarray, b_bgr: np.ndarray, stroke_tol_px: float = 2.0
) -> Tuple[np.ndarray, np.ndarray, List[Tuple[int, int, int, int]], float]:
    hb, wb = b_bgr.shape[:2]
    ha, wa = a_bgr.shape[:2]
    if (ha, wa) != (hb, wb):
        raise ValueError(f"Разные размеры растра: A={wa}x{ha}, B={wb}x{hb}")

    # Robust comparison for engineering drawings:
    # ignore tiny raster/antialias thickness differences by tolerance in pixels.
    gray_a = cv2.cvtColor(a_bgr, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(b_bgr, cv2.COLOR_BGR2GRAY)
    gray_a = cv2.GaussianBlur(gray_a, (3, 3), 0)
    gray_b = cv2.GaussianBlur(gray_b, (3, 3), 0)

    _, bw_a = cv2.threshold(gray_a, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, bw_b = cv2.threshold(gray_b, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    fg_a = cv2.bitwise_not(bw_a)  # dark strokes/text as foreground
    fg_b = cv2.bitwise_not(bw_b)

    # remove tiny raster speckles
    noise_kernel = np.ones((2, 2), np.uint8)
    fg_a = cv2.morphologyEx(fg_a, cv2.MORPH_OPEN, noise_kernel, iterations=1)
    fg_b = cv2.morphologyEx(fg_b, cv2.MORPH_OPEN, noise_kernel, iterations=1)

    dt_to_b = cv2.distanceTransform(cv2.bitwise_not(fg_b), cv2.DIST_L2, 3)
    dt_to_a = cv2.distanceTransform(cv2.bitwise_not(fg_a), cv2.DIST_L2, 3)
    mask_del = cv2.bitwise_and(fg_a, (dt_to_b > stroke_tol_px).astype(np.uint8) * 255)  # was in A, not in B
    mask_add = cv2.bitwise_and(fg_b, (dt_to_a > stroke_tol_px).astype(np.uint8) * 255)  # new in B
    mask = cv2.bitwise_or(mask_del, mask_add)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bboxes: List[Tuple[int, int, int, int]] = []
    for c in contours:
        area = cv2.contourArea(c)
        if area >= 180:
            x, y, w, h = cv2.boundingRect(c)
            bboxes.append((int(x), int(y), int(w), int(h)))

    diff_percent = (cv2.countNonZero(mask) / mask.size) * 100.0

    overlay = b_bgr.copy()
    # two-color semi-transparent overlay:
    # old-only pixels -> pale blue (50%), new-only pixels -> bright red (30%)
    alpha_old = 0.50
    alpha_new = 0.30
    mask_del_idx = mask_del > 0
    if np.any(mask_del_idx):
        del_color = np.array((255.0, 190.0, 120.0), dtype=np.float32)
        src = overlay[mask_del_idx].astype(np.float32)
        overlay[mask_del_idx] = np.clip(src * (1.0 - alpha_old) + del_color * alpha_old, 0, 255).astype(np.uint8)
    mask_add_idx = mask_add > 0
    if np.any(mask_add_idx):
        add_color = np.array((0.0, 0.0, 255.0), dtype=np.float32)
        src = overlay[mask_add_idx].astype(np.float32)
        overlay[mask_add_idx] = np.clip(src * (1.0 - alpha_new) + add_color * alpha_new, 0, 255).astype(np.uint8)

    return mask, overlay, bboxes, float(diff_percent)


def classify(diff_percent: float) -> str:
    if diff_percent < 0.15:
        return "unchanged"
    if diff_percent < 1.0:
        return "minor"
    if diff_percent < 5.0:
        return "moderate"
    return "major"


def write_summary_md(
    out_path: Path,
    file_a: Path,
    file_b: Path,
    pairs: Sequence[MatchPair],
    details: Sequence[dict],
    lang: str = "ru",
) -> None:
    matched = sum(1 for p in pairs if p.status == "matched")
    added = sum(1 for p in pairs if p.status == "added")
    removed = sum(1 for p in pairs if p.status == "removed")
    unchanged = sum(1 for d in details if d["status"] == "matched" and d["change_level"] == "unchanged")
    changed = matched - unchanged

    en = str(lang).lower().startswith("en")
    if en:
        lines = [
            "# PDF Compare Report",
            "",
            f"- Document A: `{file_a.name}`",
            f"- Document B: `{file_b.name}`",
            f"- Matched pages: **{matched}**",
            f"- Changed pages: **{changed}**",
            f"- Unchanged pages: **{unchanged}**",
            f"- Added in B: **{added}**",
            f"- Removed from A: **{removed}**",
            "",
            "## Page mapping",
            "",
            "| A page | B page | status | score | diff % | level |",
            "|---:|---:|---|---:|---:|---|",
        ]
    else:
        lines = [
            "# Отчет сравнения PDF",
            "",
            f"- Документ A: `{file_a.name}`",
            f"- Документ B: `{file_b.name}`",
            f"- Сопоставленных листов: **{matched}**",
            f"- Листов с изменениями: **{changed}**",
            f"- Листов без изменений: **{unchanged}**",
            f"- Добавлено листов в B: **{added}**",
            f"- Удалено листов из A: **{removed}**",
            "",
            "## Карта соответствия листов",
            "",
            "| Лист A | Лист B | статус | оценка | разница % | уровень |",
            "|---:|---:|---|---:|---:|---|",
        ]
    for d in details:
        a = "-" if d["a_page"] is None else str(d["a_page"])
        b = "-" if d["b_page"] is None else str(d["b_page"])
        diffp = "-" if d["diff_percent"] is None else f'{d["diff_percent"]:.3f}'
        lvl = "-" if d["change_level"] is None else d["change_level"]
        lines.append(f"| {a} | {b} | {d['status']} | {d['score']:.3f} | {diffp} | {lvl} |")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_engineer_report_md(out_path: Path, file_a: Path, file_b: Path, details: Sequence[dict], lang: str = "ru") -> None:
    en = str(lang).lower().startswith("en")
    matched = [d for d in details if d["status"] == "matched"]
    added = [d for d in details if d["status"] == "added"]
    removed = [d for d in details if d["status"] == "removed"]
    size_mismatch = [d for d in details if d["status"] == "size_mismatch"]

    unchanged = [d for d in matched if d["change_level"] == "unchanged"]
    minor = [d for d in matched if d["change_level"] == "minor"]
    moderate = [d for d in matched if d["change_level"] == "moderate"]
    major = [d for d in matched if d["change_level"] == "major"]

    if en:
        lines = [
            "# Engineering PDF Compare Report",
            "",
            f"- Base document (A): `{file_a.name}`",
            f"- New document (B): `{file_b.name}`",
            "",
            "## Summary",
            "",
            f"- Matched sheets: **{len(matched)}**",
            f"- Added in B: **{len(added)}**",
            f"- Removed from A: **{len(removed)}**",
            f"- Unchanged: **{len(unchanged)}**",
            f"- Minor changes: **{len(minor)}**",
            f"- Moderate changes: **{len(moderate)}**",
            f"- Major changes: **{len(major)}**",
        ]
    else:
        lines = [
            "# Инженерный отчёт сравнения PDF",
            "",
            f"- Базовый документ (A): `{file_a.name}`",
            f"- Новый документ (B): `{file_b.name}`",
            "",
            "## Краткий итог",
            "",
            f"- Сопоставлено листов: **{len(matched)}**",
            f"- Добавлено листов в B: **{len(added)}**",
            f"- Удалено листов из A: **{len(removed)}**",
            f"- Без изменений: **{len(unchanged)}**",
            f"- Небольшие изменения: **{len(minor)}**",
            f"- Заметные изменения: **{len(moderate)}**",
            f"- Сильные изменения: **{len(major)}**",
        ]

    if size_mismatch:
        lines.append(
            f"- {'Incompatible sheet format' if en else 'Несовместимый формат листа'}: **{len(size_mismatch)}**"
        )

    lines.extend(
        [
            "",
            "## Added sheets" if en else "## Добавленные листы",
            "",
        ]
    )
    if added:
        for d in added:
            lines.append(f"- B{d['b_page']}: {'new sheet in revision' if en else 'новый лист в ревизии'}")
    else:
        lines.append("- None" if en else "- Нет")

    lines.extend(
        [
            "",
            "## Removed sheets" if en else "## Удалённые листы",
            "",
        ]
    )
    if removed:
        for d in removed:
            lines.append(f"- A{d['a_page']}: {'sheet missing in new revision' if en else 'лист отсутствует в новой ревизии'}")
    else:
        lines.append("- None" if en else "- Нет")

    def emit_changes(title: str, rows: Sequence[dict]) -> None:
        lines.extend(["", f"## {title}", ""])
        if not rows:
            lines.append("- None" if en else "- Нет")
            return
        for d in sorted(rows, key=lambda x: (x.get("diff_percent") or 0.0), reverse=True):
            lines.append(
                f"- A{d['a_page']} -> B{d['b_page']}: {'diff' if en else 'разница'}={d['diff_percent']:.3f}%"
                f", bbox={d['bboxes_count']}"
            )

    emit_changes("Unchanged" if en else "Без изменений", unchanged)
    emit_changes("Minor changes" if en else "Небольшие изменения", minor)
    emit_changes("Moderate changes" if en else "Заметные изменения", moderate)
    emit_changes("Major changes" if en else "Сильные изменения", major)

    if size_mismatch:
        lines.extend(["", "## Incompatible sheet format" if en else "## Несовместимый формат листа", ""])
        for d in size_mismatch:
            lines.append(
                f"- A{d['a_page']} -> B{d['b_page']}: {'sheet sizes do not match' if en else 'размеры листов не совпадают'}"
            )

    lines.extend(
        [
            "",
            "## Note" if en else "## Примечание",
            "",
            "- Each mapped pair has a folder `pages/<seq>__A_<n>__B_<m>/` with `overlay.png`, `mask.png`, `bboxes.json`."
            if en
            else "- Для каждой сопоставленной пары есть папка `pages/<seq>__A_<n>__B_<m>/` c `overlay.png`, `mask.png`, `bboxes.json`.",
        ]
    )

    out_path.write_text("\n".join(lines), encoding="utf-8")


def status_and_confidence(row: dict) -> Tuple[str, str, str, bool]:
    status = row["status"]
    moved = bool(row.get("a_page") and row.get("b_page") and row["a_page"] != row["b_page"])
    if status == "added":
        return "ADDED", "NONE", "ADDED", False
    if status == "removed":
        return "REMOVED", "NONE", "REMOVED", False
    if status == "size_mismatch":
        return "CHANGED", "NONE", "CHANGED", moved

    diff = row.get("diff_percent")
    content_status = "UNCHANGED" if diff is not None and diff < 0.15 else "CHANGED"
    page_status = content_status

    score = float(row.get("score") or 0.0)
    if score >= 0.98:
        conf = "EXACT"
    elif score >= 0.75:
        conf = "PROBABLE"
    else:
        conf = "NONE"
    return page_status, conf, content_status, moved


def copy_thumb(src: Path | None, dst: Path, max_w: int = 420) -> None:
    if src is None or not src.exists():
        return
    img = imread_compat(src, cv2.IMREAD_UNCHANGED)
    if img is None:
        return
    h, w = img.shape[:2]
    if w > max_w:
        scale = max_w / float(w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    imwrite_compat(dst, img)


def build_compact_report_zip(run_dir: Path, zip_base: Path) -> Path:
    """Create shareable zip with report_bundle + only files required for HTML navigation."""
    zip_path = Path(str(zip_base) + ".zip")
    pages_allow = {
        "a.png",
        "a_preview.png",
        "b.png",
        "b_preview.png",
        "overlay.png",
        "bbox_overlay.png",
        "bboxes.json",
    }

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        report_bundle = run_dir / "report_bundle"
        if report_bundle.exists():
            for fp in report_bundle.rglob("*"):
                if fp.is_file():
                    zf.write(fp, arcname=str(fp.relative_to(run_dir)).replace("\\", "/"))

        pages_dir = run_dir / "pages"
        if pages_dir.exists():
            for pair_dir in pages_dir.iterdir():
                if not pair_dir.is_dir():
                    continue
                for fp in pair_dir.iterdir():
                    if fp.is_file() and fp.name in pages_allow:
                        zf.write(fp, arcname=str(fp.relative_to(run_dir)).replace("\\", "/"))

        # Keep lightweight run-level summaries.
        for name in ("summary.json", "summary.md", "engineer_report.md", "page_map.csv"):
            fp = run_dir / name
            if fp.exists() and fp.is_file():
                zf.write(fp, arcname=name)

    return zip_path


def generate_html_report(
    run_dir: Path,
    file_a: Path,
    file_b: Path,
    details: Sequence[dict],
    high_dpi: int,
    stroke_tol_px: float,
    report_lang: str = "ru",
    progress_cb: Callable[[float, str], None] | None = None,
) -> Path:
    def emit(pct: float, msg: str) -> None:
        if progress_cb is not None:
            progress_cb(float(max(0.0, min(100.0, pct))), msg)

    lang = "en" if str(report_lang).lower().startswith("en") else "ru"
    t = {
        "ru": {
            "progress_prepare_bundle": "Подготовка папки отчета...",
            "progress_prepare_pages": "Подготовка страниц отчета {idx}/{total}",
            "progress_generate_view": "Генерация HTML вида {idx}/{total}",
            "progress_pack_zip": "Упаковка report.zip...",
            "status_new_sheet": "новый лист",
            "status_changed_short": "Есть изменения",
            "status_unchanged_short": "без изменений",
            "note_new_only": "Лист присутствует только в новом документе.",
            "note_removed_in_b": "Лист отсутствует в новом документе (удален относительно A).",
            "note_no_significant": "Существенные изменения не обнаружены.",
            "note_visual_changes": "Обнаружены изменения визуального содержимого: разница={d:.3f}%.",
            "note_ecc_failed": "ECC-выравнивание не сошлось, сравнение выполнено без выравнивания.",
            "nav_sheet_word": "лист",
            "conf_exact": "точное",
            "conf_probable": "вероятное",
            "conf_none": "нет",
            "status_col_changed": "ИЗМЕНЕН",
            "status_col_unchanged": "БЕЗ ИЗМЕНЕНИЙ",
            "status_col_added": "НОВЫЙ",
            "status_col_removed": "УДАЛЕН",
            "level_major": "КРУПНЫЕ",
            "level_moderate": "СРЕДНИЕ",
            "level_minor": "МАЛЫЕ",
            "level_unchanged": "БЕЗ ИЗМЕНЕНИЙ",
            "pv_old": "СТАР",
            "pv_new": "НОВ",
            "pv_diff": "ДИФ",
            "pv_new_pill": "НОВЫЙ",
            "pv_removed_pill": "УДАЛЕН",
            "pv_preview_pill": "ПРЕВЬЮ",
            "title_matrix": "Сводка сравнения PDF - матрица изменений",
            "subtitle_docs": "Документ A: {a} ({ac} листов) → Документ B: {b} ({bc} листов)",
            "chip_all": "Все",
            "chip_changed": "Есть изменения",
            "chip_added": "Новый лист",
            "chip_removed": "Удален",
            "chip_major": "Крупные",
            "chip_moderate": "Средние",
            "chip_minor": "Малые",
            "search_sheet": "Поиск листа...",
            "th_seq_b": "Порядок (B)",
            "th_a_page": "Лист A",
            "th_b_page": "Лист B",
            "th_status": "Статус",
            "th_level": "Уровень изменений",
            "th_diff": "Разница %",
            "th_boxes": "Δ зоны",
            "th_preview": "Превью",
            "th_open": "Открыть",
            "empty_filter": "Нет листов по выбранному фильтру.",
            "summary_title": "Сводка",
            "summary_changed": "Есть изменения:",
            "summary_added": "Новые листы:",
            "summary_removed": "Удалено листов:",
            "summary_unchanged": "Без изменений:",
            "legend_title": "Легенда",
            "legend_major_desc": "существенные изменения",
            "legend_moderate_desc": "заметные изменения",
            "legend_minor_desc": "небольшие изменения",
            "legend_added_desc": "лист добавлен в B",
            "legend_removed_desc": "удален / отсутствует",
            "foot_open_row": "Нажмите строку для детального просмотра СТАРЫЙ / НОВЫЙ / РАЗНИЦА",
            "open_sheet_title": "Открыть лист",
            "nav_title": "Навигация по листам",
            "back_summary": "← К сводке",
            "summary_preview_title": "Превью сводки",
            "search_hint": "Поиск (например, 5)",
            "old_document": "Старый документ",
            "new_document": "Новый документ",
            "moved_label": "перемещен",
            "conf_label": "уверенность",
            "diff_label": "разница",
            "open_old_win": "Открыть <span class=\"tag tag-old\">СТАРЫЙ</span> в приложении Windows",
            "open_new_win": "Открыть <span class=\"tag tag-new\">НОВЫЙ</span> в приложении Windows",
            "open_diff_win": "Открыть <span class=\"tag tag-diff\">РАЗНИЦА</span> в приложении Windows",
            "slider_mode": "↔ Режим сравнения (слайдер)",
            "cap_old": "СТАРЫЙ",
            "cap_new": "НОВЫЙ",
            "cap_diff": "РАЗНИЦА",
            "no_data": "нет данных",
            "prev_page": "← предыдущий",
            "next_page": "следующий →",
            "slider_title_page": "Слайдер сравнения лист {b}",
            "slider_mode_title": "Режим сравнения (слайдер)",
            "slider_subtitle": "{a_name} лист {a_idx} ↔ {b_name} лист {b_idx}",
            "back_to_sheet": "Назад к листу",
            "fit_to_window": "Вписать в окно",
            "slider_old": "СТАРЫЙ",
            "slider_new": "НОВЫЙ",
            "slider_zoom": "Масштаб",
            "slider_help": "Режим 1:1 по умолчанию. ЛКМ по чертежу — двигать разделитель, ПКМ+перетаскивание — панорамирование, Ctrl+колесо — масштаб внутри этого окна.",
        },
        "en": {
            "progress_prepare_bundle": "Preparing report bundle...",
            "progress_prepare_pages": "Preparing report pages {idx}/{total}",
            "progress_generate_view": "Generating HTML view {idx}/{total}",
            "progress_pack_zip": "Packing report.zip...",
            "status_new_sheet": "new sheet",
            "status_changed_short": "Changed",
            "status_unchanged_short": "unchanged",
            "note_new_only": "Sheet exists only in the new document.",
            "note_removed_in_b": "Sheet is missing in the new document (removed vs A).",
            "note_no_significant": "No significant changes detected.",
            "note_visual_changes": "Visual content changes detected: diff={d:.3f}%.",
            "note_ecc_failed": "ECC alignment failed; comparison was performed without alignment.",
            "nav_sheet_word": "sheet",
            "conf_exact": "exact",
            "conf_probable": "probable",
            "conf_none": "none",
            "status_col_changed": "CHANGED",
            "status_col_unchanged": "UNCHANGED",
            "status_col_added": "ADDED",
            "status_col_removed": "REMOVED",
            "level_major": "MAJOR",
            "level_moderate": "MODERATE",
            "level_minor": "MINOR",
            "level_unchanged": "UNCHANGED",
            "pv_old": "OLD",
            "pv_new": "NEW",
            "pv_diff": "DIFF",
            "pv_new_pill": "ADDED",
            "pv_removed_pill": "REMOVED",
            "pv_preview_pill": "PREVIEW",
            "title_matrix": "PDF Compare Summary - Change Matrix",
            "subtitle_docs": "Doc A: {a} ({ac} sheets) → Doc B: {b} ({bc} sheets)",
            "chip_all": "All",
            "chip_changed": "Changed",
            "chip_added": "Added",
            "chip_removed": "Removed",
            "chip_major": "Major",
            "chip_moderate": "Moderate",
            "chip_minor": "Minor",
            "search_sheet": "Search sheet...",
            "th_seq_b": "Seq (B)",
            "th_a_page": "A page",
            "th_b_page": "B page",
            "th_status": "Status",
            "th_level": "Change level",
            "th_diff": "Diff %",
            "th_boxes": "Δ boxes",
            "th_preview": "Preview",
            "th_open": "Open",
            "empty_filter": "No pages match current filter.",
            "summary_title": "Summary",
            "summary_changed": "Changed:",
            "summary_added": "Added:",
            "summary_removed": "Removed:",
            "summary_unchanged": "Unchanged:",
            "legend_title": "Legend",
            "legend_major_desc": "significant change",
            "legend_moderate_desc": "visible change",
            "legend_minor_desc": "small change",
            "legend_added_desc": "new sheet in B",
            "legend_removed_desc": "removed / missing",
            "foot_open_row": "Click a row to open OLD / NEW / DIFF detailed view",
            "open_sheet_title": "Open sheet",
            "nav_title": "Sheet Navigation",
            "back_summary": "← Back to Summary",
            "summary_preview_title": "Summary preview",
            "search_hint": "Search (e.g., 5)",
            "old_document": "Old document",
            "new_document": "New document",
            "moved_label": "moved",
            "conf_label": "confidence",
            "diff_label": "diff",
            "open_old_win": "Open <span class=\"tag tag-old\">OLD</span> in Windows viewer",
            "open_new_win": "Open <span class=\"tag tag-new\">NEW</span> in Windows viewer",
            "open_diff_win": "Open <span class=\"tag tag-diff\">DIFF</span> in Windows viewer",
            "slider_mode": "↔ Compare mode (slider)",
            "cap_old": "OLD",
            "cap_new": "NEW",
            "cap_diff": "DIFF",
            "no_data": "n/a",
            "prev_page": "← previous",
            "next_page": "next →",
            "slider_title_page": "Slider compare page {b}",
            "slider_mode_title": "Compare mode (slider)",
            "slider_subtitle": "{a_name} page {a_idx} ↔ {b_name} page {b_idx}",
            "back_to_sheet": "Back to page",
            "fit_to_window": "Fit to window",
            "slider_old": "OLD",
            "slider_new": "NEW",
            "slider_zoom": "Zoom",
            "slider_help": "1:1 mode by default. Left-click on drawing to move split, right-drag to pan, Ctrl+wheel to zoom inside this view.",
        },
    }[lang]

    emit(2, t["progress_prepare_bundle"])
    bundle_dir = run_dir / "report_bundle"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    pages_root = run_dir / "pages"
    if not pages_root.exists():
        raise RuntimeError(f"Не найдена папка страниц: {pages_root}")
    thumbs_dir = bundle_dir / "assets" / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    with fitz.open(file_a) as da, fitz.open(file_b) as db:
        page_count_a = len(da)
        page_count_b = len(db)

    pages_records: List[dict] = []
    total_details = max(1, len(details))
    for row_idx, row in enumerate(details, start=1):
        seq = int(row["seq"])
        a_page = row.get("a_page")
        b_page = row.get("b_page")
        pair_name = row.get("pair_dir", f"{seq:03d}__A_{a_page or 'NA'}__B_{b_page or 'NA'}")
        pair_rel = Path("..") / "pages" / pair_name
        pair_abs = pages_root / pair_name

        old_img = pair_rel / "a.png"
        new_img = pair_rel / "b.png"
        diff_img = pair_rel / "overlay.png"
        bbox_img = pair_rel / "bbox_overlay.png"
        if not (pair_abs / "a.png").exists():
            old_img = pair_rel / "a_preview.png"
        if not (pair_abs / "b.png").exists():
            new_img = pair_rel / "b_preview.png"
        if not (pair_abs / "overlay.png").exists():
            diff_img = Path()
        if not (pair_abs / "bbox_overlay.png").exists():
            bbox_img = Path()

        thumb_old = Path("assets") / "thumbs" / f"{seq:03d}_old.jpg"
        thumb_new = Path("assets") / "thumbs" / f"{seq:03d}_new.jpg"
        thumb_diff = Path("assets") / "thumbs" / f"{seq:03d}_diff.jpg"
        old_src = pair_abs / old_img.name if old_img and old_img.name else None
        new_src = pair_abs / new_img.name if new_img and new_img.name else None
        diff_src = pair_abs / diff_img.name if diff_img and diff_img.name else None
        copy_thumb(old_src if old_src and old_src.is_file() else None, thumbs_dir / thumb_old.name)
        copy_thumb(new_src if new_src and new_src.is_file() else None, thumbs_dir / thumb_new.name)
        copy_thumb(diff_src if diff_src and diff_src.is_file() else None, thumbs_dir / thumb_diff.name)

        status, conf, content_status, moved = status_and_confidence(row)
        if row["status"] == "added":
            status_simple = "NEW"
            status_ru = t["status_new_sheet"]
            note = t["note_new_only"]
        elif row["status"] == "removed":
            status_simple = "CHANGED"
            status_ru = t["status_changed_short"]
            note = t["note_removed_in_b"]
        elif content_status == "UNCHANGED":
            status_simple = "UNCHANGED"
            status_ru = t["status_unchanged_short"]
            note = t["note_no_significant"]
        else:
            status_simple = "CHANGED"
            status_ru = t["status_changed_short"]
            d = row.get("diff_percent") or 0.0
            note = t["note_visual_changes"].format(d=d)
        if row.get("ecc_failed"):
            note = f"{note} {t['note_ecc_failed']}"

        a_label = "-" if a_page is None else str(a_page)
        b_label = "-" if b_page is None else str(b_page)
        nav_label = f"({file_a.name} {t['nav_sheet_word']} {a_label}) - ({file_b.name} {t['nav_sheet_word']} {b_label})"
        pages_records.append(
            {
                "seq": seq,
                "b_index": b_page,
                "a_index": a_page,
                "status_raw": status,
                "status": status_simple,
                "status_ru": status_ru,
                "content_status": content_status,
                "match_confidence": conf,
                "moved": moved,
                "diff_metric": row.get("diff_percent"),
                "bboxes_count": row.get("bboxes_count"),
                "score": row.get("score"),
                "notes": note,
                "nav_label": nav_label,
                "view_file": f"{seq:03d}.html",
                "assets": {
                    "thumb_old": str(thumb_old).replace("\\", "/") if (thumbs_dir / thumb_old.name).exists() else None,
                    "thumb_new": str(thumb_new).replace("\\", "/") if (thumbs_dir / thumb_new.name).exists() else None,
                    "thumb_diff": str(thumb_diff).replace("\\", "/") if (thumbs_dir / thumb_diff.name).exists() else None,
                    "hires_old": str(old_img).replace("\\", "/") if old_img and (pair_abs / old_img.name).exists() else None,
                    "hires_new": str(new_img).replace("\\", "/") if new_img and (pair_abs / new_img.name).exists() else None,
                    "hires_diff": str(diff_img).replace("\\", "/") if diff_img and (pair_abs / diff_img.name).exists() else None,
                    "hires_bbox": str(bbox_img).replace("\\", "/") if bbox_img and (pair_abs / bbox_img.name).exists() else None,
                },
            }
        )
        emit(6 + 58 * (row_idx / total_details), t["progress_prepare_pages"].format(idx=row_idx, total=total_details))

    pages_records.sort(key=lambda x: (x["b_index"] is None, x["b_index"] or 0, x["seq"]))
    for idx, p in enumerate(pages_records):
        p["prev_view_file"] = pages_records[idx - 1]["view_file"] if idx > 0 else None
        p["next_view_file"] = pages_records[idx + 1]["view_file"] if idx + 1 < len(pages_records) else None

    counts = {
        "unchanged": sum(1 for p in pages_records if p["status"] == "UNCHANGED"),
        "changed": sum(1 for p in pages_records if p["status"] == "CHANGED"),
        "new": sum(1 for p in pages_records if p["status"] == "NEW"),
        "removed": sum(1 for p in pages_records if p["status_raw"] == "REMOVED"),
        "moved": sum(1 for p in pages_records if p["moved"]),
    }

    report_model = {
        "documents": {
            "a": {
                "name": file_a.name,
                "path": str(file_a),
                "size_bytes": file_a.stat().st_size,
                "page_count": page_count_a,
            },
            "b": {
                "name": file_b.name,
                "path": str(file_b),
                "size_bytes": file_b.stat().st_size,
                "page_count": page_count_b,
            },
        },
        "settings": {
            "dpi_thumb": 120,
            "dpi_diff": high_dpi,
            "stroke_tolerance_px": stroke_tol_px,
            "threshold_unchanged_percent": 0.15,
            "align_mode": "ECC_AFFINE",
            "report_lang": lang,
        },
        "summary": {"counts": counts},
        "pages": pages_records,
    }
    (bundle_dir / "report.json").write_text(json.dumps(report_model, ensure_ascii=False, indent=2), encoding="utf-8")

    def badge_class(status: str) -> str:
        return {
            "UNCHANGED": "ok",
            "CHANGED": "warn",
            "NEW": "add",
        }.get(status, "warn")

    def heat_style(diff: float | None, level: str, max_diff: float) -> str:
        if diff is None:
            return "background:#f6f7fb;"
        if level == "MAJOR":
            alpha = 0.18 + 0.35 * min(1.0, diff / max(1.0, max_diff))
            return f"background:rgba(244,92,92,{alpha:.3f});"
        if level == "MODERATE":
            alpha = 0.16 + 0.30 * min(1.0, diff / max(1.0, max_diff))
            return f"background:rgba(241,170,52,{alpha:.3f});"
        if level == "MINOR":
            alpha = 0.14 + 0.26 * min(1.0, diff / max(1.0, max_diff))
            return f"background:rgba(233,214,111,{alpha:.3f});"
        return "background:#f1f4f9;"

    matrix_rows: list[str] = []
    matrix_rows_data: list[dict] = []
    status_ui = {
        "CHANGED": t["status_col_changed"],
        "UNCHANGED": t["status_col_unchanged"],
        "ADDED": t["status_col_added"],
        "REMOVED": t["status_col_removed"],
    }
    level_ui = {
        "MAJOR": t["level_major"],
        "MODERATE": t["level_moderate"],
        "MINOR": t["level_minor"],
        "UNCHANGED": t["level_unchanged"],
        "": "",
    }
    diff_values = [float(p["diff_metric"]) for p in pages_records if p.get("diff_metric") is not None]
    max_diff_value = max(diff_values) if diff_values else 1.0
    changed_cnt = 0
    added_cnt = 0
    removed_cnt = 0
    unchanged_cnt = 0

    for p in pages_records:
        status_raw = str(p.get("status_raw") or "")
        if status_raw == "ADDED":
            status_tag = "ADDED"
            level_tag = ""
            added_cnt += 1
        elif status_raw == "REMOVED":
            status_tag = "REMOVED"
            level_tag = ""
            removed_cnt += 1
        else:
            diff_val = None if p.get("diff_metric") is None else float(p["diff_metric"])
            if diff_val is None or diff_val < 0.15:
                level_tag = "UNCHANGED"
                status_tag = "UNCHANGED"
                unchanged_cnt += 1
            elif diff_val < 1.0:
                level_tag = "MINOR"
                status_tag = "CHANGED"
                changed_cnt += 1
            elif diff_val < 5.0:
                level_tag = "MODERATE"
                status_tag = "CHANGED"
                changed_cnt += 1
            else:
                level_tag = "MAJOR"
                status_tag = "CHANGED"
                changed_cnt += 1

        a_idx = "—" if p["a_index"] is None else f"A{p['a_index']}"
        b_idx = "—" if p["b_index"] is None else f"B{p['b_index']}"
        seq_b = "—" if p["b_index"] is None else str(p["b_index"])
        diff_val = None if p.get("diff_metric") is None else float(p["diff_metric"])
        diff_txt = "—" if diff_val is None else f"{diff_val:.3f}%"
        boxes_txt = "—" if p.get("bboxes_count") is None else str(int(p["bboxes_count"]))
        href = f"views/{p['view_file']}"

        thumb_old = p["assets"].get("thumb_old")
        thumb_new = p["assets"].get("thumb_new")
        thumb_diff = p["assets"].get("thumb_diff")
        if thumb_old or thumb_new or thumb_diff:
            preview_html = (
                "<div class='pv'>"
                f"<div><small>{html.escape(t['pv_old'])}</small>{f'<img loading=\"lazy\" src=\"{html.escape(thumb_old)}\" alt=\"old\"/>' if thumb_old else '<div class=\"ph\">—</div>'}</div>"
                f"<div><small>{html.escape(t['pv_new'])}</small>{f'<img loading=\"lazy\" src=\"{html.escape(thumb_new)}\" alt=\"new\"/>' if thumb_new else '<div class=\"ph\">—</div>'}</div>"
                f"<div><small>{html.escape(t['pv_diff'])}</small>{f'<img loading=\"lazy\" src=\"{html.escape(thumb_diff)}\" alt=\"diff\"/>' if thumb_diff else '<div class=\"ph\">—</div>'}</div>"
                "</div>"
            )
        elif status_tag == "ADDED":
            preview_html = f"<div class='pv-pill'>{html.escape(t['pv_new_pill'])}</div>"
        elif status_tag == "REMOVED":
            preview_html = f"<div class='pv-pill'>{html.escape(t['pv_removed_pill'])}</div>"
        else:
            preview_html = f"<div class='pv-pill'>{html.escape(t['pv_preview_pill'])}</div>"

        status_badge_cls = {
            "CHANGED": "st-changed",
            "UNCHANGED": "st-unchanged",
            "ADDED": "st-added",
            "REMOVED": "st-removed",
        }.get(status_tag, "st-changed")
        level_badge_cls = {
            "MAJOR": "lv-major",
            "MODERATE": "lv-moderate",
            "MINOR": "lv-minor",
            "UNCHANGED": "lv-unchanged",
            "": "lv-empty",
        }.get(level_tag, "lv-empty")

        matrix_rows_data.append(
            {
                "status": status_tag,
                "level": level_tag or "NONE",
                "search": f"{seq_b} {a_idx} {b_idx} {status_tag} {level_tag} {status_ui.get(status_tag, '')} {level_ui.get(level_tag, '')}".lower(),
            }
        )
        matrix_rows.append(
            f"<tr class='mx-row' data-status='{status_tag}' data-level='{level_tag or 'NONE'}' "
            f"data-search='{html.escape(matrix_rows_data[-1]['search'])}' data-href='{html.escape(href)}'>"
            f"<td>{html.escape(seq_b)}</td>"
            f"<td>{html.escape(a_idx)}</td>"
            f"<td>{html.escape(b_idx)}</td>"
            f"<td><span class='badge {status_badge_cls}'>{html.escape(status_ui.get(status_tag, status_tag))}</span></td>"
            f"<td>{f'<span class=\"badge {level_badge_cls}\">{html.escape(level_ui.get(level_tag, level_tag))}</span>' if level_tag else '—'}</td>"
            f"<td style='{heat_style(diff_val, level_tag, max_diff_value)}'>{html.escape(diff_txt)}</td>"
            f"<td>{html.escape(boxes_txt)}</td>"
            f"<td>{preview_html}</td>"
            f"<td><a class='open-link' href='{html.escape(href)}' title='{html.escape(t['open_sheet_title'])}'>&#8599;</a></td>"
            "</tr>"
        )

    summary_html = f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{html.escape(t["title_matrix"])}</title>
  <style>
    :root {{
      --bg:#f2f4f8; --panel:#ffffff; --ink:#1f2126; --muted:#5c6272; --line:#d6dbe5; --shadow:0 8px 24px rgba(0,0,0,.07);
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Segoe UI,Arial,sans-serif; color:var(--ink); background:radial-gradient(circle at 0 0,#f8f9fc, #edf0f5); }}
    .wrap {{ max-width:1320px; margin:0 auto; padding:26px; }}
    h1 {{ margin:0 0 4px 0; font-size:48px; font-weight:800; letter-spacing:.2px; }}
    .sub {{ color:#2f3440; font-size:23px; margin-bottom:18px; }}
    .topbar {{ display:flex; gap:12px; align-items:center; justify-content:space-between; flex-wrap:wrap; margin-bottom:14px; }}
    .chips {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
    .chip {{ border:1px solid #bcc4d4; border-radius:999px; padding:8px 14px; font-size:17px; background:#fff; color:#2a3040; cursor:pointer; }}
    .chip.active {{ background:#dcefff; border-color:#7cb1e6; color:#23588c; font-weight:700; }}
    .search {{ width:250px; max-width:100%; border:1px solid #c9cfdb; border-radius:12px; padding:10px 12px; font-size:17px; background:#fff; }}
    .layout {{ display:grid; grid-template-columns:1fr 220px; gap:22px; align-items:start; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:16px; box-shadow:var(--shadow); }}
    .matrix {{ padding:16px; overflow:auto; }}
    table {{ width:100%; border-collapse:separate; border-spacing:0; font-size:17px; min-width:980px; }}
    thead th {{ position:sticky; top:0; background:#fff; border-bottom:2px solid #d8dde8; z-index:2; }}
    th,td {{ padding:10px 12px; border-right:1px solid #e2e6ef; text-align:center; vertical-align:middle; }}
    th:last-child, td:last-child {{ border-right:none; }}
    tbody tr {{ border-bottom:1px solid #eceff5; cursor:pointer; }}
    tbody tr:nth-child(even) td {{ background:#f3f5f9; }}
    tbody tr:hover td {{ background:#edf3ff !important; }}
    .badge {{ display:inline-block; min-width:86px; border-radius:999px; padding:5px 10px; font-weight:700; font-size:15px; }}
    .st-changed {{ background:#f1a8a8; color:#612020; }}
    .st-unchanged {{ background:#b7d5f3; color:#173a5f; }}
    .st-added {{ background:#bc8ff0; color:#3b1a63; }}
    .st-removed {{ background:#d8d8d8; color:#343434; }}
    .lv-major {{ background:#f49999; color:#632020; }}
    .lv-moderate {{ background:#f2b558; color:#5c3a06; }}
    .lv-minor {{ background:#ece09b; color:#4f4516; }}
    .lv-unchanged {{ background:#dfe3eb; color:#3b4251; }}
    .open-link {{ font-size:24px; color:#2e3441; text-decoration:none; }}
    .pv {{ display:grid; grid-template-columns:repeat(3,1fr); gap:4px; }}
    .pv small {{ display:block; font-size:9px; color:#394154; font-weight:700; margin-bottom:1px; }}
    .pv img {{ width:100%; height:36px; object-fit:cover; border:1px solid #cfd5e2; border-radius:4px; background:#fff; }}
    .ph {{ height:36px; display:flex; align-items:center; justify-content:center; border:1px solid #cfd5e2; border-radius:4px; background:#f7f8fb; color:#8b91a0; font-size:12px; }}
    .pv-pill {{ border:1px solid #b9c1d1; border-radius:8px; padding:8px 10px; background:#f6f7fa; font-weight:700; font-size:15px; }}
    .aside {{ display:grid; gap:14px; }}
    .aside .box {{ background:#fff; border:1px solid var(--line); border-radius:14px; padding:14px 16px; box-shadow:var(--shadow); }}
    .aside h3 {{ margin:0 0 12px 0; font-size:34px; }}
    .kv {{ display:flex; justify-content:space-between; margin:5px 0; font-size:30px; }}
    .lg {{ display:flex; align-items:center; gap:8px; margin:7px 0; }}
    .legend-dot {{ width:86px; text-align:center; border-radius:999px; padding:4px 8px; font-weight:700; font-size:15px; }}
    .empty {{ text-align:center; color:#6a7386; padding:20px; }}
    .foot {{ margin-top:12px; color:#5f6778; font-size:14px; }}
    @media (max-width:1100px) {{
      .layout {{ grid-template-columns:1fr; }}
      .aside {{ grid-template-columns:1fr 1fr; }}
      h1 {{ font-size:34px; }}
      .sub {{ font-size:18px; }}
    }}
    @media (max-width:760px) {{
      .wrap {{ padding:14px; }}
      .aside {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{html.escape(t["title_matrix"])}</h1>
    <div class="sub">{html.escape(t["subtitle_docs"].format(a=file_a.stem, ac=page_count_a, b=file_b.stem, bc=page_count_b))}</div>
    <div class="topbar">
      <div class="chips">
        <button class="chip active" data-kind="all">{html.escape(t["chip_all"])}</button>
        <button class="chip" data-kind="status" data-value="CHANGED">{html.escape(t["chip_changed"])}</button>
        <button class="chip" data-kind="status" data-value="ADDED">{html.escape(t["chip_added"])}</button>
        <button class="chip" data-kind="status" data-value="REMOVED">{html.escape(t["chip_removed"])}</button>
        <button class="chip" data-kind="level" data-value="MAJOR">{html.escape(t["chip_major"])}</button>
        <button class="chip" data-kind="level" data-value="MODERATE">{html.escape(t["chip_moderate"])}</button>
        <button class="chip" data-kind="level" data-value="MINOR">{html.escape(t["chip_minor"])}</button>
      </div>
      <input id="sheetSearch" class="search" placeholder="{html.escape(t["search_sheet"])}"/>
    </div>

    <div class="layout">
      <div class="card matrix">
        <table>
          <thead>
            <tr>
              <th>{html.escape(t["th_seq_b"])}</th>
              <th>{html.escape(t["th_a_page"])}</th>
              <th>{html.escape(t["th_b_page"])}</th>
              <th>{html.escape(t["th_status"])}</th>
              <th>{html.escape(t["th_level"])}</th>
              <th>{html.escape(t["th_diff"])}</th>
              <th>{html.escape(t["th_boxes"])}</th>
              <th>{html.escape(t["th_preview"])}</th>
              <th>{html.escape(t["th_open"])}</th>
            </tr>
          </thead>
          <tbody id="mxBody">
            {''.join(matrix_rows)}
          </tbody>
        </table>
        <div id="emptyMsg" class="empty" style="display:none;">{html.escape(t["empty_filter"])}</div>
      </div>

      <div class="aside">
        <div class="box">
          <h3>{html.escape(t["summary_title"])}</h3>
          <div class="kv"><span>{html.escape(t["summary_changed"])}</span><b>{changed_cnt}</b></div>
          <div class="kv"><span>{html.escape(t["summary_added"])}</span><b>{added_cnt}</b></div>
          <div class="kv"><span>{html.escape(t["summary_removed"])}</span><b>{removed_cnt}</b></div>
          <div class="kv"><span>{html.escape(t["summary_unchanged"])}</span><b>{unchanged_cnt}</b></div>
        </div>
        <div class="box">
          <h3>{html.escape(t["legend_title"])}</h3>
          <div class="lg"><span class="legend-dot lv-major">{html.escape(t["chip_major"])}</span><span>{html.escape(t["legend_major_desc"])}</span></div>
          <div class="lg"><span class="legend-dot lv-moderate">{html.escape(t["chip_moderate"])}</span><span>{html.escape(t["legend_moderate_desc"])}</span></div>
          <div class="lg"><span class="legend-dot lv-minor">{html.escape(t["chip_minor"])}</span><span>{html.escape(t["legend_minor_desc"])}</span></div>
          <div class="lg"><span class="legend-dot st-added">{html.escape(t["status_col_added"])}</span><span>{html.escape(t["legend_added_desc"])}</span></div>
          <div class="lg"><span class="legend-dot st-removed">{html.escape(t["status_col_removed"])}</span><span>{html.escape(t["legend_removed_desc"])}</span></div>
        </div>
      </div>
    </div>

    <div class="foot">{html.escape(t["foot_open_row"])} | <a href="report.json">report.json</a></div>
  </div>

  <script>
    const chips = [...document.querySelectorAll('.chip')];
    const rows = [...document.querySelectorAll('#mxBody tr.mx-row')];
    const searchInput = document.getElementById('sheetSearch');
    const emptyMsg = document.getElementById('emptyMsg');
    let statusFilter = 'ALL';
    let levelFilter = 'ALL';

    function applyFilters() {{
      const q = searchInput.value.trim().toLowerCase();
      let visible = 0;
      rows.forEach(row => {{
        const st = row.dataset.status;
        const lv = row.dataset.level;
        const text = row.dataset.search || '';
        let ok = true;
        if (statusFilter === 'CHANGED') {{
          ok = st === 'CHANGED';
        }} else if (statusFilter === 'ADDED') {{
          ok = st === 'ADDED';
        }} else if (statusFilter === 'REMOVED') {{
          ok = st === 'REMOVED';
        }}
        if (ok && levelFilter !== 'ALL') {{
          ok = lv === levelFilter;
        }}
        if (ok && q) {{
          ok = text.includes(q);
        }}
        row.style.display = ok ? '' : 'none';
        if (ok) visible += 1;
      }});
      emptyMsg.style.display = visible ? 'none' : 'block';
    }}

    chips.forEach(chip => {{
      chip.addEventListener('click', () => {{
        const kind = chip.dataset.kind || 'all';
        const value = chip.dataset.value || '';
        if (kind === 'all') {{
          statusFilter = 'ALL';
          levelFilter = 'ALL';
          chips.forEach(c => c.classList.remove('active'));
          chip.classList.add('active');
        }} else if (kind === 'status') {{
          statusFilter = value;
          chips.forEach(c => {{
            if (c.dataset.kind === 'status') c.classList.remove('active');
          }});
          chip.classList.add('active');
          const allChip = chips.find(c => c.dataset.kind === 'all');
          if (allChip) allChip.classList.remove('active');
        }} else if (kind === 'level') {{
          if (levelFilter === value) {{
            levelFilter = 'ALL';
            chip.classList.remove('active');
          }} else {{
            levelFilter = value;
            chips.forEach(c => {{
              if (c.dataset.kind === 'level') c.classList.remove('active');
            }});
            chip.classList.add('active');
            const allChip = chips.find(c => c.dataset.kind === 'all');
            if (allChip) allChip.classList.remove('active');
          }}
        }}
        applyFilters();
      }});
    }});

    searchInput.addEventListener('input', applyFilters);
    rows.forEach(row => {{
      row.addEventListener('click', (e) => {{
        const target = e.target;
        if (target && target.closest('a')) return;
        const href = row.dataset.href;
        if (href) window.location.href = href;
      }});
    }});
    applyFilters();
  </script>
</body>
</html>
"""
    (bundle_dir / "index.html").write_text(summary_html, encoding="utf-8")

    views_dir = bundle_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)

    nav_items = []
    for p in pages_records:
        search_label = (p["nav_label"] + " " + p["status_ru"] + " " + str(p["b_index"] or "") + " " + str(p["a_index"] or "")).lower()
        nav_items.append(
            f"<a class='nav-item' data-label='{html.escape(search_label)}' "
            f"href='{html.escape(p['view_file'])}'><span>{html.escape(p['nav_label'])}</span><span class='s {badge_class(p['status'])}'>{html.escape(p['status_ru'])}</span></a>"
        )
    nav_html = "".join(nav_items)

    total_views = max(1, len(pages_records))
    for view_idx, p in enumerate(pages_records, start=1):
        a_idx = "-" if p["a_index"] is None else str(p["a_index"])
        b_idx = "-" if p["b_index"] is None else str(p["b_index"])
        diff_txt = "-" if p["diff_metric"] is None else f'{p["diff_metric"]:.3f}%'
        moved_text = ("yes" if p["moved"] else "no") if lang == "en" else ("да" if p["moved"] else "нет")
        conf_text = {"EXACT": t["conf_exact"], "PROBABLE": t["conf_probable"], "NONE": t["conf_none"]}.get(
            str(p["match_confidence"]),
            str(p["match_confidence"]).lower(),
        )
        old_src = f"../{p['assets']['hires_old']}" if p["assets"]["hires_old"] else None
        new_src = f"../{p['assets']['hires_new']}" if p["assets"]["hires_new"] else None
        diff_src = f"../{p['assets']['hires_diff']}" if p["assets"]["hires_diff"] else None
        bbox_src_file = f"../{p['assets']['hires_bbox']}" if p["assets"].get("hires_bbox") else None
        bbox_overlay_src = f"../{p['assets']['hires_bbox']}" if p["assets"].get("hires_bbox") else None
        prev_link = p["prev_view_file"]
        next_link = p["next_view_file"]
        slider_file = f"cmp_{p['view_file']}" if old_src and new_src else None
        pair_rel = None
        bboxes_data: list[dict] = []
        if p["assets"]["hires_old"]:
            pair_rel = Path(p["assets"]["hires_old"]).parent
        elif p["assets"]["hires_new"]:
            pair_rel = Path(p["assets"]["hires_new"]).parent
        if pair_rel is not None and (bundle_dir / pair_rel / "bboxes.json").exists():
            try:
                bboxes_data = json.loads((bundle_dir / pair_rel / "bboxes.json").read_text(encoding="utf-8"))
            except Exception:
                bboxes_data = []

        detail_html = f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{html.escape(t["nav_sheet_word"])} {html.escape(b_idx)} / {html.escape(a_idx)}</title>
  <style>
    :root {{ --bg:#f3f6fb; --panel:#fff; --ink:#1d2433; --muted:#5f6b84; --line:#d7deea; --ok:#1f8c4f; --warn:#cc3d17; --add:#0569d0; --yellow:#ffe06a; }}
    body {{ margin:0; font-family:Segoe UI,Arial,sans-serif; color:var(--ink); background:var(--bg); }}
    .app {{ display:grid; grid-template-columns:340px 1fr; min-height:100vh; }}
    .side {{ border-right:1px solid var(--line); background:#fff; padding:12px; position:sticky; top:0; height:100vh; overflow:auto; }}
    .main {{ padding:14px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:12px; }}
    .muted {{ color:var(--muted); font-size:12px; }}
    .summary-tools {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:8px 0 10px 0; }}
    .back-summary {{ display:flex; align-items:center; justify-content:center; padding:10px 12px; border-radius:8px; background:var(--yellow); color:#000; font-size:16px; font-weight:800; text-decoration:none; }}
    .summary-preview {{ border:1px solid #f2d46d; border-radius:8px; background:#fff8d8; padding:8px 10px; text-decoration:none; color:#463f1b; }}
    .summary-preview .sp-title {{ font-weight:700; font-size:13px; margin-bottom:4px; }}
    .summary-preview .sp-row {{ display:flex; justify-content:space-between; font-size:12px; line-height:1.35; }}
    .search {{ width:100%; border:1px solid var(--line); border-radius:8px; padding:8px; margin:8px 0 10px 0; box-sizing:border-box; }}
    .nav-list {{ display:grid; gap:6px; }}
    .nav-item {{ display:flex; justify-content:space-between; gap:8px; border:1px solid var(--line); border-radius:8px; padding:8px; text-decoration:none; color:inherit; font-size:12px; background:#fafcff; }}
    .nav-item.current {{ border-color:#0f4fa8; background:#eef5ff; }}
    .s {{ font-size:11px; border-radius:999px; padding:2px 8px; color:#fff; white-space:nowrap; align-self:center; }}
    .s.ok {{ background:var(--ok); }} .s.warn {{ background:var(--warn); }} .s.add {{ background:var(--add); }}
    .head {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:10px; }}
    .box {{ border:1px solid var(--line); border-radius:8px; padding:8px; background:#fbfdff; }}
    .doc-title {{ font-size:20px; font-weight:700; }}
    .doc-sub {{ color:#44516c; font-size:14px; font-weight:700; }}
    .cmp {{ display:grid; grid-template-columns:1fr 4fr; gap:12px; margin-top:10px; }}
    .left-stack {{ display:grid; grid-template-rows:1fr 1fr; gap:10px; min-height:70vh; }}
    figure {{ margin:0; border:1px solid var(--line); border-radius:8px; background:#fff; }}
    .left-stack figure img {{ width:100%; height:34vh; min-height:180px; object-fit:contain; background:#fff; }}
    .diff-figure img {{ width:100%; height:70vh; min-height:420px; object-fit:contain; background:#fff; }}
    figcaption {{ font-size:12px; color:var(--muted); text-align:center; padding:6px; border-top:1px solid var(--line); }}
    .noimg {{ height:32vh; min-height:180px; display:flex; align-items:center; justify-content:center; color:var(--muted); }}
    .noimg.diff {{ height:70vh; min-height:420px; }}
    .actions {{ margin-top:10px; display:flex; flex-wrap:wrap; gap:8px; }}
    .btn {{ border:1px solid var(--line); border-radius:8px; padding:6px 10px; text-decoration:none; color:#0f4fa8; background:#fff; font-size:13px; cursor:pointer; }}
    .btn-old {{ background:#fff8cc; border-color:#ecd573; color:#6d5a00; }}
    .btn-new {{ background:#ebf9ef; border-color:#9fdcb2; color:#1f6235; }}
    .btn-diff {{ background:#ffecec; border-color:#f0b7b7; color:#8a2a2a; }}
    .btn-compare {{ margin-left:24px; background:#fff1df; border-color:#ffc98f; color:#8f560c; font-weight:700; }}
    .tag {{ font-weight:800; padding:0 4px; border-radius:4px; }}
    .tag-old {{ background:#f7e793; color:#574700; }}
    .tag-new {{ background:#cfeeda; color:#15552d; }}
    .tag-diff {{ background:#f7cccc; color:#7a1f1f; }}
    .topnav {{ margin-top:8px; display:flex; gap:8px; }}
    @media (max-width:1000px) {{
      .app {{ grid-template-columns:1fr; }}
      .side {{ position:relative; height:auto; border-right:none; border-bottom:1px solid var(--line); }}
      .cmp {{ grid-template-columns:1fr; }}
      .left-stack {{ grid-template-rows:auto; }}
      .left-stack figure img,.diff-figure img,.noimg,.noimg.diff {{ height:44vh; min-height:220px; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="side">
      <h3 style="margin:0">{html.escape(t["nav_title"])}</h3>
      <div class="summary-tools">
        <a class="back-summary" href="../index.html">{html.escape(t["back_summary"])}</a>
        <a class="summary-preview" href="../index.html">
          <div class="sp-title">{html.escape(t["summary_preview_title"])}</div>
          <div class="sp-row"><span>{html.escape(t["summary_unchanged"])}</span><b>{counts['unchanged']}</b></div>
          <div class="sp-row"><span>{html.escape(t["summary_changed"])}</span><b>{counts['changed']}</b></div>
          <div class="sp-row"><span>{html.escape(t["summary_added"])}</span><b>{counts['new']}</b></div>
        </a>
      </div>
      <input id="search" class="search" placeholder="{html.escape(t["search_hint"])}"/>
      <div id="navList" class="nav-list">{nav_html}</div>
    </aside>
    <main class="main">
      <div class="panel">
        <div class="head">
          <div class="box"><div class="doc-title">{html.escape(t["old_document"])}</div><div class="doc-sub">{html.escape(file_a.name)} | {html.escape(t["nav_sheet_word"])} {html.escape(a_idx)}</div></div>
          <div class="box"><div class="doc-title">{html.escape(t["new_document"])}</div><div class="doc-sub">{html.escape(file_b.name)} | {html.escape(t["nav_sheet_word"])} {html.escape(b_idx)}</div></div>
        </div>
        <h2 style="margin:0 0 6px 0">{html.escape(p['status_ru'])} <span class="muted">| {html.escape(t["moved_label"])}: {moved_text} | {html.escape(t["conf_label"])}: {html.escape(conf_text)}</span></h2>
        <div class="muted">{html.escape(t["diff_label"])}: {html.escape(diff_txt)} | {html.escape(p['notes'])}</div>
        <div class="actions">
          {f'<button type="button" class="btn open-ext btn-old" data-src="{html.escape(old_src)}">{t["open_old_win"]}</button>' if old_src else ''}
          {f'<button type="button" class="btn open-ext btn-new" data-src="{html.escape(new_src)}">{t["open_new_win"]}</button>' if new_src else ''}
          {f'<button type="button" class="btn open-ext btn-diff" data-src="{html.escape(diff_src)}">{t["open_diff_win"]}</button>' if diff_src else ''}
          {f'<a class="btn btn-compare" href="{html.escape(slider_file)}">{html.escape(t["slider_mode"])}</a>' if slider_file else ''}
        </div>
        <div class="cmp">
          <div class="left-stack">
            <figure>{f'<img loading="lazy" src="{html.escape(old_src)}" alt="old sheet"/>' if old_src else f'<div class="noimg">{html.escape(t["no_data"])}</div>'}<figcaption>{html.escape(t["cap_old"])}</figcaption></figure>
            <figure>{f'<img loading="lazy" src="{html.escape(new_src)}" alt="new sheet"/>' if new_src else f'<div class="noimg">{html.escape(t["no_data"])}</div>'}<figcaption>{html.escape(t["cap_new"])}</figcaption></figure>
          </div>
          <figure class="diff-figure">{f'<img loading="lazy" src="{html.escape(diff_src)}" alt="diff"/>' if diff_src else f'<div class="noimg diff">{html.escape(t["no_data"])}</div>'}<figcaption>{html.escape(t["cap_diff"])}</figcaption></figure>
        </div>
        <div class="topnav">
          {f'<a class="btn" href="{html.escape(prev_link)}">{html.escape(t["prev_page"])}</a>' if prev_link else ''}
          {f'<a class="btn" href="{html.escape(next_link)}">{html.escape(t["next_page"])}</a>' if next_link else ''}
        </div>
      </div>
    </main>
  </div>
  <script>
    const current = "{html.escape(p['view_file'])}";
    document.querySelectorAll('.nav-item').forEach(a => {{
      const href = a.getAttribute('href');
      if (href === current) a.classList.add('current');
    }});
    const inp = document.getElementById('search');
    const items = [...document.querySelectorAll('.nav-item')];
    inp.addEventListener('input', () => {{
      const q = inp.value.trim().toLowerCase();
      items.forEach(it => {{
        it.style.display = !q || it.dataset.label.includes(q) ? '' : 'none';
      }});
    }});
    function toWinPath(rel) {{
      try {{
        const u = new URL(rel, window.location.href);
        if (u.protocol !== 'file:') return null;
        let p = decodeURIComponent(u.pathname);
        if (/^\\/[A-Za-z]:/.test(p)) p = p.slice(1);
        return p.replace(/\\//g, '\\\\');
      }} catch (e) {{
        return null;
      }}
    }}
    document.querySelectorAll('.open-ext').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const rel = btn.dataset.src;
        const wp = toWinPath(rel);
        if (!wp) {{
          window.open(rel, '_blank');
          return;
        }}
        const uri = 'ms-photos:viewer?fileName=' + encodeURIComponent(wp);
        window.location.href = uri;
      }});
    }});
  </script>
</body>
</html>
"""
        (views_dir / p["view_file"]).write_text(detail_html, encoding="utf-8")

        if slider_file and old_src and new_src:
            slider_html = f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{html.escape(t["slider_title_page"].format(b=b_idx))}</title>
  <style>
    html, body {{ width:100%; height:100%; }}
    body {{ margin:0; font-family:Segoe UI,Arial,sans-serif; background:#f3f6fb; color:#1d2433; overflow:hidden; }}
    .wrap {{ width:100vw; height:100vh; margin:0; padding:0; }}
    .panel {{ width:100%; height:100%; background:#fff; border:0; border-radius:0; padding:10px; box-sizing:border-box; display:flex; flex-direction:column; }}
    .top {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:space-between; margin-bottom:10px; }}
    .btn {{ border:1px solid #d7deea; border-radius:8px; padding:6px 10px; text-decoration:none; color:#0f4fa8; background:#fff; }}
    .stage {{ flex:1; width:100%; border:1px solid #d7deea; border-radius:10px; background:#fff; padding:8px; box-sizing:border-box; overflow:auto; min-height:0; }}
    .stage.dragging {{ cursor:ew-resize; }}
    .stage.panning {{ cursor:grabbing; }}
    canvas {{ display:block; cursor:ew-resize; }}
    .stage.panning canvas {{ cursor:grabbing; }}
    .slider-wrap {{ margin:10px 0 0 0; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
    input[type=range] {{ width:100%; }}
    .muted {{ color:#5f6b84; font-size:12px; }}
    .small {{ width:150px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <div class="top">
        <div><b>{html.escape(t["slider_mode_title"])}</b><div class="muted">{html.escape(t["slider_subtitle"].format(a_name=file_a.name, a_idx=a_idx, b_name=file_b.name, b_idx=b_idx))}</div></div>
        <div>
          <a class="btn" href="{html.escape(p['view_file'])}">{html.escape(t["back_to_sheet"])}</a>
          <a class="btn" href="../index.html">{html.escape(t["back_summary"])}</a>
          <button class="btn" id="fitBtn" type="button">{html.escape(t["fit_to_window"])}</button>
        </div>
      </div>
      <div class="stage" id="stage" tabindex="0"><canvas id="cmpCanvas"></canvas></div>
      <div class="slider-wrap">
        <span>{html.escape(t["slider_old"])}</span><input id="split" type="range" min="0" max="100" step="0.1" value="50"/><span>{html.escape(t["slider_new"])}</span>
        <span>{html.escape(t["slider_zoom"])}</span><input id="zoom" class="small" type="range" min="1" max="300" value="100"/><span id="zoomVal">100%</span>
      </div>
      <div class="muted">{html.escape(t["slider_help"])}</div>
    </div>
  </div>
  <script>
    const oldSrc = {json.dumps(old_src)};
    const newSrc = {json.dumps(new_src)};
    const bboxOverlaySrc = {json.dumps(bbox_overlay_src)};
    const bboxData = {json.dumps(bboxes_data, ensure_ascii=False)};
    const slider = document.getElementById('split');
    const zoom = document.getElementById('zoom');
    const zoomVal = document.getElementById('zoomVal');
    const fitBtn = document.getElementById('fitBtn');
    const stage = document.getElementById('stage');
    const canvas = document.getElementById('cmpCanvas');
    const ctx = canvas.getContext('2d');
    const oldImg = new Image();
    const newImg = new Image();
    const bboxImg = new Image();
    let bboxImgLoaded = false;
    let loaded = 0;
    function ready() {{ loaded += 1; if (loaded >= 2) draw(); }}
    oldImg.onload = ready;
    newImg.onload = ready;
    oldImg.src = oldSrc;
    newImg.src = newSrc;
    if (bboxOverlaySrc) {{
      bboxImg.onload = () => {{ bboxImgLoaded = true; draw(); }};
      bboxImg.src = bboxOverlaySrc;
    }}
    function setZoomPercent(v) {{
      const clamped = Math.max(1, Math.min(300, Math.round(v)));
      zoom.value = String(clamped);
      applyZoom();
    }}
    function applyZoom() {{
      const z = Number(zoom.value) / 100;
      zoomVal.textContent = Math.round(z * 100) + '%';
      if (canvas.width > 0) {{
        canvas.style.width = Math.max(1, Math.round(canvas.width * z)) + 'px';
        canvas.style.height = Math.max(1, Math.round(canvas.height * z)) + 'px';
      }}
    }}
    function fitToWindow() {{
      if (!canvas.width || !canvas.height) return;
      const pad = 16;
      const sx = Math.max(0.01, (stage.clientWidth - pad) / canvas.width);
      const sy = Math.max(0.01, (stage.clientHeight - pad) / canvas.height);
      const s = Math.max(0.01, Math.min(sx, sy));
      setZoomPercent(s * 100);
    }}
    function setSplitFromClientX(clientX) {{
      const rect = canvas.getBoundingClientRect();
      if (!rect.width) return;
      const x = Math.max(0, Math.min(rect.width, clientX - rect.left));
      const pct = (x / rect.width) * 100;
      slider.value = String(pct);
      draw();
    }}
    function draw() {{
      if (!oldImg.naturalWidth || !newImg.naturalWidth) return;
      const w0 = oldImg.naturalWidth;
      const h0 = oldImg.naturalHeight;
      const w = Math.max(1, w0);
      const h = Math.max(1, h0);
      canvas.width = w;
      canvas.height = h;
      const splitX = Math.round((Number(slider.value) / 100) * w);
      ctx.clearRect(0, 0, w, h);
      ctx.drawImage(newImg, 0, 0, w, h);
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, splitX, h);
      ctx.clip();
      ctx.drawImage(oldImg, 0, 0, w, h);
      ctx.restore();
      if (bboxImgLoaded) {{
        ctx.drawImage(bboxImg, 0, 0, w, h);
      }} else if (bboxData.length) {{
        ctx.fillStyle = 'rgba(255,235,120,0.22)';
        ctx.strokeStyle = 'rgba(255,180,0,0.55)';
        ctx.lineWidth = 1.2;
        bboxData.forEach(b => {{
          const x = Math.round((b.x || 0));
          const y = Math.round((b.y || 0));
          const bw = Math.round((b.w || 0));
          const bh = Math.round((b.h || 0));
          if (bw > 1 && bh > 1) {{
            ctx.fillRect(x, y, bw, bh);
            ctx.strokeRect(x, y, bw, bh);
          }}
        }});
      }}
      ctx.strokeStyle = 'rgba(20,120,255,0.95)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(splitX, 0);
      ctx.lineTo(splitX, h);
      ctx.stroke();
      applyZoom();
    }}
    let draggingSplit = false;
    let panning = false;
    let panStartX = 0;
    let panStartY = 0;
    let panStartScrollLeft = 0;
    let panStartScrollTop = 0;
    canvas.addEventListener('mousedown', (e) => {{
      if (e.button === 2) {{
        panning = true;
        stage.classList.add('panning');
        panStartX = e.clientX;
        panStartY = e.clientY;
        panStartScrollLeft = stage.scrollLeft;
        panStartScrollTop = stage.scrollTop;
        e.preventDefault();
        return;
      }}
      if (e.button !== 0) return;
      draggingSplit = true;
      stage.classList.add('dragging');
      setSplitFromClientX(e.clientX);
    }});
    window.addEventListener('mousemove', (e) => {{
      if (panning) {{
        stage.scrollLeft = panStartScrollLeft - (e.clientX - panStartX);
        stage.scrollTop = panStartScrollTop - (e.clientY - panStartY);
        return;
      }}
      if (!draggingSplit) return;
      setSplitFromClientX(e.clientX);
    }});
    window.addEventListener('mouseup', () => {{
      if (draggingSplit) {{
        draggingSplit = false;
        stage.classList.remove('dragging');
      }}
      if (panning) {{
        panning = false;
        stage.classList.remove('panning');
      }}
    }});
    stage.addEventListener('contextmenu', (e) => {{
      e.preventDefault();
    }});
    canvas.addEventListener('touchstart', (e) => {{
      if (!e.touches || !e.touches.length) return;
      draggingSplit = true;
      stage.classList.add('dragging');
      setSplitFromClientX(e.touches[0].clientX);
      e.preventDefault();
    }}, {{ passive: false }});
    window.addEventListener('touchmove', (e) => {{
      if (!draggingSplit || !e.touches || !e.touches.length) return;
      setSplitFromClientX(e.touches[0].clientX);
      e.preventDefault();
    }}, {{ passive: false }});
    window.addEventListener('touchend', () => {{
      draggingSplit = false;
      stage.classList.remove('dragging');
    }});
    stage.addEventListener('wheel', (e) => {{
      if (!e.ctrlKey) return;
      e.preventDefault();
      const delta = e.deltaY < 0 ? 6 : -6;
      setZoomPercent(Number(zoom.value) + delta);
    }}, {{ passive: false }});
    slider.addEventListener('input', draw);
    zoom.addEventListener('input', () => setZoomPercent(Number(zoom.value)));
    fitBtn.addEventListener('click', fitToWindow);
    window.addEventListener('resize', draw);
  </script>
</body>
</html>"""
            (views_dir / slider_file).write_text(slider_html, encoding="utf-8")
        emit(66 + 32 * (view_idx / total_views), t["progress_generate_view"].format(idx=view_idx, total=total_views))

    zip_base = run_dir.parent / f"{run_dir.name}_report"
    zip_path = build_compact_report_zip(run_dir, zip_base)
    emit(100, t["progress_pack_zip"])
    return zip_path


def compare_pdfs(
    file_a: Path,
    file_b: Path,
    out_dir: Path,
    high_dpi: int = 250,
    stroke_tol_px: float = 2.0,
    report_lang: str = "ru",
    progress_cb: Callable[[float, str], None] | None = None,
) -> Path:
    def emit(pct: float, msg: str) -> None:
        if progress_cb is not None:
            progress_cb(float(max(0.0, min(100.0, pct))), msg)

    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid4().hex[:6]}"
    run_dir = out_dir / f"run_{run_id}"
    pages_dir = run_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

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

    details: List[dict] = []

    total_pairs = max(1, len(pairs))
    with fitz.open(file_a) as doc_a, fitz.open(file_b) as doc_b:
        for idx, p in enumerate(pairs, start=1):
            a_page = None if p.a_idx is None else p.a_idx + 1
            b_page = None if p.b_idx is None else p.b_idx + 1
            pair_name = f"{idx:03d}__A_{a_page or 'NA'}__B_{b_page or 'NA'}"
            pair_dir = pages_dir / pair_name
            pair_dir.mkdir(parents=True, exist_ok=True)

            entry = {
                "seq": idx,
                "a_page": a_page,
                "b_page": b_page,
                "pair_dir": pair_name,
                "status": p.status,
                "score": float(p.score),
                "diff_percent": None,
                "change_level": None,
                "bboxes_count": None,
                "ecc_failed": False,
            }

            if p.status == "matched" and p.a_idx is not None and p.b_idx is not None:
                a_img = render_page(doc_a, p.a_idx, high_dpi)
                b_img = render_page(doc_b, p.b_idx, high_dpi)
                harmonized = harmonize_canvas(a_img, b_img)
                if harmonized is None:
                    entry["status"] = "size_mismatch"
                    entry["change_level"] = "size_mismatch"
                    imwrite_compat(pair_dir / "a.png", a_img)
                    imwrite_compat(pair_dir / "b.png", b_img)
                    details.append(entry)
                    continue

                a_h, b_h = harmonized
                b_aligned, ecc_ok = align_ecc(a_h, b_h)
                entry["ecc_failed"] = not ecc_ok
                mask, overlay, bboxes, diff_percent = compute_diff(a_h, b_aligned, stroke_tol_px=stroke_tol_px)
                level = classify(diff_percent)

                imwrite_compat(pair_dir / "a.png", a_h)
                # Keep report visuals consistent: b.png must be the aligned image used for diff.
                imwrite_compat(pair_dir / "b.png", b_aligned)
                imwrite_compat(pair_dir / "b_raw.png", b_h)
                imwrite_compat(pair_dir / "b_aligned.png", b_aligned)
                imwrite_compat(pair_dir / "mask.png", mask)
                imwrite_compat(pair_dir / "overlay.png", overlay)
                # Separate bbox layer for slider mode (transparent PNG).
                bbox_layer = np.zeros((a_h.shape[0], a_h.shape[1], 4), dtype=np.uint8)
                for x, y, w, h in bboxes:
                    cv2.rectangle(bbox_layer, (x, y), (x + w, y + h), (120, 235, 255, 70), -1)
                    cv2.rectangle(bbox_layer, (x, y), (x + w, y + h), (0, 180, 255, 135), 1)
                imwrite_compat(pair_dir / "bbox_overlay.png", bbox_layer)
                (pair_dir / "bboxes.json").write_text(
                    json.dumps([{"x": x, "y": y, "w": w, "h": h} for x, y, w, h in bboxes], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                entry["diff_percent"] = float(diff_percent)
                entry["change_level"] = level
                entry["bboxes_count"] = len(bboxes)
                del a_img, b_img, harmonized, a_h, b_h, b_aligned, mask, overlay, bbox_layer
            else:
                # Keep quick preview for unmatched pages.
                if p.a_idx is not None:
                    a_full = render_page(doc_a, p.a_idx, high_dpi)
                    a_prev = render_page(doc_a, p.a_idx, 120)
                    imwrite_compat(pair_dir / "a.png", a_full)
                    imwrite_compat(pair_dir / "a_preview.png", a_prev)
                    del a_full, a_prev
                if p.b_idx is not None:
                    b_full = render_page(doc_b, p.b_idx, high_dpi)
                    b_prev = render_page(doc_b, p.b_idx, 120)
                    imwrite_compat(pair_dir / "b.png", b_full)
                    imwrite_compat(pair_dir / "b_preview.png", b_prev)
                    del b_full, b_prev

            details.append(entry)
            if idx % 8 == 0:
                gc.collect()
            emit(38 + 48 * (idx / total_pairs), f"Сравнение листов {idx}/{total_pairs}")

    emit(87, "Подготовка сводки и CSV")
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "file_a": str(file_a),
                "file_b": str(file_b),
                "created_at": datetime.now().isoformat(),
                "pairs": details,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with (run_dir / "page_map.csv").open("w", newline="", encoding="utf-8") as f:
        csv_fields = ["seq", "a_page", "b_page", "status", "score", "diff_percent", "change_level", "bboxes_count", "ecc_failed"]
        w = csv.DictWriter(
            f,
            fieldnames=csv_fields,
        )
        w.writeheader()
        for row in details:
            w.writerow({k: row.get(k) for k in csv_fields})

    write_summary_md(run_dir / "summary.md", file_a, file_b, pairs, details, lang=report_lang)
    write_engineer_report_md(run_dir / "engineer_report.md", file_a, file_b, details, lang=report_lang)
    emit(90, "Генерация HTML отчета")
    zip_path = generate_html_report(
        run_dir,
        file_a,
        file_b,
        details,
        high_dpi=high_dpi,
        stroke_tol_px=stroke_tol_px,
        report_lang=report_lang,
        progress_cb=lambda p, msg: emit(90 + 9 * (p / 100.0), msg),
    )
    (run_dir / "report_zip.txt").write_text(str(zip_path), encoding="utf-8")
    emit(100, "Готово")
    return run_dir


def pick_two_pdfs(folder: Path) -> Tuple[Path, Path]:
    pdfs = sorted(folder.glob("*.pdf"))
    if len(pdfs) != 2:
        raise RuntimeError(f"Ожидалось ровно 2 PDF-файла в {folder}, найдено {len(pdfs)}")
    return pdfs[0], pdfs[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two multi-page PDFs and build visual report.")
    parser.add_argument("--old", type=Path, help="Path to file A (old/base)")
    parser.add_argument("--new", type=Path, help="Path to file B (new/target)")
    parser.add_argument("--input-dir", type=Path, default=Path("TestDocs"), help="Folder with two PDFs (used if --old/--new omitted)")
    parser.add_argument("--out-dir", type=Path, default=Path("runs"), help="Output runs folder")
    parser.add_argument("--dpi", type=int, default=250, help="High DPI for final page diff rendering")
    parser.add_argument("--stroke-tol", type=float, default=2.0, help="Tolerance in pixels for line-thickness jitter")
    parser.add_argument("--lang", type=str, default="ru", choices=["ru", "en"], help="Report language")
    args = parser.parse_args()

    if args.old and args.new:
        file_a = args.old
        file_b = args.new
    else:
        file_a, file_b = pick_two_pdfs(args.input_dir)

    run_dir = compare_pdfs(
        file_a,
        file_b,
        args.out_dir,
        high_dpi=args.dpi,
        stroke_tol_px=args.stroke_tol,
        report_lang=args.lang,
    )
    print(f"Готово. Результаты: {run_dir}")
    print(f"Сводка: {run_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
