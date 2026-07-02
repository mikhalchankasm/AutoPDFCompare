"""Pixel-level diff detection between rendered PDF pages."""

from __future__ import annotations

import cv2
import numpy as np

from .exclusions import ExcludeRegion, exclusion_regions_to_pixel_boxes


DIFF_STRICTNESS_CHOICES = ("strict", "normal", "loose")
STRICTNESS_PROFILES = {
    "strict": {"tol_multiplier": 0.65, "min_area": 80},
    "normal": {"tol_multiplier": 1.0, "min_area": 180},
    "loose": {"tol_multiplier": 1.6, "min_area": 360},
}

type BBox = tuple[int, int, int, int]


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


def _boxes_touch_or_nearly_touch(left: BBox, right: BBox, gap_px: int) -> bool:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    return not (
        lx + lw + gap_px < rx
        or rx + rw + gap_px < lx
        or ly + lh + gap_px < ry
        or ry + rh + gap_px < ly
    )


def _union_box(boxes: list[BBox]) -> BBox:
    x0 = min(x for x, _, _, _ in boxes)
    y0 = min(y for _, y, _, _ in boxes)
    x1 = max(x + w for x, _, w, _ in boxes)
    y1 = max(y + h for _, y, _, h in boxes)
    return int(x0), int(y0), int(x1 - x0), int(y1 - y0)


def _merge_nearby_bboxes(
    bboxes: list[BBox],
    gap_px: int,
    max_area_ratio: float,
    page_area: int,
    max_page_area_ratio: float = 0.25,
) -> list[BBox]:
    if len(bboxes) <= 1 or gap_px <= 0:
        return bboxes

    parent = list(range(len(bboxes)))

    def find(idx: int) -> int:
        while parent[idx] != idx:
            parent[idx] = parent[parent[idx]]
            idx = parent[idx]
        return idx

    def union(left_idx: int, right_idx: int) -> None:
        left_root = find(left_idx)
        right_root = find(right_idx)
        if left_root != right_root:
            parent[right_root] = left_root

    for i, left in enumerate(bboxes):
        for j in range(i + 1, len(bboxes)):
            right = bboxes[j]
            if not _boxes_touch_or_nearly_touch(left, right, gap_px):
                continue
            union_candidate = _union_box([left, right])
            union_area = max(1, union_candidate[2] * union_candidate[3])
            source_area = max(1, left[2] * left[3] + right[2] * right[3])
            # Avoid turning two thin, distant strokes into one giant empty rectangle.
            if union_area / source_area <= max(1.0, float(max_area_ratio)):
                union(i, j)

    groups: dict[int, list[BBox]] = {}
    for idx, box in enumerate(bboxes):
        groups.setdefault(find(idx), []).append(box)

    merged: list[BBox] = []
    for boxes in groups.values():
        if len(boxes) == 1:
            merged.append(boxes[0])
            continue
        candidate = _union_box(boxes)
        candidate_area = max(1, candidate[2] * candidate[3])
        source_area = max(1, sum(w * h for _, _, w, h in boxes))
        page_area_ok = candidate_area <= max(1, int(page_area * max_page_area_ratio))
        if page_area_ok and candidate_area / source_area <= max(1.0, float(max_area_ratio)):
            merged.append(candidate)
        else:
            merged.extend(boxes)

    merged.sort(key=lambda box: (box[1], box[0], box[2] * box[3]))
    return merged


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
    hb, wb = b_bgr.shape[:2]
    ha, wa = a_bgr.shape[:2]
    if (ha, wa) != (hb, wb):
        raise ValueError(f"Разные размеры растра: A={wa}x{ha}, B={wb}x{hb}")

    strictness = str(diff_strictness or "normal").strip().lower()
    if strictness not in STRICTNESS_PROFILES:
        raise ValueError(f"Некорректная строгость сравнения: {diff_strictness}")
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

    fg_a = cv2.bitwise_not(bw_a)  # dark strokes/text as foreground
    fg_b = cv2.bitwise_not(bw_b)

    # remove tiny raster speckles
    noise_kernel = np.ones((2, 2), np.uint8)
    fg_a = cv2.morphologyEx(fg_a, cv2.MORPH_OPEN, noise_kernel, iterations=1)
    fg_b = cv2.morphologyEx(fg_b, cv2.MORPH_OPEN, noise_kernel, iterations=1)

    dt_to_b = cv2.distanceTransform(cv2.bitwise_not(fg_b), cv2.DIST_L2, 3)
    dt_to_a = cv2.distanceTransform(cv2.bitwise_not(fg_a), cv2.DIST_L2, 3)
    mask_del = cv2.bitwise_and(fg_a, (dt_to_b > effective_stroke_tol_px).astype(np.uint8) * 255)
    mask_add = cv2.bitwise_and(fg_b, (dt_to_a > effective_stroke_tol_px).astype(np.uint8) * 255)
    mask = cv2.bitwise_or(mask_del, mask_add)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    for x, y, w, h in exclusion_regions_to_pixel_boxes(exclude_regions or [], wb, hb, dpi=render_dpi):
        mask[y : y + h, x : x + w] = 0
        mask_del[y : y + h, x : x + w] = 0
        mask_add[y : y + h, x : x + w] = 0

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bboxes: list[BBox] = []
    for c in contours:
        area = cv2.contourArea(c)
        if area >= min_contour_area:
            x, y, w, h = cv2.boundingRect(c)
            bbox = (int(x), int(y), int(w), int(h))
            if not _is_sparse_page_bbox(mask, bbox, page_area=int(mask.size)):
                bboxes.append(bbox)
    bboxes = _merge_nearby_bboxes(
        bboxes,
        int(round(bbox_merge_gap_px)),
        bbox_merge_max_area_ratio,
        page_area=int(mask.size),
    )

    diff_percent = (cv2.countNonZero(mask) / mask.size) * 100.0

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

    return mask, overlay, bboxes, float(diff_percent)
