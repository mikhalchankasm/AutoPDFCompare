"""Contract tests for the assets shared by live and finished slider pages."""

from __future__ import annotations

import inspect
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pdfcompare_core import html_report, live_report
from pdfcompare_core.html_css import CSS_CMP
from pdfcompare_core.html_i18n import HTML_REPORT_I18N
from pdfcompare_core.html_slider import SLIDER_RUNTIME_SOURCE
from pdfcompare_core.pdf_io import find_pages_dir, report_dir


class SliderSharedAssetsTests(unittest.TestCase):
    def test_live_slider_uses_report_i18n_css_and_runtime(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            pages_dir = find_pages_dir(run_dir) / "pair_001"
            pages_dir.mkdir(parents=True)
            (pages_dir / "bboxes.json").write_text(
                json.dumps([{"x": 10, "y": 20, "w": 30, "h": 40}]), encoding="utf-8"
            )
            row = {"seq": 1, "pair_dir": "pair_001", "a_page": 1, "b_page": 1}
            slider_file = live_report.write_live_slider_view(
                run_dir,
                Path("old.pdf"),
                Path("new.pdf"),
                row,
                "en",
                "../../pages/pair_001/a.png",
                "../../pages/pair_001/b.png",
            )
            self.assertEqual(slider_file, "cmp_001.html")
            if slider_file is None:
                self.fail("the live slider should be written when both sources exist")
            live_html = (report_dir(run_dir) / "views" / slider_file).read_text(encoding="utf-8")

        final_source = inspect.getsource(html_report)
        self.assertIn("CSS_CMP", final_source)
        self.assertIn(CSS_CMP, live_html)
        self.assertIn(SLIDER_RUNTIME_SOURCE, live_html)
        for key in (
            "back_to_sheet",
            "back_summary",
            "fit_to_window",
            "slider_zoom",
            "bbox_color",
            "bbox_yellow",
            "bbox_pink",
            "bbox_green",
            "bbox_opacity",
            "slider_load_error",
        ):
            self.assertIn(key, HTML_REPORT_I18N["ru"])
            self.assertIn(key, HTML_REPORT_I18N["en"])

        live_source = inspect.getsource(live_report)
        self.assertNotIn('if lang == "en" else', live_source)


if __name__ == "__main__":
    unittest.main()
