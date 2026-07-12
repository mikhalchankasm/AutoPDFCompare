"""Tests for GUI file-dialog helpers (no Tk display required).

_dialog_initialdir builds the initialdir kwarg for Выбрать… dialogs so they
open at the folder already written in the field instead of the OS's
last-used location.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pdfcompare_gui import PDFCompareApp


class DialogInitialdirTests(unittest.TestCase):
    def call(self, *candidates: str) -> str | None:
        # The helper touches no Tk state, so it can run without a root window.
        return PDFCompareApp._dialog_initialdir(None, *candidates)  # type: ignore[arg-type]

    def test_file_path_yields_its_parent(self) -> None:
        with TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "drawing.pdf"
            pdf.write_bytes(b"")
            self.assertEqual(self.call(str(pdf)), str(Path(tmp)))

    def test_directory_path_yields_itself(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertEqual(self.call(tmp), str(Path(tmp)))

    def test_missing_file_still_yields_existing_parent(self) -> None:
        # Field points at a not-yet-existing file inside an existing folder.
        with TemporaryDirectory() as tmp:
            self.assertEqual(self.call(str(Path(tmp) / "missing.pdf")), str(Path(tmp)))

    def test_first_existing_candidate_wins(self) -> None:
        with TemporaryDirectory() as tmp:
            bogus = r"Z:\no\such\folder\file.pdf"
            self.assertEqual(self.call(bogus, tmp), str(Path(tmp)))

    def test_empty_and_invalid_yield_none(self) -> None:
        self.assertIsNone(self.call("", "   "))
        self.assertIsNone(self.call(r"Z:\no\such\folder\file.pdf"))


if __name__ == "__main__":
    unittest.main()
