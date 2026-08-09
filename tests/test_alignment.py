"""Unit tests for page alignment strategies (synthetic PageInfo, no real PDFs)."""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from compare_pdfs import (
    MatchPair,
    PageInfo,
    align_ecc,
    align_ecc_detailed,
    align_pages_hungarian,
    align_pages_monotonic,
    align_pages_v1,
    count_inversions,
    pair_similarity,
)


def _thumb(intensity: float) -> np.ndarray:
    """160x160 float32 image of constant intensity in [0, 255].

    Constant thumbs give deterministic MSE-based similarity:
    identical intensity → sim=1, |Δ|=255 → sim=0.
    """
    return np.full((160, 160), float(intensity), dtype=np.float32)


def _page(
    idx: int,
    intensity: float,
    width: float = 595.0,
    height: float = 842.0,
    sheet_mark: str | None = None,
    text_tokens: set[str] | None = None,
) -> PageInfo:
    return PageInfo(
        index=idx,
        thumb=_thumb(intensity),
        text_tokens=set() if text_tokens is None else text_tokens,
        width_pt=width,
        height_pt=height,
        sheet_mark=sheet_mark,
    )


def _matched_pairs(pairs):
    return [p for p in pairs if p.status == "matched"]


def _statuses(pairs) -> list[str]:
    return [p.status for p in pairs]


def _large_drawing(width: int = 2400, height: int = 1600) -> np.ndarray:
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (40, 40), (width - 40, height - 40), (0, 0, 0), 3)
    for x in range(180, width - 300, 260):
        cv2.line(image, (x, 180), (x + 170, height - 320), (0, 0, 0), 2)
        cv2.circle(image, (x + 80, 420 + (x % 300)), 55, (0, 0, 0), 3)
    for y in range(220, height - 260, 190):
        cv2.line(image, (130, y), (width - 180, y), (0, 0, 0), 2)
    cv2.putText(image, "DRAWING REV 00", (180, 125), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
    return image


def _translate(image: np.ndarray, shift_x: float, shift_y: float) -> np.ndarray:
    warp = np.array([[1.0, 0.0, shift_x], [0.0, 1.0, shift_y]], dtype=np.float32)
    return cv2.warpAffine(
        image,
        warp,
        (image.shape[1], image.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


class ImageRegistrationTests(unittest.TestCase):
    def test_multiscale_alignment_recovers_large_raster_translation(self) -> None:
        base = _large_drawing()
        moving = _translate(base, 42.0, -18.0)
        before = float(np.mean(cv2.absdiff(base, moving)))

        result = align_ecc_detailed(base, moving)
        after = float(np.mean(cv2.absdiff(base, result.image)))

        self.assertTrue(result.ok)
        self.assertIn(result.method, {"ECC_TRANSLATION_PYRAMID", "ECC_AFFINE_PYRAMID"})
        self.assertAlmostEqual(result.shift_x_px, 42.0, delta=1.0)
        self.assertAlmostEqual(result.shift_y_px, -18.0, delta=1.0)
        self.assertLess(after, before * 0.12)
        self.assertGreater(result.improvement, 0.80)

    def test_excluded_fixed_stamp_does_not_anchor_moving_drawing(self) -> None:
        base = _large_drawing()
        stamp_box = (1850, 1250, 500, 280)
        cv2.rectangle(base, (1850, 1250), (2350, 1530), (0, 0, 0), 5)
        cv2.putText(base, "REV 00", (1930, 1410), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 4)
        moving = _translate(base, 36.0, 14.0)
        x, y, width, height = stamp_box
        moving[y : y + height, x : x + width] = base[y : y + height, x : x + width]

        result = align_ecc_detailed(base, moving, [stamp_box])

        self.assertTrue(result.ok)
        self.assertAlmostEqual(result.shift_x_px, 36.0, delta=1.0)
        self.assertAlmostEqual(result.shift_y_px, 14.0, delta=1.0)

    def test_public_wrapper_keeps_two_value_contract(self) -> None:
        base = _large_drawing(800, 600)

        aligned, ok = align_ecc(base, base.copy())

        self.assertTrue(ok)
        self.assertTrue(np.array_equal(aligned, base))

    def test_shape_mismatch_fails_without_modifying_moving_image(self) -> None:
        base = _large_drawing(800, 600)
        moving = _large_drawing(700, 500)

        result = align_ecc_detailed(base, moving)

        self.assertFalse(result.ok)
        self.assertIs(result.image, moving)


class PairSimilaritySanityTests(unittest.TestCase):
    """Sanity checks that our synthetic PageInfo factory produces the similarities we expect."""

    def test_identical_intensity_gives_full_similarity(self) -> None:
        a = _page(0, 100.0)
        b = _page(0, 100.0)
        self.assertAlmostEqual(pair_similarity(a, b), 1.0, places=4)

    def test_opposite_intensity_gives_zero_similarity(self) -> None:
        a = _page(0, 0.0)
        b = _page(0, 255.0)
        self.assertAlmostEqual(pair_similarity(a, b), 0.0, places=4)

    def test_incompatible_size_gives_zero_similarity(self) -> None:
        a = _page(0, 100.0, width=595.0, height=842.0)  # A4 portrait
        b = _page(0, 100.0, width=842.0, height=595.0)  # A4 landscape
        self.assertEqual(pair_similarity(a, b), 0.0)


class HungarianAlignmentTests(unittest.TestCase):
    def test_identical_pages_all_match(self) -> None:
        a = [_page(0, 0.0), _page(1, 128.0), _page(2, 200.0)]
        b = [_page(0, 0.0), _page(1, 128.0), _page(2, 200.0)]

        pairs = align_pages_hungarian(a, b)

        self.assertEqual(len(_matched_pairs(pairs)), 3)
        for pair in _matched_pairs(pairs):
            self.assertEqual(pair.a_idx, pair.b_idx)
            self.assertGreaterEqual(pair.score, 0.95)

    def test_extra_page_in_b_is_added(self) -> None:
        a = [_page(0, 0.0), _page(1, 255.0)]
        b = [_page(0, 0.0), _page(1, 255.0), _page(2, 128.0)]

        pairs = align_pages_hungarian(a, b)

        matched = _matched_pairs(pairs)
        added = [p for p in pairs if p.status == "added"]
        removed = [p for p in pairs if p.status == "removed"]
        self.assertEqual(len(matched), 2)
        self.assertEqual(len(added), 1)
        self.assertEqual(len(removed), 0)
        self.assertEqual(added[0].b_idx, 2)

    def test_extra_page_in_a_is_removed(self) -> None:
        a = [_page(0, 0.0), _page(1, 128.0), _page(2, 255.0)]
        b = [_page(0, 0.0), _page(1, 255.0)]

        pairs = align_pages_hungarian(a, b)

        self.assertEqual(len(_matched_pairs(pairs)), 2)
        removed = [p for p in pairs if p.status == "removed"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0].a_idx, 1)  # middle page (128) has no counterpart in B

    def test_reordered_pages_still_match_globally(self) -> None:
        """Hungarian is global — swapped pages should still pair correctly."""
        a = [_page(0, 0.0), _page(1, 255.0)]
        b = [_page(0, 255.0), _page(1, 0.0)]  # swapped

        pairs = align_pages_hungarian(a, b)

        matched = _matched_pairs(pairs)
        self.assertEqual(len(matched), 2)
        mapping = {p.a_idx: p.b_idx for p in matched}
        self.assertEqual(mapping, {0: 1, 1: 0})


class MonotonicAlignmentTests(unittest.TestCase):
    def test_identical_pages_all_match(self) -> None:
        a = [_page(0, 0.0), _page(1, 128.0), _page(2, 200.0)]
        b = [_page(0, 0.0), _page(1, 128.0), _page(2, 200.0)]

        pairs = align_pages_monotonic(a, b)

        self.assertEqual(len(_matched_pairs(pairs)), 3)
        for pair in _matched_pairs(pairs):
            self.assertEqual(pair.a_idx, pair.b_idx)

    def test_does_not_produce_crossings(self) -> None:
        """Reversed B → monotonic must not cross-match; it should drop pages instead."""
        a = [_page(0, 0.0), _page(1, 255.0)]
        b = [_page(0, 255.0), _page(1, 0.0)]  # reversed identities

        pairs = align_pages_monotonic(a, b)

        # No matched pair may have a_idx > a_idx_of_next while b_idx > b_idx_of_next
        # (i.e., sequence of matched b_idx must be non-decreasing).
        matched_b = [p.b_idx for p in _matched_pairs(pairs)]
        self.assertEqual(matched_b, sorted(matched_b))

        # At least one page should be marked added/removed since cross-match is forbidden.
        self.assertTrue(
            any(p.status in {"added", "removed"} for p in pairs),
            f"Expected gaps, got statuses: {_statuses(pairs)}",
        )

    def test_insertion_in_middle_yields_added(self) -> None:
        """A=[id0,id1], B=[id0,extra,id1] → both A pages match, middle B is added."""
        a = [_page(0, 0.0), _page(1, 255.0)]
        b = [_page(0, 0.0), _page(1, 128.0), _page(2, 255.0)]

        pairs = align_pages_monotonic(a, b)

        matched = _matched_pairs(pairs)
        added = [p for p in pairs if p.status == "added"]
        self.assertEqual(len(matched), 2)
        self.assertEqual(len(added), 1)
        # Added page should be the middle one (b_idx=1).
        self.assertEqual(added[0].b_idx, 1)


class AlignPagesV1Tests(unittest.TestCase):
    def test_matches_revision_republished_on_larger_same_aspect_sheet(self) -> None:
        common = {f"DRAWING_TOKEN_{i}" for i in range(30)}
        a = [_page(0, 100.0, width=2383.0, height=1683.0, sheet_mark="1", text_tokens=common | {"2025"})]
        b = [_page(0, 100.0, width=3370.0, height=2383.0, sheet_mark="1", text_tokens=common | {"2026"})]

        pairs = align_pages_v1(a, b)

        self.assertEqual(_statuses(pairs), ["matched"])
        self.assertEqual((pairs[0].a_idx, pairs[0].b_idx), (0, 0))

    def test_does_not_relax_size_gate_for_weak_content_match(self) -> None:
        a = [_page(0, 100.0, width=2383.0, height=1683.0, text_tokens={"A", "B"})]
        b = [_page(0, 100.0, width=3370.0, height=2383.0, text_tokens={"A", "B"})]

        pairs = align_pages_v1(a, b)

        self.assertEqual(sorted(_statuses(pairs)), ["added", "removed"])

    def test_picks_global_when_reorder_dominates(self) -> None:
        """For swapped pages, global (hungarian) recovers all matches and should win."""
        a = [_page(0, 0.0), _page(1, 255.0)]
        b = [_page(0, 255.0), _page(1, 0.0)]

        pairs = align_pages_v1(a, b)
        matched = _matched_pairs(pairs)
        self.assertEqual(len(matched), 2)
        mapping = {p.a_idx: p.b_idx for p in matched}
        self.assertEqual(mapping, {0: 1, 1: 0})

    def test_returns_matched_pairs_for_sequential_input(self) -> None:
        a = [_page(0, 0.0), _page(1, 128.0), _page(2, 200.0)]
        b = [_page(0, 0.0), _page(1, 128.0), _page(2, 200.0)]

        pairs = align_pages_v1(a, b)
        matched = _matched_pairs(pairs)
        self.assertEqual(len(matched), 3)
        for p in matched:
            self.assertEqual(p.a_idx, p.b_idx)


class CountInversionsTests(unittest.TestCase):
    def test_sorted_sequence_has_zero_inversions(self) -> None:
        self.assertEqual(count_inversions([1, 2, 3, 4, 5]), 0)

    def test_empty_and_singleton(self) -> None:
        self.assertEqual(count_inversions([]), 0)
        self.assertEqual(count_inversions([42]), 0)

    def test_reverse_sequence_has_maximum_inversions(self) -> None:
        n = 5
        self.assertEqual(count_inversions(list(range(n, 0, -1))), n * (n - 1) // 2)

    def test_known_mixed_case(self) -> None:
        # [2, 4, 1, 3, 5]: pairs (2,1), (4,1), (4,3) → 3 inversions
        self.assertEqual(count_inversions([2, 4, 1, 3, 5]), 3)


class MatchPairShapeTests(unittest.TestCase):
    """Defend the public contract callers depend on."""

    def test_hungarian_returns_match_pair_dataclass(self) -> None:
        a = [_page(0, 0.0)]
        b = [_page(0, 0.0)]
        pairs = align_pages_hungarian(a, b)
        self.assertTrue(all(isinstance(p, MatchPair) for p in pairs))

    def test_monotonic_returns_match_pair_dataclass(self) -> None:
        a = [_page(0, 0.0)]
        b = [_page(0, 0.0)]
        pairs = align_pages_monotonic(a, b)
        self.assertTrue(all(isinstance(p, MatchPair) for p in pairs))


if __name__ == "__main__":
    unittest.main()
