"""Deterministic product opportunity rankings per customer for a commercial plan."""

from __future__ import annotations

from typing import Any

import math

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.commercial_planner import (
    CommercialCustomerTerm,
    CommercialPlanLine,
    CommercialSkuAssumption,
)
from app.models.dimensions import DimProduct
from app.models.facts import FactForecast, FactPricing, FactPromotionPlan, FactSalesSellout
from app.models.historical_lineup import HistoricalLineupImportHeader, HistoricalLineupImportLine
from app.models.ingestion import ImportJob
from app.services.commercial_planner.calculator import CommercialCalcInputs, compute_line_economics
from app.services.commercial_planner.economics_trust import classify_line_economics_trust


async def _sellout_avg_by_product(
    db: AsyncSession, customer_id: int, product_ids: list[int]
) -> dict[int, float]:
    if not product_ids:
        return {}
    rows = (
        await db.execute(
            select(
                FactSalesSellout.product_id,
                func.coalesce(func.avg(FactSalesSellout.units), 0).label("avg_units"),
            )
            .where(
                FactSalesSellout.customer_id == customer_id,
                FactSalesSellout.product_id.in_(product_ids),
            )
            .group_by(FactSalesSellout.product_id)
        )
    ).all()
    return {int(r.product_id): float(r.avg_units) for r in rows}


async def _net_price_by_product(
    db: AsyncSession, customer_id: int, product_ids: list[int]
) -> dict[int, float]:
    """Latest net price per product; prefer customer-specific rows over global."""
    if not product_ids:
        return {}
    pricing_sq = (
        select(
            FactPricing.product_id,
            FactPricing.net_price,
            FactPricing.customer_id,
            func.row_number()
            .over(
                partition_by=FactPricing.product_id,
                order_by=(
                    (FactPricing.customer_id == customer_id).desc(),
                    FactPricing.effective_date.desc(),
                ),
            )
            .label("rn"),
        )
        .where(
            FactPricing.product_id.in_(product_ids),
            (FactPricing.customer_id == customer_id) | (FactPricing.customer_id.is_(None)),
        )
        .subquery()
    )
    rows = (
        await db.execute(
            select(pricing_sq.c.product_id, pricing_sq.c.net_price).where(pricing_sq.c.rn == 1)
        )
    ).all()
    return {int(r.product_id): float(r.net_price) for r in rows}


async def _lineup_msrp_by_product(
    db: AsyncSession, *, plan_id: int, customer_id: int, product_ids: list[int]
) -> dict[int, float]:
    """MSRP evidence from current lineup case lines, else latest historical lineup apply job."""
    if not product_ids:
        return {}
    out: dict[int, float] = {}
    cl_rows = (
        await db.execute(
            select(
                CommercialLineupLine.product_id,
                func.max(CommercialLineupLine.msrp_local).label("msrp"),
            )
            .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupLine.case_id)
            .where(
                CommercialLineupCase.commercial_plan_id == plan_id,
                CommercialLineupLine.product_id.in_(product_ids),
                CommercialLineupLine.msrp_local.isnot(None),
            )
            .group_by(CommercialLineupLine.product_id)
        )
    ).all()
    for r in cl_rows:
        if r.product_id is not None and r.msrp is not None:
            out[int(r.product_id)] = float(r.msrp)

    missing = [pid for pid in product_ids if pid not in out]
    if not missing:
        return out

    latest_job_id = await db.scalar(
        select(func.max(HistoricalLineupImportHeader.import_job_id))
        .join(HistoricalLineupImportLine, HistoricalLineupImportLine.header_id == HistoricalLineupImportHeader.id)
        .join(ImportJob, ImportJob.id == HistoricalLineupImportHeader.import_job_id)
        .where(
            HistoricalLineupImportLine.product_id.in_(missing),
            ImportJob.import_mode == "apply",
            ImportJob.template_slug == "historical_lineup",
        )
    )
    if not latest_job_id:
        return out

    hist_rows = (
        await db.execute(
            select(
                HistoricalLineupImportLine.product_id,
                func.max(HistoricalLineupImportLine.msrp_local).label("msrp"),
            )
            .join(
                HistoricalLineupImportHeader,
                HistoricalLineupImportHeader.id == HistoricalLineupImportLine.header_id,
            )
            .where(
                HistoricalLineupImportHeader.import_job_id == latest_job_id,
                HistoricalLineupImportLine.product_id.in_(missing),
                HistoricalLineupImportHeader.customer_id == customer_id,
                HistoricalLineupImportLine.msrp_local.isnot(None),
            )
            .group_by(HistoricalLineupImportLine.product_id)
        )
    ).all()
    for r in hist_rows:
        if r.product_id is not None and r.msrp is not None:
            out[int(r.product_id)] = float(r.msrp)
    return out


async def _promo_product_ids(db: AsyncSession, product_ids: list[int]) -> set[int]:
    if not product_ids:
        return set()
    rows = (
        await db.execute(
            select(FactPromotionPlan.product_id)
            .where(FactPromotionPlan.product_id.in_(product_ids))
            .distinct()
        )
    ).scalars().all()
    return {int(x) for x in rows}


def _suggested_srp_local(
    *,
    lineup_msrp: float | None,
    net_price: float | None,
    default: float = 1000.0,
) -> float:
    if lineup_msrp is not None and lineup_msrp > 0:
        return round(lineup_msrp, 2)
    if net_price is not None and net_price > 0:
        return round(net_price * 1.12, 2)
    return default


async def _forecast_by_product(db: AsyncSession, product_ids: list[int]) -> dict[int, float]:
    if not product_ids:
        return {}
    forecast_sq = (
        select(
            FactForecast.product_id,
            FactForecast.forecast_units,
            func.row_number()
            .over(partition_by=FactForecast.product_id, order_by=FactForecast.period_start.desc())
            .label("rn"),
        )
        .where(FactForecast.product_id.in_(product_ids))
        .subquery()
    )
    rows = (
        await db.execute(
            select(forecast_sq.c.product_id, forecast_sq.c.forecast_units).where(forecast_sq.c.rn == 1)
        )
    ).all()
    return {int(r.product_id): float(r.forecast_units) for r in rows}


async def _historical_lineup_qty(
    db: AsyncSession, customer_id: int, product_ids: list[int]
) -> dict[int, float]:
    if not product_ids:
        return {}
    latest_job_id = await db.scalar(
        select(func.max(HistoricalLineupImportHeader.import_job_id))
        .join(HistoricalLineupImportLine, HistoricalLineupImportLine.header_id == HistoricalLineupImportHeader.id)
        .join(ImportJob, ImportJob.id == HistoricalLineupImportHeader.import_job_id)
        .where(
            HistoricalLineupImportLine.product_id.in_(product_ids),
            ImportJob.import_mode == "apply",
            ImportJob.template_slug == "historical_lineup",
        )
    )
    if not latest_job_id:
        return {}
    rows = (
        await db.execute(
            select(
                HistoricalLineupImportLine.product_id,
                func.sum(HistoricalLineupImportLine.quantity_units).label("qty"),
            )
            .join(
                HistoricalLineupImportHeader,
                HistoricalLineupImportHeader.id == HistoricalLineupImportLine.header_id,
            )
            .where(
                HistoricalLineupImportHeader.import_job_id == latest_job_id,
                HistoricalLineupImportLine.product_id.in_(product_ids),
                HistoricalLineupImportHeader.customer_id == customer_id,
            )
            .group_by(HistoricalLineupImportLine.product_id)
        )
    ).all()
    return {int(r.product_id): float(r.qty) for r in rows if r.qty is not None}


async def _current_lineup_qty(
    db: AsyncSession, plan_id: int, product_ids: list[int]
) -> dict[int, float]:
    if not product_ids:
        return {}
    rows = (
        await db.execute(
            select(
                CommercialLineupLine.product_id,
                func.sum(CommercialLineupLine.quantity_units).label("qty"),
            )
            .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupLine.case_id)
            .where(
                CommercialLineupCase.commercial_plan_id == plan_id,
                CommercialLineupLine.product_id.in_(product_ids),
            )
            .group_by(CommercialLineupLine.product_id)
        )
    ).all()
    return {int(r.product_id): float(r.qty) for r in rows if r.qty is not None and r.product_id is not None}


async def _plan_product_ids(db: AsyncSession, plan_id: int) -> set[int]:
    rows = (
        await db.execute(
            select(CommercialPlanLine.product_id).where(CommercialPlanLine.commercial_plan_id == plan_id)
        )
    ).scalars().all()
    return {int(x) for x in rows}


def _score_product(
    *,
    product_id: int,
    sku: str,
    name: str,
    sellout_avg: float,
    forecast_units: float | None,
    hist_qty: float | None,
    current_qty: float | None,
    in_plan: bool,
    gp_per_unit: float | None,
    calc_flags: list[str],
    suggested_srp_local: float,
    has_promo_plan: bool,
) -> dict[str, Any]:
    factors: list[dict[str, Any]] = []
    score = 0.0

    if sellout_avg > 0:
        sellout_pts = min(25.0, math.log1p(sellout_avg) * 5.0)
        score += sellout_pts
        factors.append({"signal": "sellout_avg_units", "value": sellout_avg, "weight": sellout_pts})

    if forecast_units is not None and forecast_units > 0:
        uplift = min(15.0, max(0.0, (forecast_units / max(sellout_avg, 1.0) - 1.0) * 10.0))
        score += uplift
        factors.append({"signal": "forecast_units", "value": forecast_units, "weight": uplift})

    if hist_qty is not None and hist_qty > 0:
        score += 12.0
        factors.append({"signal": "historical_lineup_qty", "value": hist_qty, "weight": 12.0})

    if current_qty is not None and current_qty > 0:
        score += 13.0
        factors.append({"signal": "current_lineup_qty", "value": current_qty, "weight": 13.0})

    if gp_per_unit is not None:
        if gp_per_unit > 0:
            gp_pts = min(20.0, gp_per_unit / 100.0 * 20.0)
            score += gp_pts
            factors.append({"signal": "hypothetical_gp_per_unit", "value": gp_per_unit, "weight": gp_pts})
        else:
            score -= 5.0
            factors.append({"signal": "negative_gp", "value": gp_per_unit, "weight": -5.0})

    if in_plan:
        score -= 8.0
        factors.append({"signal": "already_in_plan", "value": True, "weight": -8.0})

    if has_promo_plan:
        score += 4.0
        factors.append({"signal": "promotion_plan_exists", "value": True, "weight": 4.0})

    tier, tier_reasons = classify_line_economics_trust(calc_flags)
    confidence = "high" if sellout_avg > 0 and tier == "ok" else "medium" if sellout_avg > 0 else "low"
    if tier == "blocked":
        score = min(score, 40.0)
        confidence = "low"

    return {
        "product_id": product_id,
        "sku": sku,
        "product_name": name,
        "opportunity_score": round(max(0.0, min(100.0, score)), 1),
        "confidence": confidence,
        "trust_tier": tier,
        "trust_reasons": tier_reasons,
        "already_in_plan": in_plan,
        "explanation_factors": factors,
        "suggested_target_units": round(
            max(
                sellout_avg * 1.08,
                forecast_units or 0,
                hist_qty or 0,
                current_qty or 0,
                1.0,
            ),
            2,
        ),
        "suggested_srp_local": suggested_srp_local,
    }


async def rank_products_for_customer(
    db: AsyncSession,
    *,
    plan_id: int,
    customer_id: int,
    distributor_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Rank catalogue products for a customer on a plan (deterministic v1)."""
    limit = max(1, min(limit, 200))
    in_plan = await _plan_product_ids(db, plan_id)

    products = (await db.execute(select(DimProduct).order_by(DimProduct.sku).limit(500))).scalars().all()
    product_ids = [p.id for p in products]

    sellout_map = await _sellout_avg_by_product(db, customer_id, product_ids)
    forecast_map = await _forecast_by_product(db, product_ids)
    hist_map = await _historical_lineup_qty(db, customer_id, product_ids)
    current_map = await _current_lineup_qty(db, plan_id, product_ids)
    net_price_map = await _net_price_by_product(db, customer_id, product_ids)
    msrp_map = await _lineup_msrp_by_product(
        db, plan_id=plan_id, customer_id=customer_id, product_ids=product_ids
    )
    promo_ids = await _promo_product_ids(db, product_ids)

    cterm = (
        await db.execute(select(CommercialCustomerTerm).where(CommercialCustomerTerm.customer_id == customer_id))
    ).scalars().first()
    sku_rows = (
        await db.execute(select(CommercialSkuAssumption).where(CommercialSkuAssumption.product_id.in_(product_ids)))
    ).scalars().all()
    sku_by_product = {s.product_id: s for s in sku_rows}

    from app.models.commercial_planner import CommercialDistributorTerm

    dterm = (
        await db.execute(
            select(CommercialDistributorTerm).where(CommercialDistributorTerm.distributor_id == distributor_id)
        )
    ).scalars().first()

    ranked: list[dict[str, Any]] = []
    for p in products:
        sku = sku_by_product.get(p.id)
        sellout_avg = sellout_map.get(p.id, 0.0)
        # Skip products with zero signals unless in plan or lineup
        if (
            sellout_avg <= 0
            and p.id not in hist_map
            and p.id not in current_map
            and p.id not in in_plan
        ):
            continue

        target_srp = _suggested_srp_local(
            lineup_msrp=msrp_map.get(p.id),
            net_price=net_price_map.get(p.id),
        )
        gp_per_unit = None
        calc_flags: list[str] = []
        if sku and cterm and dterm:
            inp = CommercialCalcInputs(
                target_units=1.0,
                target_srp_local=target_srp,
                promo_srp_local=None,
                promo_mix_pct=0.5,
                fx_plan_currency_per_cost_currency=float(sku.fx_plan_currency_per_cost_currency),
                vat_rate_pct=float(sku.vat_rate_pct),
                controlled_cost_amount=float(sku.controlled_cost_amount),
                customer_margin_pct=float(cterm.customer_margin_pct),
                customer_rebate_pct=float(cterm.customer_rebate_pct),
                distributor_margin_pct=float(dterm.distributor_margin_pct),
                reserve_total_pct=float(sku.reserve_total_pct),
                promo_reserve_split_pct=float(sku.promo_reserve_split_pct),
            )
            calc = compute_line_economics(inp)
            gp_per_unit = calc.calc_internal_gp_amount
            calc_flags = list(calc.flags)
        elif sku is None:
            calc_flags = ["missing_sku_assumption"]

        ranked.append(
            _score_product(
                product_id=p.id,
                sku=p.sku or "",
                name=p.name or "",
                sellout_avg=sellout_avg,
                forecast_units=forecast_map.get(p.id),
                hist_qty=hist_map.get(p.id),
                current_qty=current_map.get(p.id),
                in_plan=p.id in in_plan,
                gp_per_unit=gp_per_unit,
                calc_flags=calc_flags,
                suggested_srp_local=target_srp,
                has_promo_plan=p.id in promo_ids,
            )
        )

    ranked.sort(key=lambda x: (-float(x["opportunity_score"]), x["sku"]))
    return ranked[:limit]
