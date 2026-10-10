"""What the report tells the reader about a sheet beyond its raw numbers."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from pdfcompare_core.classification import classify, level_signals
from pdfcompare_core.html_fragments import ReportBadges, ReportI18n
from pdfcompare_core.html_i18n import HTML_REPORT_I18N
from pdfcompare_core.html_report import _page_notes, _prepare_pages_records
from pdfcompare_core.pdf_io import imwrite_compat


class LevelSignalsTests(unittest.TestCase):
    def test_signals_explain_a_major_level_below_the_fg_threshold(self) -> None:
        # KM4 sheet 11: 6.64% drawn reads "moderate at most", yet the sheet is
        # major — the 67 zones set it. The tooltip must be able to say so.
        signals = level_signals(6.64, False, 2019.7, 67)
        self.assertEqual([(name, level) for name, _value, level in signals], [
            ("fg", "minor"),
            ("region", "minor"),
            ("zones", "major"),
        ])
        self.assertEqual(classify(0.4, 67, 6.64, max_region_area_mm2=2019.7), "major")

    def test_sparse_sheet_skips_the_fg_signal(self) -> None:
        names = [name for name, _value, _level in level_signals(50.0, True, 10.0, 1)]
        self.assertEqual(names, ["region", "zones"])

    def test_legacy_rows_have_no_signal_breakdown(self) -> None:
        self.assertEqual(level_signals(None, False, None, 3), [])

    def test_level_badge_carries_a_bilingual_reason(self) -> None:
        badges = ReportBadges(ReportI18n("ru"), 150)
        page = {
            "diff_foreground_metric": 6.64,
            "foreground_sparse": False,
            "max_region_area_mm2": 2019.7,
            "bboxes_count": 67,
        }
        badge = badges.level_badge_html("MAJOR", page)
        self.assertIn("зон 67 → крупные", badge)
        self.assertIn("zones 67 → major", badge)
        self.assertIn('data-i18n-title-en="', badge)

    def test_size_mismatch_level_is_localized_not_a_raw_key(self) -> None:
        for lang in ("ru", "en"):
            badge = ReportBadges(ReportI18n(lang), 150).level_badge_html("SIZE_MISMATCH")
            self.assertNotIn(">SIZE_MISMATCH<", badge)
            self.assertIn(HTML_REPORT_I18N[lang]["level_size_mismatch"], badge)


class PageNotesTests(unittest.TestCase):
    def test_size_mismatch_says_no_diff_was_computed(self) -> None:
        row = {"status": "size_mismatch", "change_level": "size_mismatch"}
        for lang in ("ru", "en"):
            notes = _page_notes(row, "CHANGED", HTML_REPORT_I18N[lang])
            self.assertEqual(notes, [("warn", HTML_REPORT_I18N[lang]["note_size_mismatch"])])

    def test_alignment_notes_follow_the_summary(self) -> None:
        base = {
            "status": "matched",
            "diff_foreground_percent": 2.0,
            "diff_area_mm2": 10.0,
            "bboxes_count": 2,
            "max_region_area_mm2": 6.0,
        }
        t = HTML_REPORT_I18N["en"]
        kinds = [kind for kind, _text in _page_notes({**base, "ecc_failed": True}, "CHANGED", t)]
        self.assertEqual(kinds, ["summary", "info"])
        shifted = {**base, "alignment_shift_x_mm": 1.5, "alignment_shift_y_mm": 0.0}
        notes = _page_notes(shifted, "CHANGED", t)
        self.assertEqual(notes[1], ("info", t["note_alignment_shift"].format(x=1.5, y=0.0)))
        self.assertEqual(len(_page_notes(base, "CHANGED", t)), 1)


class MissingOverlayTests(unittest.TestCase):
    def test_sheet_without_overlay_has_no_diff_image(self) -> None:
        # A size-mismatch pair has a.png/b.png but no overlay.png. The empty
        # Path() placeholder used to resolve to the pair directory itself, which
        # "exists", so the DIFF panel rendered a broken <img src="../.">.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pair = root / "pages" / "001__A_1__B_1"
            pair.mkdir(parents=True)
            white = np.full((20, 30, 3), 255, dtype=np.uint8)
            imwrite_compat(pair / "a.png", white)
            imwrite_compat(pair / "b.png", white)
            bundle = root / "report"
            thumbs = bundle / "assets" / "thumbs"
            thumbs.mkdir(parents=True)
            row = {"seq": 1, "a_page": 1, "b_page": 1, "status": "size_mismatch", "change_level": "size_mismatch"}
            (record,) = _prepare_pages_records(
                [row], root / "a.pdf", root / "b.pdf", root / "pages", bundle, thumbs, HTML_REPORT_I18N["ru"]
            )
        self.assertIsNone(record["assets"]["hires_diff"])
        self.assertIsNotNone(record["assets"]["hires_old"])
        self.assertEqual([kind for kind, _ in record["notes_by_lang"]["en"]], ["warn"])


if __name__ == "__main__":
    unittest.main()
