from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from typing import Protocol

from app.models import Charge, Usage

USD_QUANT = Decimal("0.00000001")
MILLION = Decimal("1000000")


class BillingSettings(Protocol):
    credits_per_usd: int
    price_input_per_million_usd: Decimal
    price_output_per_million_usd: Decimal
    commission_percent: Decimal
    commission_flat_usd: Decimal
    min_charge_credits: int
    fallback_charge_credits: int


def _fmt_usd(value: Decimal) -> str:
    quantized = value.quantize(USD_QUANT)
    return format(quantized, "f")


def billable_output_tokens(usage: Usage) -> int:
    """Reasoning is billed as output only when it is extra, not a subset of completion."""
    completion = max(0, usage.completion_tokens)
    reasoning = max(0, usage.reasoning_tokens)
    if reasoning <= 0:
        return completion
    if reasoning <= completion:
        return completion
    return completion + reasoning


def calculate_charge(usage: Usage, settings: BillingSettings) -> Charge:
    prompt = Decimal(max(0, usage.prompt_tokens))
    output = Decimal(billable_output_tokens(usage))
    provider = (prompt / MILLION) * settings.price_input_per_million_usd
    provider += (output / MILLION) * settings.price_output_per_million_usd
    billed = provider * (
        Decimal("1") + settings.commission_percent / Decimal("100")
    ) + settings.commission_flat_usd
    credits_raw = (billed * Decimal(settings.credits_per_usd)).to_integral_value(
        rounding=ROUND_CEILING
    )
    credits_charged = int(credits_raw)
    if credits_charged < settings.min_charge_credits:
        credits_charged = settings.min_charge_credits
    markup = billed - provider
    return Charge(
        provider_cost_usd=_fmt_usd(provider),
        markup_usd=_fmt_usd(markup),
        billed_usd=_fmt_usd(billed),
        credits_charged=credits_charged,
    )


def fallback_charge(settings: BillingSettings) -> Charge:
    credits = max(settings.fallback_charge_credits, settings.min_charge_credits)
    if settings.credits_per_usd <= 0:
        billed = Decimal("0")
    else:
        billed = Decimal(credits) / Decimal(settings.credits_per_usd)
    return Charge(
        provider_cost_usd=_fmt_usd(Decimal("0")),
        markup_usd=_fmt_usd(billed),
        billed_usd=_fmt_usd(billed),
        credits_charged=credits,
    )
