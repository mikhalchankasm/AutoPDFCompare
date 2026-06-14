from __future__ import annotations

import unittest
from pathlib import Path

from compare_pdfs import MAX_RUN_FOLDER_NAME_LEN, _page_value_to_idx, build_run_dir, sanitize_run_folder_name


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


if __name__ == "__main__":
    unittest.main()
