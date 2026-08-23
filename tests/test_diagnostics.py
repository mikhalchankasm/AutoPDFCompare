"""Tests for the desktop diagnostic log lifecycle."""

from __future__ import annotations

import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pdfcompare_ui.diagnostics import close_file_logging, configure_file_logging


class DiagnosticLogTests(unittest.TestCase):
    def test_log_is_written_and_released(self) -> None:
        with TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / ".pdfcompare_local"
            log_path = configure_file_logging(state_dir)
            self.assertEqual(log_path, state_dir / "pdfcompare.log")

            logging.getLogger("pdfcompare.test").error("diagnostic marker")
            close_file_logging()

            assert log_path is not None
            self.assertIn("diagnostic marker", log_path.read_text(encoding="utf-8"))
            log_path.unlink()
            self.assertFalse(log_path.exists())

    def tearDown(self) -> None:
        close_file_logging()


if __name__ == "__main__":
    unittest.main()
