"""P3 volume handlers — sellout_units (DSI) and cst_sellthrough_units (CST).

Raw units only. Never velocity / weeks-of-cover. Calendar buckets from already-dated
facts (DSI ``transaction_date``; CST ``period_start_date``). Generalises Channel Ops
``date_trunc('week', transaction_date)`` to week/month/quarter + extra grains.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.facts import FactSalesSellout
from app.query.calendar_grain import (
    as_date,
    coarsest_stored_rank,
    date_trunc_expr,
    finer_than_stored_message,
    parse_period_bound,
    request_rank,
    series_point,
)
from app.query.types import HandlerResult, QueryRequest

INVARIANTS = [
    "raw_units_not_velocity",
    "calendar_period_grain_week_month_quarter",
    "no_daily_widget_grain",
    "cst_never_finer_than_stored_period_type",
    "dsi_customer_is_not_cst_customer",
]

VOLUME_KEYS = frozenset({"sellout_units", "cst_sellthrough_units"})

_DSI_GRAIN_COLS = {
    "customer": FactSalesSellout.customer_id,
    "product": FactSalesSellout.product_id,
    "distributor": FactSalesSellout.distributor_id,
}


def _grain_set(grains: list[str]) -> set[str]:
    return {str(g).strip().lower() for g in grains if str(g).strip()}


def _opt_int(filters: dict[str, Any], *keys: str) -> int | None:
    for k in keys:
        raw = filters.get(k)
        if raw is None or raw == "":
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _date_filters(filters: dict[str, Any]) -> tuple[Any, Any]:
    start = parse_period_bound(filters.get("period_from") or filters.get("period"), end=False)
    end = parse_period_bound(filters.get("period_to") or filters.get("period"), end=True)
    return start, end


async def handle_volume(
    db: AsyncSession,
    req: QueryRequest,
    *,
    metric_key: str,
    explain_only: bool = False,
) -> HandlerResult:
    key = (metric_key or "").strip().lower()
    grains = _grain_set(req.grains)
    period_in = "period" in grains
    period_grain = req.period_grain if period_in else None
    is_cst = key == "cst_sellthrough_units"
    explain = {
        "handler": "volume_series",
        "metric_key": key,
        "period_grain": period_grain,
        "sql_fragments": [
            (
                "date_trunc(period_grain, fact_customer_sellthrough.period_start_date)"
                if is_cst
                else "date_trunc(period_grain, fact_sales_sellout.transaction_date)"
            ),
            "SUM(units_sold)" if is_cst else "SUM(units)",
        ],
        "owner_pattern": "apps/api/app/api/v1/endpoints/channel_ops.py:channel_ops_weekly_series",
    }
    if explain_only:
        return HandlerResult(
            status="ok",
            invariants_applied=list(INVARIANTS),
            explain=explain,
            message="Would execute calendar-bucketed volume SUM (no DB run).",
        )

    if is_cst:
        return await _handle_cst(db, req, grains=grains, period_grain=period_grain, explain=explain)
    return await _handle_dsi(db, req, grains=grains, period_grain=period_grain, explain=explain)


async def _handle_dsi(
    db: AsyncSession,
    req: QueryRequest,
    *,
    grains: set[str],
    period_grain: str | None,
    explain: dict[str, Any],
) -> HandlerResult:
    filters = req.filters or {}
    date_col = FactSalesSellout.transaction_date
    start, end = _date_filters(filters)
    conds: list[Any] = [FactSalesSellout.tenant_id == (req.tenant_id or "default")]
    if start is not None:
        conds.append(date_col >= start)
    if end is not None:
        conds.append(date_col <= end)
    cid = _opt_int(filters, "customer_id", "customer")
    if cid is not None:
        conds.append(FactSalesSellout.customer_id == cid)
    pid = _opt_int(filters, "product_id", "product")
    if pid is not None:
        conds.append(FactSalesSellout.product_id == pid)
    did = _opt_int(filters, "distributor_id", "distributor")
    if did is not None:
        conds.append(FactSalesSellout.distributor_id == did)

    dim_cols: list[tuple[str, Any]] = []
    for g in ("distributor", "customer", "product"):
        if g in grains:
            dim_cols.append((f"{g}_id", _DSI_GRAIN_COLS[g]))
            if g == "distributor":
                conds.append(FactSalesSellout.distributor_id.is_not(None))

    return await _run_grouped_sum(
        db,
        amount_col=FactSalesSellout.units,
        date_col=date_col,
        conds=conds,
        dim_cols=dim_cols,
        period_grain=period_grain,
        vintage_table="fact_sales_sellout",
        explain=explain,
    )


async def _handle_cst(
    db: AsyncSession,
    req: QueryRequest,
    *,
    grains: set[str],
    period_grain: str | None,
    explain: dict[str, Any],
) -> HandlerResult:
    filters = req.filters or {}
    date_col = FactCustomerSellthrough.period_start_date
    conds: list[Any] = [FactCustomerSellthrough.tenant_id == (req.tenant_id or "default")]
    start, end = _date_filters(filters)
    if start is not None:
        conds.append(date_col >= start)
    if end is not None:
        conds.append(date_col <= end)
    cid = _opt_int(filters, "customer_id", "customer")
    if cid is not None:
        conds.append(FactCustomerSellthrough.customer_id == cid)
    pid = _opt_int(filters, "product_id", "product")
    if pid is not None:
        conds.append(FactCustomerSellthrough.product_id == pid)
    site = filters.get("site_label")
    if site is not None and str(site).strip() != "":
        conds.append(FactCustomerSellthrough.site_label == str(site).strip())

    if period_grain is not None:
        type_q = select(func.distinct(FactCustomerSellthrough.period_type)).where(*conds)
        stored = [str(r[0] or "weekly") for r in (await db.execute(type_q)).all()]
        if stored and coarsest_stored_rank(stored) > request_rank(period_grain):
            return HandlerResult(
                status="refused",
                invariants_applied=list(INVARIANTS),
                message=finer_than_stored_message(period_grain, stored),
                explain=explain,
            )

    dim_cols: list[tuple[str, Any]] = []
    for g, col in (
        ("customer", FactCustomerSellthrough.customer_id),
        ("product", FactCustomerSellthrough.product_id),
        ("site_label", FactCustomerSellthrough.site_label),
    ):
        if g in grains:
            dim_cols.append((g if g == "site_label" else f"{g}_id", col))

    return await _run_grouped_sum(
        db,
        amount_col=FactCustomerSellthrough.units_sold,
        date_col=date_col,
        conds=conds,
        dim_cols=dim_cols,
        period_grain=period_grain,
        vintage_table="fact_customer_sellthrough",
        explain=explain,
    )


async def _run_grouped_sum(
    db: AsyncSession,
    *,
    amount_col: Any,
    date_col: Any,
    conds: list[Any],
    dim_cols: list[tuple[str, Any]],
    period_grain: str | None,
    vintage_table: str,
    explain: dict[str, Any],
) -> HandlerResult:
    bucket_expr = date_trunc_expr(date_col, period_grain) if period_grain else None
    select_cols: list[Any] = [func.coalesce(func.sum(amount_col), 0).label("value")]
    group_cols: list[Any] = []
    if bucket_expr is not None:
        select_cols.insert(0, bucket_expr.label("bucket_start"))
        group_cols.append(bucket_expr)
    for name, col in dim_cols:
        select_cols.append(col.label(name))
        group_cols.append(col)

    q = select(*select_cols).where(*conds)
    if group_cols:
        q = q.group_by(*group_cols)
    if bucket_expr is not None:
        q = q.order_by(bucket_expr)
        for _, col in dim_cols:
            q = q.order_by(col)
    elif dim_cols:
        q = q.order_by(*[col for _, col in dim_cols])

    result_rows = (await db.execute(q)).all()
    rows: list[dict[str, Any]] = []
    by_bucket: dict[Any, float] = defaultdict(float)
    total = 0.0
    min_d: Any = None
    max_d: Any = None
    for r in result_rows:
        mapping = r._mapping
        val = float(mapping["value"] or 0)
        total += val
        row: dict[str, Any] = {"value": val}
        if bucket_expr is not None:
            bs = as_date(mapping["bucket_start"])
            if bs is None:
                continue
            point = series_point(bs, period_grain or "week", val)
            row.update(point)
            by_bucket[bs] += val
            min_d = bs if min_d is None or bs < min_d else min_d
            max_d = bs if max_d is None or bs > max_d else max_d
        for name, _ in dim_cols:
            row[name] = mapping[name]
        rows.append(row)

    series = None
    if period_grain:
        series = [
            series_point(bs, period_grain, by_bucket[bs])
            for bs in sorted(by_bucket.keys())
        ]

    vintage = {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "source_table": vintage_table,
        "period_grain": period_grain,
        "row_count": len(rows),
        "bucket_min": min_d.isoformat() if min_d else None,
        "bucket_max": max_d.isoformat() if max_d else None,
        "formula": f"SUM({vintage_table} units) at calendar {period_grain or 'no-period'} grain",
    }
    return HandlerResult(
        status="ok",
        invariants_applied=list(INVARIANTS),
        data_vintage=vintage,
        value=total,
        rows=rows,
        series=series,
        scorecard={"total_units": total, "series_len": len(series or [])},
        explain=explain,
    )
