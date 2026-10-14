"""CPOR case margin under the one profit definition (N-0080, spec §9 item 3).

Margin is measured against PM controlled cost (``commercial_sku_assumption``), the same
definition lineup profitability reads (``app.services.profit_definition``):

    DAP / unit   = lineup backwards chain from the line's SRP, VAT and dealer margin, with the
                   customer rebate and distributor margin from trade terms, / case ROE (USD)
    margin / unit = DAP - PM controlled cost - support / unit (USD)
    margin total  = margin / unit * units (result qty when recorded, else estimate qty)

DAP and landed cost are returned beside the margin and never folded into it. Read-only: no
case line is written. Missing inputs are flagged (FLAG != BLOCK), never filled with zero.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commercial_planner import (
    CommercialCustomerTerm,
    CommercialDistributorTerm,
    CommercialSkuAssumption,
)
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimProduct
from app.services.commercial_planner.lineup_pricing import LineupPricingInputs, compute_lineup_pricing
from app.services.cpor.pivot import is_voided_line
from app.services.profit_definition import FIGURE_LABELS, HEADLINE_COST_BASIS, compute_profit, profit_payload

MARGIN_CURRENCY = "USD"


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _line_margin(
    line: CporCaseLine,
    *,
    roe: float | None,
    sku: CommercialSkuAssumption | None,
    rebate_pct: float | None,
    distributor_margin_pct: float | None,
) -> dict[str, Any]:
    flags: list[str] = []
    if rebate_pct is None:
        flags.append("no_customer_rebate_term")
    if distributor_margin_pct is None:
        flags.append("no_distributor_margin_term")
    if roe is None or roe <= 0:
        flags.append("no_case_roe")

    dap: float | None = None
    if roe is not None and roe > 0:
        pricing = compute_lineup_pricing(
            LineupPricingInputs(
                srp_inc_vat_local=_f(line.srp) or 0.0,
                vat_rate_pct=_f(line.vat_rate) or 0.0,
                dealer_margin_pct=_f(line.dealer_margin_pct) or 0.0,
                rebate_pct=rebate_pct or 0.0,
                distributor_margin_pct=distributor_margin_pct or 0.0,
                import_tax_pct=0.0,
                roe_local_per_cost_currency=roe,
                controlled_cost_amount=None,
                quantity_units=None,
            )
        )
        dap = pricing.calc_dap_cost_currency or None

    pm_cost: float | None = None
    landed: float | None = None
    if sku is None:
        flags.append("no_sku_economics")
    else:
        ccy = (sku.controlled_cost_currency_code or "USD").strip().upper()
        if ccy != MARGIN_CURRENCY:
            # Margin is in USD (case ROE). A cost in another currency is not converted silently.
            flags.append("cost_currency_not_usd")
        else:
            pm_cost = _f(sku.controlled_cost_amount)
            landed = _f(sku.landed_cost_amount)

    result_qty = _f(line.result_qty)
    units = result_qty if result_qty is not None else _f(line.estimate_qty)
    fig = compute_profit(
        dap_per_unit=dap,
        pm_controlled_cost=pm_cost,
        landed_cost=landed,
        units=units,
        support_per_unit=_f(line.support_usd),
        currency=MARGIN_CURRENCY,
    )
    payload = profit_payload(fig)
    payload["flags"] = list(dict.fromkeys(flags + payload["flags"]))
    payload["line_id"] = line.id
    payload["product_id"] = line.product_id
    payload["units_source"] = "result_qty" if result_qty is not None else "estimate_qty"
    return payload


def build_case_margin(session: Session, case: CporCase) -> dict[str, Any]:
    lines = [
        ln
        for ln in session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case.id).order_by(CporCaseLine.id))
        if not is_voided_line(ln)
    ]
    product_ids = sorted({int(ln.product_id) for ln in lines})
    dist_ids = sorted({int(ln.distributor_id) for ln in lines if ln.distributor_id is not None})
    skus = {
        int(s.product_id): s
        for s in session.scalars(
            select(CommercialSkuAssumption).where(CommercialSkuAssumption.product_id.in_(product_ids))
        )
    } if product_ids else {}
    products = {
        int(p.id): p for p in session.scalars(select(DimProduct).where(DimProduct.id.in_(product_ids)))
    } if product_ids else {}
    dist_terms = {
        int(t.distributor_id): t
        for t in session.scalars(
            select(CommercialDistributorTerm).where(CommercialDistributorTerm.distributor_id.in_(dist_ids))
        )
    } if dist_ids else {}
    cust_term = session.scalar(
        select(CommercialCustomerTerm).where(CommercialCustomerTerm.customer_id == case.customer_id)
    )
    rebate = _f(cust_term.customer_rebate_pct) if cust_term is not None else None
    roe = _f(case.roe_snapshot)

    out_lines: list[dict[str, Any]] = []
    margin_total = 0.0
    included = 0
    for ln in lines:
        dt = dist_terms.get(int(ln.distributor_id)) if ln.distributor_id is not None else None
        row = _line_margin(
            ln,
            roe=roe,
            sku=skus.get(int(ln.product_id)),
            rebate_pct=rebate,
            distributor_margin_pct=_f(dt.distributor_margin_pct) if dt is not None else None,
        )
        prod = products.get(int(ln.product_id))
        row["product_sku"] = prod.sku if prod else None
        row["product_name"] = prod.name if prod else None
        if row["margin_total"] is not None:
            margin_total += float(row["margin_total"])
            included += 1
        out_lines.append(row)

    return {
        "case_id": case.id,
        "cost_basis": HEADLINE_COST_BASIS,
        "currency": MARGIN_CURRENCY,
        "labels": dict(FIGURE_LABELS),
        "definition": (
            "Margin = DAP - PM controlled cost - support, per unit, times units. DAP and landed cost are "
            "shown beside it and are not folded into the margin."
        ),
        "roe": roe,
        "margin_total": round(margin_total, 4) if included else None,
        "lines_included": included,
        "lines_total": len(out_lines),
        "lines": out_lines,
    }
