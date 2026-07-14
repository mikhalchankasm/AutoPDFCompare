"""The report must not grow quadratically with the number of sheets (PDF-008).

Every detail page used to carry an inlined copy of the whole sheet list, and every
slider re-walked all N sheets to emit its own copy of the drawer *plus* a JSON copy
of the same list beside it. N sheets therefore cost O(N²) bytes and O(N²) work.
Measured on this generator before the fix:

    sheets   gen s   html MB   detail KB   slider KB
       100     1.0        26        64.3       204.1
       300     6.1       192       141.4       510.7
      1000    31.9      1951       411.5      1584.0

Ten times the sheets, seventy-four times the HTML — and a single slider page had
grown to 1.5 MB. The list now ships once as `nav-data.js` and every page renders
from it, so a page is a fixed size and the bundle is linear.

The assertions below are the regression guard and run in a second. The full
100/300/1000 table is reproducible on demand:

    PDFCOMPARE_BENCH=1 python -m pytest tests/test_html_report_scaling.py -s -k benchmark
"""

from __future__ import annotations

import json
import os
import shutil
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
import pytest

from pdfcompare_core.html_report import NAV_DATA_FILE, generate_html_report
from pdfcompare_core.pdf_io import internal_dir

CANNED: dict[str, object] = {
    "diff_percent": 1.25,
    "change_level": "moderate",
    "bboxes_count": 3,
    "effective_dpi": 100.0,
    "stroke_tol_px": 2.0,
    "width_px": 827,
    "height_px": 1169,
    "diff_area_mm2": 780.5,
    "diff_foreground_percent": 4.5,
    "max_region_area_mm2": 120.4,
    "foreground_sparse": False,
    "ecc_failed": False,
}


def _seed_png(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=40, height=56)
    page.get_pixmap(dpi=20).save(path)
    doc.close()


def _build_run(root: Path, sheets: int) -> tuple[Path, Path, Path, list[dict]]:
    """A run folder with N page pairs, without paying for a real diff of N sheets."""
    run_dir = root / f"run_{sheets}"
    pages = run_dir / "pages"
    pages.mkdir(parents=True)

    doc = fitz.open()
    doc.new_page(width=595, height=842)
    file_a, file_b = root / "a.pdf", root / "b.pdf"
    doc.save(file_a)
    doc.save(file_b)
    doc.close()

    seed = root / "seed.png"
    _seed_png(seed)

    details: list[dict] = []
    for seq in range(1, sheets + 1):
        pair = f"{seq:03d}__A_{seq}__B_{seq}"
        pair_dir = pages / pair
        pair_dir.mkdir()
        for name in ("a.png", "b.png", "overlay.png", "a_preview.png", "b_preview.png"):
            shutil.copyfile(seed, pair_dir / name)
        details.append(
            {"seq": seq, "a_page": seq, "b_page": seq, "pair_dir": pair, "status": "matched", "score": 0.99, **CANNED}
        )
    return run_dir, file_a, file_b, details


def _render(root: Path, sheets: int) -> tuple[Path, float]:
    run_dir, file_a, file_b, details = _build_run(root, sheets)
    started = time.perf_counter()
    generate_html_report(run_dir, file_a, file_b, details, high_dpi=100, stroke_tol_px=2.0, report_lang="ru")
    return internal_dir(run_dir) / "report", time.perf_counter() - started


def _html_bytes(bundle: Path) -> int:
    return sum(p.stat().st_size for p in bundle.rglob("*.html"))


class ReportScalingTests(unittest.TestCase):
    SMALL = 25
    LARGE = 100  # 4x the sheets

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = TemporaryDirectory()
        root = Path(cls._tmp.name)
        cls.small, _ = _render(root / "small", cls.SMALL)
        cls.large, _ = _render(root / "large", cls.LARGE)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_a_detail_page_is_the_same_size_whatever_the_sheet_count(self) -> None:
        small = (self.small / "views" / "001.html").stat().st_size
        large = (self.large / "views" / "001.html").stat().st_size
        # 4x the sheets used to mean ~4x the page. Only the "1 / N" counters differ now.
        self.assertLess(
            large,
            small * 1.05,
            f"a detail page grew with the sheet count: {small} -> {large} bytes for "
            f"{self.SMALL} -> {self.LARGE} sheets",
        )

    def test_a_slider_page_is_the_same_size_whatever_the_sheet_count(self) -> None:
        small = (self.small / "views" / "cmp_001.html").stat().st_size
        large = (self.large / "views" / "cmp_001.html").stat().st_size
        self.assertLess(
            large,
            small * 1.05,
            f"a slider page grew with the sheet count: {small} -> {large} bytes",
        )

    def test_total_html_grows_linearly_not_quadratically(self) -> None:
        small = _html_bytes(self.small)
        large = _html_bytes(self.large)
        growth = large / small
        # 4x the sheets: linear is ~4x, quadratic was ~16x.
        self.assertLess(growth, 6.0, f"HTML grew {growth:.1f}x for 4x the sheets — still superlinear")

    def test_the_sheet_list_ships_once_and_every_page_loads_it(self) -> None:
        nav_file = self.large / NAV_DATA_FILE
        self.assertTrue(nav_file.exists(), "the shared sheet list was not written")

        payload = nav_file.read_text(encoding="utf-8")
        self.assertTrue(payload.startswith("window.PDFCOMPARE_NAV="))
        nav = json.loads(payload.split("=", 1)[1].rstrip().rstrip(";"))
        self.assertEqual(len(nav["pages"]), self.LARGE, "the shared list is missing sheets")

        for name in ("001.html", "cmp_001.html"):
            page = (self.large / "views" / name).read_text(encoding="utf-8")
            self.assertIn(f'src="../{NAV_DATA_FILE}"', page, f"{name} does not load the shared list")
            # A relative <script src> is what keeps the report openable from the
            # file system; fetch() of a local file would be blocked by the browser.
            self.assertNotIn("fetch(", page, f"{name} fetches at runtime — that breaks file:// offline use")

        # And the list is no longer pasted into the pages themselves.
        detail = (self.large / "views" / "001.html").read_text(encoding="utf-8")
        self.assertIn('<div id="navList" class="nav-list"></div>', detail)
        self.assertNotIn("href='100.html'", detail, "the sheet list is still inlined into the detail page")

    def test_the_dashboard_still_lists_every_sheet_itself(self) -> None:
        # The dashboard is the one page that legitimately holds the full table: it
        # is O(N) once, not O(N) per page.
        index = (self.large / "index.html").read_text(encoding="utf-8")
        self.assertIn("100.html", index)


class ReportScalingBenchmark(unittest.TestCase):
    def test_benchmark(self) -> None:
        if os.getenv("PDFCOMPARE_BENCH") != "1":
            pytest.skip("set PDFCOMPARE_BENCH=1 to run the 100/300/1000-sheet benchmark")

        rows = []
        for sheets in (100, 300, 1000):
            with TemporaryDirectory() as tmp:
                bundle, elapsed = _render(Path(tmp), sheets)
                rows.append(
                    {
                        "sheets": sheets,
                        "gen_sec": round(elapsed, 2),
                        "html_mb": round(_html_bytes(bundle) / 1024 / 1024, 1),
                        "detail_kb": round((bundle / "views" / "001.html").stat().st_size / 1024, 1),
                        "slider_kb": round((bundle / "views" / "cmp_001.html").stat().st_size / 1024, 1),
                        "nav_js_kb": round((bundle / NAV_DATA_FILE).stat().st_size / 1024, 1),
                    }
                )

        print(f"\n{'sheets':>7} {'gen s':>7} {'html MB':>8} {'detail KB':>10} {'slider KB':>10} {'nav.js KB':>10}")
        for row in rows:
            print(
                f"{row['sheets']:>7} {row['gen_sec']:>7} {row['html_mb']:>8} "
                f"{row['detail_kb']:>10} {row['slider_kb']:>10} {row['nav_js_kb']:>10}"
            )

        first, last = rows[0], rows[-1]
        html_growth = last["html_mb"] / first["html_mb"]
        print(f"\nsheets x10 -> html x{html_growth:.1f} (quadratic was x74)")
        self.assertLess(html_growth, 15.0, "HTML still grows superlinearly with the sheet count")
        self.assertLess(last["detail_kb"], first["detail_kb"] * 1.05, "a detail page still grows with the sheet count")


if __name__ == "__main__":
    unittest.main()
