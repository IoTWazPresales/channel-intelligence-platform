"""Backwards lineup pricing: SRP -> Dealer -> Net -> Disti Cost -> DAP.

Pure deterministic module (no DB, no I/O), mirroring ``calculator.compute_line_economics``.
Computes the dollar DAP a PO is raised on by walking the agreed price chain backwards from
consumer SRP, then derives profit against the PM bottom (``controlled_cost``).

Chain (per unit, local currency unless noted), validated against the ACZA Consumer Lineup
workbook to the cent::

    SRP_ex_vat  = srp_inc_vat / (1 + vat_rate_pct)
    dealer      = SRP_ex_vat  * (1 - dealer_margin_pct)
    net         = dealer      * (1 - rebate_pct)            # agreed customer rebate
    disti_cost  = net         * (1 - distributor_margin_pct)
    pre_dap     = disti_cost  / (1 + import_tax_pct)        # import tax default 0
    dap (cost)  = pre_dap     / roe                         # roe = local units per 1 cost-ccy unit
    profit/unit = dap - controlled_cost                     # PM bottom; flag if absent
    profit_total= profit/unit * quantity_units

Margins are margin-on-selling-price (``* (1 - pct)``) and applied sequentially (compounding),
matching how the PM team's lineup spreadsheet builds the chain. Percentages are fractions
(e.g. VAT 15% -> 0.15).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineupPricingInputs:
    srp_inc_vat_local: float
    vat_rate_pct: float
    dealer_margin_pct: float
    rebate_pct: float
    distributor_margin_pct: float
    import_tax_pct: float
    roe_local_per_cost_currency: float
    controlled_cost_amount: float | None
    quantity_units: float | None


@dataclass(frozen=True)
class LineupPricingResult:
    calc_srp_ex_vat_local: float
    calc_dealer_price_local: float
    calc_net_price_local: float
    calc_disti_cost_local: float
    calc_pre_dap_local: float
    calc_dap_cost_currency: float
    calc_profit_per_unit: float | None
    calc_profit_total: float | None
    flags: list[str]
    explanation: str


_ZERO = LineupPricingResult(
    calc_srp_ex_vat_local=0.0,
    calc_dealer_price_local=0.0,
    calc_net_price_local=0.0,
    calc_disti_cost_local=0.0,
    calc_pre_dap_local=0.0,
    calc_dap_cost_currency=0.0,
    calc_profit_per_unit=None,
    calc_profit_total=None,
    flags=[],
    explanation="",
)


def compute_lineup_pricing(inputs: LineupPricingInputs) -> LineupPricingResult:
    flags: list[str] = []

    srp = inputs.srp_inc_vat_local or 0.0
    vat = max(inputs.vat_rate_pct or 0.0, 0.0)
    dealer_m = inputs.dealer_margin_pct or 0.0
    rebate = inputs.rebate_pct or 0.0
    disti_m = inputs.distributor_margin_pct or 0.0
    import_tax = max(inputs.import_tax_pct or 0.0, 0.0)
    roe = inputs.roe_local_per_cost_currency or 0.0

    if srp <= 0:
        flags.append("missing_or_invalid_srp")
    if roe <= 0:
        flags.append("invalid_roe")
    for pct, flag in (
        (dealer_m, "invalid_dealer_margin"),
        (rebate, "invalid_rebate"),
        (disti_m, "invalid_distributor_margin"),
    ):
        if pct >= 1.0 or pct < 0.0:
            flags.append(flag)

    # Cannot derive a meaningful DAP without a positive SRP and ROE.
    if srp <= 0 or roe <= 0 or any(
        f in flags for f in ("invalid_dealer_margin", "invalid_rebate", "invalid_distributor_margin")
    ):
        return LineupPricingResult(
            calc_srp_ex_vat_local=0.0,
            calc_dealer_price_local=0.0,
            calc_net_price_local=0.0,
            calc_disti_cost_local=0.0,
            calc_pre_dap_local=0.0,
            calc_dap_cost_currency=0.0,
            calc_profit_per_unit=None,
            calc_profit_total=None,
            flags=list(dict.fromkeys(flags)),
            explanation="Pricing not computable: " + ", ".join(dict.fromkeys(flags)),
        )

    srp_ex_vat = srp / (1.0 + vat)
    dealer_price = srp_ex_vat * (1.0 - dealer_m)
    net_price = dealer_price * (1.0 - rebate)
    disti_cost = net_price * (1.0 - disti_m)
    pre_dap = disti_cost / (1.0 + import_tax)
    dap = pre_dap / roe

    controlled_cost = inputs.controlled_cost_amount
    profit_per_unit: float | None = None
    profit_total: float | None = None
    if controlled_cost is None or controlled_cost <= 0:
        flags.append("missing_pm_bottom")
    else:
        profit_per_unit = dap - controlled_cost
        if profit_per_unit < 0:
            flags.append("negative_profit")
        units = inputs.quantity_units
        if units is not None and units > 0:
            profit_total = profit_per_unit * units
        else:
            flags.append("missing_quantity")

    explanation = (
        f"SRP {srp:.2f} incl VAT {vat:.2%} -> ex-VAT {srp_ex_vat:.2f}; "
        f"dealer {dealer_price:.2f} (-{dealer_m:.2%}) -> net {net_price:.2f} (-rebate {rebate:.2%}) "
        f"-> disti cost {disti_cost:.2f} (-{disti_m:.2%}); "
        f"pre-DAP {pre_dap:.2f} (import tax {import_tax:.2%}) / ROE {roe:.4f} = DAP {dap:.4f}."
    )

    return LineupPricingResult(
        calc_srp_ex_vat_local=round(srp_ex_vat, 4),
        calc_dealer_price_local=round(dealer_price, 4),
        calc_net_price_local=round(net_price, 4),
        calc_disti_cost_local=round(disti_cost, 4),
        calc_pre_dap_local=round(pre_dap, 4),
        calc_dap_cost_currency=round(dap, 4),
        calc_profit_per_unit=round(profit_per_unit, 4) if profit_per_unit is not None else None,
        calc_profit_total=round(profit_total, 4) if profit_total is not None else None,
        flags=list(dict.fromkeys(flags)),
        explanation=explanation,
    )
