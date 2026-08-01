"""B2 profit line with embedded reservation + two commercial treatments.

Q-002 interim: reservation is **derived** from SKU economics (`reserve_total_pct` ×
revenue), not an explicit workbook column. Hard enforcement deferred (domain §1.8).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.commercial_planner.calculator import (
    CommercialCalcInputs,
    CommercialCalcResult,
    compute_line_economics,
)

DEFAULT_NORMAL_PRICE_SHARE = 0.5  # domain §1.10 nominal 50/50 volume split


@dataclass(frozen=True)
class TreatmentSplit:
    normal_price_units: float
    discount_units: float
    normal_price_share: float


def split_volume_treatments(
    net_requirement_units: float,
    *,
    normal_price_share: float = DEFAULT_NORMAL_PRICE_SHARE,
) -> TreatmentSplit:
    """Volume split into normal-price vs discount stock (not a cost split)."""
    share = min(max(float(normal_price_share), 0.0), 1.0)
    units = max(0.0, float(net_requirement_units))
    normal = round(units * share, 4)
    discount = round(units - normal, 4)
    return TreatmentSplit(
        normal_price_units=normal,
        discount_units=discount,
        normal_price_share=share,
    )


def compute_profit_with_reservation(
    *,
    net_requirement_units: float,
    target_srp_local: float,
    promo_srp_local: float | None,
    controlled_cost_amount: float,
    reserve_total_pct: float,
    promo_reserve_split_pct: float = 0.5,
    customer_margin_pct: float = 0.12,
    customer_rebate_pct: float = 0.03,
    distributor_margin_pct: float = 0.08,
    vat_rate_pct: float = 0.15,
    fx_plan_currency_per_cost_currency: float = 1.0,
    normal_price_share: float = DEFAULT_NORMAL_PRICE_SHARE,
) -> dict[str, Any]:
    """Profit + embedded reservation for a suggested lineup quantity.

    Uses the existing commercial planner economics calculator so B2 stays aligned
    with CP line math. Reservation source flagged as ``derived_q002_interim``.
    """
    treatments = split_volume_treatments(
        net_requirement_units, normal_price_share=normal_price_share
    )
    # promo_mix_pct = discount share of volume
    promo_mix = 1.0 - treatments.normal_price_share
    calc: CommercialCalcResult = compute_line_economics(
        CommercialCalcInputs(
            target_units=float(net_requirement_units),
            target_srp_local=float(target_srp_local),
            promo_srp_local=promo_srp_local,
            promo_mix_pct=promo_mix,
            fx_plan_currency_per_cost_currency=float(fx_plan_currency_per_cost_currency),
            vat_rate_pct=float(vat_rate_pct),
            controlled_cost_amount=float(controlled_cost_amount),
            customer_margin_pct=float(customer_margin_pct),
            customer_rebate_pct=float(customer_rebate_pct),
            distributor_margin_pct=float(distributor_margin_pct),
            reserve_total_pct=float(reserve_total_pct),
            promo_reserve_split_pct=float(promo_reserve_split_pct),
        )
    )
    reserved_total = (
        calc.calc_campaign_support_reserve_amount + calc.calc_non_campaign_reserve_amount
    )
    revenue = calc.calc_oem_sell_in_amount * float(net_requirement_units)
    support_pct_of_sell_in = (reserved_total / revenue) if revenue > 0 else None

    return {
        "net_requirement_units": float(net_requirement_units),
        "treatments": {
            "normal_price_units": treatments.normal_price_units,
            "discount_units": treatments.discount_units,
            "normal_price_share": treatments.normal_price_share,
            "note": "Volume split; nominal 50/50 — actual follows profit expectation",
        },
        "pm_bottom": float(controlled_cost_amount),
        "planned_srp_local": float(target_srp_local),
        "promo_srp_local": float(promo_srp_local) if promo_srp_local is not None else None,
        "oem_sell_in_per_unit": calc.calc_oem_sell_in_amount,
        "internal_gp_amount": calc.calc_internal_gp_amount,
        "reservation": {
            "source": "derived_q002_interim",
            "campaign_support": calc.calc_campaign_support_reserve_amount,
            "non_campaign": calc.calc_non_campaign_reserve_amount,
            "total": round(reserved_total, 4),
            "support_pct_of_sell_in": support_pct_of_sell_in,
            "hard_enforce": False,
        },
        "flags": calc.flags,
        "explanation": calc.explanation,
    }
