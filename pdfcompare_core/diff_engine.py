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


def compute_diff(
    a_bgr: np.ndarray,
    b_bgr: np.ndarray,
    stroke_tol_px: float = 2.0,
    exclude_regions: list[ExcludeRegion] | None = None,
    diff_strictness: str = "normal",
) -> tuple[np.ndarray, np.ndarray, list[tuple[int, int, int, int]], float]:
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

    for x, y, w, h in exclusion_regions_to_pixel_boxes(exclude_regions or [], wb, hb):
        mask[y : y + h, x : x + w] = 0
        mask_del[y : y + h, x : x + w] = 0
        mask_add[y : y + h, x : x + w] = 0

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bboxes: list[tuple[int, int, int, int]] = []
    for c in contours:
        area = cv2.contourArea(c)
        if area >= min_contour_area:
            x, y, w, h = cv2.boundingRect(c)
            bboxes.append((int(x), int(y), int(w), int(h)))

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
