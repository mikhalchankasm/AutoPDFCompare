"""Unit tests for pdfcompare_ui.utils pure helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from pdfcompare_ui.utils import (
    count_pdf_pages_pair,
    extract_revision_label,
    format_duration_mmss,
)


class FormatDurationTests(unittest.TestCase):
    def test_zero_seconds(self) -> None:
        self.assertEqual(format_duration_mmss(0), "00:00")

    def test_under_one_minute(self) -> None:
        self.assertEqual(format_duration_mmss(42), "00:42")

    def test_exact_minute(self) -> None:
        self.assertEqual(format_duration_mmss(60), "01:00")

    def test_multi_minute(self) -> None:
        self.assertEqual(format_duration_mmss(125), "02:05")

    def test_fractional_seconds_floor(self) -> None:
        self.assertEqual(format_duration_mmss(75.9), "01:15")


class ExtractRevisionTests(unittest.TestCase):
    def test_matches_rC_two_digits(self) -> None:
        self.assertEqual(extract_revision_label("/x/foo_rC03.pdf"), "v.C03")

    def test_matches_rC_three_digits(self) -> None:
        self.assertEqual(extract_revision_label("foo_rC123.pdf"), "v.C123")

    def test_lowercase_rc(self) -> None:
        self.assertEqual(extract_revision_label("bar_rc09_draft.pdf"), "v.C09")

    def test_no_match_returns_empty(self) -> None:
        self.assertEqual(extract_revision_label("plain_filename.pdf"), "")

    def test_uses_basename_only(self) -> None:
        # The directory name should NOT bleed into the result.
        self.assertEqual(extract_revision_label("/some/rC99/foo.pdf"), "")


class CountPdfPagesPairTests(unittest.TestCase):
    @staticmethod
    def _write_pdf(path: Path, pages: int) -> None:
        doc = fitz.open()
        for _ in range(pages):
            doc.new_page(width=120, height=80)
        doc.save(path)
        doc.close()

    def test_returns_old_over_new(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "old.pdf"
            new = Path(tmp) / "new.pdf"
            self._write_pdf(old, 3)
            self._write_pdf(new, 5)
            self.assertEqual(count_pdf_pages_pair(old, new), "3/5")

    def test_missing_files_yield_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                count_pdf_pages_pair(Path(tmp) / "absent_a.pdf", Path(tmp) / "absent_b.pdf"),
                "0/0",
            )


if __name__ == "__main__":
    unittest.main()
