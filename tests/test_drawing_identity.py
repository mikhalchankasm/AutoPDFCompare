from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

import fitz
import numpy as np

from pdfcompare_core.alignment import build_similarity_matrices
from pdfcompare_core.models import PageInfo
from pdfcompare_core.pdf_io import extract_drawing_id
from pdfcompare_core.runner import compare_pdfs
from pdfcompare_core.pdf_io import find_summary_json_path
import json


class DrawingIdentityTests(unittest.TestCase):
    def test_changed_paper_format_retains_identity_and_unstretched_source_rasters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name,width in (('old',1050),('new',1575)):
                with fitz.open() as doc:
                    page = doc.new_page(width=width,height=700)
                    page.insert_text((50,100),' '.join(f'word{i}' for i in range(35)))
                    page.insert_text((width-500,650),'EXAMPLE-NAG-DDD-12345-14-KM4-DWG-00031')
                    doc.save(root/f'{name}.pdf')
            run = compare_pdfs(root/'old.pdf',root/'new.pdf',root/'runs',high_dpi=72,workers=1)
            row = json.loads(find_summary_json_path(run).read_text(encoding='utf-8'))['pairs'][0]
            self.assertEqual(row['status'],'size_mismatch')
            self.assertEqual(row['drawing_id'],'EXAMPLE-NAG-DDD-12345-14-KM4-DWG-00031')
            self.assertEqual((row['a_page'],row['b_page']),(1,1))
            self.assertEqual(row['effective_dpi'],72)
    def test_title_block_code_ignores_references_and_revision_filename(self) -> None:
        with fitz.open() as doc:
            page = doc.new_page(width=2400, height=1680)
            page.insert_text((100, 100), "EXAMPLE-NAG-DDD-12345-14-KM4-DWG-00001")
            page.insert_text((1900, 1620), "EXAMPLE-NAG-DDD-12345-14-KM4-DWG-00031")
            page.insert_text((1900, 1640), "EXAMPLE-NAG-DDD-12345-14-KM4-DWG-00031-02.dwg")
            self.assertEqual(extract_drawing_id(page), "EXAMPLE-NAG-DDD-12345-14-KM4-DWG-00031")
            page.insert_text((1900, 1600), "EXAMPLE-NAG-DDD-12345-14-KM4-DWG-00032")
            self.assertIsNone(extract_drawing_id(page))

    def test_unique_identity_accepts_changed_aspect_but_not_duplicates_or_unrelated(self) -> None:
        tokens = {f"word{x}" for x in range(30)}

        def info(width: int, identity: str | None) -> PageInfo:
            return PageInfo(0, np.zeros((160, 160), np.float32), tokens, width, 100, None, identity)

        a, b = info(140, "drawing"), info(210, "drawing")
        scores, compatible = build_similarity_matrices([a], [b])
        self.assertTrue(compatible[0, 0])
        self.assertGreaterEqual(scores[0, 0], 0.95)
        self.assertFalse(build_similarity_matrices([a, a], [b])[1].any())
        self.assertFalse(build_similarity_matrices([a], [info(210, "different")])[1].any())
        b.text_tokens = {"unrelated"}
        self.assertFalse(build_similarity_matrices([a], [b])[1].any())
