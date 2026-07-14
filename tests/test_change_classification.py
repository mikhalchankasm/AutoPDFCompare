import base64
import json
import tempfile
import unittest
from pathlib import Path

import fitz

from compare_pdfs import (
    INTERNAL_REPORT_DIR,
    START_REPORT_FILE,
    MatchPair,
    classify,
    generate_html_report,
    report_pages_dir,
    status_and_confidence,
    write_live_html_report,
)


class ChangeClassificationTests(unittest.TestCase):
    def test_identical_pages_are_unchanged(self) -> None:
        self.assertEqual(classify(0.0, bboxes_count=0, diff_foreground_percent=0.0), "unchanged")

    def test_dense_page_small_change_is_minor_by_fg(self) -> None:
        # Dense page (not sparse), FG% just above minor threshold.
        self.assertEqual(
            classify(0.02, bboxes_count=1, diff_foreground_percent=1.5, foreground_sparse=False),
            "minor",
        )

    def test_dense_page_moderate_and_major_by_fg(self) -> None:
        self.assertEqual(
            classify(0.02, bboxes_count=1, diff_foreground_percent=8.0, foreground_sparse=False),
            "moderate",
        )
        self.assertEqual(
            classify(0.02, bboxes_count=1, diff_foreground_percent=20.0, foreground_sparse=False),
            "major",
        )

    def test_sparse_page_ignores_fg_uses_absolute_metrics(self) -> None:
        # Sparse page: FG% would be absurd (50%), but foreground_sparse=True
        # forces classification by mm² / zones. A 150 mm² region = minor.
        self.assertEqual(
            classify(
                0.01,
                bboxes_count=1,
                diff_foreground_percent=50.0,
                foreground_sparse=True,
                max_region_area_mm2=150.0,
            ),
            "minor",
        )
        # Same FG% but a large region → major by mm².
        self.assertEqual(
            classify(
                0.01,
                bboxes_count=1,
                diff_foreground_percent=50.0,
                foreground_sparse=True,
                max_region_area_mm2=12000.0,
            ),
            "major",
        )

    def test_many_small_zones_reach_moderate(self) -> None:
        # 20 zones → moderate by zone count (>= 15).
        self.assertEqual(
            classify(
                0.01,
                bboxes_count=20,
                diff_foreground_percent=0.5,
                foreground_sparse=False,
                max_region_area_mm2=50.0,
            ),
            "moderate",
        )

    def test_many_zones_reach_major(self) -> None:
        # 45 zones → major by zone count (>= 40).
        self.assertEqual(
            classify(
                0.01,
                bboxes_count=45,
                diff_foreground_percent=0.5,
                foreground_sparse=False,
                max_region_area_mm2=50.0,
            ),
            "major",
        )

    def test_large_single_region_is_major(self) -> None:
        self.assertEqual(
            classify(
                0.1,
                bboxes_count=1,
                diff_foreground_percent=0.5,
                foreground_sparse=False,
                max_region_area_mm2=12000.0,
            ),
            "major",
        )

    def test_composite_takes_max_across_signals(self) -> None:
        # FG% says minor (1.5), but region area says major (12000).
        self.assertEqual(
            classify(
                0.02,
                bboxes_count=1,
                diff_foreground_percent=1.5,
                foreground_sparse=False,
                max_region_area_mm2=12000.0,
            ),
            "major",
        )

    def test_legacy_fallback_uses_diff_percent_only(self) -> None:
        # Old run data: diff_foreground_percent is None.
        self.assertEqual(classify(0.2, bboxes_count=0), "minor")
        self.assertEqual(classify(2.0, bboxes_count=0), "moderate")
        self.assertEqual(classify(6.0, bboxes_count=0), "major")
        self.assertEqual(classify(0.021, bboxes_count=0), "unchanged")
        self.assertEqual(classify(0.021, bboxes_count=16), "minor")

    def test_status_and_confidence_with_new_fields(self) -> None:
        row = {
            "status": "matched",
            "a_page": 4,
            "b_page": 4,
            "diff_percent": 0.021,
            "change_level": "minor",
            "bboxes_count": 16,
            "score": 0.999,
            "diff_foreground_percent": 2.0,
            "foreground_sparse": False,
            "max_region_area_mm2": 150.0,
        }
        page_status, confidence, content_status, moved = status_and_confidence(row)
        self.assertEqual(page_status, "CHANGED")
        self.assertEqual(content_status, "CHANGED")
        self.assertEqual(confidence, "EXACT")
        self.assertFalse(moved)

    def test_unchanged_status_and_confidence(self) -> None:
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


class FinalReportTests(unittest.TestCase):
    PNG_1X1 = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
    )

    def _write_pdf(self, path: Path, pages: int) -> None:
        doc = fitz.open()
        for idx in range(pages):
            page = doc.new_page(width=120, height=80)
            page.insert_text((12, 30), f"Page {idx + 1}", fontsize=10)
        doc.save(path)
        doc.close()

    def test_slider_report_has_next_prev_and_hover_sheet_picker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_pdf = root / "old.pdf"
            new_pdf = root / "new.pdf"
            self._write_pdf(old_pdf, 2)
            self._write_pdf(new_pdf, 2)

            run_dir = root / "run"
            pages_dir = report_pages_dir(run_dir)
            details = []
            for seq in (1, 2):
                pair_name = f"{seq:03d}__A_{seq}__B_{seq}"
                pair_dir = pages_dir / pair_name
                pair_dir.mkdir(parents=True)
                for image_name in ("a.png", "b.png", "overlay.png"):
                    (pair_dir / image_name).write_bytes(self.PNG_1X1)
                (pair_dir / "bboxes.json").write_text("[]", encoding="utf-8")
                details.append(
                    {
                        "seq": seq,
                        "a_page": seq,
                        "b_page": seq,
                        "pair_dir": pair_name,
                        "status": "matched",
                        "score": 0.99,
                        "diff_percent": 0.0,
                        "change_level": "unchanged",
                        "bboxes_count": 0,
                        "ecc_failed": False,
                    }
                )
            added_dir = pages_dir / "003__A_NA__B_3"
            added_dir.mkdir(parents=True)
            (added_dir / "b.png").write_bytes(self.PNG_1X1)
            details.append(
                {
                    "seq": 3,
                    "a_page": None,
                    "b_page": 3,
                    "pair_dir": added_dir.name,
                    "status": "added",
                    "score": 0.0,
                    "diff_percent": None,
                    "change_level": None,
                    "bboxes_count": None,
                    "ecc_failed": False,
                }
            )
            removed_dir = pages_dir / "004__A_3__B_NA"
            removed_dir.mkdir(parents=True)
            (removed_dir / "a.png").write_bytes(self.PNG_1X1)
            details.append(
                {
                    "seq": 4,
                    "a_page": 3,
                    "b_page": None,
                    "pair_dir": removed_dir.name,
                    "status": "removed",
                    "score": 0.0,
                    "diff_percent": None,
                    "change_level": None,
                    "bboxes_count": None,
                    "ecc_failed": False,
                }
            )

            generate_html_report(run_dir, old_pdf, new_pdf, details, high_dpi=72, stroke_tol_px=2.0, report_lang="ru")

            index_html = (run_dir / INTERNAL_REPORT_DIR / "report" / "index.html").read_text(encoding="utf-8")
            slider_html = (run_dir / INTERNAL_REPORT_DIR / "report" / "views" / "cmp_001.html").read_text(
                encoding="utf-8"
            )
            detail_html = (run_dir / INTERNAL_REPORT_DIR / "report" / "views" / "001.html").read_text(encoding="utf-8")
            self.assertIn('class="matrix-tools"', index_html)
            self.assertNotIn('class="filters"', index_html)
            self.assertNotIn('class="chip"', index_html)
            # The sheet list is shared by every page now (PDF-008), so the drawer's
            # contents are asserted where they actually live: nav-data.js.
            nav_data = (run_dir / INTERNAL_REPORT_DIR / "report" / "nav-data.js").read_text(encoding="utf-8")
            nav_pages = json.loads(nav_data.split("=", 1)[1].rstrip().rstrip(";"))["pages"]
            self.assertEqual(len(nav_pages), 4)
            added = next(page for page in nav_pages if page["href"] == "003.html")
            self.assertFalse(added["hasSlider"], "an added sheet has no slider to open")
            self.assertTrue(any(page["href"] == "cmp_001.html" for page in nav_pages))

            self.assertIn('src="../nav-data.js"', slider_html)
            self.assertIn('src="../nav-data.js"', detail_html)
            self.assertIn("cmp_002.html", slider_html)
            self.assertIn('class="sheet-drawer"', slider_html)
            self.assertIn("const allSheets", slider_html)
            self.assertIn("disabled-slider", slider_html)
            self.assertIn('id="bboxToggle"', slider_html)
            self.assertIn('id="oneBtn"', slider_html)
            self.assertIn('data-bbox="off"', slider_html)
            self.assertIn('data-color="yellow"', slider_html)
            self.assertIn("pdfcompare.bbox", slider_html)
            self.assertIn("data-bbox-enabled", slider_html)
            self.assertIn("sliderNavSearch", slider_html)
            self.assertIn("Home", slider_html)
            self.assertNotIn("Все листы", slider_html)
            self.assertIn("К матрице изменений", detail_html)
            self.assertIn("Открыть внешне", detail_html)
            self.assertIn("Открыть в слайдере", detail_html)
            self.assertIn("side-summary", detail_html)
            self.assertNotIn('data-mode="slider"', detail_html)
            self.assertNotIn('?embed=1"', detail_html)
            self.assertNotIn("bottom-bar", detail_html)
            self.assertIn("box-shadow: inset 4px 0 0 var(--brand)", detail_html)
            self.assertNotIn("Summary preview", detail_html)


if __name__ == "__main__":
    unittest.main()
