"""Diff-percent → severity level mapping and per-row status helpers."""

from __future__ import annotations

from .constants import (
    FG_MAJOR_PERCENT,
    FG_MINOR_PERCENT,
    FG_MODERATE_PERCENT,
    MINOR_DIFF_PERCENT,
    MODERATE_DIFF_PERCENT,
    REGION_MAJOR_MM2,
    REGION_MINOR_MM2,
    REGION_MODERATE_MM2,
    UNCHANGED_DIFF_PERCENT,
    ZONES_MAJOR,
    ZONES_MINOR,
    ZONES_MODERATE,
)

_LEVEL_RANK = {"unchanged": 0, "minor": 1, "moderate": 2, "major": 3}


def _signal_level(value: float, minor: float, moderate: float, major: float) -> str:
    """Map a single numeric signal to its severity level."""
    if value >= major:
        return "major"
    if value >= moderate:
        return "moderate"
    if value >= minor:
        return "minor"
    return "unchanged"


def classify(
    diff_percent: float,
    bboxes_count: int | None = None,
    diff_foreground_percent: float | None = None,
    foreground_sparse: bool = False,
    max_region_area_mm2: float | None = None,
    diff_area_mm2: float | None = None,
) -> str:
    """Composite severity classification (max across independent signals).

    Three independent signals each produce a level; the result is the highest:
    1. FG% (diff relative to drawn content) — ignored when ``foreground_sparse``.
    2. Largest change region in mm² (``max_region_area_mm2``).
    3. Number of change zones (``bboxes_count``).

    ``unchanged`` only when no signal reaches minor and there are zero zones.
    Fallback: when ``diff_foreground_percent`` is None (legacy runs), the old
    diff-percent-led logic is used.
    """
    boxes = int(bboxes_count or 0)

    # --- Legacy fallback: no FG% available (old run data) -------------------
    if diff_foreground_percent is None:
        if diff_percent >= MODERATE_DIFF_PERCENT:
            return "major"
        if diff_percent >= MINOR_DIFF_PERCENT:
            return "moderate"
        if diff_percent >= UNCHANGED_DIFF_PERCENT or boxes > 0:
            return "minor"
        return "unchanged"

    # --- Composite path -----------------------------------------------------
    levels: list[str] = []

    # Signal 1: FG% (only when the page is not foreground-sparse).
    if not foreground_sparse:
        fg = float(diff_foreground_percent or 0.0)
        levels.append(_signal_level(fg, FG_MINOR_PERCENT, FG_MODERATE_PERCENT, FG_MAJOR_PERCENT))

    # Signal 2: largest change region (mm²).
    if max_region_area_mm2 is not None:
        region = float(max_region_area_mm2)
        levels.append(_signal_level(region, REGION_MINOR_MM2, REGION_MODERATE_MM2, REGION_MAJOR_MM2))

    # Signal 3: number of change zones.
    levels.append(_signal_level(float(boxes), ZONES_MINOR, ZONES_MODERATE, ZONES_MAJOR))

    best = max(levels, key=lambda lv: _LEVEL_RANK.get(lv, 0))

    # unchanged only if nothing reached minor AND no zones detected.
    if best == "unchanged" and boxes == 0:
        return "unchanged"
    if best == "unchanged":
        # zones signal was the only one to fire minor but boxes>0 path above
        # already returned; if we're here with boxes==0 it's genuinely unchanged
        return "unchanged"
    return best


def level_to_report_tags(level: str | None) -> tuple[str, str]:
    if level == "unchanged" or level is None:
        return "UNCHANGED", "UNCHANGED"
    if level in {"minor", "moderate", "major", "size_mismatch"}:
        return "CHANGED", str(level).upper()
    return "CHANGED", str(level).upper()


def status_and_confidence(row: dict) -> tuple[str, str, str, bool]:
    status = row["status"]
    moved = bool(row.get("a_page") and row.get("b_page") and row["a_page"] != row["b_page"])
    if status == "added":
        return "ADDED", "NONE", "ADDED", False
    if status == "removed":
        return "REMOVED", "NONE", "REMOVED", False
    if status == "size_mismatch":
        return "CHANGED", "NONE", "CHANGED", moved

    diff = row.get("diff_percent")
    level = row.get("change_level")
    if level is None and diff is not None:
        level = classify(
            float(diff),
            row.get("bboxes_count"),
            row.get("diff_foreground_percent"),
            foreground_sparse=bool(row.get("foreground_sparse") or False),
            max_region_area_mm2=row.get("max_region_area_mm2"),
            diff_area_mm2=row.get("diff_area_mm2"),
        )
    content_status, _ = level_to_report_tags(level)
    page_status = content_status

    score = float(row.get("score") or 0.0)
    if score >= 0.98:
        conf = "EXACT"
    elif score >= 0.75:
        conf = "PROBABLE"
    else:
        conf = "NONE"
    return page_status, conf, content_status, moved
