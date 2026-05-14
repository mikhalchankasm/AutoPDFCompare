"""Core dataclasses used throughout the comparison pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PageInfo:
    index: int
    thumb: np.ndarray
    text_tokens: set[str]
    width_pt: float
    height_pt: float
    sheet_mark: str | None


@dataclass
class MatchPair:
    a_idx: int | None
    b_idx: int | None
    status: str  # matched | added | removed
    score: float
