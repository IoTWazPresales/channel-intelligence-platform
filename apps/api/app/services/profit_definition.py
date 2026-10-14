"""One profit definition for lineup profitability and CPOR margin (N-0080, spec §9 item 3).

Warren 2026-10-12 (D-0052, accepted): the headline margin is measured against **PM controlled
cost** (``commercial_sku_assumption.controlled_cost_amount``, the PM bottom). DAP and landed cost
are shown beside it as their own figures and are never folded into that margin.

    margin / unit = DAP / unit - PM controlled cost / unit - support / unit   (support: CPOR only)
    margin total  = margin / unit * units
    margin %      = margin / unit / DAP / unit

DAP is the price the company invoices the distributor (revenue side). Landed cost is reported,
never subtracted. Pure and DB-free; callers resolve inputs and keep them in one currency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

HEADLINE_COST_BASIS = "pm_controlled_cost"

FIGURE_LABELS: dict[str, str] = {
    "margin": "Margin vs PM controlled cost",
    "pm_controlled_cost": "PM controlled cost",
    "dap": "DAP (price to distributor)",
    "landed_cost": "Landed cost (shown, not in margin)",
    "support": "Support",
}


@dataclass(frozen=True)
class ProfitFigures:
    currency: str | None
    units: float | None
    dap_per_unit: float | None
    pm_controlled_cost_per_unit: float | None
    landed_cost_per_unit: float | None
    support_per_unit: float | None
    margin_per_unit: float | None
    margin_total: float | None
    margin_pct: float | None
    cost_basis: str = HEADLINE_COST_BASIS
    flags: list[str] = field(default_factory=list)


def _pos(v: float | None) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def compute_profit(
    *,
    dap_per_unit: float | None,
    pm_controlled_cost: float | None,
    landed_cost: float | None = None,
    units: float | None = None,
    support_per_unit: float | None = None,
    currency: str | None = None,
) -> ProfitFigures:
    """Margin against PM controlled cost; DAP and landed cost returned beside it."""
    flags: list[str] = []
    dap = _pos(dap_per_unit)
    cost = _pos(pm_controlled_cost)
    landed = _pos(landed_cost)
    support = float(support_per_unit) if support_per_unit is not None else None
    qty = float(units) if units is not None else None

    if dap is None:
        flags.append("missing_dap")
    if cost is None:
        flags.append("missing_pm_controlled_cost")
    if landed is None:
        flags.append("landed_cost_not_recorded")

    margin_unit: float | None = None
    margin_total: float | None = None
    margin_pct: float | None = None
    if dap is not None and cost is not None:
        margin_unit = dap - cost - (support or 0.0)
        margin_pct = margin_unit / dap
        if margin_unit < 0:
            flags.append("negative_margin")
        if qty is not None and qty > 0:
            margin_total = margin_unit * qty
        else:
            flags.append("missing_quantity")

    return ProfitFigures(
        currency=currency,
        units=qty,
        dap_per_unit=round(dap, 4) if dap is not None else None,
        pm_controlled_cost_per_unit=round(cost, 4) if cost is not None else None,
        landed_cost_per_unit=round(landed, 4) if landed is not None else None,
        support_per_unit=round(support, 4) if support is not None else None,
        margin_per_unit=round(margin_unit, 4) if margin_unit is not None else None,
        margin_total=round(margin_total, 4) if margin_total is not None else None,
        margin_pct=round(margin_pct, 4) if margin_pct is not None else None,
        flags=flags,
    )


def profit_payload(fig: ProfitFigures) -> dict[str, Any]:
    """API shape: every figure carries its own name so the UI never shows an unnamed margin."""
    return {
        "cost_basis": fig.cost_basis,
        "cost_basis_label": FIGURE_LABELS["pm_controlled_cost"],
        "currency": fig.currency,
        "units": fig.units,
        "margin_per_unit": fig.margin_per_unit,
        "margin_total": fig.margin_total,
        "margin_pct": fig.margin_pct,
        "dap_per_unit": fig.dap_per_unit,
        "pm_controlled_cost_per_unit": fig.pm_controlled_cost_per_unit,
        "landed_cost_per_unit": fig.landed_cost_per_unit,
        "support_per_unit": fig.support_per_unit,
        "labels": dict(FIGURE_LABELS),
        "flags": list(fig.flags),
    }
