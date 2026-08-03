"""Page-to-page alignment and image registration."""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from .models import MatchPair, PageInfo


def visual_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return 0.0
    # Robust to brightness shifts: compare normalized images.
    a_n = a if a.dtype == np.float32 else cv2.normalize(a, np.empty_like(a), 0, 255, cv2.NORM_MINMAX).astype(np.float32)
    b_n = b if b.dtype == np.float32 else cv2.normalize(b, np.empty_like(b), 0, 255, cv2.NORM_MINMAX).astype(np.float32)
    mse = float(np.mean((a_n - b_n) ** 2))
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


def content_compatible_across_sizes(a: PageInfo, b: PageInfo) -> bool:
    """Allow a revision to move to another paper size when its identity is clear.

    Paper size is normally a useful hard gate, but drawings are sometimes
    republished on a larger sheet without changing the drawing itself.  Keep
    this exception deliberately narrow: the aspect ratio must stay the same,
    both the rendered content and a substantial body of extracted text must
    agree, and conflicting sheet marks still reject the pair.
    """
    if min(a.width_pt, a.height_pt, b.width_pt, b.height_pt) <= 0:
        return False
    aspect_a = a.width_pt / a.height_pt
    aspect_b = b.width_pt / b.height_pt
    aspect_delta = abs(aspect_a - aspect_b) / max(aspect_a, aspect_b)
    if aspect_delta > 0.015:
        return False
    if a.sheet_mark and b.sheet_mark and sheet_mark_similarity(a.sheet_mark, b.sheet_mark) == 0.0:
        return False
    shared_tokens = len(a.text_tokens & b.text_tokens)
    if shared_tokens < 20:
        return False
    return text_similarity(a.text_tokens, b.text_tokens) >= 0.85 and visual_similarity(a.thumb, b.thumb) >= 0.90


def pages_compatible(a: PageInfo, b: PageInfo) -> bool:
    return size_compatible(a, b) or content_compatible_across_sizes(a, b)


def pair_similarity(a: PageInfo, b: PageInfo) -> float:
    if not pages_compatible(a, b):
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


def build_similarity_matrices(
    pages_a: Sequence[PageInfo], pages_b: Sequence[PageInfo]
) -> tuple[np.ndarray, np.ndarray]:
    """Precompute compatibility and similarity once for all mapping strategies."""
    n, m = len(pages_a), len(pages_b)
    sims = np.zeros((n, m), dtype=np.float64)
    compatible = np.zeros((n, m), dtype=bool)
    for i in range(n):
        for j in range(m):
            ok = pages_compatible(pages_a[i], pages_b[j])
            compatible[i, j] = ok
            if ok:
                sims[i, j] = pair_similarity(pages_a[i], pages_b[j])
    return sims, compatible


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


def align_pages_hungarian(
    pages_a: Sequence[PageInfo],
    pages_b: Sequence[PageInfo],
    sims: np.ndarray | None = None,
    compatible: np.ndarray | None = None,
) -> list[MatchPair]:
    n, m = len(pages_a), len(pages_b)
    if sims is None or compatible is None:
        sims, compatible = build_similarity_matrices(pages_a, pages_b)
    k = max(n, m)
    unmatched_cost = 0.35
    incompatible_cost = 1.20
    match_threshold = 0.55
    cost = np.full((k, k), unmatched_cost, dtype=np.float64)
    for i in range(n):
        for j in range(m):
            if compatible[i, j]:
                sim = float(sims[i, j])
                cost[i, j] = 1.0 - sim
            else:
                cost[i, j] = incompatible_cost
    if k > n and k > m:
        cost[n:, m:] = 0.0
    rows, cols = linear_sum_assignment(cost)
    matched_by_a: dict[int, tuple[int, float]] = {}
    removed: set[int] = set()
    added: set[int] = set()
    for i, j in zip(rows, cols, strict=True):
        if i < n and j < m:
            sim = float(sims[i, j])
            if sim >= match_threshold and bool(compatible[i, j]):
                matched_by_a[int(i)] = (int(j), sim)
            else:
                removed.add(int(i))
                added.add(int(j))
        elif i < n and j >= m:
            removed.add(int(i))
        elif i >= n and j < m:
            added.add(int(j))
    out: list[MatchPair] = []
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


def align_pages_monotonic(
    pages_a: Sequence[PageInfo],
    pages_b: Sequence[PageInfo],
    sims: np.ndarray | None = None,
    compatible: np.ndarray | None = None,
) -> list[MatchPair]:
    """Sequence-preserving page mapping. Guarantees non-crossing links."""
    n, m = len(pages_a), len(pages_b)
    gap_cost = 0.43
    mismatch_penalty = 0.45
    match_threshold = 0.58

    if sims is None or compatible is None:
        sims, compatible = build_similarity_matrices(pages_a, pages_b)

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

    out: list[MatchPair] = []
    for op, a_idx, b_idx, sim in reversed(rev_ops):
        if op == "M":
            out.append(MatchPair(a_idx, b_idx, "matched", sim))
        elif op == "R":
            out.append(MatchPair(a_idx, None, "removed", 0.0))
        else:
            out.append(MatchPair(None, b_idx, "added", 0.0))
    return out


def count_inversions(seq: Sequence[int]) -> int:
    """O(n log n) inversion count via merge sort."""
    arr = [int(x) for x in seq]
    n = len(arr)
    if n < 2:
        return 0
    tmp = [0] * n

    def sort_count(lo: int, hi: int) -> int:
        if hi - lo <= 1:
            return 0
        mid = (lo + hi) // 2
        inv = sort_count(lo, mid) + sort_count(mid, hi)
        i, j, k = lo, mid, lo
        while i < mid and j < hi:
            if arr[i] <= arr[j]:
                tmp[k] = arr[i]
                i += 1
            else:
                tmp[k] = arr[j]
                j += 1
                inv += mid - i
            k += 1
        while i < mid:
            tmp[k] = arr[i]
            i += 1
            k += 1
        while j < hi:
            tmp[k] = arr[j]
            j += 1
            k += 1
        arr[lo:hi] = tmp[lo:hi]
        return inv

    return sort_count(0, n)


def alignment_quality(pairs: Sequence[MatchPair], n_a: int, n_b: int) -> float:
    matched = [p for p in pairs if p.status == "matched" and p.a_idx is not None and p.b_idx is not None]
    if matched:
        sim_avg = float(sum(float(p.score) for p in matched) / len(matched))
    else:
        sim_avg = 0.0
    gap_count = sum(1 for p in pairs if p.status in {"added", "removed"})
    gap_ratio = gap_count / max(1, n_a + n_b)
    b_seq = [p.b_idx for p in matched if p.b_idx is not None]
    inv = count_inversions(b_seq)
    total = (len(b_seq) * (len(b_seq) - 1)) // 2
    cross_ratio = (inv / total) if total else 0.0
    return sim_avg - 0.38 * gap_ratio - 0.10 * cross_ratio


def align_pages_v1(pages_a: Sequence[PageInfo], pages_b: Sequence[PageInfo]) -> list[MatchPair]:
    sims, compatible = build_similarity_matrices(pages_a, pages_b)
    global_map = align_pages_hungarian(pages_a, pages_b, sims=sims, compatible=compatible)
    mono_map = align_pages_monotonic(pages_a, pages_b, sims=sims, compatible=compatible)
    q_global = alignment_quality(global_map, len(pages_a), len(pages_b))
    q_mono = alignment_quality(mono_map, len(pages_a), len(pages_b))
    # Use monotonic only when its quality is close enough or better.
    if q_mono >= q_global - 0.04:
        return mono_map
    return global_map


def align_ecc(base_bgr: np.ndarray, moving_bgr: np.ndarray) -> tuple[np.ndarray, bool]:
    """ECC sub-pixel image registration before pixel-level diff."""
    base_gray = cv2.cvtColor(base_bgr, cv2.COLOR_BGR2GRAY)
    moving_gray = cv2.cvtColor(moving_bgr, cv2.COLOR_BGR2GRAY)
    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-6)
    try:
        # OpenCV's default inputMask=None and gaussFiltSize=5 matches the previous explicit call.
        cv2.findTransformECC(base_gray, moving_gray, warp, cv2.MOTION_AFFINE, criteria)
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
