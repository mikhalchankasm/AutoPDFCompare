"""The picker's region model: physical zones that survive a format change.

The point of an anchored zone is that one setting covers every sheet the user
works with. That only holds if the zone is exported in millimetres: 185 mm is
62% of an A4 sheet but 16% of an A0 one, so a percent box drawn on A4 would
cover 741x220 mm on A0 — a quarter of the sheet.
"""

from __future__ import annotations

import json
import tkinter as tk
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import fitz

from tk_support import shared_root

from pdfcompare_core.exclusions import exclusion_regions_to_pixel_boxes
from pdfcompare_ui.exclusion_picker import (
    ISO_FORMATS,
    PT_PER_MM,
    UNIT_MM,
    UNIT_PERCENT,
    _RegionPicker,
    export_regions_from_model,
    format_regions_for_field,
    import_regions_to_model,
    incoming_unit,
    region_from_rect_mm,
    region_rect_mm,
    region_to_export,
    region_unit,
)

DPI = 100.0
MM_TO_PX = DPI / 25.4

# Landscape sheets the same stamp zone has to work on.
SHEETS_MM = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}

ANCHORS = ("top_left", "top_right", "bottom_left", "bottom_right")
FORMAT_MM = {name: (w, h) for name, w, h in ISO_FORMATS}


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


class _HiddenToplevel(tk.Toplevel):
    """The real dialog, never mapped: a test must not flash a window on screen."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.withdraw()

    def grab_set(self) -> None:
        pass  # an unmapped window cannot take a grab


def _click(x: int, y: int) -> tk.Event:
    event = tk.Event()
    event.x, event.y = x, y
    return event


def _sheet_pdf(path: Path, fmt: str, orientation: str) -> Path:
    short, long_ = sorted(FORMAT_MM[fmt])
    w_mm, h_mm = (long_, short) if orientation == "landscape" else (short, long_)
    doc = fitz.open()
    doc.new_page(width=w_mm * PT_PER_MM, height=h_mm * PT_PER_MM)
    doc.save(path)
    doc.close()
    return path


class PickerWorkflowTests(unittest.TestCase):
    """Open the real dialog on real zones, press OK, change nothing.

    PDF-001: the picker used to hold one unit for the whole dialog, so a set that
    mixed percent and mm came back entirely in mm — a saved percent zone quietly
    became a physical one, excluding a different part of any differently sized
    sheet. These drive `_RegionPicker` itself (import → model → `_accept`), not
    the conversion helpers underneath it.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        # The session's single root — see tests/tk_support.py. Spinning up and tearing
        # down a Tk() per test class is what broke Tcl for whatever ran next.
        cls.root = shared_root()

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def build(self, existing: list[dict], fmt: str, orientation: str) -> _RegionPicker:
        pdf = _sheet_pdf(Path(self._tmp.name) / f"{fmt}_{orientation}.pdf", fmt, orientation)
        doc = fitz.open(pdf)
        try:
            picker = _RegionPicker(self.root, doc, 1, [dict(r) for r in existing])
        finally:
            doc.close()
        self.addCleanup(picker.dialog.destroy)
        self.assertEqual(picker.format_var.get(), fmt, "the sheet format was not detected")
        self.assertEqual(picker.orient_var.get(), orientation)
        return picker

    def open_and_accept(
        self,
        existing: list[dict],
        fmt: str = "A4",
        orientation: str = "portrait",
        confirm_migration: bool = False,
        click_unit: str | None = None,
    ) -> list[dict]:
        with mock.patch.object(tk, "Toplevel", _HiddenToplevel):
            picker = self.build(existing, fmt, orientation)
            if click_unit is not None:
                with mock.patch.object(_RegionPicker, "_confirm_unit_migration", return_value=confirm_migration):
                    picker.unit_var.set(click_unit)
                    picker._on_unit_change()
            picker._accept()
            return list(picker.result["regions"])

    def assert_round_trip(self, existing: list[dict], fmt: str, orientation: str) -> None:
        produced = self.open_and_accept(existing, fmt, orientation)
        self.assertEqual(len(produced), len(existing), f"{fmt} {orientation}: region lost")
        for got, want in zip(produced, existing, strict=True):
            for key in ("unit", "anchor"):
                self.assertEqual(got[key], want[key], f"{fmt} {orientation} {key}")
            for key in ("x", "y", "w", "h"):
                self.assertAlmostEqual(
                    float(got[key]), float(want[key]), places=2, msg=f"{fmt} {orientation} {key}"
                )

    def test_percent_set_round_trips_on_every_anchor_format_and_orientation(self) -> None:
        for fmt in ("A4", "A3", "A0"):
            for orientation in ("portrait", "landscape"):
                for anchor in ANCHORS:
                    zone = {"x": 12.0, "y": 8.0, "w": 30.0, "h": 20.0, "unit": "percent", "anchor": anchor}
                    with self.subTest(fmt=fmt, orientation=orientation, anchor=anchor):
                        self.assert_round_trip([zone], fmt, orientation)

    def test_mm_set_round_trips_on_every_anchor_format_and_orientation(self) -> None:
        for fmt in ("A4", "A3", "A0"):
            for orientation in ("portrait", "landscape"):
                for anchor in ANCHORS:
                    zone = {"x": 5.0, "y": 5.0, "w": 185.0, "h": 55.0, "unit": "mm", "anchor": anchor}
                    with self.subTest(fmt=fmt, orientation=orientation, anchor=anchor):
                        self.assert_round_trip([zone], fmt, orientation)

    def test_mixed_percent_and_mm_set_round_trips_unchanged(self) -> None:
        # The finding itself: this set used to come back entirely in mm.
        mixed = [
            {"x": 70.0, "y": 80.0, "w": 30.0, "h": 20.0, "unit": "percent", "anchor": "top_left"},
            {"x": 0.0, "y": 0.0, "w": 185.0, "h": 55.0, "unit": "mm", "anchor": "bottom_right"},
            {"x": 4.0, "y": 6.0, "w": 25.0, "h": 10.0, "unit": "percent", "anchor": "bottom_left"},
        ]
        for fmt in ("A4", "A3", "A0"):
            for orientation in ("portrait", "landscape"):
                with self.subTest(fmt=fmt, orientation=orientation):
                    self.assert_round_trip(mixed, fmt, orientation)

    def test_mixed_set_keeps_percent_semantics_on_a_bigger_sheet(self) -> None:
        # Not just the same numbers: the same *meaning*. The percent zone must
        # still scale with the sheet and the mm zone must still not.
        mixed = [
            {"x": 0.0, "y": 0.0, "w": 50.0, "h": 50.0, "unit": "percent", "anchor": "top_left"},
            {"x": 0.0, "y": 0.0, "w": 185.0, "h": 55.0, "unit": "mm", "anchor": "bottom_right"},
        ]
        produced = self.open_and_accept(mixed, "A4", "landscape")
        a0_w, a0_h = _px(1189.0, 841.0)
        boxes = exclusion_regions_to_pixel_boxes(produced, a0_w, a0_h, dpi=DPI)
        pct_w, pct_h = boxes[0][2] / MM_TO_PX, boxes[0][3] / MM_TO_PX
        mm_w, mm_h = boxes[1][2] / MM_TO_PX, boxes[1][3] / MM_TO_PX
        # Half of an A0 landscape sheet (1189x841 mm), within a pixel of rounding.
        self.assertAlmostEqual(pct_w, 594.5, delta=1.0, msg="percent zone stopped scaling with the sheet")
        self.assertAlmostEqual(pct_h, 420.5, delta=1.0, msg="percent zone stopped scaling with the sheet")
        self.assertAlmostEqual(mm_w, 185.0, delta=1.0, msg="mm zone stopped being physical")
        self.assertAlmostEqual(mm_h, 55.0, delta=1.0, msg="mm zone stopped being physical")

    def test_opening_a_mixed_set_touches_no_unit_without_a_click(self) -> None:
        mixed = [
            {"x": 70.0, "y": 80.0, "w": 30.0, "h": 20.0, "unit": "percent", "anchor": "top_left"},
            {"x": 0.0, "y": 0.0, "w": 185.0, "h": 55.0, "unit": "mm", "anchor": "bottom_right"},
        ]
        produced = self.open_and_accept(mixed, "A4", "portrait")
        self.assertEqual([r["unit"] for r in produced], ["percent", "mm"])

    def test_switching_units_migrates_only_when_the_user_confirms(self) -> None:
        mixed = [
            {"x": 70.0, "y": 80.0, "w": 30.0, "h": 20.0, "unit": "percent", "anchor": "top_left"},
            {"x": 0.0, "y": 0.0, "w": 185.0, "h": 55.0, "unit": "mm", "anchor": "bottom_right"},
        ]
        confirmed = self.open_and_accept(mixed, "A4", "portrait", click_unit=UNIT_MM, confirm_migration=True)
        self.assertEqual([r["unit"] for r in confirmed], ["mm", "mm"])
        # 70% of a 210 mm sheet is 147 mm — the migration is a real conversion.
        self.assertAlmostEqual(float(confirmed[0]["x"]), 147.0, places=1)

        declined = self.open_and_accept(mixed, "A4", "portrait", click_unit=UNIT_MM, confirm_migration=False)
        self.assertEqual([r["unit"] for r in declined], ["percent", "mm"])
        self.assertAlmostEqual(float(declined[0]["x"]), 70.0, places=2)

    def switch_sheet(self, picker: _RegionPicker, fmt: str, orientation: str) -> None:
        picker.format_var.set(fmt)
        picker.orient_var.set(orientation)
        picker._on_format_change()

    def test_switching_the_sheet_format_does_not_rewrite_percent_zones(self) -> None:
        # The reported case: draw 70/10/20/15 percent on A4, switch the preview to A0,
        # press OK — and it came back as 17.4792/2.4979/4.9941/3.7468. The switch is
        # meant to *show* where a zone lands on another sheet, not to convert it.
        zone = {"x": 70.0, "y": 10.0, "w": 20.0, "h": 15.0, "unit": "percent", "anchor": "top_left"}

        with mock.patch.object(tk, "Toplevel", _HiddenToplevel):
            picker = self.build([zone], "A4", "portrait")
            self.switch_sheet(picker, "A0", "portrait")
            picker._accept()
            produced = picker.result["regions"]

        self.assertEqual(produced[0]["unit"], "percent")
        for key in ("x", "y", "w", "h"):
            self.assertAlmostEqual(float(produced[0][key]), float(zone[key]), places=3, msg=key)

    def test_a_mixed_set_survives_a_format_switch_in_both_senses(self) -> None:
        # The two units have to disagree here, and that is the point: on the bigger
        # sheet the percent zone must grow with it and the mm zone must not.
        mixed = [
            {"x": 70.0, "y": 10.0, "w": 20.0, "h": 15.0, "unit": "percent", "anchor": "top_left"},
            {"x": 0.0, "y": 0.0, "w": 185.0, "h": 55.0, "unit": "mm", "anchor": "bottom_right"},
        ]

        with mock.patch.object(tk, "Toplevel", _HiddenToplevel):
            picker = self.build(mixed, "A4", "portrait")
            self.switch_sheet(picker, "A0", "portrait")
            picker._accept()
            produced = picker.result["regions"]

        for got, want in zip(produced, mixed, strict=True):
            self.assertEqual(got["unit"], want["unit"])
            self.assertEqual(got["anchor"], want["anchor"])
            for key in ("x", "y", "w", "h"):
                self.assertAlmostEqual(float(got[key]), float(want[key]), places=2, msg=f"{want['unit']} {key}")

        # And the meaning is intact: 20% of an A0 sheet is 168 mm wide, the stamp is
        # still 185 mm wide.
        a0_w, a0_h = _px(841.0, 1189.0)
        boxes = exclusion_regions_to_pixel_boxes(produced, a0_w, a0_h, dpi=DPI)
        self.assertAlmostEqual(boxes[0][2] / MM_TO_PX, 0.20 * 841.0, delta=1.0)
        self.assertAlmostEqual(boxes[1][2] / MM_TO_PX, 185.0, delta=1.0)

    def test_a_percent_zone_survives_any_format_and_orientation_switch(self) -> None:
        for anchor in ANCHORS:
            zone = {"x": 12.0, "y": 8.0, "w": 30.0, "h": 20.0, "unit": "percent", "anchor": anchor}
            for fmt in ("A3", "A0"):
                for orientation in ("portrait", "landscape"):
                    with self.subTest(anchor=anchor, fmt=fmt, orientation=orientation):
                        with mock.patch.object(tk, "Toplevel", _HiddenToplevel):
                            picker = self.build([zone], "A4", "portrait")
                            self.switch_sheet(picker, fmt, orientation)
                            picker._accept()
                            produced = picker.result["regions"]
                        for key in ("x", "y", "w", "h"):
                            self.assertAlmostEqual(float(produced[0][key]), float(zone[key]), places=3, msg=key)

    def test_switching_back_and_forth_does_not_drift(self) -> None:
        zone = {"x": 70.0, "y": 10.0, "w": 20.0, "h": 15.0, "unit": "percent", "anchor": "bottom_right"}
        with mock.patch.object(tk, "Toplevel", _HiddenToplevel):
            picker = self.build([zone], "A4", "portrait")
            for fmt, orientation in (("A0", "landscape"), ("A3", "portrait"), ("A4", "portrait")):
                self.switch_sheet(picker, fmt, orientation)
            picker._accept()
            produced = picker.result["regions"]
        for key in ("x", "y", "w", "h"):
            self.assertAlmostEqual(float(produced[0][key]), float(zone[key]), places=3, msg=key)

    def test_a_newly_drawn_region_takes_the_selected_unit(self) -> None:
        with mock.patch.object(tk, "Toplevel", _HiddenToplevel):
            picker = self.build([], "A4", "landscape")
            self.assertEqual(picker.unit_var.get(), UNIT_MM, "a fresh set must default to mm")
            picker.unit_var.set(UNIT_PERCENT)
            picker._on_unit_change()  # nothing to migrate: no confirmation is asked

            # Drag out a box on the canvas — the picker's own draw path.
            picker._on_press(_click(40, 30))
            picker._on_drag(_click(180, 120))
            picker._on_release(_click(180, 120))
            picker._accept()
            produced = picker.result["regions"]

        self.assertEqual(len(produced), 1)
        self.assertEqual(produced[0]["unit"], UNIT_PERCENT)


class ModelFlowTests(unittest.TestCase):
    """The same open→OK path as the dialog, without Tk — so it also runs headless."""

    def round_trip(self, existing: list[dict], sheet_w: float, sheet_h: float) -> list[dict]:
        model = import_regions_to_model(existing, sheet_w, sheet_h)
        return export_regions_from_model(model, sheet_w, sheet_h)

    def test_every_anchor_orientation_and_format_survives_a_mixed_set(self) -> None:
        mixed = [
            {"x": 12.0, "y": 9.0, "w": 30.0, "h": 20.0, "unit": "percent"},
            {"x": 7.0, "y": 3.0, "w": 185.0, "h": 55.0, "unit": "mm"},
        ]
        for fmt, short, long_ in ISO_FORMATS:
            for orientation in ("portrait", "landscape"):
                sheet_w, sheet_h = (long_, short) if orientation == "landscape" else (short, long_)
                for anchor in ANCHORS:
                    existing = [dict(zone, anchor=anchor) for zone in mixed]
                    with self.subTest(fmt=fmt, orientation=orientation, anchor=anchor):
                        produced = self.round_trip(existing, sheet_w, sheet_h)
                        for got, want in zip(produced, existing, strict=True):
                            self.assertEqual(got["unit"], want["unit"])
                            self.assertEqual(got["anchor"], want["anchor"])
                            for key in ("x", "y", "w", "h"):
                                self.assertAlmostEqual(float(got[key]), float(want[key]), places=2, msg=key)

    def test_a_malformed_neighbour_does_not_drop_the_rest(self) -> None:
        existing = [
            {"x": 1.0, "y": 1.0, "w": 10.0, "h": 10.0, "unit": "percent"},
            {"x": 0.0, "y": 0.0, "w": 5.0, "h": 5.0, "unit": "cm"},  # rejected by the core
            {"x": 2.0, "y": 2.0, "w": 20.0, "h": 10.0, "unit": "mm"},
        ]
        produced = self.round_trip(existing, 210.0, 297.0)
        self.assertEqual([r["unit"] for r in produced], ["percent", "mm"])

    def test_units_the_picker_cannot_reproduce_become_physical(self) -> None:
        # px is tied to a raster's DPI and ratio to the sheet: neither is a picker
        # unit, so both land on mm — the physical representation, as before.
        self.assertEqual(region_unit({"unit": "px"}), UNIT_MM)
        self.assertEqual(region_unit({"unit": "ratio"}), UNIT_MM)
        self.assertEqual(region_unit({"unit": "%"}), UNIT_PERCENT)
        self.assertEqual(region_unit({}), UNIT_PERCENT)  # no unit is the legacy percent default


def _canon(rect: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return tuple(round(v, 6) for v in rect)  # type: ignore[return-value]


if __name__ == "__main__":
    unittest.main()
