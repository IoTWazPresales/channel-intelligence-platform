"""A1-09 Support bias — planned campaign reservation vs actual CPOR support.

CPOR-owned (not Plan vs Executed). Planned reservation is derived_from_profit:
SKU ``reserve_total_pct`` × sell-in economics on case ``estimate_qty`` (campaign split).
Actual = Σ non-voided ``ttl_support_usd``. Missing SKU assumption → no fabricated zero.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.commercial_planner import (
    CommercialCustomerTerm,
    CommercialDistributorTerm,
    CommercialSkuAssumption,
)
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer, DimProduct
from app.services.commercial_planner.calculator import (
    CommercialCalcInputs,
    compute_line_economics,
)
from app.services.cpor.pivot import _line_ttl_support_usd, is_voided_line

DEFAULT_CUSTOMER_MARGIN = 0.12
DEFAULT_CUSTOMER_REBATE = 0.03
DEFAULT_DISTRIBUTOR_MARGIN = 0.08


def _f(v: Any, default: float | None = None) -> float | None:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _case_in_period(case: CporCase, period_start: date | None, period_end: date | None) -> bool:
    if period_start is None and period_end is None:
        return True
    ws, we = case.window_start, case.window_end
    if ws is None or we is None:
        return False
    if period_start is not None and we < period_start:
        return False
    if period_end is not None and ws > period_end:
        return False
    return True


def _planned_campaign_reserve_for_line(
    line: CporCaseLine,
    *,
    sku: CommercialSkuAssumption | None,
    cust_term: CommercialCustomerTerm | None,
    dist_term: CommercialDistributorTerm | None,
) -> dict[str, Any]:
    """Return planned campaign reserve for one case line, or a missing/invalid flag."""
    est = _f(line.estimate_qty, 0.0) or 0.0
    if est <= 0:
        return {
            "planned_usd": None,
            "flags": ["non_positive_estimate_qty"],
            "included": False,
        }
    if sku is None:
        return {
            "planned_usd": None,
            "flags": ["missing_sku_assumption"],
            "included": False,
        }
    cost = _f(sku.controlled_cost_amount)
    if cost is None or cost <= 0:
        return {
            "planned_usd": None,
            "flags": ["missing_sku_economics"],
            "included": False,
        }
    srp = _f(line.srp, 0.0) or 0.0
    if srp <= 0:
        return {
            "planned_usd": None,
            "flags": ["non_positive_srp"],
            "included": False,
        }

    cust_m = _f(line.dealer_margin_pct)
    if cust_m is None:
        cust_m = _f(
            cust_term.customer_margin_pct if cust_term else None, DEFAULT_CUSTOMER_MARGIN
        ) or DEFAULT_CUSTOMER_MARGIN
    cust_r = _f(cust_term.customer_rebate_pct if cust_term else None, DEFAULT_CUSTOMER_REBATE) or DEFAULT_CUSTOMER_REBATE
    dist_m = _f(
        dist_term.distributor_margin_pct if dist_term else None,
        DEFAULT_DISTRIBUTOR_MARGIN,
    ) or DEFAULT_DISTRIBUTOR_MARGIN

    # Promo case: treat volume as campaign (promo_mix=1) so campaign reserve is the planned support pool
    result = compute_line_economics(
        CommercialCalcInputs(
            target_units=est,
            target_srp_local=srp,
            promo_srp_local=srp,
            promo_mix_pct=1.0,
            fx_plan_currency_per_cost_currency=_f(sku.fx_plan_currency_per_cost_currency, 1.0) or 1.0,
            vat_rate_pct=_f(line.vat_rate, _f(sku.vat_rate_pct, 0.15)) or 0.15,
            controlled_cost_amount=cost,
            customer_margin_pct=float(cust_m),
            customer_rebate_pct=cust_r,
            distributor_margin_pct=float(dist_m),
            reserve_total_pct=_f(sku.reserve_total_pct, 0.0) or 0.0,
            promo_reserve_split_pct=_f(sku.promo_reserve_split_pct, 0.5) or 0.5,
        )
    )
    flags = list(result.flags)
    if "missing_or_invalid_controlled_cost" in flags or "impossible_economics" in flags:
        return {"planned_usd": None, "flags": flags + ["missing_sku_economics"], "included": False}

    return {
        "planned_usd": float(result.calc_campaign_support_reserve_amount),
        "flags": flags,
        "included": True,
        "explanation": result.explanation,
    }


def build_support_bias(
    session: Session,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    customer_id: int | None = None,
    case_id: int | None = None,
    limit_cases: int = 200,
) -> dict[str, Any]:
    """Portfolio (+ optional case) support bias read model."""
    q = (
        select(CporCase)
        .where(CporCase.superseded_by_case_id.is_(None))
        .options(joinedload(CporCase.lines))
    )
    if case_id is not None:
        q = q.where(CporCase.id == int(case_id))
    if customer_id is not None:
        q = q.where(CporCase.customer_id == int(customer_id))
    cases = list(session.scalars(q).unique().all())
    cases = [c for c in cases if _case_in_period(c, period_start, period_end)]
    cases = cases[: max(1, min(int(limit_cases), 500))]

    if not cases:
        return {
            "reservation_source": "derived_from_profit",
            "currency_compute": "USD",
            "period_start": period_start.isoformat() if period_start else None,
            "period_end": period_end.isoformat() if period_end else None,
            "cases_in_scope": 0,
            "totals": {
                "planned_usd": None,
                "actual_usd": 0.0,
                "bias_pct": None,
                "flags": ["no_cases_in_scope"],
            },
            "cases": [],
            "data_unavailable": False,
            "sku_assumption_seed_hint": "/commercial-planner (SKU economics) or admin product economics",
        }

    product_ids: set[int] = set()
    customer_ids: set[int] = set()
    distributor_ids: set[int] = set()
    for case in cases:
        customer_ids.add(int(case.customer_id))
        for line in case.lines or []:
            product_ids.add(int(line.product_id))
            if line.distributor_id is not None:
                distributor_ids.add(int(line.distributor_id))

    sku_by_pid = {
        int(r.product_id): r
        for r in session.scalars(
            select(CommercialSkuAssumption).where(
                CommercialSkuAssumption.product_id.in_(list(product_ids) or [-1])
            )
        ).all()
    }
    cust_terms = {
        int(r.customer_id): r
        for r in session.scalars(
            select(CommercialCustomerTerm).where(
                CommercialCustomerTerm.customer_id.in_(list(customer_ids) or [-1])
            )
        ).all()
    }
    dist_terms = {
        int(r.distributor_id): r
        for r in session.scalars(
            select(CommercialDistributorTerm).where(
                CommercialDistributorTerm.distributor_id.in_(list(distributor_ids) or [-1])
            )
        ).all()
    } if distributor_ids else {}

    cust_meta = {
        int(r[0]): (r[1], r[2])
        for r in session.execute(
            select(DimCustomer.id, DimCustomer.code, DimCustomer.name).where(
                DimCustomer.id.in_(list(customer_ids))
            )
        ).all()
    }
    prod_meta = {
        int(r[0]): (r[1], r[2])
        for r in session.execute(
            select(DimProduct.id, DimProduct.sku, DimProduct.name).where(
                DimProduct.id.in_(list(product_ids) or [-1])
            )
        ).all()
    }

    case_rows: list[dict[str, Any]] = []
    tot_planned = 0.0
    tot_actual = 0.0
    planned_lines = 0
    missing_sku_lines = 0
    any_planned = False

    for case in cases:
        actual = 0.0
        planned = 0.0
        case_flags: set[str] = set()
        line_details: list[dict[str, Any]] = []
        case_planned_ok = False

        for line in case.lines or []:
            if is_voided_line(line):
                continue
            est = _f(line.estimate_qty, 0.0) or 0.0
            if est <= 0:
                continue
            usd = _line_ttl_support_usd(line)
            if usd is not None:
                actual += float(usd)

            sku = sku_by_pid.get(int(line.product_id))
            plan = _planned_campaign_reserve_for_line(
                line,
                sku=sku,
                cust_term=cust_terms.get(int(case.customer_id)),
                dist_term=dist_terms.get(int(line.distributor_id))
                if line.distributor_id is not None
                else None,
            )
            for f in plan["flags"]:
                case_flags.add(f)
            if not plan["included"]:
                if "missing_sku_assumption" in plan["flags"] or "missing_sku_economics" in plan["flags"]:
                    missing_sku_lines += 1
                sku_m = prod_meta.get(int(line.product_id), (None, None))
                line_details.append(
                    {
                        "line_id": int(line.id),
                        "product_id": int(line.product_id),
                        "product_sku": sku_m[0],
                        "planned_usd": None,
                        "actual_usd": float(usd) if usd is not None else None,
                        "flags": plan["flags"],
                    }
                )
                continue

            planned += float(plan["planned_usd"] or 0.0)
            planned_lines += 1
            case_planned_ok = True
            any_planned = True
            sku_m = prod_meta.get(int(line.product_id), (None, None))
            line_details.append(
                {
                    "line_id": int(line.id),
                    "product_id": int(line.product_id),
                    "product_sku": sku_m[0],
                    "planned_usd": plan["planned_usd"],
                    "actual_usd": float(usd) if usd is not None else None,
                    "flags": plan["flags"],
                }
            )

        bias = None
        if case_planned_ok and planned > 0:
            bias = (actual - planned) / planned
            tot_planned += planned
        elif missing_sku_lines and not case_planned_ok:
            case_flags.add("missing_sku_assumption")

        tot_actual += actual
        code, name = cust_meta.get(int(case.customer_id), (None, None))
        case_rows.append(
            {
                "case_id": int(case.id),
                "case_code": case.case_code,
                "customer_id": int(case.customer_id),
                "customer_code": code,
                "customer_name": name,
                "window_start": case.window_start.isoformat() if case.window_start else None,
                "window_end": case.window_end.isoformat() if case.window_end else None,
                "planned_usd": planned if case_planned_ok else None,
                "actual_usd": actual,
                "bias_pct": bias,
                "flags": sorted(case_flags),
                "lines": line_details[:50],
            }
        )

    portfolio_bias = (tot_actual - tot_planned) / tot_planned if any_planned and tot_planned > 0 else None
    tot_flags: list[str] = []
    if not any_planned:
        tot_flags.append("missing_sku_assumption" if missing_sku_lines else "no_plannable_lines")
    if missing_sku_lines:
        tot_flags.append("partial_missing_sku_assumption")

    return {
        "reservation_source": "derived_from_profit",
        "currency_compute": "USD",
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "cases_in_scope": len(case_rows),
        "planned_lines_included": planned_lines,
        "missing_sku_lines": missing_sku_lines,
        "totals": {
            "planned_usd": tot_planned if any_planned else None,
            "actual_usd": tot_actual,
            "bias_pct": portfolio_bias,
            "flags": tot_flags,
        },
        "cases": case_rows,
        "data_unavailable": False,
        "sku_assumption_seed_hint": (
            "Seed via POST /api/v1/commercial-planner/sku-assumptions or "
            "Commercial Planner SKU economics / product admin panel"
        ),
    }
