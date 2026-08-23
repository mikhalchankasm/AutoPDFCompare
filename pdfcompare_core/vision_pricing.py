from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, timezone


PRICING_LAST_VERIFIED = "2026-08-22"
OPENROUTER_CREDIT_FEE_RATE = 0.055
OPENROUTER_MINIMUM_CREDIT_PURCHASE_FEE_USD = 0.80

_BEIJING = timezone(timedelta(hours=8))
_WEEKEND_RULE_START = datetime(2026, 8, 22, 16, 0, tzinfo=UTC)


@dataclass(frozen=True)
class VisionTokenRates:
    cache_hit_input_usd_per_million: float
    cache_miss_input_usd_per_million: float
    output_usd_per_million: float


@dataclass(frozen=True)
class VisionCostEstimate:
    prompt_tokens: int
    cached_prompt_tokens: int
    completion_tokens: int
    period: str
    direct_deepseek_usd: float
    openrouter_inference_usd: float
    openrouter_credit_fee_proportional_usd: float
    openrouter_effective_usd: float
    off_peak_direct_usd: float
    peak_direct_usd: float
    pricing_last_verified: str = PRICING_LAST_VERIFIED


OFF_PEAK_RATES = VisionTokenRates(
    cache_hit_input_usd_per_million=0.007,
    cache_miss_input_usd_per_million=0.22,
    output_usd_per_million=0.66,
)
PEAK_RATES = VisionTokenRates(
    cache_hit_input_usd_per_million=0.014,
    cache_miss_input_usd_per_million=0.44,
    output_usd_per_million=1.32,
)


def deepseek_vision_price_period(at: datetime | None = None) -> str:
    moment = at or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    utc_moment = moment.astimezone(UTC)
    beijing_moment = utc_moment.astimezone(_BEIJING)
    if utc_moment >= _WEEKEND_RULE_START and beijing_moment.weekday() >= 5:
        return "off_peak"
    utc_clock = utc_moment.time().replace(tzinfo=None)
    peak = time(1, 0) <= utc_clock < time(4, 0) or time(6, 0) <= utc_clock < time(10, 0)
    return "peak" if peak else "off_peak"


def estimate_deepseek_vision_cost(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    cached_prompt_tokens: int = 0,
    at: datetime | None = None,
) -> VisionCostEstimate:
    prompt = max(0, int(prompt_tokens))
    completion = max(0, int(completion_tokens))
    cached = min(prompt, max(0, int(cached_prompt_tokens)))
    period = deepseek_vision_price_period(at)
    rates = PEAK_RATES if period == "peak" else OFF_PEAK_RATES
    direct = _cost(prompt, cached, completion, rates)
    off_peak = _cost(prompt, cached, completion, OFF_PEAK_RATES)
    peak = _cost(prompt, cached, completion, PEAK_RATES)
    openrouter_fee = direct * OPENROUTER_CREDIT_FEE_RATE
    return VisionCostEstimate(
        prompt_tokens=prompt,
        cached_prompt_tokens=cached,
        completion_tokens=completion,
        period=period,
        direct_deepseek_usd=direct,
        openrouter_inference_usd=direct,
        openrouter_credit_fee_proportional_usd=openrouter_fee,
        openrouter_effective_usd=direct + openrouter_fee,
        off_peak_direct_usd=off_peak,
        peak_direct_usd=peak,
    )


def _cost(prompt: int, cached: int, completion: int, rates: VisionTokenRates) -> float:
    cache_miss = prompt - cached
    return (
        cached * rates.cache_hit_input_usd_per_million
        + cache_miss * rates.cache_miss_input_usd_per_million
        + completion * rates.output_usd_per_million
    ) / 1_000_000
