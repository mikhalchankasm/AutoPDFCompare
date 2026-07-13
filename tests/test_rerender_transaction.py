"""Failpoint tests: re-rendering must be transactional.

If writing summary.json or rebuilding the HTML report fails after the new page
rasters were swapped in, the run must be restored to its pre-rerender state —
pages, summary, report bundle and start.html together. Previously the page
backups were deleted right after the swap (leaving the run half-updated), and
the report bundle was published before start.html was written (leaving a new
report behind a rolled-back run).
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import fitz

from pdfcompare_core import html_report, runner
from pdfcompare_core.pdf_io import find_pages_dir, find_summary_json_path, internal_dir, report_dir


def _make_pdf(path: Path, extra: bool) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(fitz.Rect(50, 50, 400, 300), color=(0, 0, 0), width=2)
    if extra:
        page.draw_circle(fitz.Point(300, 500), 40, color=(0, 0, 0), width=3)
    doc.save(path)
    doc.close()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fingerprint(run_dir: Path) -> dict[str, str]:
    """Hash everything a re-render touches: pages, summary, report, start page."""
    pages_dir = find_pages_dir(run_dir)
    bundle = report_dir(run_dir)
    snap = {
        "summary.json": _digest(find_summary_json_path(run_dir)),
        "start.html": _digest(run_dir / "start.html"),
    }
    for png in sorted(pages_dir.rglob("*.png")):
        snap[f"page:{png.relative_to(pages_dir)}"] = _digest(png)
    for item in sorted(bundle.rglob("*")):
        if item.is_file():
            snap[f"report:{item.relative_to(bundle)}"] = _digest(item)
    return snap


class RerenderTransactionTests(unittest.TestCase):
    def _build_run(self, tmp: Path) -> Path:
        _make_pdf(tmp / "a.pdf", extra=False)
        _make_pdf(tmp / "b.pdf", extra=True)
        return runner.compare_pdfs(tmp / "a.pdf", tmp / "b.pdf", tmp / "runs", high_dpi=72, run_name="base")

    def _assert_unchanged(self, run_dir: Path, before: dict[str, str]) -> None:
        self.assertEqual(_fingerprint(run_dir), before)
        for pattern in (".rerender_*", ".report_*", ".start_backup_*"):
            leftovers = list(internal_dir(run_dir).glob(pattern))
            self.assertEqual(leftovers, [], f"leftovers for {pattern}: {leftovers}")

    def test_failure_while_writing_summary_rolls_back_pages(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = self._build_run(Path(tmp))
            before = _fingerprint(run_dir)

            with mock.patch.object(runner, "_write_run_summary_files", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    runner.regenerate_report_pages(run_dir, [1], high_dpi=100, report_lang="ru")

            self._assert_unchanged(run_dir, before)

    def test_failure_while_building_html_rolls_back_everything(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = self._build_run(Path(tmp))
            before = _fingerprint(run_dir)

            with mock.patch.object(runner, "generate_html_report", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    runner.regenerate_report_pages(run_dir, [1], high_dpi=100, report_lang="ru")

            self._assert_unchanged(run_dir, before)

    def test_failure_while_writing_start_page_restores_old_report(self) -> None:
        # The new bundle is fully built and only the last step (start.html) fails:
        # the run must keep the old report, not a new bundle behind a stale entry.
        with TemporaryDirectory() as tmp:
            run_dir = self._build_run(Path(tmp))
            before = _fingerprint(run_dir)

            with mock.patch.object(html_report, "write_start_page", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    runner.regenerate_report_pages(run_dir, [1], high_dpi=100, report_lang="ru")

            self._assert_unchanged(run_dir, before)

    def test_successful_rerender_updates_pages_and_summary_together(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = self._build_run(Path(tmp))
            before = _fingerprint(run_dir)

            runner.regenerate_report_pages(run_dir, [1], high_dpi=100, report_lang="ru")

            payload = json.loads(find_summary_json_path(run_dir).read_text(encoding="utf-8"))
            row = next(r for r in payload["pairs"] if int(r["seq"]) == 1)
            self.assertEqual(int(row["high_dpi"]), 100)
            after = _fingerprint(run_dir)
            self.assertNotEqual(after, before)
            self.assertTrue((run_dir / "start.html").exists())
            self.assertTrue((report_dir(run_dir) / "index.html").exists())
            for pattern in (".rerender_*", ".report_*", ".start_backup_*"):
                self.assertEqual(list(internal_dir(run_dir).glob(pattern)), [])

    def test_failed_restore_keeps_the_last_copy(self) -> None:
        # If rollback cannot put a file back (locked by a viewer, disk error), the
        # staging dir holds the only remaining copy — deleting it would turn a
        # recoverable failure into permanent data loss.
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            staging_root = tmp_path / "staging"
            staging_root.mkdir()
            live = tmp_path / "summary.json"
            live.write_text("OLD", encoding="utf-8")

            txn = runner._RunUpdateTransaction(staging_root)
            txn.preserve_file(live)
            live.write_text("NEW", encoding="utf-8")

            with mock.patch.object(runner.shutil, "copy2", side_effect=OSError("locked")):
                txn.rollback()

            self.assertEqual(txn.unrestored, [live])
            self.assertTrue(staging_root.exists(), "staging was deleted with the only backup inside")
            backups = list(staging_root.rglob("*summary.json"))
            self.assertEqual(len(backups), 1, backups)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "OLD")

    def test_successful_rollback_still_cleans_staging(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            staging_root = tmp_path / "staging"
            staging_root.mkdir()
            live = tmp_path / "summary.json"
            live.write_text("OLD", encoding="utf-8")

            txn = runner._RunUpdateTransaction(staging_root)
            txn.preserve_file(live)
            live.write_text("NEW", encoding="utf-8")
            txn.rollback()

            self.assertEqual(txn.unrestored, [])
            self.assertEqual(live.read_text(encoding="utf-8"), "OLD")
            self.assertFalse(staging_root.exists())

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
