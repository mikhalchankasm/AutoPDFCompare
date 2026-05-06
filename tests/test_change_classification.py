import tempfile
import unittest
from pathlib import Path

from compare_pdfs import (
    INTERNAL_REPORT_DIR,
    MINOR_DIFF_PERCENT,
    MODERATE_DIFF_PERCENT,
    START_REPORT_FILE,
    UNCHANGED_DIFF_PERCENT,
    MatchPair,
    classify,
    status_and_confidence,
    write_live_html_report,
)


class ChangeClassificationTests(unittest.TestCase):
    def test_detected_regions_make_tiny_area_changed(self) -> None:
        self.assertEqual(classify(0.021, bboxes_count=16), "minor")

        row = {
            "status": "matched",
            "a_page": 4,
            "b_page": 4,
            "diff_percent": 0.021,
            "change_level": "minor",
            "bboxes_count": 16,
            "score": 0.999,
        }
        page_status, confidence, content_status, moved = status_and_confidence(row)

        self.assertEqual(page_status, "CHANGED")
        self.assertEqual(content_status, "CHANGED")
        self.assertEqual(confidence, "EXACT")
        self.assertFalse(moved)

    def test_tiny_noise_without_detected_regions_remains_unchanged(self) -> None:
        self.assertEqual(classify(0.021, bboxes_count=0), "unchanged")

        row = {
            "status": "matched",
            "a_page": 4,
            "b_page": 4,
            "diff_percent": 0.021,
            "change_level": "unchanged",
            "bboxes_count": 0,
            "score": 0.999,
        }
        page_status, _, content_status, _ = status_and_confidence(row)

        self.assertEqual(page_status, "UNCHANGED")
        self.assertEqual(content_status, "UNCHANGED")

    def test_area_threshold_still_marks_larger_diffs_changed(self) -> None:
        self.assertEqual(classify(0.2, bboxes_count=0), "minor")
        self.assertEqual(classify(2.0, bboxes_count=0), "moderate")
        self.assertEqual(classify(6.0, bboxes_count=0), "major")

    def test_threshold_boundaries_are_inclusive_for_next_level(self) -> None:
        self.assertEqual(classify(UNCHANGED_DIFF_PERCENT, bboxes_count=0), "minor")
        self.assertEqual(classify(MINOR_DIFF_PERCENT, bboxes_count=0), "moderate")
        self.assertEqual(classify(MODERATE_DIFF_PERCENT, bboxes_count=0), "major")
        self.assertEqual(classify(UNCHANGED_DIFF_PERCENT - 0.000001, bboxes_count=1), "minor")


class LiveReportTests(unittest.TestCase):
    def test_live_report_lists_completed_and_pending_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            pair_dir = run_dir / "pages" / "001__A_1__B_1"
            pair_dir.mkdir(parents=True)
            (pair_dir / "a.png").write_bytes(b"png")
            (pair_dir / "b.png").write_bytes(b"png")
            details = [
                {
                    "seq": 1,
                    "a_page": 1,
                    "b_page": 1,
                    "pair_dir": pair_dir.name,
                    "status": "matched",
                    "score": 0.99,
                    "diff_percent": 0.25,
                    "change_level": "minor",
                    "bboxes_count": 2,
                    "ecc_failed": False,
                }
            ]
            pairs = [MatchPair(0, 0, "matched", 0.99), MatchPair(1, 1, "matched", 0.98)]

            write_live_html_report(run_dir, Path("old.pdf"), Path("new.pdf"), pairs, details, report_lang="ru", in_progress=True)

            index_html = (run_dir / INTERNAL_REPORT_DIR / "report" / "index.html").read_text(encoding="utf-8")
            self.assertIn("1/2", index_html)
            self.assertIn("Обрабатывается", index_html)
            self.assertIn("views/001.html", index_html)
            self.assertTrue((run_dir / START_REPORT_FILE).exists())
            self.assertTrue((run_dir / INTERNAL_REPORT_DIR / "report" / "views" / "001.html").exists())
            self.assertTrue((run_dir / INTERNAL_REPORT_DIR / "report" / "views" / "cmp_001.html").exists())
            slider_html = (run_dir / INTERNAL_REPORT_DIR / "report" / "views" / "cmp_001.html").read_text(encoding="utf-8")
            self.assertIn("bboxPalettes", slider_html)
            self.assertIn('name="bboxColor"', slider_html)
            self.assertIn('id="bboxOpacity"', slider_html)
            self.assertIn("bboxOpacityVal", slider_html)
            self.assertIn("--bbox-fill:rgba(255,235,120,.13)", slider_html)

            write_live_html_report(run_dir, Path("old.pdf"), Path("new.pdf"), pairs, details, report_lang="ru", in_progress=False)
            final_live_html = (run_dir / INTERNAL_REPORT_DIR / "report" / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("http-equiv=\"refresh\"", final_live_html)


if __name__ == "__main__":
    unittest.main()
