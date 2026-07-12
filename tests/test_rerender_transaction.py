"""Failpoint tests: re-rendering must be transactional.

If writing summary.json or rebuilding the HTML report fails after the new page
rasters were swapped in, the run must be restored to its pre-rerender state —
pages, summary, and CSV together. Previously the page backups were deleted
right after the swap, leaving the run half-updated.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import fitz

from pdfcompare_core import runner
from pdfcompare_core.pdf_io import find_pages_dir, find_summary_json_path, internal_dir


def _make_pdf(path: Path, extra: bool) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(fitz.Rect(50, 50, 400, 300), color=(0, 0, 0), width=2)
    if extra:
        page.draw_circle(fitz.Point(300, 500), 40, color=(0, 0, 0), width=3)
    doc.save(path)
    doc.close()


def _hash_pages(pages_dir: Path) -> dict[str, str]:
    return {
        str(png.relative_to(pages_dir)): hashlib.sha256(png.read_bytes()).hexdigest()
        for png in sorted(pages_dir.rglob("*.png"))
    }


class RerenderTransactionTests(unittest.TestCase):
    def _build_run(self, tmp: Path) -> Path:
        _make_pdf(tmp / "a.pdf", extra=False)
        _make_pdf(tmp / "b.pdf", extra=True)
        return runner.compare_pdfs(tmp / "a.pdf", tmp / "b.pdf", tmp / "runs", high_dpi=72, run_name="base")

    def _assert_unchanged(self, run_dir: Path, summary_before: bytes, hashes_before: dict[str, str]) -> None:
        self.assertEqual(find_summary_json_path(run_dir).read_bytes(), summary_before)
        self.assertEqual(_hash_pages(find_pages_dir(run_dir)), hashes_before)
        leftovers = list(internal_dir(run_dir).glob(".rerender_*"))
        self.assertEqual(leftovers, [], f"staging leftovers: {leftovers}")

    def test_failure_while_writing_summary_rolls_back_pages(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = self._build_run(Path(tmp))
            summary_before = find_summary_json_path(run_dir).read_bytes()
            hashes_before = _hash_pages(find_pages_dir(run_dir))

            with mock.patch.object(runner, "_write_run_summary_files", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    runner.regenerate_report_pages(run_dir, [1], high_dpi=100, report_lang="ru")

            self._assert_unchanged(run_dir, summary_before, hashes_before)

    def test_failure_while_building_html_rolls_back_everything(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = self._build_run(Path(tmp))
            summary_before = find_summary_json_path(run_dir).read_bytes()
            hashes_before = _hash_pages(find_pages_dir(run_dir))

            with mock.patch.object(runner, "generate_html_report", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    runner.regenerate_report_pages(run_dir, [1], high_dpi=100, report_lang="ru")

            self._assert_unchanged(run_dir, summary_before, hashes_before)

    def test_successful_rerender_updates_pages_and_summary_together(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = self._build_run(Path(tmp))
            hashes_before = _hash_pages(find_pages_dir(run_dir))

            runner.regenerate_report_pages(run_dir, [1], high_dpi=100, report_lang="ru")

            payload = json.loads(find_summary_json_path(run_dir).read_text(encoding="utf-8"))
            row = next(r for r in payload["pairs"] if int(r["seq"]) == 1)
            self.assertEqual(int(row["high_dpi"]), 100)
            self.assertNotEqual(_hash_pages(find_pages_dir(run_dir)), hashes_before)
            self.assertEqual(list(internal_dir(run_dir).glob(".rerender_*")), [])

    def test_failed_compare_quarantines_run_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_pdf(tmp_path / "a.pdf", extra=False)
            _make_pdf(tmp_path / "b.pdf", extra=True)
            with mock.patch.object(runner, "align_pages_v1", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    runner.compare_pdfs(tmp_path / "a.pdf", tmp_path / "b.pdf", tmp_path / "runs", high_dpi=72, run_name="named")
            # The original folder name is free again; debris moved aside.
            self.assertFalse((tmp_path / "runs" / "named").exists())
            quarantined = list((tmp_path / "runs").glob("named.failed-*"))
            self.assertEqual(len(quarantined), 1, quarantined)
            # And the same run_name can be used right away.
            run_dir = runner.compare_pdfs(tmp_path / "a.pdf", tmp_path / "b.pdf", tmp_path / "runs", high_dpi=72, run_name="named")
            self.assertTrue((run_dir / "start.html").exists())


if __name__ == "__main__":
    unittest.main()
