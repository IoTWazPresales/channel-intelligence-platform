"""Rule-based pricing recommendation states (deterministic)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PricingInputs:
    current_net_price: float
    reference_price: float
    stock_risk_kind: str
    days_to_promo: int | None
    competitor_net: float | None


@dataclass(frozen=True)
class PricingResult:
    suggested_state: str
    explanation_summary: str
    factors: dict


def pricing_state(inputs: PricingInputs) -> PricingResult:
    factors: dict = {
        "current_net_price": inputs.current_net_price,
        "reference_price": inputs.reference_price,
        "stock_risk_kind": inputs.stock_risk_kind,
        "days_to_promo": inputs.days_to_promo,
        "competitor_net": inputs.competitor_net,
    }

    gap_vs_ref = (
        (inputs.current_net_price - inputs.reference_price) / inputs.reference_price
        if inputs.reference_price
        else 0.0
    )
    comp_gap = None
    if inputs.competitor_net:
        comp_gap = (inputs.current_net_price - inputs.competitor_net) / inputs.competitor_net

    if inputs.stock_risk_kind == "stockout_risk" and inputs.days_to_promo is not None and inputs.days_to_promo <= 21:
        return PricingResult(
            suggested_state="support_promo",
            explanation_summary="Stockout risk near promo window; prioritize in-stock and promo support over discounting.",
            factors=factors | {"rule": "stockout_plus_promo_proximity"},
        )

    if comp_gap is not None and comp_gap > 0.08:
        return PricingResult(
            suggested_state="consider_reduction",
            explanation_summary="Priced materially above observed competitor net; evaluate targeted price action.",
            factors=factors | {"comp_gap_pct": comp_gap, "rule": "comp_above"},
        )

    if gap_vs_ref < -0.05:
        return PricingResult(
            suggested_state="avoid_discounting",
            explanation_summary="Net already below internal reference; avoid incremental discount unless strategically justified.",
            factors=factors | {"gap_vs_ref": gap_vs_ref, "rule": "below_reference"},
        )

    return PricingResult(
        suggested_state="hold",
        explanation_summary="No strong rule-based trigger from reference, stock risk, promo timing, or competitor gap.",
        factors=factors | {"gap_vs_ref": gap_vs_ref, "comp_gap_pct": comp_gap},
    )
