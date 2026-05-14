"""Unit tests for compute_diff and harmonize_canvas (synthetic BGR images)."""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from compare_pdfs import compute_diff, harmonize_canvas


def _white_canvas(h: int = 200, w: int = 200) -> np.ndarray:
    """White BGR canvas."""
    return np.full((h, w, 3), 255, dtype=np.uint8)


def _draw_filled_rect(img: np.ndarray, x: int, y: int, w: int, h: int, color: tuple[int, int, int] = (0, 0, 0)) -> None:
    cv2.rectangle(img, (x, y), (x + w - 1, y + h - 1), color, thickness=-1)


class ComputeDiffTests(unittest.TestCase):
    def test_identical_images_have_near_zero_diff(self) -> None:
        a = _white_canvas()
        b = a.copy()
        _, _, bboxes, diff_percent = compute_diff(a, b)

        self.assertEqual(bboxes, [])
        self.assertLess(diff_percent, 0.1)

    def test_added_rectangle_in_b_produces_bbox(self) -> None:
        a = _white_canvas()
        b = _white_canvas()
        _draw_filled_rect(b, x=70, y=70, w=50, h=50)  # area 2500 >> 180 threshold

        _, _, bboxes, diff_percent = compute_diff(a, b)

        self.assertGreater(len(bboxes), 0)
        self.assertGreater(diff_percent, 0.0)
        # At least one bbox should overlap the inserted rectangle.
        rect = (70, 70, 50, 50)
        self.assertTrue(
            any(self._overlap_ratio(bb, rect) > 0.5 for bb in bboxes),
            f"No bbox overlaps the added rectangle; got: {bboxes}",
        )

    def test_removed_rectangle_in_a_produces_bbox(self) -> None:
        a = _white_canvas()
        _draw_filled_rect(a, x=70, y=70, w=50, h=50)
        b = _white_canvas()

        _, _, bboxes, diff_percent = compute_diff(a, b)

        self.assertGreater(len(bboxes), 0)
        self.assertGreater(diff_percent, 0.0)

    def test_tiny_speck_below_area_threshold_yields_no_bbox(self) -> None:
        """Single tiny mark (< 180 px² contour area) is filtered out as bbox candidate."""
        a = _white_canvas()
        b = _white_canvas()
        _draw_filled_rect(b, x=10, y=10, w=8, h=8)  # area 64

        _, _, bboxes, _ = compute_diff(a, b)
        self.assertEqual(bboxes, [])

    def test_subpixel_stroke_shift_absorbed_by_tolerance(self) -> None:
        """A line shifted by 1 px should not register as a diff when stroke_tol_px=2.0."""
        a = _white_canvas()
        b = _white_canvas()
        cv2.line(a, (20, 100), (180, 100), (0, 0, 0), thickness=2)
        cv2.line(b, (20, 101), (180, 101), (0, 0, 0), thickness=2)

        _, _, bboxes, diff_percent = compute_diff(a, b, stroke_tol_px=2.0)

        self.assertEqual(bboxes, [])
        self.assertLess(diff_percent, 0.2)

    def test_size_mismatch_raises_value_error(self) -> None:
        a = _white_canvas(200, 200)
        b = _white_canvas(200, 300)
        with self.assertRaises(ValueError):
            compute_diff(a, b)

    def test_return_types_and_shapes(self) -> None:
        a = _white_canvas(120, 160)
        b = _white_canvas(120, 160)
        _draw_filled_rect(b, x=40, y=40, w=30, h=30)

        mask, overlay, bboxes, diff_percent = compute_diff(a, b)

        self.assertEqual(mask.shape, (120, 160))
        self.assertEqual(mask.dtype, np.uint8)
        self.assertEqual(overlay.shape, b.shape)
        self.assertEqual(overlay.dtype, np.uint8)
        self.assertIsInstance(diff_percent, float)
        self.assertIsInstance(bboxes, list)
        for bb in bboxes:
            self.assertEqual(len(bb), 4)
            x, y, w, h = bb
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + w, 160)
            self.assertLessEqual(y + h, 120)

    def test_overlay_differs_from_b_on_changed_pixels(self) -> None:
        """Overlay should colorize at least some pixels where the diff lives."""
        a = _white_canvas()
        b = _white_canvas()
        _draw_filled_rect(b, x=80, y=80, w=40, h=40)

        _, overlay, _, _ = compute_diff(a, b)

        # Some overlay pixels must differ from b (the colorization is applied to changed regions).
        changed_pixels = np.any(overlay != b, axis=-1)
        self.assertGreater(int(np.count_nonzero(changed_pixels)), 0)

    @staticmethod
    def _overlap_ratio(bbox: tuple[int, int, int, int], target: tuple[int, int, int, int]) -> float:
        bx, by, bw, bh = bbox
        tx, ty, tw, th = target
        inter_x0 = max(bx, tx)
        inter_y0 = max(by, ty)
        inter_x1 = min(bx + bw, tx + tw)
        inter_y1 = min(by + bh, ty + th)
        iw = max(0, inter_x1 - inter_x0)
        ih = max(0, inter_y1 - inter_y0)
        return (iw * ih) / float(tw * th)


class HarmonizeCanvasTests(unittest.TestCase):
    def test_same_size_returns_unchanged(self) -> None:
        a = _white_canvas(100, 100)
        b = _white_canvas(100, 100)
        result = harmonize_canvas(a, b)

        self.assertIsNotNone(result)
        out_a, out_b = result
        self.assertEqual(out_a.shape, (100, 100, 3))
        self.assertEqual(out_b.shape, (100, 100, 3))

    def test_small_size_delta_is_padded(self) -> None:
        a = _white_canvas(100, 100)
        b = _white_canvas(98, 100)  # delta 2 ≤ default max_delta=3
        result = harmonize_canvas(a, b)

        self.assertIsNotNone(result)
        out_a, out_b = result
        self.assertEqual(out_a.shape[:2], out_b.shape[:2])
        self.assertEqual(out_a.shape[:2], (100, 100))

    def test_large_delta_returns_none(self) -> None:
        a = _white_canvas(100, 100)
        b = _white_canvas(50, 100)  # delta 50 >> max_delta
        result = harmonize_canvas(a, b)
        self.assertIsNone(result)

    def test_max_delta_threshold_respected(self) -> None:
        a = _white_canvas(100, 100)
        b = _white_canvas(100, 95)  # width delta 5

        self.assertIsNone(harmonize_canvas(a, b, max_delta=3))
        result = harmonize_canvas(a, b, max_delta=10)
        self.assertIsNotNone(result)
        out_a, out_b = result
        self.assertEqual(out_a.shape[:2], out_b.shape[:2])


if __name__ == "__main__":
    unittest.main()
