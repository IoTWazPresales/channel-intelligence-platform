"""BACKLOG-093 — case-scoped promo load recon (CST vs approved CPOR terms).

Evidence: ``fact_customer_sellthrough`` only. Never DSI sell-out.
Settlement claim-vs-CST stays separate (``settlement.compute_cst_divergence_flags``).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.cpor.pivot import is_voided_line

# Relative |cst_price - expected| / expected
PROMO_LOAD_PRICE_REL_TOLERANCE = 0.02
# Near-miss band outside window for wrong_window bucket
WINDOW_NEAR_MISS_DAYS = 14


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _expected_shelf_price(line: CporCaseLine) -> float | None:
    """Preferred expected retail/dealer shelf for price check."""
    for cand in (line.dealer_price, line.srp):
        p = _f(cand)
        if p is not None and p > 0:
            return p
    return None


def _classify_line(
    *,
    cst_in_window_units: float,
    cst_in_window_price_wtd: float | None,
    cst_near_miss_units: float,
    expected_price: float | None,
    price_tol: float,
) -> str:
    if cst_in_window_units <= 0:
        if cst_near_miss_units > 0:
            return "wrong_window"
        return "missing_load"
    if expected_price is None or expected_price <= 0:
        return "ok" if cst_in_window_price_wtd is None else "ok"
    if cst_in_window_price_wtd is None:
        return "price_unknown"
    rel = abs(cst_in_window_price_wtd - expected_price) / abs(expected_price)
    if rel > price_tol:
        return "wrong_price"
    return "ok"


def build_promo_load_recon(
    session: Session,
    case_id: int,
    *,
    price_tol: float = PROMO_LOAD_PRICE_REL_TOLERANCE,
) -> dict[str, Any]:
    case = session.scalars(
        select(CporCase)
        .where(CporCase.id == int(case_id))
        .options(joinedload(CporCase.lines))
    ).unique().first()
    if case is None:
        raise ValueError(f"cpor_case id={case_id} not found")

    cid = int(case.customer_id)
    ws, we = case.window_start, case.window_end

    # Any CST for this customer at all?
    any_cst = session.scalar(
        select(func.count())
        .select_from(FactCustomerSellthrough)
        .where(FactCustomerSellthrough.customer_id == cid)
    )
    if not any_cst:
        return {
            "case_id": int(case.id),
            "customer_id": cid,
            "window_start": ws.isoformat() if ws else None,
            "window_end": we.isoformat() if we else None,
            "cst_available": False,
            "data_unavailable": True,
            "reason": "no_cst",
            "price_tolerance": float(price_tol),
            "lines": [],
            "summary": {
                "ok": 0,
                "missing_load": 0,
                "wrong_window": 0,
                "wrong_price": 0,
                "price_unknown": 0,
                "no_cst": 1,
            },
            "cst_vintage": {"max_period_start_date": None},
            "import_steward_hint": "/admin/imports (customer_sell_through) or /admin/cst-steward",
        }

    if ws is None or we is None:
        return {
            "case_id": int(case.id),
            "customer_id": cid,
            "window_start": None,
            "window_end": None,
            "cst_available": True,
            "data_unavailable": True,
            "reason": "missing_window",
            "price_tolerance": float(price_tol),
            "lines": [],
            "summary": {
                "ok": 0,
                "missing_load": 0,
                "wrong_window": 0,
                "wrong_price": 0,
                "price_unknown": 0,
                "no_cst": 0,
            },
            "cst_vintage": {"max_period_start_date": None},
            "import_steward_hint": "/admin/imports (customer_sell_through) or /admin/cst-steward",
        }

    product_ids = sorted(
        {
            int(ln.product_id)
            for ln in (case.lines or [])
            if not is_voided_line(ln) and (_f(ln.estimate_qty) or 0) > 0
        }
    )
    if not product_ids:
        return {
            "case_id": int(case.id),
            "customer_id": cid,
            "window_start": ws.isoformat(),
            "window_end": we.isoformat(),
            "cst_available": True,
            "data_unavailable": False,
            "reason": "no_estimate_lines",
            "price_tolerance": float(price_tol),
            "lines": [],
            "summary": {
                "ok": 0,
                "missing_load": 0,
                "wrong_window": 0,
                "wrong_price": 0,
                "price_unknown": 0,
                "no_cst": 0,
            },
            "cst_vintage": {"max_period_start_date": None},
            "import_steward_hint": "/admin/imports (customer_sell_through) or /admin/cst-steward",
        }

    near_start = ws - timedelta(days=WINDOW_NEAR_MISS_DAYS)
    near_end = we + timedelta(days=WINDOW_NEAR_MISS_DAYS)

    cst_rows = session.execute(
        select(
            FactCustomerSellthrough.product_id,
            FactCustomerSellthrough.period_start_date,
            FactCustomerSellthrough.units_sold,
            FactCustomerSellthrough.unit_sell_price,
        ).where(
            FactCustomerSellthrough.customer_id == cid,
            FactCustomerSellthrough.product_id.in_(product_ids),
            FactCustomerSellthrough.period_start_date >= near_start,
            FactCustomerSellthrough.period_start_date <= near_end,
        )
    ).all()

    max_period = session.scalar(
        select(func.max(FactCustomerSellthrough.period_start_date)).where(
            FactCustomerSellthrough.customer_id == cid
        )
    )

    # Aggregate per product
    in_win_units: dict[int, float] = defaultdict(float)
    in_win_price_num: dict[int, float] = defaultdict(float)
    in_win_price_den: dict[int, float] = defaultdict(float)
    near_units: dict[int, float] = defaultdict(float)

    for pid, pstart, units, price in cst_rows:
        pid_i = int(pid)
        u = float(units or 0)
        if u == 0:
            continue
        if ws <= pstart <= we:
            in_win_units[pid_i] += u
            pr = _f(price)
            if pr is not None and pr > 0:
                in_win_price_num[pid_i] += pr * u
                in_win_price_den[pid_i] += u
        else:
            near_units[pid_i] += u

    prod_meta = {
        int(r[0]): (r[1], r[2])
        for r in session.execute(
            select(DimProduct.id, DimProduct.sku, DimProduct.name).where(
                DimProduct.id.in_(product_ids)
            )
        ).all()
    }

    # One recon row per product (rollup multi-distributor case lines)
    by_product_lines: dict[int, list[CporCaseLine]] = defaultdict(list)
    for ln in case.lines or []:
        if is_voided_line(ln):
            continue
        if (_f(ln.estimate_qty) or 0) <= 0:
            continue
        by_product_lines[int(ln.product_id)].append(ln)

    summary = {
        "ok": 0,
        "missing_load": 0,
        "wrong_window": 0,
        "wrong_price": 0,
        "price_unknown": 0,
        "no_cst": 0,
    }
    out_lines: list[dict[str, Any]] = []

    for pid, lines in sorted(by_product_lines.items()):
        est = sum(_f(ln.estimate_qty) or 0.0 for ln in lines)
        res = sum(_f(ln.result_qty) or 0.0 for ln in lines if ln.result_qty is not None)
        # Prefer first line with dealer_price / srp
        expected = None
        support_unit = None
        srp = None
        for ln in lines:
            expected = _expected_shelf_price(ln)
            support_unit = _f(ln.support_unit)
            srp = _f(ln.srp)
            if expected is not None:
                break

        wtd = None
        if in_win_price_den.get(pid, 0) > 0:
            wtd = in_win_price_num[pid] / in_win_price_den[pid]

        bucket = _classify_line(
            cst_in_window_units=in_win_units.get(pid, 0.0),
            cst_in_window_price_wtd=wtd,
            cst_near_miss_units=near_units.get(pid, 0.0),
            expected_price=expected,
            price_tol=float(price_tol),
        )
        summary[bucket] = summary.get(bucket, 0) + 1
        sku, name = prod_meta.get(pid, (None, None))
        out_lines.append(
            {
                "product_id": pid,
                "product_sku": sku,
                "product_name": name,
                "estimate_qty": est,
                "result_qty": res if res else None,
                "srp": srp,
                "support_unit": support_unit,
                "expected_shelf_price": expected,
                "cst_units": in_win_units.get(pid, 0.0),
                "cst_near_miss_units": near_units.get(pid, 0.0),
                "cst_unit_sell_price_wtd": wtd,
                "bucket": bucket,
                "flags": [bucket] if bucket != "ok" else [],
            }
        )

    return {
        "case_id": int(case.id),
        "customer_id": cid,
        "window_start": ws.isoformat(),
        "window_end": we.isoformat(),
        "cst_available": True,
        "data_unavailable": False,
        "reason": None,
        "price_tolerance": float(price_tol),
        "lines": out_lines,
        "summary": summary,
        "cst_vintage": {
            "max_period_start_date": max_period.isoformat() if max_period else None
        },
        "import_steward_hint": "/admin/imports (customer_sell_through) or /admin/cst-steward",
    }
