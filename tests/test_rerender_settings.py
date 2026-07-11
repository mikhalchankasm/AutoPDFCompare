"""Tests for the rerender override parsing and page_settings assembly.

These cover the pure logic that decides how the Re-render tab turns its
StringVar fields into kwargs for regenerate_report_pages /
regenerate_report_pages_mixed, without spinning up a full Tk window.
"""

from __future__ import annotations

import unittest
import tkinter as tk

from pdfcompare_ui.rerender_tab import RerenderTabMixin


class StubApp:
    """Minimal stand-in exposing just the StringVars the rerender logic reads.

    Mirrors the field names PDFCompareApp declares; the rerender helpers only
    touch these attributes, so we can exercise their logic directly.
    """

    def __init__(self, root: tk.Tk) -> None:
        self.rerender_stroke_tol = tk.StringVar(master=root, value="")
        self.rerender_strictness = tk.StringVar(master=root, value="")
        self.rerender_exclude = tk.StringVar(master=root, value="")
        self.rerender_bbox_gap = tk.StringVar(master=root, value="")
        self.rerender_page_settings: dict[int, dict] = {}

    # Bind the real mixin methods so we test the production logic.
    _parse_optional_float = RerenderTabMixin._parse_optional_float
    _collect_uniform_overrides_safe = RerenderTabMixin._collect_uniform_overrides_safe
    _build_page_settings = RerenderTabMixin._build_page_settings


class CollectOverridesTests(unittest.TestCase):
    def setUp(self) -> None:
        # Tk root is required for StringVar but we never create windows.
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = StubApp(self.root)

    def tearDown(self) -> None:
        self.root.destroy()

    def test_empty_fields_yield_no_overrides(self) -> None:
        overrides = self.app._collect_uniform_overrides_safe()
        self.assertEqual(overrides, {})

    def test_stroke_and_strictness_and_exclude_collected(self) -> None:
        self.app.rerender_stroke_tol.set("1.5")
        self.app.rerender_strictness.set("strict")
        self.app.rerender_exclude.set("70,80,30,20")
        overrides = self.app._collect_uniform_overrides_safe()
        self.assertAlmostEqual(overrides["stroke_tol"], 1.5)
        self.assertEqual(overrides["diff_strictness"], "strict")
        self.assertEqual(overrides["exclude_regions"], "70,80,30,20")
        self.assertNotIn("bbox_merge_gap_mm", overrides)

    def test_bbox_gap_enables_merge_with_default_ratio(self) -> None:
        self.app.rerender_bbox_gap.set("5")
        overrides = self.app._collect_uniform_overrides_safe()
        self.assertAlmostEqual(overrides["bbox_merge_gap_mm"], 5.0)
        self.assertAlmostEqual(overrides["bbox_merge_max_area_ratio"], 16.0)

    def test_invalid_strictness_is_ignored_safe(self) -> None:
        self.app.rerender_strictness.set("bogus")
        overrides = self.app._collect_uniform_overrides_safe()
        self.assertNotIn("diff_strictness", overrides)

    def test_invalid_gap_out_of_range_is_ignored_safe(self) -> None:
        self.app.rerender_bbox_gap.set("999")
        overrides = self.app._collect_uniform_overrides_safe()
        self.assertNotIn("bbox_merge_gap_mm", overrides)


class BuildPageSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = StubApp(self.root)

    def tearDown(self) -> None:
        self.root.destroy()

    def test_no_overrides_single_group_all_seqs(self) -> None:
        self.app.rerender_page_settings = {}
        settings = self.app._build_page_settings([1, 2, 3])
        self.assertEqual(len(settings), 1)
        self.assertEqual(sorted(settings[0]["seqs"]), [1, 2, 3])

    def test_per_page_overrides_split_into_groups(self) -> None:
        self.app.rerender_page_settings = {
            4: {"dpi": 500, "diff_strictness": "strict"},
            7: {"dpi": 300, "diff_strictness": "loose"},
        }
        settings = self.app._build_page_settings([4, 7])
        # Two distinct setting dicts -> two groups.
        self.assertEqual(len(settings), 2)
        all_seqs = [seq for spec in settings for seq in spec["seqs"]]
        self.assertEqual(sorted(all_seqs), [4, 7])

    def test_uniform_overrides_apply_to_seqs_without_explicit_settings(self) -> None:
        self.app.rerender_stroke_tol.set("0.5")
        self.app.rerender_page_settings = {2: {"dpi": 600}}
        settings = self.app._build_page_settings([1, 2])
        # seq 1 inherits uniform stroke_tol; seq 2 uses its explicit dpi only.
        by_seq: dict[int, dict] = {}
        for spec in settings:
            for seq in spec["seqs"]:
                by_seq[seq] = spec
        self.assertAlmostEqual(by_seq[1]["stroke_tol"], 0.5)
        self.assertEqual(by_seq[2]["dpi"], 600)
        self.assertNotIn("stroke_tol", by_seq[2])


if __name__ == "__main__":
    unittest.main()
