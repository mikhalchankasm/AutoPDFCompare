from __future__ import annotations

from datetime import UTC, datetime

from pdfcompare_core.vision_pricing import estimate_deepseek_vision_cost


def test_cost_outside_peak() -> None:
    estimate = estimate_deepseek_vision_cost(
        10_000,
        2_000,
        at=datetime(2026, 8, 22, 12, 58, tzinfo=UTC),
    )

    assert estimate.period == "off_peak"
    assert estimate.direct_deepseek_usd == 0.00352
    assert estimate.peak_direct_usd == 0.00704
    assert estimate.openrouter_inference_usd == estimate.direct_deepseek_usd
    assert estimate.openrouter_effective_usd == 0.0037136


def test_peak_window_doubles_all_rates() -> None:
    estimate = estimate_deepseek_vision_cost(
        1_000_000,
        1_000_000,
        cached_prompt_tokens=100_000,
        at=datetime(2026, 8, 21, 6, 30, tzinfo=UTC),
    )

    assert estimate.period == "peak"
    assert estimate.off_peak_direct_usd == 0.8587
    assert estimate.direct_deepseek_usd == 1.7174


def test_weekends_in_beijing_are_off_peak_after_rule_change() -> None:
    estimate = estimate_deepseek_vision_cost(
        1_000_000,
        0,
        at=datetime(2026, 8, 23, 6, 30, tzinfo=UTC),
    )

    assert estimate.period == "off_peak"
    assert estimate.direct_deepseek_usd == 0.22


def test_cached_input_uses_the_lower_rate_and_is_clamped() -> None:
    estimate = estimate_deepseek_vision_cost(
        1000,
        0,
        cached_prompt_tokens=5000,
        at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
    )

    assert estimate.cached_prompt_tokens == 1000
    assert estimate.direct_deepseek_usd == 0.000007
