"""Run a v2 query on the request ``AsyncSession`` (never a raw engine connection).

The request session's transactions are bound to the caller's product-line scope by the
``after_begin`` listener (core/product_line_scope.py), so row security applies to every
statement here. The statement timeout is ``SET LOCAL`` (this transaction only).
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.query.cache import DEFAULT_TTL_SECONDS, cache_key_v2, get_cached, set_cached
from app.query.calendar_grain import as_date, coarsest_stored_rank, finer_than_stored_message
from app.query.labels import attach_names
from app.query.model.calc import total_for, window_weeks
from app.query.model.compiler import STATEMENT_TIMEOUT_SQL, UNASSIGNED, Compiled, bucket_fields, compile_plan
from app.query.model.explain import build_explain
from app.query.model.graph import Plan, Refusal, V2Request, plan_request
from app.query.model.loader import DataModel, default_model

_SCOPE_SQL = "SELECT current_setting('cip.product_lines', true) AS pl, current_setting('cip.request_role', true) AS role"
_GRAIN_RANK = {"week": 1, "month": 2, "quarter": 3, "year": 4}
_NAMED_ENTITIES = ("customer", "product", "distributor")


def _float(v: Any) -> float | None:
    if v is None:
        return None
    return float(v)


def catalog_version_for(dm: DataModel, v1_catalog: Any) -> str:
    return f"{dm.version}.{dm.digest[:12]}.{getattr(v1_catalog, 'version', 0)}"


def _response(
    *,
    ok: bool,
    columns: list[dict[str, Any]] | None = None,
    rows: list[dict[str, Any]] | None = None,
    totals: dict[str, Any] | None = None,
    refusals: list[Refusal] | None = None,
    explain: dict[str, Any] | None = None,
    cache: dict[str, Any] | None = None,
    truncated: bool = False,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "columns": columns or [],
        "rows": rows or [],
        "totals": totals or {},
        "truncated": truncated,
        "refusals": [r.as_dict() for r in (refusals or [])],
        "explain": explain,
        "cache": cache,
    }


def _columns_payload(compiled: Compiled) -> list[dict[str, Any]]:
    out = []
    for c in compiled.columns:
        d = {"id": c.id, "kind": c.kind, "label": c.label, "fields": c.fields}
        if c.kind == "measure":
            d["unit"] = c.unit
        else:
            d["group"] = c.group
        out.append(d)
    return out


async def _rows_from(db: AsyncSession, plan: Plan, compiled: Compiled, result: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in result:
        m = r._mapping
        row: dict[str, Any] = {}
        for col in compiled.columns:
            if col.kind == "measure":
                row[col.id] = _float(m[col.sql_label])
            elif col.id == "period":
                bs = as_date(m["bucket_start"])
                if bs is not None and plan.period_grain:
                    row.update(bucket_fields(bs, plan.period_grain))
            elif len(col.fields) == 2:  # entity / reference: id + name
                row[col.fields[0]] = m[col.fields[0]]
                if col.fields[1] in m:
                    row[col.fields[1]] = m[col.fields[1]]
            else:
                row[col.id] = m[col.id]
        rows.append(row)
    # Names beside ids (Warren 2026-10-20), with the v1 helper; a null key reads "Unassigned".
    await attach_names(db, rows)
    for row in rows:
        for e in _NAMED_ENTITIES:
            if f"{e}_id" in row and row[f"{e}_id"] is None:
                row[f"{e}_name"] = UNASSIGNED
    return rows


async def run_v2(
    db: AsyncSession,
    req: V2Request,
    *,
    tenant_id: str,
    explain_only: bool = False,
    skip_cache: bool = False,
    dm: DataModel | None = None,
) -> dict[str, Any]:
    from app.semantics.registry import catalog_for_tenant_cached

    dm = dm or default_model()
    tid = (tenant_id or "default").strip() or "default"
    v1_catalog = catalog_for_tenant_cached(tid)
    version = catalog_version_for(dm, v1_catalog)
    plan = plan_request(dm, req, v1_catalog=v1_catalog)

    if plan.governed is not None:
        return await _run_governed(db, plan, tid=tid, explain_only=explain_only, version=version)

    if not plan.measures:
        return _response(ok=False, refusals=plan.refusals, explain=build_explain(dm, plan, None, catalog_version=version))

    compiled = compile_plan(dm, plan, tenant_id=tid)
    if explain_only:
        explain = build_explain(dm, plan, compiled, catalog_version=version)
        if compiled.stored_types is not None:
            explain["notes"].append("The stored-period check (W-ONE-STORED-PERIOD) runs at execute.")
        return _response(ok=True, columns=_columns_payload(compiled), refusals=plan.refusals, explain=explain)

    key = cache_key_v2(tenant_id=tid, request=req.canonical(), catalog_version=version)
    if not skip_cache:
        cached = get_cached(key)
        if cached is not None:
            cached["cache"] = {"hit": True, "ttl_seconds": DEFAULT_TTL_SECONDS, "key": key}
            return cached

    t0 = time.perf_counter()
    await db.execute(text(STATEMENT_TIMEOUT_SQL))
    scope_row = (await db.execute(text(_SCOPE_SQL))).one()
    scope = {"product_lines": scope_row.pl or None, "role": scope_row.role or None, "source": "this transaction"}

    if compiled.stored_types is not None and plan.period_grain:
        stored = [str(r[0] or "weekly") for r in (await db.execute(compiled.stored_types)).all()]
        if stored and coarsest_stored_rank(stored) > _GRAIN_RANK[plan.period_grain]:
            msg = finer_than_stored_message(plan.period_grain, stored)
            refusals = plan.refusals + [Refusal(measure=m.id, reason=msg, wall="W-ONE-STORED-PERIOD") for m in plan.measures]
            explain = build_explain(dm, plan, compiled, catalog_version=version, scope=scope)
            return _response(ok=False, refusals=refusals, explain=explain)

    result = list((await db.execute(compiled.rows)).all())
    truncated = len(result) > plan.limit
    result = result[: plan.limit]
    row_count = len(result) if not truncated else int((await db.execute(compiled.count)).scalar_one())
    trow = (await db.execute(compiled.totals)).one()._mapping
    ms = round((time.perf_counter() - t0) * 1000, 1)

    rows = await _rows_from(db, plan, compiled, result)
    base_totals: dict[str, Decimal | None] = {mid: trow[lab] for mid, lab in compiled.total_labels.items()}
    vmin = as_date(trow.get("vintage_min")) if "vintage_min" in trow else None
    vmax = as_date(trow.get("vintage_max")) if "vintage_max" in trow else None
    weeks = compiled.weeks_in_window or window_weeks(
        period_from=plan.period_from,
        period_to=plan.period_to,
        grain=plan.period_grain if "period" in plan.breakdowns else None,
        vintage_min=vmin,
        vintage_max=vmax,
    )
    totals = {m.id: _float(total_for(dm, m, base_totals, weeks=weeks)) for m in plan.measures}

    explain = build_explain(dm, plan, compiled, catalog_version=version, scope=scope)
    explain["ms"] = ms
    explain["row_count"] = row_count
    explain["data_vintage"] = {"min": vmin.isoformat() if vmin else None, "max": vmax.isoformat() if vmax else None}
    resp = _response(
        ok=True,
        columns=_columns_payload(compiled),
        rows=rows,
        totals=totals,
        refusals=plan.refusals,
        explain=explain,
        cache={"hit": False, "ttl_seconds": DEFAULT_TTL_SECONDS, "key": key},
        truncated=truncated,
    )
    set_cached(key, resp, ttl_seconds=DEFAULT_TTL_SECONDS)
    return resp


async def _run_governed(db: AsyncSession, plan: Plan, *, tid: str, explain_only: bool, version: str) -> dict[str, Any]:
    """A governed (v1 handler) metric: the v1 engine runs unchanged; v2 reshapes the answer."""
    from app.query.engine import execute_query
    from app.semantics.registry import catalog_for_tenant_cached

    metric = plan.governed
    res = await execute_query(
        db,
        metric=metric.key,
        grains=plan.breakdowns,
        filters=plan.governed_filters,
        tenant_id=tid,
        explain_only=explain_only,
        period_grain=plan.period_grain,
    )
    cat = catalog_for_tenant_cached(tid)
    columns: list[dict[str, Any]] = []
    for g in res.grains:
        dim = next((d for d in cat.dimensions if d.id == g), None)
        fields = ["bucket_key", "bucket_start", "bucket_end"] if g == "period" else (
            [f"{g}_id", f"{g}_name"] if g in _NAMED_ENTITIES else [g]
        )
        columns.append({"id": g, "kind": "breakdown", "label": dim.label if dim else g, "fields": fields, "group": None})
    columns.append({"id": metric.key, "kind": "measure", "label": metric.label, "fields": [metric.key], "unit": None})
    rows = [{**r, metric.key: r.get("value")} for r in (res.rows or []) if isinstance(r, dict)]
    refusals = [] if res.ok else [Refusal(measure=metric.key, reason=res.message or res.status)]
    explain = {
        "engine": "governed_handler",
        "catalog_version": version,
        "handler": res.handler,
        "status": res.status,
        "validation": res.validation,
        "invariants_applied": res.invariants_applied,
        "handler_explain": res.explain,
        "walls_checked": sorted(set(plan.walls_checked)),
        "data_vintage": res.data_vintage,
    }
    return _response(
        ok=res.ok,
        columns=columns,
        rows=rows,
        totals={metric.key: res.value},
        refusals=refusals,
        explain=explain,
        cache=res.cache.as_dict() if res.cache else None,
    )
