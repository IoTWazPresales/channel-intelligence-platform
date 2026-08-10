"""CPOR portfolio intelligence (A2-U1) — A2-01 / A2-02 / A2-06.

Compute and aggregate in USD; ZAR is summed from each line's own totals (per-case FX).
Voided / zero-estimate lines excluded (same rule as pivot).
Claim rate (A2-03) is intentionally absent — see COMMERCIAL_SEMANTICS non-computable register.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer, DimProduct
from app.services.cpor.pivot import _line_ttl_support_usd, is_voided_line


def _line_ttl_support_zar(line: CporCaseLine) -> float | None:
    if line.ttl_support is None:
        return None
    try:
        return float(line.ttl_support)
    except (TypeError, ValueError):
        return None


def build_portfolio_intelligence(session: Session) -> dict[str, Any]:
    """Portfolio aggregates over non-superseded cases."""
    cases = list(
        session.scalars(
            select(CporCase)
            .where(CporCase.superseded_by_case_id.is_(None))
            .options(joinedload(CporCase.lines))
        ).unique().all()
    )
    if not cases:
        return _empty_payload(cases_in_scope=0, lines_included=0)

    customer_ids = {int(c.customer_id) for c in cases if c.customer_id is not None}
    cust_rows = (
        session.execute(
            select(DimCustomer.id, DimCustomer.code, DimCustomer.name).where(
                DimCustomer.id.in_(customer_ids)
            )
        ).all()
        if customer_ids
        else []
    )
    cust_meta = {int(r[0]): (r[1], r[2]) for r in cust_rows}

    product_ids: set[int] = set()
    for case in cases:
        for line in case.lines or []:
            if line.product_id is not None:
                product_ids.add(int(line.product_id))
    prod_rows = (
        session.execute(
            select(DimProduct.id, DimProduct.product_line).where(DimProduct.id.in_(product_ids))
        ).all()
        if product_ids
        else []
    )
    bu_by_product = {
        int(r[0]): (str(r[1]).strip() if r[1] else None) or "(unassigned)" for r in prod_rows
    }

    by_customer: dict[int, dict[str, float]] = defaultdict(
        lambda: {
            "support_usd": 0.0,
            "support_zar": 0.0,
            "estimate_qty": 0.0,
            "result_qty": 0.0,
        }
    )
    by_bu: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "support_usd": 0.0,
            "support_zar": 0.0,
            "estimate_qty": 0.0,
            "result_qty": 0.0,
        }
    )
    by_promo: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "support_usd": 0.0,
            "support_zar": 0.0,
            "estimate_qty": 0.0,
            "result_qty": 0.0,
        }
    )

    tot_usd = 0.0
    tot_zar = 0.0
    tot_est = 0.0
    tot_res = 0.0
    lines_included = 0
    lines_excluded_voided = 0

    for case in cases:
        promo = (case.promotion_type or "").strip() or "(unknown)"
        cid = int(case.customer_id)
        for line in case.lines or []:
            if is_voided_line(line):
                lines_excluded_voided += 1
                continue
            try:
                est = float(line.estimate_qty or 0)
            except (TypeError, ValueError):
                est = 0.0
            if est <= 0:
                lines_excluded_voided += 1
                continue

            usd = _line_ttl_support_usd(line)
            zar = _line_ttl_support_zar(line)
            usd_v = float(usd) if usd is not None else 0.0
            zar_v = float(zar) if zar is not None else 0.0
            res = float(line.result_qty) if line.result_qty is not None else 0.0

            tot_usd += usd_v
            tot_zar += zar_v
            tot_est += est
            tot_res += res
            lines_included += 1

            bu = bu_by_product.get(int(line.product_id), "(unassigned)") if line.product_id else "(unassigned)"

            for bucket in (by_customer[cid], by_bu[bu], by_promo[promo]):
                bucket["support_usd"] += usd_v
                bucket["support_zar"] += zar_v
                bucket["estimate_qty"] += est
                bucket["result_qty"] += res

    delivery_rate = (tot_res / tot_est) if tot_est > 0 else None
    support_per_unit_usd = (tot_usd / tot_res) if tot_res > 0 else None
    support_per_unit_zar = (tot_zar / tot_res) if tot_res > 0 else None

    def _rate(bucket: dict[str, float]) -> float | None:
        e = bucket["estimate_qty"]
        return (bucket["result_qty"] / e) if e > 0 else None

    def _spu_usd(bucket: dict[str, float]) -> float | None:
        r = bucket["result_qty"]
        return (bucket["support_usd"] / r) if r > 0 else None

    def _spu_zar(bucket: dict[str, float]) -> float | None:
        r = bucket["result_qty"]
        return (bucket["support_zar"] / r) if r > 0 else None

    customers_out = []
    for cid, b in sorted(by_customer.items(), key=lambda kv: -kv[1]["support_usd"]):
        code, name = cust_meta.get(cid, (None, None))
        customers_out.append(
            {
                "customer_id": cid,
                "customer_code": code,
                "customer_name": name,
                "support_usd": round(b["support_usd"], 4),
                "support_zar": round(b["support_zar"], 4),
                "estimate_qty": round(b["estimate_qty"], 4),
                "result_qty": round(b["result_qty"], 4),
                "delivery_rate": _rate(b),
                "support_per_unit_sold_usd": _spu_usd(b),
                "support_per_unit_sold_zar": _spu_zar(b),
            }
        )

    bu_out = []
    for bu, b in sorted(by_bu.items(), key=lambda kv: -kv[1]["support_usd"]):
        bu_out.append(
            {
                "bu": bu,
                "support_usd": round(b["support_usd"], 4),
                "support_zar": round(b["support_zar"], 4),
                "estimate_qty": round(b["estimate_qty"], 4),
                "result_qty": round(b["result_qty"], 4),
                "delivery_rate": _rate(b),
                "support_per_unit_sold_usd": _spu_usd(b),
                "support_per_unit_sold_zar": _spu_zar(b),
            }
        )

    promo_out = []
    for promo, b in sorted(by_promo.items(), key=lambda kv: -kv[1]["support_usd"]):
        promo_out.append(
            {
                "promotion_type": promo,
                "support_usd": round(b["support_usd"], 4),
                "support_zar": round(b["support_zar"], 4),
                "estimate_qty": round(b["estimate_qty"], 4),
                "result_qty": round(b["result_qty"], 4),
                "delivery_rate": _rate(b),
                "support_per_unit_sold_usd": _spu_usd(b),
                "support_per_unit_sold_zar": _spu_zar(b),
            }
        )

    from app.services.cpor.incremental_unit_cost import build_portfolio_incremental_summary

    incremental = build_portfolio_incremental_summary(session)

    return {
        "currency_compute": "USD",
        "currency_display_secondary": "ZAR",
        "fx_note": (
            "ZAR totals sum each line at its case FX (booked or floating); "
            "never one period rate applied to a USD total."
        ),
        "cases_in_scope": len(cases),
        "lines_included": lines_included,
        "lines_excluded_voided": lines_excluded_voided,
        "totals": {
            "support_usd": round(tot_usd, 4),
            "support_zar": round(tot_zar, 4),
            "estimate_qty": round(tot_est, 4),
            "result_qty": round(tot_res, 4),
            "delivery_rate": delivery_rate,
            "support_per_unit_sold_usd": support_per_unit_usd,
            "support_per_unit_sold_zar": support_per_unit_zar,
        },
        "incremental_unit_cost": incremental,
        "by_customer": customers_out,
        "by_bu": bu_out,
        "by_promotion_type": promo_out,
    }


def _empty_payload(*, cases_in_scope: int, lines_included: int) -> dict[str, Any]:
    return {
        "currency_compute": "USD",
        "currency_display_secondary": "ZAR",
        "fx_note": (
            "ZAR totals sum each line at its case FX (booked or floating); "
            "never one period rate applied to a USD total."
        ),
        "cases_in_scope": cases_in_scope,
        "lines_included": lines_included,
        "lines_excluded_voided": 0,
        "totals": {
            "support_usd": 0.0,
            "support_zar": 0.0,
            "estimate_qty": 0.0,
            "result_qty": 0.0,
            "delivery_rate": None,
            "support_per_unit_sold_usd": None,
            "support_per_unit_sold_zar": None,
        },
        "by_customer": [],
        "by_bu": [],
        "by_promotion_type": [],
    }
