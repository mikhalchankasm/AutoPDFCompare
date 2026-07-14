"""Characterization test: the generated report must not change byte-for-byte.

This is the safety net for refactoring html_report.py. It does not assert that
the HTML is *good* — only that it is exactly what it was before the change. Any
diff in the output, down to whitespace, fails the test.

The page metrics are canned (not derived from the images) so the golden hashes
do not depend on the OpenCV/PyMuPDF version doing the diff; everything volatile
(timestamps, temp paths, version) is masked before hashing.

To re-bless the golden after an intentional output change:
    PDFCOMPARE_UPDATE_GOLDEN=1 python -m pytest tests/test_html_report_golden.py
and review the resulting diff in tests/golden/report_hashes.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

from pdfcompare_core.constants import APP_VERSION
from pdfcompare_core.html_report import generate_html_report
from pdfcompare_core.pdf_io import internal_dir
from pdfcompare_core.runner import compare_pdfs

GOLDEN_PATH = Path(__file__).parent / "golden" / "report_hashes.json"

TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
# PyMuPDF does not write byte-identical files for identical input (embedded
# dates / object ids shift the length), so the fixture's size is an input from
# the environment, not report logic. report.json echoes it — mask it.
SIZE_BYTES_RE = re.compile(r'"size_bytes":\s*\d+')

# Fixed stand-ins for every metric the diff engine would otherwise compute, so a
# different OpenCV build cannot shift a single digit in the HTML.
CANNED_METRICS: dict[str, object] = {
    "diff_percent": 1.25,
    "change_level": "moderate",
    "bboxes_count": 3,
    "excluded_regions_count": 1,
    "effective_dpi": 100.0,
    "stroke_tol_px": 2.0,
    "bbox_merge_gap_mm": 0.0,
    "bbox_merge_max_area_ratio": 16.0,
    "ecc_failed": False,
    "width_px": 827,
    "height_px": 1169,
    "pixel_count": 966763,
    "diff_area_px": 12085,
    "diff_area_mm2": 780.5,
    "diff_foreground_percent": 4.5,
    "foreground_px": 268545,
    "added_px": 8000,
    "removed_px": 4085,
    "added_area_mm2": 516.7,
    "removed_area_mm2": 263.8,
    "max_region_area_mm2": 120.4,
    "foreground_sparse": False,
    "elapsed_sec": 1.5,
}


def _make_pdf(path: Path, pages: int, extra: bool) -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.draw_rect(fitz.Rect(50, 50, 400, 300), color=(0, 0, 0), width=2)
        page.insert_text(fitz.Point(70, 350), f"sheet {i + 1}", fontsize=14)
        if extra:
            page.draw_circle(fitz.Point(300, 500), 40, color=(0, 0, 0), width=3)
    doc.save(path)
    doc.close()


def _canned_details(details: list[dict]) -> list[dict]:
    out = []
    for row in details:
        canned = dict(row)
        canned.update(CANNED_METRICS)
        out.append(canned)
    return out


def _normalize(text: str, tmp_root: Path, run_dir: Path) -> str:
    """Strip everything that legitimately differs between two runs."""
    text = TIMESTAMP_RE.sub("<TIMESTAMP>", text)
    text = SIZE_BYTES_RE.sub('"size_bytes": <SIZE>', text)
    for path in (run_dir, tmp_root):
        for variant in (str(path), str(path).replace("\\", "/"), str(path).replace("\\", "\\\\")):
            text = text.replace(variant, "<PATH>")
    return text.replace(APP_VERSION, "<VERSION>")


def _hash_report(run_dir: Path, tmp_root: Path) -> dict[str, str]:
    bundle = internal_dir(run_dir) / "report"
    # nav-data.js is the shared sheet list every page renders from (PDF-008): it is
    # report output like any other, so it is pinned like any other.
    targets = (
        sorted(bundle.rglob("*.html"))
        + sorted(bundle.rglob("*.json"))
        + sorted(bundle.rglob("*.js"))
        + [run_dir / "start.html"]
    )
    digests = {}
    for path in targets:
        if not path.exists():
            continue
        text = _normalize(path.read_text(encoding="utf-8"), tmp_root, run_dir)
        key = str(path.relative_to(run_dir)).replace("\\", "/")
        digests[key] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digests


class HtmlReportGoldenTests(unittest.TestCase):
    def _render(self, tmp: Path, lang: str) -> dict[str, str]:
        _make_pdf(tmp / "a.pdf", pages=2, extra=False)
        _make_pdf(tmp / "b.pdf", pages=2, extra=True)
        run_dir = compare_pdfs(tmp / "a.pdf", tmp / "b.pdf", tmp / "runs", high_dpi=72, run_name=f"golden_{lang}")

        summary = json.loads((internal_dir(run_dir) / "summary.json").read_text(encoding="utf-8"))
        details = _canned_details(list(summary["pairs"]))

        generate_html_report(
            run_dir,
            tmp / "a.pdf",
            tmp / "b.pdf",
            details,
            high_dpi=100,
            stroke_tol_px=2.0,
            report_lang=lang,
        )
        return _hash_report(run_dir, tmp)

    def test_report_generation_is_deterministic(self) -> None:
        # Guards the guard: if the output is not reproducible run-to-run, a golden
        # mismatch would mean nothing. This must fail loudly rather than making
        # test_report_output_is_unchanged flaky.
        for lang in ("ru", "en"):
            with TemporaryDirectory() as tmp:
                first = self._render(Path(tmp), lang)
            with TemporaryDirectory() as tmp:
                second = self._render(Path(tmp), lang)
            self.assertEqual(first, second, f"{lang}: report generation is not deterministic")

    def test_report_output_is_unchanged(self) -> None:
        produced = {}
        for lang in ("ru", "en"):
            with TemporaryDirectory() as tmp:
                produced[lang] = self._render(Path(tmp), lang)

        # Sanity: the report must actually consist of several files, or the test
        # would happily pass on an empty bundle.
        for lang, digests in produced.items():
            self.assertGreaterEqual(len(digests), 4, f"{lang}: too few report files: {sorted(digests)}")
            self.assertIn("start.html", digests)

        if os.getenv("PDFCOMPARE_UPDATE_GOLDEN") == "1":
            GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN_PATH.write_text(json.dumps(produced, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            self.skipTest(f"golden re-blessed: {GOLDEN_PATH}")

        self.assertTrue(GOLDEN_PATH.exists(), f"missing golden file: {GOLDEN_PATH}")
        expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        for lang in ("ru", "en"):
            self.assertEqual(
                produced[lang],
                expected[lang],
                f"{lang}: report output changed. If this was intentional, re-bless with "
                f"PDFCOMPARE_UPDATE_GOLDEN=1 and review the diff.",
            )


if __name__ == "__main__":
    unittest.main()
