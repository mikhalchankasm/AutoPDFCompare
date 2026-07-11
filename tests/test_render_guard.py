"""Tests for the render megapixel guard and diff engine memory handling.

These verify that very large page rasters are downscaled before entering the
diff pipeline (which allocates several full-frame float32 buffers), and that
the diff engine still produces correct results after the distanceTransform
buffer-release refactor.
"""

from __future__ import annotations

import unittest
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
    def __init__(self, pixmap: FakePixmap) -> None:
        self._pixmap = pixmap

    def get_pixmap(self, **_kwargs: object) -> FakePixmap:
        return self._pixmap


class FakeDoc:
    def __init__(self, page: FakePage) -> None:
        self._page = page

    def __getitem__(self, _index: int) -> FakePage:
        return self._page


class RenderMegapixelGuardTests(unittest.TestCase):
    def test_huge_raster_is_downscaled_under_cap(self) -> None:
        # Simulate a ~60 MP page (above MAX_RENDER_MEGAPIXELS).
        w, h = 8000, 7500  # 60 MP
        pixmap = FakePixmap(w, h, channels=3)
        doc = FakeDoc(FakePage(pixmap))

        with mock.patch.object(pdf_io, "fitz") as mock_fitz:
            mock_fitz.Matrix.return_value = object()
            mock_fitz.csRGB = object()
            img = pdf_io.render_page(doc, 0, dpi=250)

        out_h, out_w = img.shape[:2]
        out_mp = (out_w * out_h) / 1_000_000.0
        self.assertLessEqual(out_mp, MAX_RENDER_MEGAPIXELS + 0.5)  # rounding slack
        self.assertLess(out_w, w)
        self.assertLess(out_h, h)

    def test_small_raster_is_not_downscaled(self) -> None:
        w, h = 500, 400  # 0.2 MP — well under the cap
        pixmap = FakePixmap(w, h, channels=3)
        doc = FakeDoc(FakePage(pixmap))

        with mock.patch.object(pdf_io, "fitz") as mock_fitz:
            mock_fitz.Matrix.return_value = object()
            mock_fitz.csRGB = object()
            img = pdf_io.render_page(doc, 0, dpi=250)

        self.assertEqual(img.shape[:2], (h, w))


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
