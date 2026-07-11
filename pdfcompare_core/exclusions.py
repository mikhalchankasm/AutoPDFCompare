"""Parsing and scaling page regions excluded from visual diff."""

from __future__ import annotations

import json
import re

type ExcludeRegion = dict[str, float | str]
type PixelBox = tuple[int, int, int, int]


def normalize_exclude_regions(raw_regions: object) -> list[ExcludeRegion]:
    """Return validated exclusion regions in percent or pixel units.

    Accepted shapes:
    - ``None`` / empty string: no regions;
    - string ``"x,y,w,h; x,y,w,h"`` in percent of page;
    - JSON string with a list of region objects;
    - list of dicts with ``x``, ``y``, ``w``, ``h`` and optional ``unit``/``label``;
    - list of four-number sequences.
    """

    if raw_regions is None:
        return []
    if isinstance(raw_regions, str):
        raw_text = raw_regions.strip()
        if not raw_text:
            return []
        if raw_text.startswith("["):
            try:
                return normalize_exclude_regions(json.loads(raw_text))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Некорректный JSON исключений: {exc}") from exc
        return _parse_region_text(raw_text)
    if not isinstance(raw_regions, (list, tuple)):
        raise ValueError("Исключаемые области должны быть списком или строкой")

    regions: list[ExcludeRegion] = []
    for idx, item in enumerate(raw_regions, start=1):
        regions.append(_normalize_region_item(item, idx))
    return regions


def exclusion_regions_to_pixel_boxes(regions: object, width: int, height: int, dpi: float = 72.0) -> list[PixelBox]:
    normalized = normalize_exclude_regions(regions)
    boxes: list[PixelBox] = []
    for region in normalized:
        unit = str(region.get("unit") or "percent").casefold()
        anchor = str(region.get("anchor") or "top_left").strip().casefold().replace("-", "_")
        x = float(region["x"])
        y = float(region["y"])
        w = float(region["w"])
        h = float(region["h"])
        if unit in {"px", "pixel", "pixels"}:
            x_px = x
            y_px = y
            w_px = w
            h_px = h
        elif unit in {"mm", "millimeter", "millimeters"}:
            scale = float(dpi) / 25.4
            x_px = x * scale
            y_px = y * scale
            w_px = w * scale
            h_px = h * scale
        else:
            scale = 0.01 if unit in {"percent", "%"} else 1.0
            x_px = width * x * scale
            y_px = height * y * scale
            w_px = width * w * scale
            h_px = height * h * scale

        if anchor in {"top_left", "left_top", "tl"}:
            left = round(x_px)
            top = round(y_px)
            right = round(x_px + w_px)
            bottom = round(y_px + h_px)
        elif anchor in {"top_right", "right_top", "tr"}:
            right = round(width - x_px)
            left = round(right - w_px)
            top = round(y_px)
            bottom = round(y_px + h_px)
        elif anchor in {"bottom_left", "left_bottom", "bl"}:
            left = round(x_px)
            right = round(x_px + w_px)
            bottom = round(height - y_px)
            top = round(bottom - h_px)
        elif anchor in {"bottom_right", "right_bottom", "br"}:
            right = round(width - x_px)
            left = round(right - w_px)
            bottom = round(height - y_px)
            top = round(bottom - h_px)
        else:
            raise ValueError(f"Некорректная привязка исключаемой области: {anchor}")

        left = max(0, min(width, int(left)))
        top = max(0, min(height, int(top)))
        right = max(0, min(width, int(right)))
        bottom = max(0, min(height, int(bottom)))
        if right > left and bottom > top:
            boxes.append((left, top, right - left, bottom - top))
    return boxes


def _parse_region_text(raw_text: str) -> list[ExcludeRegion]:
    parts = [part.strip() for part in re.split(r"[;\n]+", raw_text) if part.strip()]
    regions: list[ExcludeRegion] = []
    for idx, part in enumerate(parts, start=1):
        cleaned = part.strip().strip("()[]{}")
        values = [value for value in re.split(r"[,\s]+", cleaned) if value]
        if len(values) != 4:
            raise ValueError(f"Область #{idx}: нужен формат x,y,w,h в процентах")
        regions.append(_normalize_region_values(values, idx, unit="percent"))
    return regions


def _normalize_region_item(item: object, idx: int) -> ExcludeRegion:
    if isinstance(item, dict):
        unit = str(item.get("unit") or "percent").strip().lower()
        label = str(item.get("label") or item.get("name") or f"region_{idx}").strip()
        region = _normalize_region_values(
            [item.get("x"), item.get("y"), item.get("w"), item.get("h")],
            idx,
            unit=unit,
            label=label,
        )
        if item.get("anchor") is not None:
            region["anchor"] = str(item.get("anchor") or "").strip().lower()
        return region
    if isinstance(item, (list, tuple)) and len(item) == 4:
        return _normalize_region_values(list(item), idx, unit="percent")
    raise ValueError(f"Область #{idx}: нужен объект {{x,y,w,h}} или список из 4 чисел")


def _normalize_region_values(values: list[object], idx: int, *, unit: str, label: str | None = None) -> ExcludeRegion:
    try:
        x, y, w, h = (float(str(value)) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Область #{idx}: x,y,w,h должны быть числами") from exc

    unit = unit.casefold()
    if unit in {"ratio", "relative"}:
        limit = 1.0
    elif unit in {"px", "pixel", "pixels", "mm", "millimeter", "millimeters"}:
        limit = None
    else:
        unit = "percent"
        limit = 100.0

    if x < 0 or y < 0 or w <= 0 or h <= 0:
        raise ValueError(f"Область #{idx}: x/y должны быть >= 0, w/h > 0")
    # Allow a tiny tolerance for rounding (e.g. a picker that rounds x and w
    # independently may produce x+w = 100.0002). Clamp small overflows instead
    # of rejecting; large overflows are still a user error.
    eps = 0.01
    if limit is not None:
        if x > limit + eps or y > limit + eps:
            label_text = "0..1" if unit == "ratio" else "0..100%"
            raise ValueError(f"Область #{idx}: координаты должны помещаться в диапазон {label_text}")
        if x + w > limit:
            if x + w > limit + eps:
                label_text = "0..1" if unit == "ratio" else "0..100%"
                raise ValueError(f"Область #{idx}: координаты должны помещаться в диапазон {label_text}")
            w = limit - x
        if y + h > limit:
            if y + h > limit + eps:
                label_text = "0..1" if unit == "ratio" else "0..100%"
                raise ValueError(f"Область #{idx}: координаты должны помещаться в диапазон {label_text}")
            h = limit - y

    region: ExcludeRegion = {"x": x, "y": y, "w": w, "h": h, "unit": unit}
    if label:
        region["label"] = label
    return region
