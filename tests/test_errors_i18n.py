"""Errors a user can trigger must speak the interface's language.

The engine used to raise Russian-only text, which the English UI showed as-is.
"""

from __future__ import annotations

import unittest

from pdfcompare_core.errors import ERROR_MESSAGES, InvalidInput, RunFailed, localize_error
from pdfcompare_core.exclusions import normalize_exclude_regions
from pdfcompare_core.runner import sanitize_run_folder_name, validate_render_dpi


class ErrorCatalogueTests(unittest.TestCase):
    def test_every_message_exists_in_both_languages(self) -> None:
        self.assertEqual(set(ERROR_MESSAGES["ru"]), set(ERROR_MESSAGES["en"]))
        self.assertNotEqual(ERROR_MESSAGES["ru"], ERROR_MESSAGES["en"])

    def test_no_message_is_left_untranslated(self) -> None:
        # A copy-pasted Russian string in the English table is the failure this
        # guards against.
        cyrillic = [key for key, text in ERROR_MESSAGES["en"].items() if any("а" <= ch.lower() <= "я" for ch in text)]
        self.assertEqual(cyrillic, [], f"Russian text left in the English catalogue: {cyrillic}")

    def test_placeholders_match_between_languages(self) -> None:
        import re

        fields = re.compile(r"\{(\w+)")
        for key, ru in ERROR_MESSAGES["ru"].items():
            en = ERROR_MESSAGES["en"][key]
            self.assertEqual(set(fields.findall(ru)), set(fields.findall(en)), f"{key}: placeholders differ")


class RaisedErrorTests(unittest.TestCase):
    def test_dpi_error_is_localized_and_keeps_its_type(self) -> None:
        with self.assertRaises(ValueError) as ctx:  # callers catch ValueError
            validate_render_dpi(5)
        exc = ctx.exception
        self.assertIsInstance(exc, InvalidInput)
        self.assertIn("DPI должен быть в диапазоне", localize_error(exc, "ru"))
        self.assertIn("DPI must be between", localize_error(exc, "en"))
        self.assertIn("72", localize_error(exc, "en"))

    def test_zone_error_is_localized(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            normalize_exclude_regions([{"x": 0, "y": 0, "w": 10, "h": 10, "unit": "cm"}])
        self.assertIn("неизвестная единица", localize_error(ctx.exception, "ru"))
        self.assertIn("unknown unit", localize_error(ctx.exception, "en"))

    def test_run_name_error_is_localized(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            sanitize_run_folder_name("   ")
        self.assertIn("не может быть пустым", localize_error(ctx.exception, "ru"))
        self.assertIn("cannot be empty", localize_error(ctx.exception, "en"))

    def test_str_stays_russian_for_logs(self) -> None:
        # Anything that just logs str(exc) behaves as before.
        exc = RunFailed("summary_missing", path="C:/runs/x/summary.json")
        self.assertIn("Не найден summary.json", str(exc))
        self.assertIn("C:/runs/x/summary.json", str(exc))

    def test_foreign_errors_pass_through(self) -> None:
        self.assertEqual(localize_error(OSError("disk is on fire"), "en"), "disk is on fire")


if __name__ == "__main__":
    unittest.main()
