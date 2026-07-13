"""The picker's region model: physical zones that survive a format change.

The point of an anchored zone is that one setting covers every sheet the user
works with. That only holds if the zone is exported in millimetres: 185 mm is
62% of an A4 sheet but 16% of an A0 one, so a percent box drawn on A4 would
cover 741x220 mm on A0 — a quarter of the sheet.
"""

from __future__ import annotations

import json
import unittest

from pdfcompare_core.exclusions import exclusion_regions_to_pixel_boxes
from pdfcompare_ui.exclusion_picker import (
    UNIT_MM,
    UNIT_PERCENT,
    format_regions_for_field,
    incoming_unit,
    region_from_rect_mm,
    region_rect_mm,
    region_to_export,
)

DPI = 100.0
MM_TO_PX = DPI / 25.4

# Landscape sheets the same stamp zone has to work on.
SHEETS_MM = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}


def _px(width_mm: float, height_mm: float) -> tuple[int, int]:
    return int(round(width_mm * MM_TO_PX)), int(round(height_mm * MM_TO_PX))


class RegionModelTests(unittest.TestCase):
    def test_rect_round_trips_through_every_anchor(self) -> None:
        sheet_w, sheet_h = 297.0, 210.0
        for anchor in ("top_left", "top_right", "bottom_left", "bottom_right"):
            region = region_from_rect_mm(100.0, 40.0, 185.0, 55.0, anchor, sheet_w, sheet_h)
            self.assertEqual(_canon(region_rect_mm(region, sheet_w, sheet_h)), (100.0, 40.0, 185.0, 55.0))

    def test_bottom_right_zone_is_measured_from_that_corner(self) -> None:
        # A stamp flush to the bottom-right corner has zero offsets.
        region = region_from_rect_mm(297.0 - 185.0, 210.0 - 55.0, 185.0, 55.0, "bottom_right", 297.0, 210.0)
        self.assertEqual((round(region["x_mm"], 6), round(region["y_mm"], 6)), (0.0, 0.0))


class ExportTests(unittest.TestCase):
    def _stamp(self) -> dict:
        # 185x55 mm title block in the bottom-right corner of an A4 landscape sheet.
        return region_from_rect_mm(297.0 - 185.0, 210.0 - 55.0, 185.0, 55.0, "bottom_right", 297.0, 210.0)

    def _applied_size_mm(self, exported: dict, sheet: str) -> tuple[float, float]:
        w_mm, h_mm = SHEETS_MM[sheet]
        width, height = _px(w_mm, h_mm)
        boxes = exclusion_regions_to_pixel_boxes([exported], width, height, dpi=DPI)
        self.assertEqual(len(boxes), 1, f"{sheet}: region did not apply")
        _x, _y, w_px, h_px = boxes[0]
        return round(w_px / MM_TO_PX), round(h_px / MM_TO_PX)

    def test_mm_zone_is_identical_on_every_format(self) -> None:
        exported = region_to_export(self._stamp(), 297.0, 210.0, UNIT_MM)
        self.assertEqual(exported["unit"], UNIT_MM)
        for sheet in SHEETS_MM:
            self.assertEqual(self._applied_size_mm(exported, sheet), (185, 55), f"on {sheet}")

    def test_mm_zone_stays_glued_to_its_corner(self) -> None:
        exported = region_to_export(self._stamp(), 297.0, 210.0, UNIT_MM)
        for sheet, (w_mm, h_mm) in SHEETS_MM.items():
            width, height = _px(w_mm, h_mm)
            (x_px, y_px, w_px, h_px), = exclusion_regions_to_pixel_boxes([exported], width, height, dpi=DPI)
            self.assertLessEqual(abs((x_px + w_px) - width), 1, f"{sheet}: not flush right")
            self.assertLessEqual(abs((y_px + h_px) - height), 1, f"{sheet}: not flush bottom")

    def test_percent_zone_does_not_survive_a_format_change(self) -> None:
        # Documents the reason mm is the default: this is what the old export did.
        exported = region_to_export(self._stamp(), 297.0, 210.0, UNIT_PERCENT)
        self.assertEqual(self._applied_size_mm(exported, "A4"), (185, 55))
        self.assertEqual(self._applied_size_mm(exported, "A0"), (741, 220))


class IncomingUnitTests(unittest.TestCase):
    """Opening zones and pressing OK unchanged must not rewrite them.

    Saved percent zones silently re-exported as mm would exclude a different part
    of a differently sized sheet — a data migration disguised as "open and
    confirm".
    """

    def test_a_percent_set_opens_in_percent(self) -> None:
        existing = [{"x": 70.0, "y": 80.0, "w": 30.0, "h": 20.0, "unit": "percent"}]
        self.assertEqual(incoming_unit(existing), UNIT_PERCENT)

    def test_a_set_with_no_unit_is_percent_the_legacy_default(self) -> None:
        self.assertEqual(incoming_unit([{"x": 70.0, "y": 80.0, "w": 30.0, "h": 20.0}]), UNIT_PERCENT)

    def test_an_mm_set_opens_in_mm(self) -> None:
        existing = [{"x": 0.0, "y": 0.0, "w": 185.0, "h": 55.0, "unit": "mm", "anchor": "bottom_right"}]
        self.assertEqual(incoming_unit(existing), UNIT_MM)

    def test_a_mixed_set_opens_in_mm(self) -> None:
        existing = [
            {"x": 70.0, "y": 80.0, "w": 30.0, "h": 20.0, "unit": "percent"},
            {"x": 0.0, "y": 0.0, "w": 185.0, "h": 55.0, "unit": "mm", "anchor": "bottom_right"},
        ]
        self.assertEqual(incoming_unit(existing), UNIT_MM)

    def test_a_fresh_set_defaults_to_mm(self) -> None:
        self.assertEqual(incoming_unit(None), UNIT_MM)
        self.assertEqual(incoming_unit([]), UNIT_MM)

    def test_percent_zone_round_trips_unchanged(self) -> None:
        # What the picker does to a legacy zone on open+OK: percent -> mm model ->
        # export in the incoming unit. The numbers must come back the same.
        sheet_w, sheet_h = 210.0, 297.0
        original = {"x": 70.0, "y": 80.0, "w": 30.0, "h": 20.0, "unit": "percent", "anchor": "top_left"}
        left = original["x"] / 100.0 * sheet_w
        top = original["y"] / 100.0 * sheet_h
        w = original["w"] / 100.0 * sheet_w
        h = original["h"] / 100.0 * sheet_h
        model = region_from_rect_mm(left, top, w, h, "top_left", sheet_w, sheet_h)

        exported = region_to_export(model, sheet_w, sheet_h, incoming_unit([original]))

        self.assertEqual(exported["unit"], UNIT_PERCENT)
        for key in ("x", "y", "w", "h"):
            self.assertAlmostEqual(float(exported[key]), float(original[key]), places=3, msg=key)


class FieldSerializationTests(unittest.TestCase):
    def test_mm_regions_become_json_with_unit_and_anchor(self) -> None:
        region = region_to_export(
            region_from_rect_mm(0.0, 0.0, 185.0, 55.0, "bottom_right", 297.0, 210.0), 297.0, 210.0, UNIT_MM
        )
        text = format_regions_for_field([region])
        payload = json.loads(text)
        self.assertEqual(payload[0]["unit"], "mm")
        self.assertEqual(payload[0]["anchor"], "bottom_right")
        self.assertEqual(payload[0]["w"], 185.0)
        # And the core accepts it back unchanged.
        width, height = _px(841.0, 1189.0)
        boxes = exclusion_regions_to_pixel_boxes(text, width, height, dpi=DPI)
        self.assertEqual(len(boxes), 1)

    def test_legacy_percent_top_left_regions_stay_plain_text(self) -> None:
        regions = [{"x": 70.0, "y": 80.0, "w": 30.0, "h": 20.0, "unit": "percent", "anchor": "top_left"}]
        self.assertEqual(format_regions_for_field(regions), "70,80,30,20")


def _canon(rect: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return tuple(round(v, 6) for v in rect)  # type: ignore[return-value]


if __name__ == "__main__":
    unittest.main()
