# PLAN (Phase 5 Channel Operations)
# - CREATE: this file — GET summary|sell-out|inventory|movements|forecasts under /channel-ops
# - MODIFY: apps/api/app/api/v1/router.py — register channel_ops router
# - CREATE: apps/api/tests/test_channel_ops_api.py
# - MODIFY: apps/web/src/app/(app)/sell-out/page.tsx — wrap tabs + intel depth; preserve sell-out tab
# - CREATE: sell-out/SellOutTab.tsx, ChannelOpsKpiCards.tsx, ChannelOpsOverviewTab.tsx,
#   ChannelOpsInventoryTab.tsx, ChannelOpsMovementsTab.tsx, intelDepth.ts, page.test.tsx
# - MODIFY: apps/web/src/features/shell/navConfig.ts — rename nav label
# - EXTEND (not replace): existing sell-out uses /sellout/commercial-* ; new KPI/tabs use /channel-ops/*
# - PATTERN: async endpoints like sellout.py + shipping.py; React Query + MUI like sell-out/shipping pages
# - SHIPMENT TABLE: shipment_evidence read model (Plan D current-state view), NOT FactForecast
# - EXISTING SELL-OUT PAGE: PageHeader, 4 KPI papers, smart chips, Autocomplete filters,
#   /sellout/commercial-summary, commercial-lines, filter-options, zero-sellout-products

"""Channel Operations read APIs (sell-out, inventory, velocity, DSI forecasts, movements)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.core.tenant_scope import where_tenant
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.fact_customer_velocity import FactCustomerVelocity
from app.models.fact_dsi_forecast import FactDsiForecast
from app.models.facts import FactInventoryReconciliation, FactSalesSellout
from app.services.channel_ops_config import REPLENISHMENT_WOC_THRESHOLD_WEEKS
from app.services.channel_ops_derived_stock import (
    derived_stock_by_dist_product,
    derived_stock_rows_for_distributor,
    replenishment_flag_v1,
    sellout_velocity_52wk_by_dist_product,
    weeks_of_cover_or_none,
    yoy_pct_or_none,
)
from app.services.woc_observation_read import (
    latest_woc_observations,
    observations_to_stock_vel,
)
from app.services.imports.shipment_evidence_read import (
    apply_active_evidence_filter,
    shipment_evidence_read_model,
)

EV = shipment_evidence_read_model()

router = APIRouter()


def _parse_opt_date(s: str | None) -> date | None:
    if not s or not str(s).strip():
        return None
    try:
        return date.fromisoformat(str(s).strip()[:10])
    except ValueError:
        return None


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    try:
        conn = await db.connection()

        def _check(sync_conn: Any) -> bool:
            return bool(sa_inspect(sync_conn).has_table(table_name))

        return await conn.run_sync(_check)
    except Exception:
        return False


async def _has_rows(db: AsyncSession, table_name: str) -> bool:
    if not await _table_exists(db, table_name):
        return False
    model_map = {
        "fact_customer_velocity": FactCustomerVelocity,
        "fact_dsi_forecast": FactDsiForecast,
        "fact_inventory_reconciliation": FactInventoryReconciliation,
    }
    model = model_map.get(table_name)
    if model is None:
        return False
    try:
        n = int(await db.scalar(select(func.count()).select_from(model)) or 0)
        return n > 0
    except Exception:
        return False


def _quarter_bounds(d: date) -> tuple[date, date]:
    q_start_month = ((d.month - 1) // 3) * 3 + 1
    start = date(d.year, q_start_month, 1)
    if q_start_month == 10:
        end = date(d.year, 12, 31)
    else:
        end = date(d.year, q_start_month + 3, 1) - timedelta(days=1)
    return start, end


def _prior_year_quarter_bounds(d: date) -> tuple[date, date]:
    start, end = _quarter_bounds(d)
    return start.replace(year=start.year - 1), end.replace(year=end.year - 1)


@router.get("/weekly-series")
async def channel_ops_weekly_series(
    db: AsyncSession = Depends(get_db),
    distributor_id: int | None = None,
    weeks: int = Query(13, ge=1, le=52),
) -> dict[str, Any]:
    """Sell-out units by ISO week (last N weeks) for overview charts."""
    end = date.today()
    start = end - timedelta(days=weeks * 7)
    week_col = func.date_trunc("week", FactSalesSellout.transaction_date)
    q = (
        select(week_col.label("week_start"), func.sum(FactSalesSellout.units).label("units"))
        .where(FactSalesSellout.transaction_date >= start)
        .group_by(week_col)
        .order_by(week_col)
    )
    if distributor_id is not None:
        q = q.where(FactSalesSellout.distributor_id == int(distributor_id))
    rows = (await db.execute(q)).all()
    points: list[dict[str, Any]] = []
    for r in rows:
        ws = r.week_start
        if hasattr(ws, "date"):
            ws = ws.date()
        points.append({"week_start": ws.isoformat() if isinstance(ws, date) else str(ws)[:10], "units": float(r.units or 0)})
    return {"weeks": weeks, "points": points}


def _wants_live_woc(woc_source: str | None, recompute: str | None) -> bool:
    if str(woc_source or "").strip().lower() == "live":
        return True
    return str(recompute or "").strip().lower() in {"1", "true", "yes"}


@router.get("/summary")
async def channel_ops_summary(
    db: AsyncSession = Depends(get_db),
    distributor_id: int | None = None,
    woc_source: str | None = Query(None),
    recompute: str | None = Query(None),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    today = date.today()
    q_start, q_end = _quarter_bounds(today)
    py_start, py_end = _prior_year_quarter_bounds(today)

    sell_q = select(
        func.coalesce(func.sum(FactSalesSellout.units), 0),
        func.coalesce(func.sum(FactSalesSellout.revenue), 0),
    ).where(
        FactSalesSellout.transaction_date >= q_start,
        FactSalesSellout.transaction_date <= q_end,
    )
    sell_py = select(
        func.coalesce(func.sum(FactSalesSellout.units), 0),
        func.coalesce(func.sum(FactSalesSellout.revenue), 0),
    ).where(
        FactSalesSellout.transaction_date >= py_start,
        FactSalesSellout.transaction_date <= py_end,
    )
    if distributor_id is not None:
        did = int(distributor_id)
        sell_q = sell_q.where(FactSalesSellout.distributor_id == did)
        sell_py = sell_py.where(FactSalesSellout.distributor_id == did)

    cur = (await db.execute(sell_q)).one()
    prior = (await db.execute(sell_py)).one()
    cur_units, cur_rev = float(cur[0]), float(cur[1])
    py_units, py_rev = float(prior[0]), float(prior[1])

    # Coverage (COMMERCIAL_SEMANTICS): zero units with no rows in-window is "no data",
    # not a true zero — do not emit −100% YoY against a prior quarter that has volume.
    cur_row_count = int(
        await db.scalar(
            select(func.count())
            .select_from(FactSalesSellout)
            .where(
                FactSalesSellout.transaction_date >= q_start,
                FactSalesSellout.transaction_date <= q_end,
                *(
                    [FactSalesSellout.distributor_id == int(distributor_id)]
                    if distributor_id is not None
                    else []
                ),
            )
        )
        or 0
    )
    sell_out_max = await db.scalar(select(func.max(FactSalesSellout.transaction_date)))
    current_quarter_has_data = cur_row_count > 0
    # Denominator sanity + coverage: missing current OR zero/missing prior → n/a.
    yoy_pct = (
        yoy_pct_or_none(cur_units, py_units) if current_quarter_has_data else None
    )

    # Channel stock / WoC: observation tape by default (BACKLOG-097). Live calculator
    # only when woc_source=live or recompute=1 — never a silent fallback.
    from app.core.tenant_scope import tenant_id_from_user

    tid = tenant_id_from_user(user if isinstance(user, dict) else None)
    use_live = _wants_live_woc(woc_source, recompute)
    woc_src = "live" if use_live else "observations"
    if use_live:
        stock_by_pair = await derived_stock_by_dist_product(
            db, distributor_id=int(distributor_id) if distributor_id is not None else None, tenant_id=tid
        )
        vel_by_pair = await sellout_velocity_52wk_by_dist_product(
            db, distributor_id=int(distributor_id) if distributor_id is not None else None, tenant_id=tid
        )
    else:
        obs = await latest_woc_observations(
            db,
            tenant_id=tid,
            distributor_id=int(distributor_id) if distributor_id is not None else None,
        )
        stock_by_pair, vel_by_pair = observations_to_stock_vel(obs)
    total_inv = float(sum(stock_by_pair.values())) if stock_by_pair else 0.0
    pair_count = len(stock_by_pair)
    total_weekly_velocity = sum(vel_by_pair.values()) if vel_by_pair else 0.0
    weeks_of_cover = weeks_of_cover_or_none(total_inv, total_weekly_velocity or None)
    has_sellout_velocity = bool(vel_by_pair) or bool(stock_by_pair)

    threshold = float(REPLENISHMENT_WOC_THRESHOLD_WEEKS)
    pairs_below = 0
    for key, stock in stock_by_pair.items():
        woc = weeks_of_cover_or_none(stock, vel_by_pair.get(key))
        if replenishment_flag_v1(woc, threshold_weeks=threshold):
            pairs_below += 1
    portfolio_replenishment = replenishment_flag_v1(weeks_of_cover, threshold_weeks=threshold)

    since_35 = today - timedelta(days=35)
    dist_reporting_q = select(func.count(func.distinct(FactSalesSellout.distributor_id))).where(
        FactSalesSellout.distributor_id.isnot(None),
        FactSalesSellout.transaction_date >= since_35,
    )
    dist_expected_q = select(func.count(func.distinct(FactSalesSellout.distributor_id))).where(
        FactSalesSellout.distributor_id.isnot(None),
        FactSalesSellout.transaction_date >= since_35,
    )
    distributors_reporting = int(await db.scalar(dist_reporting_q) or 0)
    distributors_expected = int(await db.scalar(dist_expected_q) or 0)

    period_days = 90
    d_now = today - timedelta(days=period_days)
    d_prev_start = today - timedelta(days=period_days * 2)
    cust_now_q = select(func.count(func.distinct(FactSalesSellout.customer_id))).where(
        FactSalesSellout.transaction_date >= d_now
    )
    cust_prev_q = select(func.count(func.distinct(FactSalesSellout.customer_id))).where(
        FactSalesSellout.transaction_date >= d_prev_start,
        FactSalesSellout.transaction_date < d_now,
    )
    if distributor_id is not None:
        did = int(distributor_id)
        cust_now_q = cust_now_q.where(FactSalesSellout.distributor_id == did)
        cust_prev_q = cust_prev_q.where(FactSalesSellout.distributor_id == did)

    return {
        "sell_out_this_quarter": {
            "units": cur_units,
            "revenue": cur_rev,
            "has_data": current_quarter_has_data,
            "period_start": q_start.isoformat(),
            "period_end": q_end.isoformat(),
        },
        "sell_out_prior_year_quarter": {
            "units": py_units,
            "revenue": py_rev,
            "period_start": py_start.isoformat(),
            "period_end": py_end.isoformat(),
        },
        "sell_out_yoy_pct": yoy_pct,
        "sell_out_data_vintage": {
            "max_transaction_date": sell_out_max.isoformat() if sell_out_max else None,
            "current_quarter_has_data": current_quarter_has_data,
            "as_of_date": today.isoformat(),
        },
        "total_inventory_units": int(total_inv),
        "weeks_of_cover": weeks_of_cover,
        "woc_source": woc_src,
        "missing_data_alert": not stock_by_pair,
        "replenishment_threshold_weeks": threshold,
        "replenishment_flag": portfolio_replenishment,
        "replenishment_pairs_below_threshold": pairs_below,
        "replenishment_pair_count": pair_count,
        "distributors_reporting": distributors_reporting,
        "distributors_expected": distributors_expected,
        "active_customers_this_period": int(await db.scalar(cust_now_q) or 0),
        "active_customers_prior_period": int(await db.scalar(cust_prev_q) or 0),
        "has_velocity_data": has_sellout_velocity
        or await _has_rows(db, "fact_customer_velocity"),
        "has_forecast_data": await _has_rows(db, "fact_dsi_forecast"),
        "has_reconciliation_data": await _has_rows(db, "fact_inventory_reconciliation"),
        "velocity_grain": "distributor_product",
        "velocity_weekly_units": float(total_weekly_velocity),
    }


@router.get("/sell-out")
async def channel_ops_sell_out(
    db: AsyncSession = Depends(get_db),
    distributor_id: int | None = None,
    product_id: int | None = None,
    customer_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    df = _parse_opt_date(date_from)
    dt = _parse_opt_date(date_to)
    skip = (page - 1) * page_size
    tenant_f = where_tenant(FactSalesSellout.tenant_id, user)

    q = (
        select(
            FactSalesSellout,
            DimProduct.sku,
            DimProduct.name.label("product_name"),
            DimCustomer.name.label("customer_name"),
            DimDistributor.name.label("distributor_name"),
        )
        .join(DimProduct, FactSalesSellout.product_id == DimProduct.id)
        .join(DimCustomer, FactSalesSellout.customer_id == DimCustomer.id)
        .outerjoin(DimDistributor, FactSalesSellout.distributor_id == DimDistributor.id)
        .where(tenant_f)
    )
    if distributor_id is not None:
        q = q.where(FactSalesSellout.distributor_id == int(distributor_id))
    if product_id is not None:
        q = q.where(FactSalesSellout.product_id == int(product_id))
    if customer_id is not None:
        q = q.where(FactSalesSellout.customer_id == int(customer_id))
    if df is not None:
        q = q.where(FactSalesSellout.transaction_date >= df)
    if dt is not None:
        q = q.where(FactSalesSellout.transaction_date <= dt)

    total = int(await db.scalar(select(func.count()).select_from(q.subquery())) or 0)

    prior_units_map: dict[tuple[int, int, int], float] = {}
    if df is not None and dt is not None:
        span = (dt - df).days + 1
        p_end = df - timedelta(days=1)
        p_start = p_end - timedelta(days=span - 1)
        prior_q = (
            select(
                FactSalesSellout.distributor_id,
                FactSalesSellout.product_id,
                FactSalesSellout.customer_id,
                func.sum(FactSalesSellout.units),
            )
            .where(
                FactSalesSellout.transaction_date >= p_start,
                FactSalesSellout.transaction_date <= p_end,
                tenant_f,
            )
            .group_by(
                FactSalesSellout.distributor_id,
                FactSalesSellout.product_id,
                FactSalesSellout.customer_id,
            )
        )
        if distributor_id is not None:
            prior_q = prior_q.where(FactSalesSellout.distributor_id == int(distributor_id))
        if product_id is not None:
            prior_q = prior_q.where(FactSalesSellout.product_id == int(product_id))
        if customer_id is not None:
            prior_q = prior_q.where(FactSalesSellout.customer_id == int(customer_id))
        for row in (await db.execute(prior_q)).all():
            key = (int(row[0] or 0), int(row[1]), int(row[2]))
            prior_units_map[key] = float(row[3] or 0)

    rows = (
        await db.execute(
            q.order_by(desc(FactSalesSellout.transaction_date)).offset(skip).limit(page_size)
        )
    ).all()

    items: list[dict[str, Any]] = []
    for row in rows:
        s = row[0]
        unit_price: float | None = None
        if s.units and float(s.units) != 0:
            unit_price = float(s.revenue) / float(s.units)
        prior_units: float | None = None
        if prior_units_map:
            key = (int(s.distributor_id or 0), int(s.product_id), int(s.customer_id))
            if key in prior_units_map:
                prior_units = prior_units_map[key]
        items.append(
            {
                "date": s.transaction_date.isoformat(),
                "distributor_name": row.distributor_name,
                "customer_name": row.customer_name,
                "product_name": row.product_name,
                "sku": row.sku,
                "units": float(s.units),
                "unit_price": unit_price,
                "revenue": float(s.revenue),
                "prior_period_units": prior_units,
            }
        )

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/inventory")
async def channel_ops_inventory(
    db: AsyncSession = Depends(get_db),
    distributor_id: int | None = Query(None),
    product_id: int | None = None,
    woc_source: str | None = Query(None),
    recompute: str | None = Query(None),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    if distributor_id is None:
        raise HTTPException(status_code=400, detail="distributor_id is required")

    from app.core.tenant_scope import tenant_id_from_user

    tid = tenant_id_from_user(user if isinstance(user, dict) else None)
    use_live = _wants_live_woc(woc_source, recompute)
    woc_src = "live" if use_live else "observations"

    if use_live:
        derived_rows = await derived_stock_rows_for_distributor(
            db, distributor_id=int(distributor_id), product_id=product_id, tenant_id=tid
        )
        vel_by_pair = await sellout_velocity_52wk_by_dist_product(
            db, distributor_id=int(distributor_id), tenant_id=tid
        )
        velocity_by_product = {pid: vel for (_did, pid), vel in vel_by_pair.items()}
    else:
        obs = await latest_woc_observations(
            db,
            tenant_id=tid,
            distributor_id=int(distributor_id),
            product_id=int(product_id) if product_id is not None else None,
        )
        derived_rows = [
            {
                "distributor_id": r.distributor_id,
                "product_id": r.product_id,
                "snapshot_date": r.snapshot_date.isoformat() if r.snapshot_date else None,
                "reported_soh": r.reported_soh,
                "sell_out_since": r.sell_out_since,
                "landed_since": r.landed_since,
                "derived_stock": r.derived_stock,
                "calculated_soh": None,
                "variance_units": None,
                "reconciliation_status": None,
                "weeks_of_cover": r.weeks_of_cover,
                "weekly_velocity": r.weekly_velocity,
                "replenishment_flag": r.replenishment_flag,
                "cover_as_of_date": r.cover_as_of_date.isoformat(),
                "trigger": r.trigger,
            }
            for r in obs
        ]
        velocity_by_product = {
            r.product_id: r.weekly_velocity for r in obs if r.weekly_velocity is not None
        }

    product_ids = [int(r["product_id"]) for r in derived_rows]
    product_meta: dict[int, tuple[str | None, str | None]] = {}
    dist_name: str | None = None
    if product_ids:
        prod_rows = (
            await db.execute(
                select(DimProduct.id, DimProduct.sku, DimProduct.name).where(
                    DimProduct.id.in_(product_ids)
                )
            )
        ).all()
        product_meta = {int(r[0]): (r[1], r[2]) for r in prod_rows}
        dist_name = await db.scalar(
            select(DimDistributor.name).where(DimDistributor.id == int(distributor_id))
        )

    threshold = float(REPLENISHMENT_WOC_THRESHOLD_WEEKS)

    # B1-04: distributor×product rollup of demand forecast (next 13 weeks from today).
    demand_by_product: dict[int, float] = {}
    if await _table_exists(db, "fact_demand_forecast"):
        from datetime import date as date_cls

        from app.models.fact_demand_forecast import FactDemandForecast

        today = date_cls.today()
        horizon = today + timedelta(weeks=13)
        fc_rows = (
            await db.execute(
                select(
                    FactDemandForecast.product_id,
                    func.coalesce(func.sum(FactDemandForecast.forecast_units), 0),
                )
                .where(
                    FactDemandForecast.distributor_id == int(distributor_id),
                    FactDemandForecast.period_start >= today,
                    FactDemandForecast.period_start <= horizon,
                    FactDemandForecast.tenant_id == tid,
                )
                .group_by(FactDemandForecast.product_id)
            )
        ).all()
        demand_by_product = {int(r[0]): float(r[1] or 0) for r in fc_rows}

    items: list[dict[str, Any]] = []
    for row in derived_rows:
        pid = int(row["product_id"])
        sku, pname = product_meta.get(pid, (None, None))
        v52 = velocity_by_product.get(pid)
        derived = float(row["derived_stock"])
        if "weeks_of_cover" in row and not use_live:
            weeks = row.get("weeks_of_cover")
            flag = bool(row.get("replenishment_flag"))
        else:
            weeks = weeks_of_cover_or_none(derived, v52)
            flag = replenishment_flag_v1(weeks, threshold_weeks=threshold)
        items.append(
            {
                "distributor_id": int(row["distributor_id"]),
                "distributor_name": dist_name,
                "product_id": pid,
                "sku": sku,
                "product_name": pname,
                "snapshot_date": row.get("snapshot_date"),
                "reported_soh": float(row["reported_soh"]),
                "sell_out_since": float(row["sell_out_since"]),
                "landed_since": float(row["landed_since"]),
                "derived_stock": derived,
                "calculated_soh": row.get("calculated_soh"),
                "variance_units": row.get("variance_units"),
                "variance_pct": None,
                "reconciliation_status": row.get("reconciliation_status"),
                "velocity_52wk": v52,
                "weeks_of_cover": weeks,
                "computed_through_date": None,
                "replenishment_flag": flag,
                "replenishment_threshold_weeks": threshold,
                "reorder_signal": flag,  # alias — prefer replenishment_flag (A3-03)
                "velocity_grain": "distributor_product",
                "demand_forecast_units_13w": demand_by_product.get(pid),
                "woc_source": woc_src,
                "cover_as_of_date": row.get("cover_as_of_date"),
            }
        )

    return {
        "items": items,
        "total": len(items),
        "woc_source": woc_src,
        "missing_data_alert": not items,
        "replenishment_threshold_weeks": threshold,
        "replenishment_pairs_below_threshold": sum(1 for i in items if i["replenishment_flag"]),
    }


@router.get("/movements")
async def channel_ops_movements(
    db: AsyncSession = Depends(get_db),
    distributor_id: int | None = Query(None),
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    if distributor_id is None:
        raise HTTPException(status_code=400, detail="distributor_id is required")
    df = _parse_opt_date(date_from)
    dt = _parse_opt_date(date_to)
    skip = (page - 1) * page_size

    ship_date_col = func.coalesce(
        EV.ship_confirm_date,
        EV.schedule_ship_date,
    )

    q = apply_active_evidence_filter(
        select(
            EV,
            DimProduct.sku,
            DimProduct.name.label("product_name"),
            DimDistributor.name.label("distributor_name"),
            ship_date_col.label("ship_date"),
        )
        .outerjoin(DimProduct, EV.product_id == DimProduct.id)
        .outerjoin(DimDistributor, EV.distributor_id == DimDistributor.id)
        .where(EV.distributor_id == int(distributor_id)),
        model=EV,
    )
    if df is not None:
        q = q.where(ship_date_col >= df)
    if dt is not None:
        q = q.where(ship_date_col <= dt)

    total = int(await db.scalar(select(func.count()).select_from(q.subquery())) or 0)
    rows = (await db.execute(q.order_by(desc(ship_date_col)).offset(skip).limit(page_size))).all()

    items = []
    for row in rows:
        line = row[0]
        items.append(
            {
                "product_id": line.product_id,
                "sku": row.sku,
                "product_name": row.product_name,
                "order_no": line.order_no,
                "delivery_no": line.delivery_no,
                "ship_date": row.ship_date.isoformat() if row.ship_date else None,
                "units_shipped": float(line.quantity) if line.quantity is not None else None,
                "line_state": line.line_state,
                "distributor_name": row.distributor_name,
            }
        )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/forecasts")
async def channel_ops_forecasts(
    db: AsyncSession = Depends(get_db),
    distributor_id: int | None = Query(None),
    product_id: int | None = None,
    weeks_ahead: int = Query(13, ge=1, le=26),
) -> dict[str, Any]:
    if distributor_id is None:
        raise HTTPException(status_code=400, detail="distributor_id is required")
    if not await _table_exists(db, "fact_dsi_forecast"):
        return {"items": [], "total": 0}

    today = date.today()
    horizon = today + timedelta(days=weeks_ahead * 7)
    q = (
        select(
            FactDsiForecast,
            DimProduct.sku,
            DimProduct.name.label("product_name"),
        )
        .join(DimProduct, FactDsiForecast.product_id == DimProduct.id)
        .where(
            FactDsiForecast.distributor_id == int(distributor_id),
            FactDsiForecast.forecast_date <= horizon,
            FactDsiForecast.forecast_date >= today,
        )
    )
    if product_id is not None:
        q = q.where(FactDsiForecast.product_id == int(product_id))

    rows = (await db.execute(q.order_by(FactDsiForecast.forecast_date.asc()))).all()
    items = []
    for row in rows:
        f = row[0]
        items.append(
            {
                "product_id": f.product_id,
                "sku": row.sku,
                "product_name": row.product_name,
                "forecast_date": f.forecast_date.isoformat(),
                "forecast_units": float(f.forecast_units),
                "upper_band": float(f.upper_band) if f.upper_band is not None else None,
                "lower_band": float(f.lower_band) if f.lower_band is not None else None,
                "confidence_level": f.confidence_level,
                "velocity_basis": f.velocity_basis,
                "generated_at": f.generated_at.isoformat() if f.generated_at else None,
            }
        )
    return {"items": items, "total": len(items)}
