"""Plan readiness aggregation (shared by API and dashboard)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_planner import (
    CommercialCustomerTerm,
    CommercialDistributorTerm,
    CommercialPlan,
    CommercialPlanLine,
    CommercialSkuAssumption,
)
from app.services.commercial_planner.open_channel_customer import get_open_channel_customer_id
from app.services.commercial_planner.unassigned_distributor import get_unassigned_distributor_id


def _coerce_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _sku_assumption_invalid_controlled_cost(sku: CommercialSkuAssumption | None) -> bool:
    if sku is None:
        return False
    v = _coerce_float(sku.controlled_cost_amount)
    return v is None or v <= 0


def _sku_assumption_invalid_fx(sku: CommercialSkuAssumption | None) -> bool:
    if sku is None:
        return False
    v = _coerce_float(sku.fx_plan_currency_per_cost_currency)
    return v is None or v <= 0


def _sku_assumption_invalid_vat(sku: CommercialSkuAssumption | None) -> bool:
    if sku is None:
        return False
    v = _coerce_float(sku.vat_rate_pct)
    if v is None:
        return True
    return v < 0 or v > 1.0


def _sku_assumption_invalid_reserve(sku: CommercialSkuAssumption | None) -> bool:
    if sku is None:
        return False
    rt = _coerce_float(sku.reserve_total_pct)
    ps = _coerce_float(sku.promo_reserve_split_pct)
    if rt is None or ps is None:
        return True
    if rt < 0 or rt > 1.0 or ps < 0 or ps > 1.0:
        return True
    return False


async def compute_plan_readiness_payload(db: AsyncSession, plan_id: int) -> dict | None:
    """Plan-level readiness; returns None when plan does not exist."""
    plan = await db.get(CommercialPlan, plan_id)
    if not plan:
        return None

    rows = (
        await db.execute(select(CommercialPlanLine).where(CommercialPlanLine.commercial_plan_id == plan_id))
    ).scalars().all()

    open_channel_dim_ok = await get_open_channel_customer_id(db) is not None
    unassigned_distributor_id = await get_unassigned_distributor_id(db)
    unassigned_dim_ok = unassigned_distributor_id is not None

    if not rows:
        parts0: list[str] = []
        if not open_channel_dim_ok:
            parts0.append(
                "Admin/setup: dim_customer OPEN_CHANNEL missing — run `alembic upgrade head` or "
                "`python scripts/seed.py --commercial-system-reference-only`."
            )
        if not unassigned_dim_ok:
            parts0.append(
                "Admin/setup: dim_distributor UNASSIGNED missing — run `alembic upgrade head` or "
                "`python scripts/seed.py --commercial-system-reference-only`."
            )
        return {
            "plan_id": plan_id,
            "line_count": 0,
            "missing_customer_term": 0,
            "missing_distributor_term": 0,
            "missing_sku_assumption": 0,
            "invalid_controlled_cost": 0,
            "invalid_fx": 0,
            "invalid_vat": 0,
            "invalid_reserve": 0,
            "using_unassigned_distributor": 0,
            "lines_with_calc_flags": 0,
            "ready": open_channel_dim_ok and unassigned_dim_ok,
            "system_reference_open_channel_dim_ok": open_channel_dim_ok,
            "system_reference_unassigned_distributor_dim_ok": unassigned_dim_ok,
            "readiness_summary": ("; ".join(parts0) if parts0 else "No lines in plan."),
        }

    product_ids = list({r.product_id for r in rows})
    customer_ids = list({r.customer_id for r in rows})
    distributor_ids = list({r.distributor_id for r in rows})

    existing_cterms: set[int] = set(
        (await db.execute(
            select(CommercialCustomerTerm.customer_id).where(CommercialCustomerTerm.customer_id.in_(customer_ids))
        )).scalars().all()
    )
    existing_dterms: set[int] = set(
        (await db.execute(
            select(CommercialDistributorTerm.distributor_id).where(
                CommercialDistributorTerm.distributor_id.in_(distributor_ids)
            )
        )).scalars().all()
    )
    sku_rows = (
        await db.execute(select(CommercialSkuAssumption).where(CommercialSkuAssumption.product_id.in_(product_ids)))
    ).scalars().all()
    sku_by_product: dict[int, CommercialSkuAssumption] = {s.product_id: s for s in sku_rows}

    missing_ct = sum(1 for r in rows if r.customer_id not in existing_cterms)
    missing_dt = sum(1 for r in rows if r.distributor_id not in existing_dterms)
    missing_sku = sum(1 for r in rows if r.product_id not in sku_by_product)

    invalid_cc = invalid_fx = invalid_vat = invalid_res = 0
    for r in rows:
        sku = sku_by_product.get(r.product_id)
        if sku is None:
            continue
        if _sku_assumption_invalid_controlled_cost(sku):
            invalid_cc += 1
        if _sku_assumption_invalid_fx(sku):
            invalid_fx += 1
        if _sku_assumption_invalid_vat(sku):
            invalid_vat += 1
        if _sku_assumption_invalid_reserve(sku):
            invalid_res += 1

    using_una = (
        sum(1 for r in rows if unassigned_distributor_id is not None and r.distributor_id == unassigned_distributor_id)
        if unassigned_distributor_id is not None
        else 0
    )
    lines_with_flags = sum(1 for r in rows if r.calc_flags)

    parts: list[str] = []
    if not open_channel_dim_ok:
        parts.append("Admin/setup: dim_customer OPEN_CHANNEL missing.")
    if not unassigned_dim_ok:
        parts.append("Admin/setup: dim_distributor UNASSIGNED missing.")
    if missing_ct:
        parts.append(f"{missing_ct} line(s) missing customer terms")
    if missing_dt:
        parts.append(f"{missing_dt} line(s) missing distributor terms")
    if missing_sku:
        parts.append(f"{missing_sku} line(s) missing SKU assumptions")
    if invalid_cc:
        parts.append(f"{invalid_cc} line(s) have invalid controlled cost")
    if invalid_fx:
        parts.append(f"{invalid_fx} line(s) have invalid FX")
    if invalid_vat:
        parts.append(f"{invalid_vat} line(s) have invalid VAT %")
    if invalid_res:
        parts.append(f"{invalid_res} line(s) have invalid reserve %")
    if using_una:
        parts.append(f"{using_una} line(s) use UNASSIGNED distributor")
    if lines_with_flags:
        parts.append(f"{lines_with_flags} line(s) have economics flags")

    ready = (
        missing_ct == 0
        and missing_dt == 0
        and missing_sku == 0
        and invalid_cc == 0
        and invalid_fx == 0
        and invalid_vat == 0
        and invalid_res == 0
        and open_channel_dim_ok
        and unassigned_dim_ok
    )

    return {
        "plan_id": plan_id,
        "line_count": len(rows),
        "missing_customer_term": missing_ct,
        "missing_distributor_term": missing_dt,
        "missing_sku_assumption": missing_sku,
        "invalid_controlled_cost": invalid_cc,
        "invalid_fx": invalid_fx,
        "invalid_vat": invalid_vat,
        "invalid_reserve": invalid_res,
        "using_unassigned_distributor": using_una,
        "lines_with_calc_flags": lines_with_flags,
        "ready": ready,
        "system_reference_open_channel_dim_ok": open_channel_dim_ok,
        "system_reference_unassigned_distributor_dim_ok": unassigned_dim_ok,
        "readiness_summary": "; ".join(parts) if parts else "All defaults present.",
    }


async def commercial_planner_dashboard_aggregate(db: AsyncSession) -> dict:
    """Aggregate plan counts for dashboard KPI (bounded scan)."""
    plan_ids = list((await db.execute(select(CommercialPlan.id).order_by(CommercialPlan.id.desc()).limit(50))).scalars().all())
    if not plan_ids:
        return {
            "plan_count": 0,
            "plans_not_ready": 0,
            "plans_with_lines": 0,
        }
    not_ready = 0
    with_lines = 0
    for pid in plan_ids:
        payload = await compute_plan_readiness_payload(db, pid)
        if payload is None:
            continue
        if payload["line_count"] > 0:
            with_lines += 1
        if not payload["ready"]:
            not_ready += 1
    return {
        "plan_count": len(plan_ids),
        "plans_not_ready": not_ready,
        "plans_with_lines": with_lines,
    }
