from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommercialCalcInputs:
    target_units: float
    target_srp_local: float
    promo_srp_local: float | None
    promo_mix_pct: float
    fx_plan_currency_per_cost_currency: float
    vat_rate_pct: float
    controlled_cost_amount: float
    customer_margin_pct: float
    customer_rebate_pct: float
    distributor_margin_pct: float
    reserve_total_pct: float
    promo_reserve_split_pct: float


@dataclass(frozen=True)
class CommercialCalcResult:
    calc_oem_sell_in_amount: float
    calc_distributor_net_amount: float
    calc_campaign_support_reserve_amount: float
    calc_non_campaign_reserve_amount: float
    calc_internal_gp_amount: float
    calc_customer_margin_input_pct: float
    calc_distributor_margin_input_pct: float
    flags: list[str]
    explanation: str


def compute_line_economics(inputs: CommercialCalcInputs) -> CommercialCalcResult:
    flags: list[str] = []
    promo_mix = min(max(inputs.promo_mix_pct, 0.0), 1.0)
    promo_reserve_split = min(max(inputs.promo_reserve_split_pct, 0.0), 1.0)

    if inputs.target_units <= 0:
        flags.append("non_positive_target_units")
    if inputs.target_srp_local <= 0:
        flags.append("non_positive_target_srp")
    if inputs.fx_plan_currency_per_cost_currency <= 0:
        flags.append("invalid_fx_plan_currency_per_cost_currency")
    if inputs.controlled_cost_amount <= 0:
        flags.append("missing_or_invalid_controlled_cost")
    if inputs.customer_margin_pct + inputs.customer_rebate_pct + inputs.distributor_margin_pct >= 0.95:
        flags.append("impossible_margin_stack")

    promo_srp_local = inputs.promo_srp_local if inputs.promo_srp_local is not None else inputs.target_srp_local
    weighted_srp_local = (1.0 - promo_mix) * inputs.target_srp_local + promo_mix * promo_srp_local
    net_ex_vat_local = weighted_srp_local / (1.0 + max(inputs.vat_rate_pct, 0.0))

    channel_take_pct = inputs.customer_margin_pct + inputs.customer_rebate_pct + inputs.distributor_margin_pct
    sell_in_local = net_ex_vat_local * max(1.0 - channel_take_pct, 0.0)
    sell_in_econ = sell_in_local / max(inputs.fx_plan_currency_per_cost_currency, 1e-9)

    buy_price_econ = sell_in_econ * max(1.0 - inputs.distributor_margin_pct, 0.0)
    revenue_econ = sell_in_econ * inputs.target_units
    reserve_pool = max(inputs.reserve_total_pct, 0.0) * revenue_econ
    promo_reserve = reserve_pool * promo_reserve_split
    non_promo_reserve = reserve_pool - promo_reserve

    internal_gp_per_unit = buy_price_econ - inputs.controlled_cost_amount
    internal_gp = internal_gp_per_unit * inputs.target_units - promo_reserve - non_promo_reserve
    if internal_gp_per_unit < 0:
        flags.append("margin_floor_breach")
    if reserve_pool > revenue_econ * 0.8:
        flags.append("reserve_breach")
    if sell_in_econ <= 0:
        flags.append("impossible_economics")

    explanation = (
        f"Weighted list/campaign price local {weighted_srp_local:.2f} -> ex-VAT {net_ex_vat_local:.2f}; "
        f"sell-in (economics currency) {sell_in_econ:.2f} after customer+rebate+distributor stack {channel_take_pct:.2%}. "
        f"Reserve split campaign-support / non-campaign {promo_reserve:.2f}/{non_promo_reserve:.2f}."
    )
    return CommercialCalcResult(
        calc_oem_sell_in_amount=round(sell_in_econ, 4),
        calc_distributor_net_amount=round(buy_price_econ, 4),
        calc_campaign_support_reserve_amount=round(promo_reserve, 4),
        calc_non_campaign_reserve_amount=round(non_promo_reserve, 4),
        calc_internal_gp_amount=round(internal_gp, 4),
        calc_customer_margin_input_pct=round(inputs.customer_margin_pct, 4),
        calc_distributor_margin_input_pct=round(inputs.distributor_margin_pct, 4),
        flags=flags,
        explanation=explanation,
    )
