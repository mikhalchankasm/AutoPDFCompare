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


def exclusion_regions_to_pixel_boxes(regions: object, width: int, height: int) -> list[PixelBox]:
    normalized = normalize_exclude_regions(regions)
    boxes: list[PixelBox] = []
    for region in normalized:
        unit = str(region.get("unit") or "percent").casefold()
        x = float(region["x"])
        y = float(region["y"])
        w = float(region["w"])
        h = float(region["h"])
        if unit in {"px", "pixel", "pixels"}:
            left = round(x)
            top = round(y)
            right = round(x + w)
            bottom = round(y + h)
        else:
            scale = 0.01 if unit in {"percent", "%"} else 1.0
            left = round(width * x * scale)
            top = round(height * y * scale)
            right = round(width * (x + w) * scale)
            bottom = round(height * (y + h) * scale)

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
        return _normalize_region_values(
            [item.get("x"), item.get("y"), item.get("w"), item.get("h")],
            idx,
            unit=unit,
            label=label,
        )
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
    elif unit in {"px", "pixel", "pixels"}:
        limit = None
    else:
        unit = "percent"
        limit = 100.0

    if x < 0 or y < 0 or w <= 0 or h <= 0:
        raise ValueError(f"Область #{idx}: x/y должны быть >= 0, w/h > 0")
    if limit is not None and (x > limit or y > limit or x + w > limit or y + h > limit):
        label_text = "0..1" if unit == "ratio" else "0..100%"
        raise ValueError(f"Область #{idx}: координаты должны помещаться в диапазон {label_text}")

    region: ExcludeRegion = {"x": x, "y": y, "w": w, "h": h, "unit": unit}
    if label:
        region["label"] = label
    return region
