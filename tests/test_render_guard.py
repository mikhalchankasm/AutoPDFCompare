"""Tests for the render megapixel guard and diff engine memory handling.

These verify that the megapixel cap is applied BEFORE get_pixmap (so the huge
raster is never allocated), that physical metrics use the effective DPI, and
that the diff engine still produces correct results after the
distanceTransform buffer-release refactor.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

import numpy as np

from pdfcompare_core import pdf_io
from pdfcompare_core.constants import MAX_RENDER_MEGAPIXELS
from pdfcompare_core.diff_engine import compute_diff


class FakePixmap:
    """Stand-in for fitz.Pixmap with a configurable raster."""

    def __init__(self, width: int, height: int, channels: int = 3) -> None:
        self.width = width
        self.height = height
        self.n = channels
        rng = np.random.default_rng(0)
        self.samples = rng.integers(0, 255, size=(height, width, channels), dtype=np.uint8).tobytes()


class FakePage:
    """Renders a pixmap whose size follows the requested zoom, like fitz does."""

    def __init__(self, width_pt: float, height_pt: float) -> None:
        self.rect = SimpleNamespace(width=width_pt, height=height_pt)
        self.rendered_zooms: list[float] = []

    def get_pixmap(self, matrix: tuple[float, float], **_kwargs: object) -> FakePixmap:
        zoom = float(matrix[0])
        self.rendered_zooms.append(zoom)
        return FakePixmap(max(1, int(self.rect.width * zoom)), max(1, int(self.rect.height * zoom)))


class FakeDoc:
    def __init__(self, page: FakePage) -> None:
        self._page = page

    def __getitem__(self, _index: int) -> FakePage:
        return self._page


def _mock_fitz() -> mock.MagicMock:
    m = mock.MagicMock()
    m.Matrix.side_effect = lambda zx, zy: (zx, zy)
    m.csRGB = object()
    m.csGRAY = object()
    return m


class RenderMegapixelGuardTests(unittest.TestCase):
    def test_capped_render_dpi_reduces_a0_at_high_dpi(self) -> None:
        # A0 portrait is 2384x3370 pt; at 250 DPI that's ~97 MP > cap.
        page = FakePage(2384, 3370)
        eff = pdf_io.capped_render_dpi(page, 250)
        self.assertLess(eff, 250)
        w_px = page.rect.width * eff / 72.0
        h_px = page.rect.height * eff / 72.0
        self.assertLessEqual(w_px * h_px / 1e6, MAX_RENDER_MEGAPIXELS + 0.01)

    def test_capped_render_dpi_keeps_small_pages(self) -> None:
        page = FakePage(595, 842)  # A4
        self.assertEqual(pdf_io.capped_render_dpi(page, 250), 250.0)

    def test_capped_render_dpi_rejects_non_positive(self) -> None:
        page = FakePage(595, 842)
        with self.assertRaises(ValueError):
            pdf_io.capped_render_dpi(page, 0)

    def test_huge_page_never_allocates_full_raster(self) -> None:
        # A0 at 250 DPI: the cap must reduce the zoom BEFORE get_pixmap.
        page = FakePage(2384, 3370)
        doc = FakeDoc(page)

        with mock.patch.object(pdf_io, "fitz", _mock_fitz()):
            img = pdf_io.render_page(doc, 0, dpi=250)

        self.assertEqual(len(page.rendered_zooms), 1)
        self.assertLess(page.rendered_zooms[0], 250 / 72.0)  # reduced zoom requested
        out_h, out_w = img.shape[:2]
        self.assertLessEqual(out_w * out_h / 1e6, MAX_RENDER_MEGAPIXELS + 0.5)

    def test_small_raster_is_not_downscaled(self) -> None:
        page = FakePage(144, 115.2)  # 500x400 px at 250 DPI
        doc = FakeDoc(page)

        with mock.patch.object(pdf_io, "fitz", _mock_fitz()):
            img = pdf_io.render_page(doc, 0, dpi=250)

        self.assertEqual(page.rendered_zooms[0], 250 / 72.0)
        self.assertEqual(img.shape[:2], (400, 500))


class EffectiveDpiMetricsTests(unittest.TestCase):
    """When the megapixel cap reduces the render DPI, physical metrics must be
    computed from the effective DPI: a 10x10 mm change stays ~100 mm² no
    matter how strongly the cap reduced the raster."""

    def test_mm2_survives_render_cap(self) -> None:
        import fitz

        from pdfcompare_core.runner import process_pair_task

        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            side_pt = 10.0 / 25.4 * 72.0  # 10 mm in points
            for name, changed in (("a.pdf", False), ("b.pdf", True)):
                doc = fitz.open()
                page = doc.new_page(width=595, height=842)  # A4
                page.draw_rect(fitz.Rect(50, 50, 500, 700), color=(0, 0, 0), width=2)
                if changed:
                    page.draw_rect(
                        fitz.Rect(200, 200, 200 + side_pt, 200 + side_pt),
                        color=(0, 0, 0),
                        fill=(0, 0, 0),
                    )
                doc.save(tmp_path / name)
                doc.close()

            # Force the cap with tiny rasters instead of allocating real A0 frames.
            with mock.patch.object(pdf_io, "MAX_RENDER_MEGAPIXELS", 0.6):
                row = process_pair_task(
                    tmp_path / "a.pdf",
                    tmp_path / "b.pdf",
                    tmp_path / "pages",
                    1,
                    0,
                    0,
                    "matched",
                    1.0,
                    200,  # requested DPI; the cap reduces it to ~79
                    2.0,
                    False,
                )

        self.assertIsNotNone(row["effective_dpi"])
        assert row["effective_dpi"] is not None
        self.assertLess(row["effective_dpi"], 200)
        self.assertIsNotNone(row["diff_area_mm2"])
        assert row["diff_area_mm2"] is not None
        # With the pre-fix bug (metrics from the requested DPI) this reads ~15 mm².
        self.assertGreater(row["diff_area_mm2"], 55.0)
        self.assertLess(row["diff_area_mm2"], 350.0)


class DiffEngineCorrectnessTests(unittest.TestCase):
    """Regression: the distanceTransform buffer-release refactor must keep
    diff results identical to the previous two-transforms-at-once path."""

    def test_identical_images_near_zero_diff(self) -> None:
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        _, _, _, diff_percent = compute_diff(img, img)
        self.assertLess(diff_percent, 0.1)

    def test_added_region_detected(self) -> None:
        a = np.zeros((200, 200, 3), dtype=np.uint8)
        b = a.copy()
        b[40:80, 40:80] = 255  # white square added
        _, _, bboxes, diff_percent = compute_diff(a, b)
        self.assertGreater(diff_percent, 0.0)
        self.assertGreater(len(bboxes), 0)


if __name__ == "__main__":
    unittest.main()
