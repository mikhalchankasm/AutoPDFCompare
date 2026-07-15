"""Run-folder names built from the two PDF file names."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pdfcompare_core.run_names import (
    available_folder_name,
    compact_name,
    extract_revision,
    suggest_folder_names,
    suggest_run_folder_name,
)


class ExtractRevisionTests(unittest.TestCase):
    def test_marker_keeps_its_prefix(self) -> None:
        # "plan_1_vs_2" would read like a page range; "plan_R1_vs_R2" says what it is.
        self.assertEqual(extract_revision("Проект_рев5"), "РЕВ5")
        self.assertEqual(extract_revision("plan_rev_12"), "REV12")
        self.assertEqual(extract_revision("plan_r1"), "R1")

    def test_no_marker(self) -> None:
        self.assertIsNone(extract_revision("plan"))


class SuggestRunFolderNameTests(unittest.TestCase):
    def test_shared_part_is_kept_once(self) -> None:
        name = suggest_run_folder_name(Path("/x/Проект_рев5.pdf"), Path("/x/Проект_рев6.pdf"))
        self.assertEqual(name, "Проект_РЕВ5_vs_РЕВ6")

    def test_revision_word_is_not_repeated(self) -> None:
        name = suggest_run_folder_name(Path("/x/Проект_Ревизия 5.pdf"), Path("/x/Проект_Ревизия 6.pdf"))
        self.assertEqual(name, "Проект_РЕВИЗИЯ5_vs_РЕВИЗИЯ6")

    def test_falls_back_to_both_names(self) -> None:
        name = suggest_run_folder_name(Path("/x/alpha.pdf"), Path("/x/beta.pdf"))
        self.assertEqual(name, "alpha_vs_beta")

    def test_same_stem_in_different_folders(self) -> None:
        name = suggest_run_folder_name(Path("/old/plan.pdf"), Path("/new/plan.pdf"))
        self.assertEqual(name, "plan_old_vs_new")

    def test_spaces_become_underscores(self) -> None:
        name = suggest_run_folder_name(Path("/x/Схема 1 rev2.pdf"), Path("/x/Схема 1 rev3.pdf"))
        self.assertEqual(name, "Схема_1_REV2_vs_REV3")

    def test_result_is_a_usable_folder_name(self) -> None:
        name = suggest_run_folder_name(Path("/x/" + "a" * 90 + "_r1.pdf"), Path("/x/" + "a" * 90 + "_r2.pdf"))
        self.assertLessEqual(len(name), 80)
        self.assertEqual(Path(name).name, name)


class AvailableFolderNameTests(unittest.TestCase):
    def test_suffixes_until_free(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plan_vs_plan2").mkdir()
            self.assertEqual(available_folder_name(root, "plan_vs_plan2"), "plan_vs_plan2_2")
            (root / "plan_vs_plan2_2").mkdir()
            self.assertEqual(available_folder_name(root, "plan_vs_plan2"), "plan_vs_plan2_3")

    def test_free_name_is_returned_as_is(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertEqual(available_folder_name(Path(tmp), "Ревизия 5"), "Ревизия_5")


class CompactNameTests(unittest.TestCase):
    def test_empty_falls_back(self) -> None:
        self.assertEqual(compact_name("   "), "Comparison")

    def test_truncates_and_trims(self) -> None:
        self.assertEqual(compact_name("abcdefgh", max_len=4), "abcd")


class SuggestFolderNamesTests(unittest.TestCase):
    def test_offers_unique_options(self) -> None:
        with TemporaryDirectory() as tmp:
            suggestions = suggest_folder_names(Path("/x/plan_r1.pdf"), Path("/x/plan_r2.pdf"), Path(tmp))
            names = [s["name"] for s in suggestions]
            self.assertTrue(names)
            self.assertEqual(len(names), len(set(names)))
            self.assertTrue(all(s["reason"] for s in suggestions))
            self.assertIn("plan_R1_vs_R2", names)
            self.assertIn("plan_old_vs_new", names)


if __name__ == "__main__":
    unittest.main()
