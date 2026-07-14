"""User-facing errors must speak the user's language at every boundary, not just the GUI.

v0.1.19 gave the engine a bilingual error catalogue, but only the GUI called
`localize_error()`. `compare_pdfs.py --lang en --dpi 5` and an MCP tool called with
`lang="en"` both still answered in Russian (RECHECK-002) — the English workflows
were English right up to the moment something went wrong.

`str(exc)` stays Russian on purpose: worker tracebacks and `worker.log` are matched
against it. The translation happens at the boundary, and the Russian original is
carried alongside it as `error_detail`.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from pdfcompare_core.errors import InvalidInput, RunFailed, localize_error

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    # Without PYTHONIOENCODING the child writes its Russian error in the Windows
    # console code page, and reading it back as UTF-8 is what fails — not the CLI.
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "compare_pdfs.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        cwd=REPO_ROOT,
        timeout=120,
    )


class CliErrorLanguageTests(unittest.TestCase):
    def test_english_run_reports_a_bad_dpi_in_english(self) -> None:
        result = run_cli("--lang", "en", "--dpi", "5")
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("DPI must be between", output)
        self.assertNotIn("DPI должен быть", output)

    def test_russian_run_still_reports_a_bad_dpi_in_russian(self) -> None:
        result = run_cli("--lang", "ru", "--dpi", "5")
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("DPI должен быть в диапазоне", output)

    def test_english_run_reports_a_bad_zone_in_english(self) -> None:
        # A RunFailed/InvalidInput raised deeper than argparse still gets translated.
        result = run_cli("--lang", "en", "--exclude-region", "10,10,10")
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("expected x,y,w,h in percent", output)


class McpErrorLanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        pytest.importorskip("mcp")
        self.mcp = importlib.import_module("scripts.pdfcompare_mcp")
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def _pdf(self, name: str) -> Path:
        import fitz

        path = self.tmp / name
        doc = fitz.open()
        doc.new_page()
        doc.save(path)
        doc.close()
        return path

    def test_start_reports_a_bad_dpi_in_the_requested_language(self) -> None:
        old, new = self._pdf("a.pdf"), self._pdf("b.pdf")
        english = self.mcp.start_pdf_comparison(
            str(old), str(new), str(self.tmp / "runs"), "run_en", dpi=5, lang="en"
        )
        self.assertFalse(english["ok"])
        self.assertIn("DPI must be between", english["error"])
        self.assertEqual(english["error_key"], "dpi_out_of_range")
        # The Russian original stays for the log, next to the translated message.
        self.assertIn("DPI должен быть", english["error_detail"])

        russian = self.mcp.start_pdf_comparison(
            str(old), str(new), str(self.tmp / "runs"), "run_ru", dpi=5, lang="ru"
        )
        self.assertFalse(russian["ok"])
        self.assertIn("DPI должен быть в диапазоне", russian["error"])
        self.assertNotIn("error_detail", russian, "an untranslated error must not be duplicated")

    def test_start_reports_a_bad_strictness_in_the_requested_language(self) -> None:
        old, new = self._pdf("a.pdf"), self._pdf("b.pdf")
        result = self.mcp.start_pdf_comparison(
            str(old), str(new), str(self.tmp / "runs"), "run", diff_strictness="nope", lang="en"
        )
        self.assertFalse(result["ok"])
        self.assertIn("Invalid diff strictness", result["error"])

    def test_rerender_reports_a_missing_report_in_the_requested_language(self) -> None:
        empty = self.tmp / "not_a_report"
        empty.mkdir()
        english = self.mcp.rerender_pdf_comparison_pages(str(empty), seqs=[1], lang="en")
        self.assertFalse(english["ok"])
        self.assertIn("summary.json not found", english["error"])

        russian = self.mcp.rerender_pdf_comparison_pages(str(empty), seqs=[1], lang="ru")
        self.assertIn("Не найден summary.json", russian["error"])

    def test_rerender_reports_a_bad_dpi_in_the_requested_language(self) -> None:
        empty = self.tmp / "report"
        empty.mkdir()
        result = self.mcp.rerender_pdf_comparison_pages(str(empty), seqs=[1], dpi=5, lang="en")
        self.assertFalse(result["ok"])
        self.assertIn("DPI must be between", result["error"])

    def test_a_missing_path_is_reported_in_the_requested_language(self) -> None:
        result = self.mcp.prepare_pdf_comparison(str(self.tmp / "nope.pdf"), str(self.tmp / "nope2.pdf"), lang="en")
        self.assertFalse(result["ok"])
        self.assertIn("Path not found", result["error"])

    def test_an_unknown_exception_passes_through_untranslated(self) -> None:
        # Not our error: no key, no invented translation, just the original text.
        boom = RuntimeError("disk on fire")
        payload = self.mcp.error_result(boom, "en")
        self.assertEqual(payload["error"], "disk on fire")
        self.assertNotIn("error_key", payload)
        self.assertNotIn("error_detail", payload)

    def test_an_internal_invariant_is_not_translated(self) -> None:
        # Internal invariants are deliberately absent from the catalogue: they mean
        # the program is broken, not that the user did something wrong.
        payload = self.mcp.error_result(AssertionError("staging dir not built"), "en")
        self.assertEqual(payload["error"], "staging dir not built")


class LocalizeErrorTests(unittest.TestCase):
    def test_our_errors_translate_and_keep_a_russian_str(self) -> None:
        exc = InvalidInput("dpi_out_of_range", min=72, max=900, value=5)
        self.assertIn("DPI должен быть", str(exc))
        self.assertIn("DPI must be between", localize_error(exc, "en"))
        self.assertIn("DPI должен быть", localize_error(exc, "ru"))

    def test_an_unknown_language_falls_back_to_russian(self) -> None:
        exc = RunFailed("job_not_found", job_id="x")
        self.assertIn("Задача не найдена", localize_error(exc, "de"))

    def test_foreign_exceptions_are_returned_verbatim(self) -> None:
        self.assertEqual(localize_error(OSError("locked"), "en"), "locked")


class WorkerErrorLanguageTests(unittest.TestCase):
    """The worker's status is what an agent reads; its traceback is what a human reads."""

    def test_status_carries_the_translated_message_and_the_russian_detail(self) -> None:
        with TemporaryDirectory() as tmp:
            job = Path(tmp)
            request = {
                "job_id": "job_en",
                "operation": "rerender",
                "run_dir": str(job / "missing_run"),
                "page_settings": [{"seqs": [1]}],
                "dpi": 250,
                "lang": "en",
            }
            (job / "request.json").write_text(json.dumps(request), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "pdfcompare_worker.py"),
                    "--request", str(job / "request.json"),
                    "--status", str(job / "status.json"),
                    "--events", str(job / "events.jsonl"),
                ],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                timeout=120,
            )
            self.assertEqual(result.returncode, 1)
            status = json.loads((job / "status.json").read_text(encoding="utf-8"))

        self.assertEqual(status["state"], "failed")
        self.assertIn("summary.json not found", status["message"])
        self.assertIn("summary.json not found", status["error"])
        # Diagnostics keep the original Russian text and the full traceback.
        self.assertIn("Не найден summary.json", status["error_detail"])
        self.assertIn("Traceback", status["traceback"])


if __name__ == "__main__":
    unittest.main()
