from __future__ import annotations

import unittest
from unittest import mock
from pathlib import Path

import fitz

from compare_pdfs import (
    MAX_RUN_FOLDER_NAME_LEN,
    _page_value_to_idx,
    build_run_dir,
    compare_pdfs,
    regenerate_report_pages_mixed,
    sanitize_run_folder_name,
)


class RunNameTests(unittest.TestCase):
    def test_sanitizes_named_run_folder(self) -> None:
        self.assertEqual(sanitize_run_folder_name(" LT3 C10 vs C11 "), "LT3_C10_vs_C11")

    def test_rejects_path_like_names(self) -> None:
        for raw_name in ("../escape", r"..\escape", "a/b", r"a\b", "C:\\abs", r"\\server\share"):
            with self.subTest(raw_name=raw_name):
                with self.assertRaises(ValueError):
                    sanitize_run_folder_name(raw_name)

    def test_rejects_reserved_windows_names(self) -> None:
        for raw_name in ("CON", "nul", "LPT1"):
            with self.subTest(raw_name=raw_name):
                with self.assertRaises(ValueError):
                    sanitize_run_folder_name(raw_name)

    def test_rejects_trailing_dot(self) -> None:
        with self.assertRaises(ValueError):
            sanitize_run_folder_name("name.")

    def test_rejects_overlong_run_name(self) -> None:
        with self.assertRaises(ValueError):
            sanitize_run_folder_name("x" * (MAX_RUN_FOLDER_NAME_LEN + 1))

    def test_allows_max_length_run_name(self) -> None:
        self.assertEqual(sanitize_run_folder_name("x" * MAX_RUN_FOLDER_NAME_LEN), "x" * MAX_RUN_FOLDER_NAME_LEN)

    def test_rejects_empty_run_name(self) -> None:
        with self.assertRaises(ValueError):
            sanitize_run_folder_name(" :: ")

    def test_build_run_dir_uses_run_name_inside_out_dir(self) -> None:
        self.assertEqual(build_run_dir(Path("runs"), "ru", "A B"), Path("runs") / "A_B")

    def test_page_value_to_idx_accepts_json_float_strings(self) -> None:
        self.assertEqual(_page_value_to_idx("3.0"), 2)
        self.assertEqual(_page_value_to_idx(3.0), 2)

    def test_page_value_to_idx_rejects_fractional_values(self) -> None:
        self.assertIsNone(_page_value_to_idx("3.9"))

    def test_regenerate_report_pages_mixed_updates_existing_report(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "old.pdf"
            new = root / "new.pdf"
            for path, draw_change in ((old, False), (new, True)):
                doc = fitz.open()
                page = doc.new_page(width=180, height=120)
                page.insert_text((20, 30), "A-100", fontsize=10)
                if draw_change:
                    page.draw_rect(fitz.Rect(80, 50, 105, 75), color=(0, 0, 0), fill=(0, 0, 0))
                doc.save(path)
                doc.close()

            run_dir = compare_pdfs(old, new, root, high_dpi=72, run_name="base", workers=1)
            regenerate_report_pages_mixed(
                run_dir,
                [{"seq": 1, "dpi": 144, "stroke_tol": 0, "diff_strictness": "strict", "bbox_merge_gap_mm": 5}],
                workers=1,
            )

            summary = json.loads((run_dir / "_pdfcompare" / "summary.json").read_text(encoding="utf-8"))
            row = summary["pairs"][0]
            self.assertEqual(row["high_dpi"], 144)
            self.assertEqual(row["diff_strictness"], "strict")
            self.assertEqual(row["bbox_merge_gap_mm"], 5.0)
            self.assertIn("mixed_page_settings", summary)
            self.assertTrue(summary["is_mixed_precision"])
            self.assertEqual(summary["mixed_precision_seqs"], [1])
            self.assertTrue((run_dir / "start.html").exists())
            report_json = json.loads((run_dir / "_pdfcompare" / "report" / "report.json").read_text(encoding="utf-8"))
            self.assertTrue(report_json["settings"]["is_mixed_precision"])
            self.assertEqual(report_json["settings"]["mixed_precision_seqs"], [1])
            index_html = (run_dir / "_pdfcompare" / "report" / "index.html").read_text(encoding="utf-8")
            detail_html = (run_dir / "_pdfcompare" / "report" / "views" / "001.html").read_text(encoding="utf-8")
            self.assertIn("Custom precision", index_html)
            self.assertIn("Пересчитан", index_html)
            self.assertIn("DPI 144", detail_html)
            self.assertIn("смешанная точность", index_html)

    def test_regenerate_report_pages_mixed_does_not_destroy_live_pages_on_task_error(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "old.pdf"
            new = root / "new.pdf"
            for path, draw_change in ((old, False), (new, True)):
                doc = fitz.open()
                page = doc.new_page(width=180, height=120)
                page.insert_text((20, 30), "A-100", fontsize=10)
                if draw_change:
                    page.draw_rect(fitz.Rect(80, 50, 105, 75), color=(0, 0, 0), fill=(0, 0, 0))
                doc.save(path)
                doc.close()

            run_dir = compare_pdfs(old, new, root, high_dpi=72, run_name="base", workers=1)
            summary_path = run_dir / "_pdfcompare" / "summary.json"
            before_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            pair_dir = run_dir / "_pdfcompare" / "pages" / before_summary["pairs"][0]["pair_dir"]
            self.assertTrue((pair_dir / "a.png").exists())

            with mock.patch("pdfcompare_core.runner.process_pair_task", side_effect=RuntimeError("synthetic render failure")):
                with self.assertRaisesRegex(RuntimeError, "synthetic render failure"):
                    regenerate_report_pages_mixed(run_dir, [{"seq": 1, "dpi": 144}], workers=1)

            after_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(after_summary["pairs"][0]["high_dpi"], before_summary["pairs"][0]["high_dpi"])
            self.assertTrue((pair_dir / "a.png").exists())
            self.assertTrue((pair_dir / "b.png").exists())
            self.assertFalse(list((run_dir / "_pdfcompare").glob(".rerender_*")))


if __name__ == "__main__":
    unittest.main()
