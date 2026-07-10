"""CPOR pricing waterfall — configured steps per channel (spec §2.1).

v1 reseller channel: vat_divide → margin_deduct only.
Rebate / disti-margin steps are intentionally absent (BACKLOG disti channel).

All money math uses decimal.Decimal. Full precision through the chain;
quantize only at the storage/presentation boundary (workbook: un-rounded
support_unit × qty → 12,297.18, not 250.96 × 49).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Callable

from app.services.cpor.config import MONEY_QUANTIZE

StepFn = Callable[[Decimal, dict[str, Decimal]], Decimal]

CHANNEL_STEPS: dict[str, list[str]] = {
    "reseller": ["vat_divide", "margin_deduct"],
}


def _vat_divide(price: Decimal, params: dict[str, Decimal]) -> Decimal:
    vat = params["vat_rate"]
    return price / (Decimal("1") + vat)


def _margin_deduct(price: Decimal, params: dict[str, Decimal]) -> Decimal:
    margin = params["dealer_margin_pct"]
    return price * (Decimal("1") - margin)


STEP_REGISTRY: dict[str, StepFn] = {
    "vat_divide": _vat_divide,
    "margin_deduct": _margin_deduct,
}


def quantize_money(value: Decimal, places: str = MONEY_QUANTIZE) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _as_decimal(value: Decimal | float | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def run_steps(
    srp: Decimal | float | int | str,
    channel: str,
    params: dict[str, Decimal | float | int | str],
) -> Decimal:
    """Run the channel's ordered waterfall steps; return full-precision dealer price."""
    if channel not in CHANNEL_STEPS:
        raise ValueError(f"Unknown CPOR channel: {channel!r}")
    price = _as_decimal(srp)
    dec_params = {k: _as_decimal(v) for k, v in params.items()}
    for step_name in CHANNEL_STEPS[channel]:
        fn = STEP_REGISTRY.get(step_name)
        if fn is None:
            raise ValueError(f"Unknown waterfall step: {step_name!r}")
        price = fn(price, dec_params)
    return price


def compute_dealer_price(
    srp: Decimal | float | int | str,
    vat_rate: Decimal | float | int | str,
    dealer_margin_pct: Decimal | float | int | str,
    *,
    channel: str = "reseller",
) -> Decimal:
    return run_steps(
        srp,
        channel,
        {"vat_rate": vat_rate, "dealer_margin_pct": dealer_margin_pct},
    )


def compute_support_unit(
    cost_basis: Decimal | float | int | str,
    dealer_price: Decimal | float | int | str,
) -> Decimal:
    """support_unit = max(0, cost_basis - dealer_price). Clamp kills float-epsilon negatives."""
    raw = _as_decimal(cost_basis) - _as_decimal(dealer_price)
    return raw if raw > 0 else Decimal("0")


def compute_ttl_support(
    support_unit: Decimal | float | int | str,
    estimate_qty: Decimal | float | int | str,
) -> Decimal:
    return _as_decimal(support_unit) * _as_decimal(estimate_qty)


def compute_ttl_result(
    support_unit: Decimal | float | int | str,
    result_qty: Decimal | float | int | str | None,
) -> Decimal | None:
    """Settlement total — NOT capped by estimate. None when result_qty absent."""
    if result_qty is None:
        return None
    return _as_decimal(support_unit) * _as_decimal(result_qty)


def compute_support_usd(
    support_unit: Decimal | float | int | str,
    case_roe: Decimal | float | int | str | None,
) -> tuple[Decimal | None, list[str]]:
    """support_usd = support_unit / roe. Missing/zero ROE → None + missing_roe flag."""
    if case_roe is None:
        return None, ["missing_roe"]
    roe = _as_decimal(case_roe)
    if roe == 0:
        return None, ["missing_roe"]
    return _as_decimal(support_unit) / roe, []


def compute_ttl_usd(
    local_total: Decimal | float | int | str | None,
    case_roe: Decimal | float | int | str | None,
) -> Decimal | None:
    """Convert a local-currency total (ttl_support / ttl_result) to USD via case ROE.

    Uses full-precision intermediates (same discipline as support_usd / 12,297.18 lesson).
    """
    if local_total is None or case_roe is None:
        return None
    roe = _as_decimal(case_roe)
    if roe == 0:
        return None
    return _as_decimal(local_total) / roe


def compute_line_waterfall(
    *,
    srp: Decimal | float | int | str,
    vat_rate: Decimal | float | int | str,
    dealer_margin_pct: Decimal | float | int | str,
    cost_basis: Decimal | float | int | str | None,
    estimate_qty: Decimal | float | int | str,
    result_qty: Decimal | float | int | str | None = None,
    case_roe: Decimal | float | int | str | None = None,
    channel: str = "reseller",
) -> dict:
    """Full line compute. Returns full-precision values + flags; caller quantizes for storage."""
    flags: list[str] = []
    dealer_price = compute_dealer_price(srp, vat_rate, dealer_margin_pct, channel=channel)

    if cost_basis is None:
        flags.append("no_cost_basis")
        support_usd, roe_flags = compute_support_usd(Decimal("0"), case_roe)
        flags.extend(roe_flags)
        return {
            "dealer_price": dealer_price,
            "support_unit": None,
            "ttl_support": None,
            "ttl_result": None,
            "support_usd": None if "missing_roe" in flags or cost_basis is None else support_usd,
            "ttl_support_usd": None,
            "ttl_result_usd": None,
            "flags": flags,
        }

    support_unit = compute_support_unit(cost_basis, dealer_price)
    ttl_support = compute_ttl_support(support_unit, estimate_qty)
    ttl_result = compute_ttl_result(support_unit, result_qty)
    support_usd, roe_flags = compute_support_usd(support_unit, case_roe)
    flags.extend(roe_flags)
    ttl_support_usd = compute_ttl_usd(ttl_support, case_roe)
    ttl_result_usd = compute_ttl_usd(ttl_result, case_roe)

    return {
        "dealer_price": dealer_price,
        "support_unit": support_unit,
        "ttl_support": ttl_support,
        "ttl_result": ttl_result,
        "support_usd": support_usd,
        "ttl_support_usd": ttl_support_usd,
        "ttl_result_usd": ttl_result_usd,
        "flags": flags,
    }
