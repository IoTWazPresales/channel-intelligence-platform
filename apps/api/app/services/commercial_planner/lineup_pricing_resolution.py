"""Resolve a lineup line's pricing chain from file evidence + trade-term fallbacks.

Deterministic, DB-free. The parser supplies already-loaded fallback scalars (PM bottom,
VAT, ROE, margins, rebate) from ``commercial_sku_assumption`` / ``commercial_customer_term`` /
``commercial_distributor_term``; this module decides — per input — whether the file column
value or the trade-term default is used, runs ``compute_lineup_pricing`` (backwards SRP -> DAP),
and returns the calculator result plus a ``pricing_chain_json`` audit dict recording inputs,
their provenance, evidence columns, outputs, flags, and the human explanation.

Hard constraints:
- PM bottom (``controlled_cost``) is read from ``commercial_sku_assumption`` only — never from
  the file, never written back to it.
- File evidence (Actual DAP, Net price, etc.) is preserved for audit but never used as cost.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# ``commercial_lineup_line.*_pct_evidence`` columns are Numeric(8, 4). Whole-number percents
# (e.g. 15 for 15%) and fractions (0.15) are valid; currency amounts mis-labelled as margin/rebate
# (e.g. 74_347 on a 94_999 SRP row) must be dropped before persistence.
_MAX_WHOLE_NUMBER_PCT_EVIDENCE = 100.0

from app.services.commercial_planner.lineup_pricing import (
    LineupPricingInputs,
    LineupPricingResult,
    compute_lineup_pricing,
)


@dataclass(frozen=True)
class LineupTradeTermDefaults:
    """Fallback scalars resolved from trade-term tables for one line (may be all None)."""

    dealer_margin_pct: float | None = None  # commercial_customer_term.customer_margin_pct
    rebate_pct: float | None = None  # commercial_customer_term.customer_rebate_pct
    distributor_margin_pct: float | None = None  # commercial_distributor_term.distributor_margin_pct
    vat_rate_pct: float | None = None  # commercial_sku_assumption.vat_rate_pct
    roe_local_per_cost_currency: float | None = None  # commercial_sku_assumption.fx_plan_currency_per_cost_currency
    controlled_cost_amount: float | None = None  # commercial_sku_assumption.controlled_cost_amount


@dataclass(frozen=True)
class LineupPricingResolution:
    result: LineupPricingResult
    pricing_chain: dict[str, Any]
    flags: list[str]


def sanitize_pct_evidence(
    value: float | None,
    *,
    reference_price: float | None = None,
) -> float | None:
    """Reject file values that cannot plausibly be a margin/rebate/VAT percentage.

    Lineup workbooks often label currency amounts as "Dealer margin" or "Rebate". Those values
    remain in ``raw_row_payload`` for audit; only plausible percentages are stored on
    ``*_pct_evidence`` columns.
    """
    if value is None:
        return None
    v = float(value)
    if not math.isfinite(v):
        return None
    av = abs(v)
    if av <= _MAX_WHOLE_NUMBER_PCT_EVIDENCE:
        return v
    if reference_price is not None and reference_price > 0 and av <= reference_price:
        return None
    return None


def _as_fraction(value: float | None) -> float | None:
    """Normalise a percentage that may be expressed as a whole number (15 -> 0.15).

    Margins/rebate/VAT/import-tax are fractions in the calculator. File columns are commonly
    entered as ``15`` or ``45`` (percent) rather than ``0.15``. Values with magnitude > 1 are
    treated as whole-number percentages. ROE is NOT passed through here (it can legitimately
    exceed 1, e.g. ~18 ZAR per USD).
    """
    if value is None:
        return None
    if abs(value) > 1.0:
        return value / 100.0
    return value


def _pick(file_value: float | None, term_value: float | None, *, normalise_pct: bool) -> tuple[float | None, str]:
    """Choose file value over term default; return (value, source)."""
    if file_value is not None:
        return (_as_fraction(file_value) if normalise_pct else file_value), "file"
    if term_value is not None:
        # Trade-term values are already stored as fractions; do not re-normalise.
        return term_value, "trade_term"
    return None, "default"


def resolve_lineup_pricing(
    *,
    srp_inc_vat_local: float | None,
    quantity_units: float | None,
    file_vat_pct: float | None = None,
    file_dealer_margin_pct: float | None = None,
    file_rebate_pct: float | None = None,
    file_distributor_margin_pct: float | None = None,
    file_import_tax_pct: float | None = None,
    file_roe: float | None = None,
    defaults: LineupTradeTermDefaults | None = None,
    evidence: dict[str, float | None] | None = None,
) -> LineupPricingResolution:
    """Resolve inputs (file over trade-term) and run the backwards pricing calculator."""
    defaults = defaults or LineupTradeTermDefaults()
    sources: dict[str, str] = {}

    vat, sources["vat_rate_pct"] = _pick(file_vat_pct, defaults.vat_rate_pct, normalise_pct=True)
    dealer_m, sources["dealer_margin_pct"] = _pick(
        file_dealer_margin_pct, defaults.dealer_margin_pct, normalise_pct=True
    )
    rebate, sources["rebate_pct"] = _pick(file_rebate_pct, defaults.rebate_pct, normalise_pct=True)
    disti_m, sources["distributor_margin_pct"] = _pick(
        file_distributor_margin_pct, defaults.distributor_margin_pct, normalise_pct=True
    )
    import_tax, sources["import_tax_pct"] = _pick(file_import_tax_pct, None, normalise_pct=True)
    roe, sources["roe_local_per_cost_currency"] = _pick(
        file_roe, defaults.roe_local_per_cost_currency, normalise_pct=False
    )
    sources["controlled_cost_amount"] = (
        "sku_assumption" if defaults.controlled_cost_amount is not None else "missing"
    )

    inputs = LineupPricingInputs(
        srp_inc_vat_local=srp_inc_vat_local or 0.0,
        vat_rate_pct=vat or 0.0,
        dealer_margin_pct=dealer_m or 0.0,
        rebate_pct=rebate or 0.0,
        distributor_margin_pct=disti_m or 0.0,
        import_tax_pct=import_tax or 0.0,
        roe_local_per_cost_currency=roe or 0.0,
        controlled_cost_amount=defaults.controlled_cost_amount,
        quantity_units=quantity_units,
    )
    result = compute_lineup_pricing(inputs)

    pricing_chain: dict[str, Any] = {
        "inputs": {
            "srp_inc_vat_local": inputs.srp_inc_vat_local,
            "vat_rate_pct": inputs.vat_rate_pct,
            "dealer_margin_pct": inputs.dealer_margin_pct,
            "rebate_pct": inputs.rebate_pct,
            "distributor_margin_pct": inputs.distributor_margin_pct,
            "import_tax_pct": inputs.import_tax_pct,
            "roe_local_per_cost_currency": inputs.roe_local_per_cost_currency,
            "controlled_cost_amount": inputs.controlled_cost_amount,
            "quantity_units": inputs.quantity_units,
        },
        "sources": sources,
        "outputs": {
            "calc_srp_ex_vat_local": result.calc_srp_ex_vat_local,
            "calc_dealer_price_local": result.calc_dealer_price_local,
            "calc_net_price_local": result.calc_net_price_local,
            "calc_disti_cost_local": result.calc_disti_cost_local,
            "calc_pre_dap_local": result.calc_pre_dap_local,
            "calc_dap_cost_currency": result.calc_dap_cost_currency,
            "calc_profit_per_unit": result.calc_profit_per_unit,
            "calc_profit_total": result.calc_profit_total,
        },
        "evidence": {k: v for k, v in (evidence or {}).items() if v is not None},
        "flags": result.flags,
        "explanation": result.explanation,
    }

    return LineupPricingResolution(result=result, pricing_chain=pricing_chain, flags=result.flags)
