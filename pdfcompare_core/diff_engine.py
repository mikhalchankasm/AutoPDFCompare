"""Pixel-level diff detection between rendered PDF pages."""

from __future__ import annotations

import cv2
import numpy as np

from .constants import FOREGROUND_SPARSE_THRESHOLD
from .errors import InvalidInput
from .exclusions import ExcludeRegion, exclusion_regions_to_pixel_boxes


DIFF_STRICTNESS_CHOICES = ("strict", "normal", "loose")
STRICTNESS_PROFILES = {
    "strict": {"tol_multiplier": 0.65, "min_area": 80},
    "normal": {"tol_multiplier": 1.0, "min_area": 180},
    "loose": {"tol_multiplier": 1.6, "min_area": 360},
}

type BBox = tuple[int, int, int, int]


def _empty_metrics() -> dict[str, float | int | bool]:
    return {
        "changed_px": 0,
        "added_px": 0,
        "removed_px": 0,
        "foreground_px": 0,
        "diff_percent": 0.0,
        "diff_foreground_percent": 0.0,
        "diff_area_mm2": 0.0,
        "added_area_mm2": 0.0,
        "removed_area_mm2": 0.0,
        "max_region_changed_px": 0,
        "max_region_area_mm2": 0.0,
        "foreground_sparse": False,
    }


def harmonize_canvas(
    a_bgr: np.ndarray,
    b_bgr: np.ndarray,
    max_delta: int = 3,
) -> tuple[np.ndarray, np.ndarray] | None:
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


def _bboxes_overlap(left: BBox, right: BBox) -> bool:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    return lx < rx + rw and rx < lx + lw and ly < ry + rh and ry < ly + lh


def _is_sparse_page_bbox(
    mask: np.ndarray,
    bbox: BBox,
    page_area: int,
    max_page_area_ratio: float = 0.25,
    min_fill_ratio: float = 0.01,
) -> bool:
    x, y, w, h = bbox
    bbox_area = max(1, w * h)
    if bbox_area < max(1, int(page_area * max_page_area_ratio)):
        return False
    changed_px = cv2.countNonZero(mask[y : y + h, x : x + w])
    return (changed_px / float(bbox_area)) < min_fill_ratio


def _find_base_bboxes(mask: np.ndarray, min_contour_area: float) -> list[BBox]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bboxes: list[BBox] = []
    page_area = int(mask.size)
    for c in contours:
        area = cv2.contourArea(c)
        if area >= min_contour_area:
            x, y, w, h = cv2.boundingRect(c)
            bbox = (int(x), int(y), int(w), int(h))
            if not _is_sparse_page_bbox(mask, bbox, page_area=page_area):
                bboxes.append(bbox)
    bboxes.sort(key=lambda box: (box[1], box[0], box[2] * box[3]))
    return bboxes


def _merge_bboxes_from_mask(
    mask: np.ndarray,
    base_bboxes: list[BBox],
    gap_px: int,
    max_area_ratio: float,
    max_page_area_ratio: float = 0.25,
    min_fill_ratio: float = 0.01,
) -> list[BBox]:
    if len(base_bboxes) <= 1 or gap_px <= 0:
        return base_bboxes

    kernel_size = max(3, int(gap_px) * 2 + 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    grouped_mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    contours, _ = cv2.findContours(grouped_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    page_area = int(mask.size)
    consumed: set[int] = set()
    merged: list[BBox] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        candidate = (int(x), int(y), int(w), int(h))
        overlaps = [idx for idx, box in enumerate(base_bboxes) if _bboxes_overlap(candidate, box)]
        if len(overlaps) <= 1:
            continue
        candidate_area = max(1, candidate[2] * candidate[3])
        source_area = max(1, sum(base_bboxes[idx][2] * base_bboxes[idx][3] for idx in overlaps))
        changed_px = cv2.countNonZero(mask[y : y + h, x : x + w])
        fill_ratio = changed_px / float(candidate_area)
        page_area_ok = candidate_area <= max(1, int(page_area * max_page_area_ratio))
        ratio_ok = candidate_area / source_area <= max(1.0, float(max_area_ratio))
        fill_ok = fill_ratio >= min_fill_ratio
        if page_area_ok and ratio_ok and fill_ok:
            merged.append(candidate)
            consumed.update(overlaps)

    for idx, box in enumerate(base_bboxes):
        if idx not in consumed:
            merged.append(box)
    merged.sort(key=lambda box: (box[1], box[0], box[2] * box[3]))
    return merged


def _calculate_metrics(
    mask: np.ndarray,
    mask_add: np.ndarray,
    mask_del: np.ndarray,
    fg_a: np.ndarray,
    fg_b: np.ndarray,
    bboxes: list[BBox],
    render_dpi: float,
) -> dict[str, float | int | bool]:
    metrics = _empty_metrics()
    changed_px = int(cv2.countNonZero(mask))
    added_px = int(cv2.countNonZero(mask_add))
    removed_px = int(cv2.countNonZero(mask_del))
    foreground = cv2.bitwise_or(fg_a, fg_b)
    foreground_px = int(cv2.countNonZero(foreground))
    px_to_mm2 = (25.4 / float(render_dpi)) ** 2 if float(render_dpi) > 0 else 0.0
    max_region_changed_px = 0
    for x, y, w, h in bboxes:
        max_region_changed_px = max(max_region_changed_px, int(cv2.countNonZero(mask[y : y + h, x : x + w])))
    # A nearly-empty sheet makes FG% explode (two lines on a blank A0 = 50%+).
    # Flag it so classification and reports fall back to absolute metrics.
    foreground_sparse = foreground_px < (mask.size * FOREGROUND_SPARSE_THRESHOLD)
    # Clamp FG% to 100.0: mask morphing / anti-aliasing can make changed_px
    # marginally exceed foreground_px on near-empty pages.
    diff_fg = min(100.0, (changed_px / foreground_px) * 100.0) if foreground_px else 0.0
    metrics.update(
        {
            "changed_px": changed_px,
            "added_px": added_px,
            "removed_px": removed_px,
            "foreground_px": foreground_px,
            "diff_percent": (changed_px / mask.size) * 100.0,
            "diff_foreground_percent": diff_fg,
            "diff_area_mm2": changed_px * px_to_mm2,
            "added_area_mm2": added_px * px_to_mm2,
            "removed_area_mm2": removed_px * px_to_mm2,
            "max_region_changed_px": max_region_changed_px,
            "max_region_area_mm2": max_region_changed_px * px_to_mm2,
            "foreground_sparse": foreground_sparse,
        }
    )
    return metrics


def compute_diff_detailed(
    a_bgr: np.ndarray,
    b_bgr: np.ndarray,
    stroke_tol_px: float = 2.0,
    exclude_regions: list[ExcludeRegion] | None = None,
    diff_strictness: str = "normal",
    render_dpi: float = 72.0,
    bbox_merge_gap_px: int = 0,
    bbox_merge_max_area_ratio: float = 16.0,
) -> tuple[np.ndarray, np.ndarray, list[BBox], dict[str, float | int]]:
    hb, wb = b_bgr.shape[:2]
    ha, wa = a_bgr.shape[:2]
    if (ha, wa) != (hb, wb):
        raise InvalidInput("raster_size_mismatch", a_w=wa, a_h=ha, b_w=wb, b_h=hb)

    strictness = str(diff_strictness or "normal").strip().lower()
    if strictness not in STRICTNESS_PROFILES:
        raise InvalidInput("strictness_invalid", value=diff_strictness, allowed=", ".join(DIFF_STRICTNESS_CHOICES))
    profile = STRICTNESS_PROFILES[strictness]
    effective_stroke_tol_px = max(0.0, float(stroke_tol_px) * float(profile["tol_multiplier"]))
    min_contour_area = float(profile["min_area"])

    # Robust comparison for engineering drawings:
    # ignore tiny raster/antialias thickness differences by tolerance in pixels.
    gray_a = cv2.cvtColor(a_bgr, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(b_bgr, cv2.COLOR_BGR2GRAY)
    gray_a = cv2.GaussianBlur(gray_a, (3, 3), 0)
    gray_b = cv2.GaussianBlur(gray_b, (3, 3), 0)

    _, bw_a = cv2.threshold(gray_a, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, bw_b = cv2.threshold(gray_b, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    del gray_a, gray_b

    fg_a = cv2.bitwise_not(bw_a)  # dark strokes/text as foreground
    fg_b = cv2.bitwise_not(bw_b)
    del bw_a, bw_b

    # remove tiny raster speckles
    noise_kernel = np.ones((2, 2), np.uint8)
    fg_a = cv2.morphologyEx(fg_a, cv2.MORPH_OPEN, noise_kernel, iterations=1)
    fg_b = cv2.morphologyEx(fg_b, cv2.MORPH_OPEN, noise_kernel, iterations=1)

    # Distance transforms are float32 (4 bytes/px) — the single largest
    # allocations in this function. Compute each, apply the stroke-tolerance
    # threshold immediately, and release the float buffer before the next one
    # so peak memory holds one transform at a time instead of two.
    # (Large A0/A1 sheets at high DPI previously crashed here allocating
    # >1 GB; cv2.error -4 Insufficient memory.)
    not_fg_b = cv2.bitwise_not(fg_b)
    dt_to_b = cv2.distanceTransform(not_fg_b, cv2.DIST_L2, 3)
    del not_fg_b
    mask_del = cv2.bitwise_and(fg_a, (dt_to_b > effective_stroke_tol_px).astype(np.uint8) * 255)
    del dt_to_b

    not_fg_a = cv2.bitwise_not(fg_a)
    dt_to_a = cv2.distanceTransform(not_fg_a, cv2.DIST_L2, 3)
    del not_fg_a
    mask_add = cv2.bitwise_and(fg_b, (dt_to_a > effective_stroke_tol_px).astype(np.uint8) * 255)
    del dt_to_a

    mask = cv2.bitwise_or(mask_del, mask_add)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask_del = cv2.bitwise_and(mask_del, mask)
    mask_add = cv2.bitwise_and(mask_add, mask)

    for x, y, w, h in exclusion_regions_to_pixel_boxes(exclude_regions or [], wb, hb, dpi=render_dpi):
        mask[y : y + h, x : x + w] = 0
        mask_del[y : y + h, x : x + w] = 0
        mask_add[y : y + h, x : x + w] = 0
        fg_a[y : y + h, x : x + w] = 0
        fg_b[y : y + h, x : x + w] = 0

    base_bboxes = _find_base_bboxes(mask, min_contour_area)
    bboxes = _merge_bboxes_from_mask(
        mask,
        base_bboxes,
        int(round(bbox_merge_gap_px)),
        bbox_merge_max_area_ratio,
    )
    metrics = _calculate_metrics(mask, mask_add, mask_del, fg_a, fg_b, bboxes, render_dpi)

    overlay = b_bgr.copy()
    # Two-color semi-transparent overlay: removed → pale blue, added → bright red.
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

    return mask, overlay, bboxes, metrics


def compute_diff(
    a_bgr: np.ndarray,
    b_bgr: np.ndarray,
    stroke_tol_px: float = 2.0,
    exclude_regions: list[ExcludeRegion] | None = None,
    diff_strictness: str = "normal",
    render_dpi: float = 72.0,
    bbox_merge_gap_px: int = 0,
    bbox_merge_max_area_ratio: float = 16.0,
) -> tuple[np.ndarray, np.ndarray, list[BBox], float]:
    mask, overlay, bboxes, metrics = compute_diff_detailed(
        a_bgr,
        b_bgr,
        stroke_tol_px=stroke_tol_px,
        exclude_regions=exclude_regions,
        diff_strictness=diff_strictness,
        render_dpi=render_dpi,
        bbox_merge_gap_px=bbox_merge_gap_px,
        bbox_merge_max_area_ratio=bbox_merge_max_area_ratio,
    )
    return mask, overlay, bboxes, float(metrics["diff_percent"])
