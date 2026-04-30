from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SuggestionInputs:
    avg_sellout_units: float
    prior_planned_units: float | None
    forecast_units: float | None
    latest_net_price: float | None
    target_srp_local: float
    promo_mix_pct: float
    # Lineup evidence — optional, from the latest historical lineup apply job.
    # These fields are never seeded from DAP and must not be mapped to SKU controlled_cost_amount.
    lineup_msrp_local: float | None = field(default=None)
    lineup_promo_price_local: float | None = field(default=None)
    lineup_quantity_units: float | None = field(default=None)
    lineup_period_label: str | None = field(default=None)
    lineup_job_id: int | None = field(default=None)


def build_quantity_suggestion(inp: SuggestionInputs) -> tuple[float, str, str]:
    base = max(inp.avg_sellout_units, 0.0)
    if inp.prior_planned_units is not None:
        base = max(base, inp.prior_planned_units)
    if inp.forecast_units is not None:
        base = max(base, inp.forecast_units)
    if inp.lineup_quantity_units is not None and inp.lineup_quantity_units > 0:
        base = max(base, inp.lineup_quantity_units)
    qty = round(base * 1.08, 2)
    reason = (
        f"Derived from historical sellout {inp.avg_sellout_units:.2f}"
        + (f", prior planned {inp.prior_planned_units:.2f}" if inp.prior_planned_units is not None else "")
        + (f", forecast {inp.forecast_units:.2f}" if inp.forecast_units is not None else "")
        + (f", lineup qty {inp.lineup_quantity_units:.2f}" if inp.lineup_quantity_units is not None else "")
    )
    return qty, reason, "medium"


def build_pricing_suggestion(inp: SuggestionInputs) -> tuple[float, float, str, str]:
    if inp.latest_net_price is not None and inp.latest_net_price > 0:
        target = round(max(inp.target_srp_local, inp.latest_net_price * 1.12), 2)
        promo = round(target * 0.92, 2)
        reason = f"Anchored to latest net price {inp.latest_net_price:.2f} with markup and promo discount."
        confidence = "medium"
    elif inp.lineup_msrp_local is not None and inp.lineup_msrp_local > 0:
        target = round(max(inp.target_srp_local, inp.lineup_msrp_local), 2)
        promo = round(
            inp.lineup_promo_price_local if inp.lineup_promo_price_local is not None else target * 0.9, 2
        )
        period = f" ({inp.lineup_period_label})" if inp.lineup_period_label else ""
        reason = f"Anchored to lineup MSRP/list {inp.lineup_msrp_local:.2f}{period}. No net-price data available."
        confidence = "medium"
    else:
        target = round(inp.target_srp_local, 2)
        promo = round(inp.target_srp_local * 0.9, 2)
        reason = "No net-price or lineup MSRP anchor found; using plan SRP with conservative promo discount."
        confidence = "low"
    return target, promo, reason, confidence


def build_promo_mix_suggestion(inp: SuggestionInputs) -> tuple[float, str, str]:
    if inp.avg_sellout_units > 0 and inp.forecast_units is not None and inp.forecast_units > inp.avg_sellout_units * 1.2:
        suggested = 0.55
        reason = "Forecast growth over historical baseline suggests heavier promo support."
        confidence = "medium"
    else:
        suggested = 0.50
        reason = "Default balanced promo/non-promo reserve split."
        confidence = "high"
    return suggested, reason, confidence
