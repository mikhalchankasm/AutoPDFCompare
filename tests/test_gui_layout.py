"""Characterization test: the built widget tree must not change.

Safety net for refactoring PDFCompareApp._build_ui, which is a ~500-line method
that constructs the whole window. There is no output artifact to hash, so the
snapshot *is* the widget tree: every widget's position in the hierarchy, its Tk
class, its geometry manager and the options that are visible to the user.

The app reads its saved state from the user's home directory, so HOME is
redirected to a temp dir — the snapshot describes a first-run window, not
whatever the developer last had on screen.

To re-bless after an intentional UI change:
    PDFCOMPARE_UPDATE_GOLDEN=1 python -m pytest tests/test_gui_layout.py
and review the diff in tests/golden/gui_layout.json.
"""

from __future__ import annotations

import json
import os
import re
import tkinter as tk
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

GOLDEN_PATH = Path(__file__).parent / "golden" / "gui_layout.json"

# Options worth pinning: what the user sees and what wiring depends on. Fonts,
# colors and paddings are style choices that churn — they are deliberately out.
TRACKED_OPTIONS = ("text", "style", "state", "orient", "mode", "maximum", "width", "cursor")

# Tk names its variables from a process-wide counter (PY_VAR3, PY_VAR40, ...),
# so the exact number says nothing about the layout.
TK_VAR_RE = re.compile(r"PY_VAR\d+")


def _describe(widget: tk.Misc, path: str) -> list[dict]:
    rows = []
    for child in widget.winfo_children():
        name = child.winfo_name()
        child_path = f"{path}/{name}"
        row: dict = {
            "path": child_path,
            "class": child.winfo_class(),
            "manager": child.winfo_manager(),
        }
        for opt in TRACKED_OPTIONS:
            try:
                value = child.cget(opt)
            except (tk.TclError, AttributeError):
                continue
            if value not in ("", None):
                row[opt] = TK_VAR_RE.sub("PY_VAR", str(value))
        rows.append(row)
        rows.extend(_describe(child, child_path))
    return rows


class GuiLayoutGoldenTests(unittest.TestCase):
    def _snapshot(self) -> list[dict]:
        from pdfcompare_gui import PDFCompareApp

        with TemporaryDirectory() as home:
            # First-run state: no saved inputs, no history, default language.
            with mock.patch.object(Path, "home", return_value=Path(home)):
                root = tk.Tk()
                root.withdraw()
                try:
                    PDFCompareApp(root)
                    root.update_idletasks()
                    return _describe(root, "")
                finally:
                    root.destroy()

    def setUp(self) -> None:
        try:
            probe = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - depends on the runner
            pytest.skip(f"no Tk display: {exc}")
        probe.destroy()

    def test_widget_tree_is_deterministic(self) -> None:
        self.assertEqual(self._snapshot(), self._snapshot(), "the widget tree is not built deterministically")

    def test_widget_tree_is_unchanged(self) -> None:
        produced = self._snapshot()
        self.assertGreater(len(produced), 50, "suspiciously small widget tree")

        if os.getenv("PDFCOMPARE_UPDATE_GOLDEN") == "1":
            GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN_PATH.write_text(json.dumps(produced, ensure_ascii=False, indent=2), encoding="utf-8")
            self.skipTest(f"golden re-blessed: {GOLDEN_PATH}")

        self.assertTrue(GOLDEN_PATH.exists(), f"missing golden file: {GOLDEN_PATH}")
        expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            produced,
            expected,
            "the widget tree changed. If this was intentional, re-bless with "
            "PDFCOMPARE_UPDATE_GOLDEN=1 and review the diff.",
        )


if __name__ == "__main__":
    unittest.main()
