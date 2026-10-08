from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from pdfcompare_core.errors import InvalidInput
from pdfcompare_core.runner import compare_pdfs
from scripts.pdfcompare_mcp import preview_pdf_comparison


class SinglePairTests(unittest.TestCase):
    def test_explicit_pair_bypasses_matching_and_renders_one_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in (("old", "A-100"), ("new", "B-900")):
                with fitz.open() as document:
                    page = document.new_page(width=180, height=120)
                    page.insert_text((20, 30), text)
                    document.save(root / f"{name}.pdf")
            with patch("pdfcompare_core.runner.align_pages_v1", side_effect=AssertionError("automatic matching")):
                run = compare_pdfs(root / "old.pdf", root / "new.pdf", root,
                                   high_dpi=72, workers=1, force_single_pair=True)
            pairs = json.loads((run / "_pdfcompare/summary.json").read_text(encoding="utf-8"))["pairs"]
            self.assertEqual(len(pairs), 1)
            self.assertEqual((pairs[0]["status"], pairs[0]["a_page"], pairs[0]["b_page"]), ("matched", 1, 1))

    def test_core_and_preview_reject_multiple_pages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, count in (("old", 2), ("new", 1)):
                with fitz.open() as document:
                    for _ in range(count):
                        document.new_page(width=180, height=120)
                    document.save(root / f"{name}.pdf")
            preview = preview_pdf_comparison(str(root / "old.pdf"), str(root / "new.pdf"),
                                             str(root), "preview", force_single_pair=True)
            self.assertFalse(preview["ok"])
            with self.assertRaises(InvalidInput):
                compare_pdfs(root / "old.pdf", root / "new.pdf", root,
                             high_dpi=72, workers=1, force_single_pair=True)
