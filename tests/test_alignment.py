"""Unit tests for page alignment strategies (synthetic PageInfo, no real PDFs)."""

from __future__ import annotations

import unittest

import numpy as np

from compare_pdfs import (
    MatchPair,
    PageInfo,
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
) -> PageInfo:
    return PageInfo(
        index=idx,
        thumb=_thumb(intensity),
        text_tokens=set(),
        width_pt=width,
        height_pt=height,
        sheet_mark=sheet_mark,
    )


def _matched_pairs(pairs):
    return [p for p in pairs if p.status == "matched"]


def _statuses(pairs) -> list[str]:
    return [p.status for p in pairs]


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
