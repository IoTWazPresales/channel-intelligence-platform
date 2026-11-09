"""Execute D-0119 distributor stock carry-forward queries (read-time)."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facts import FactInventoryDistributor
from app.query.cache import DEFAULT_TTL_SECONDS, cache_key_v2, get_cached, set_cached
from app.query.labels import attach_names
from app.query.model.explain import build_explain
from app.query.model.graph import Plan, Refusal, V2Request
from app.query.model.loader import DataModel, Measure
from app.query.model.stock_carry_forward import (
    StockObservation,
    carry_forward_all,
    rollup_carry_rows,
)
from app.query.model.compiler import UNASSIGNED, STATEMENT_TIMEOUT_SQL
from sqlalchemy import text

_FLAG_ID = "distributor_stock.on_hand_carried_forward"
_ON_HAND_ID = "distributor_stock.on_hand"
_NAMED = ("customer", "product", "distributor")


def _columns_for(plan: Plan, dm: DataModel) -> list[dict[str, Any]]:
    cols: list[dict[str, Any]] = []
    for bid in plan.breakdowns:
        label, group = dm.breakdown_label(bid)
        if bid == "period":
            fields = ["bucket_key", "bucket_start", "bucket_end"]
        elif bid in ("product", "distributor", "customer"):
            fields = [f"{bid}_id", f"{bid}_name"]
        else:
            fields = [bid]
        cols.append({"id": bid, "kind": "breakdown", "label": label, "fields": fields, "group": group})
    for m in plan.measures:
        if isinstance(m, Measure):
            cols.append({"id": m.id, "kind": "measure", "label": m.label, "fields": [m.id], "unit": m.unit})
    cols.append(
        {
            "id": _FLAG_ID,
            "kind": "measure",
            "label": "Carried forward from an earlier count",
            "fields": [_FLAG_ID],
            "unit": "flag",
        }
    )
    return cols


def _apply_filters(stmt: Select[Any], plan: Plan) -> Select[Any]:
    f = FactInventoryDistributor
    for flt in plan.filters:
        if flt.breakdown == "distributor":
            vals = [int(v) for v in flt.values if v is not None and str(v).strip() != ""]
            if vals:
                stmt = stmt.where(f.distributor_id.in_(vals))
        elif flt.breakdown == "product":
            vals = [int(v) for v in flt.values if v is not None and str(v).strip() != ""]
            if vals:
                stmt = stmt.where(f.product_id.in_(vals))
    return stmt


async def run_carry_forward_stock(
    db: AsyncSession,
    *,
    plan: Plan,
    req: V2Request,
    dm: DataModel,
    tenant_id: str,
    version: str,
    explain_only: bool,
    skip_cache: bool,
) -> dict[str, Any]:
    from app.query.model.execute import _response

    assert plan.period_from is not None and plan.period_to is not None and plan.period_grain
    if not plan.measures or "period" not in plan.breakdowns:
        return _response(ok=False, refusals=plan.refusals, explain=build_explain(dm, plan, None, catalog_version=version))
    if plan.calendar is not None:
        return _response(
            ok=False,
            refusals=plan.refusals
            + [
                Refusal(
                    measure="distributor_stock.on_hand",
                    reason=(
                        "Distributor stock carry-forward by period uses the platform calendar "
                        "(Monday weeks, Gregorian months). This tenant's business calendar is not supported yet."
                    ),
                )
            ],
            explain=build_explain(dm, plan, None, catalog_version=version),
        )
    columns = _columns_for(plan, dm)
    explain = build_explain(dm, plan, None, catalog_version=version)
    explain["notes"] = list(plan.notes) + [
        "D-0119 carry-forward is computed at read time from fact_inventory_distributor; no stored carry column."
    ]
    if explain_only:
        return _response(ok=True, columns=columns, refusals=plan.refusals, explain=explain)

    key = cache_key_v2(
        tenant_id=tenant_id,
        request=req.canonical(),
        catalog_version=version,
        calendar=None if plan.calendar is None else dict(plan.calendar.config),
    )
    if not skip_cache:
        cached = get_cached(key)
        if cached is not None:
            cached["cache"] = {"hit": True, "ttl_seconds": DEFAULT_TTL_SECONDS, "key": key}
            return cached

    t0 = time.perf_counter()
    await db.execute(text(STATEMENT_TIMEOUT_SQL))
    f = FactInventoryDistributor
    stmt = select(f.distributor_id, f.product_id, f.as_of_date, f.on_hand_units).where(
        and_(f.tenant_id == tenant_id, f.as_of_date <= plan.period_to)
    )
    stmt = _apply_filters(stmt, plan)
    raw = (await db.execute(stmt)).all()
    observations = [
        StockObservation(
            distributor_id=int(r.distributor_id),
            product_id=int(r.product_id),
            as_of_date=r.as_of_date,
            on_hand_units=float(r.on_hand_units),
        )
        for r in raw
    ]
    pair_rows = carry_forward_all(
        observations,
        period_from=plan.period_from,
        period_to=plan.period_to,
        grain=plan.period_grain,
    )
    rolled = rollup_carry_rows(pair_rows, breakdowns=plan.breakdowns)

    rows: list[dict[str, Any]] = []
    for r in rolled:
        row: dict[str, Any] = {}
        if "period" in plan.breakdowns:
            row["bucket_key"] = r["bucket_key"]
            row["bucket_start"] = r["bucket_start"].isoformat()
            row["bucket_end"] = r["bucket_end"].isoformat()
        if "distributor" in plan.breakdowns:
            row["distributor_id"] = r["distributor_id"]
        if "product" in plan.breakdowns:
            row["product_id"] = r["product_id"]
        row[_ON_HAND_ID] = float(r["on_hand"])
        row[_FLAG_ID] = 1.0 if r["carried_forward"] else 0.0
        rows.append(row)

    await attach_names(db, rows)
    for row in rows:
        for e in _NAMED:
            if f"{e}_id" in row and row[f"{e}_id"] is None:
                row[f"{e}_name"] = UNASSIGNED

    # Totals: stock as of period_to (last bucket), never a sum across periods.
    last_bs = None
    if rows and "period" in plan.breakdowns:
        last_bs = max(date.fromisoformat(r["bucket_start"]) for r in rows)
    total_on_hand = 0.0
    total_flag = 1.0
    matched = 0
    for r in rows:
        if last_bs is not None and date.fromisoformat(r["bucket_start"]) != last_bs:
            continue
        total_on_hand += float(r[_ON_HAND_ID] or 0)
        if not r[_FLAG_ID]:
            total_flag = 0.0
        matched += 1
    if matched == 0:
        totals = {_ON_HAND_ID: None, _FLAG_ID: None}
    else:
        totals = {_ON_HAND_ID: total_on_hand, _FLAG_ID: total_flag}

    # Sort / limit
    reverse = plan.sort_dir == "desc"
    sort_by = plan.sort_by or ("bucket_start" if "period" in plan.breakdowns else _ON_HAND_ID)

    def sort_key(row: dict[str, Any]) -> Any:
        if sort_by in ("period", "bucket_start"):
            return row.get("bucket_start") or ""
        if sort_by == _FLAG_ID:
            return row.get(_FLAG_ID) or 0
        if sort_by == _ON_HAND_ID or sort_by.endswith(".on_hand"):
            return row.get(_ON_HAND_ID) if row.get(_ON_HAND_ID) is not None else -1
        if sort_by in plan.breakdowns:
            return row.get(f"{sort_by}_id") or row.get(sort_by) or ""
        return row.get(sort_by) or ""

    rows.sort(key=sort_key, reverse=reverse)
    truncated = len(rows) > plan.limit
    rows = rows[: plan.limit]
    ms = round((time.perf_counter() - t0) * 1000, 1)
    explain["ms"] = ms
    explain["row_count"] = len(rows)
    resp = _response(
        ok=True,
        columns=columns,
        rows=rows,
        totals=totals,
        refusals=plan.refusals,
        explain=explain,
        cache={"hit": False, "ttl_seconds": DEFAULT_TTL_SECONDS, "key": key},
        truncated=truncated,
    )
    set_cached(key, resp, ttl_seconds=DEFAULT_TTL_SECONDS)
    return resp
