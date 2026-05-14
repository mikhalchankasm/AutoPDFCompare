"""Diff-percent → severity level mapping and per-row status helpers."""

from __future__ import annotations

from .constants import MINOR_DIFF_PERCENT, MODERATE_DIFF_PERCENT, UNCHANGED_DIFF_PERCENT


def classify(diff_percent: float, bboxes_count: int | None = None) -> str:
    if diff_percent < UNCHANGED_DIFF_PERCENT:
        if bboxes_count is not None and bboxes_count > 0:
            return "minor"
        return "unchanged"
    if diff_percent < MINOR_DIFF_PERCENT:
        return "minor"
    if diff_percent < MODERATE_DIFF_PERCENT:
        return "moderate"
    return "major"


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
        level = classify(float(diff), row.get("bboxes_count"))
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
