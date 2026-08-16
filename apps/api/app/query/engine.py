"""P3-2 query engine — validate (P3-1) → cache → handler dispatch."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.query.cache import (
    DEFAULT_TTL_SECONDS,
    cache_key,
    get_cached,
    set_cached,
)
from app.query.compose import evaluate_composed, resolve_composed
from app.query.handlers import dispatch_handler, handler_name_for
from app.query.types import CacheMeta, QueryRequest, QueryResult
from app.semantics.registry import catalog_for_tenant_cached, validate_metric_grain


async def execute_query(
    db: AsyncSession,
    *,
    metric: str,
    grains: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    tenant_id: str = "default",
    explain_only: bool = False,
    skip_cache: bool = False,
    period_grain: str | None = None,
) -> QueryResult:
    grains_list = list(grains or [])
    filters_dict = dict(filters or {})
    tid = (tenant_id or "default").strip() or "default"
    pg_raw = period_grain if period_grain not in (None, "") else filters_dict.get("period_grain")
    cat = catalog_for_tenant_cached(tid)

    validation = validate_metric_grain(
        metric, grains_list, catalog=cat, tenant_id=tid, period_grain=pg_raw
    )
    val_dict = validation.as_dict()
    effective_pg = validation.period_grain

    if not validation.ok:
        return QueryResult(
            ok=False,
            status="refused",
            metric_id=validation.metric_id,
            metric_key=validation.metric_key,
            grains=validation.requested_grains,
            filters=filters_dict,
            validation=val_dict,
            message=validation.message,
            handler=handler_name_for(validation.metric_key or metric, catalog=cat),
            period_grain=effective_pg,
        )

    metric_key = validation.metric_key or metric
    req = QueryRequest(
        metric=metric_key,
        grains=validation.requested_grains,
        filters=filters_dict,
        tenant_id=tid,
        period_grain=effective_pg,
    )
    composed = resolve_composed(metric_key, cat)

    async def _run(*, explain: bool):
        if composed is not None:
            hr = await evaluate_composed(db, req, composed, cat, explain_only=explain)
            return "composed", hr
        return await dispatch_handler(db, req, metric_key=metric_key, explain_only=explain)

    if explain_only:
        handler_name, hr = await _run(explain=True)
        return QueryResult(
            ok=hr.status == "ok",
            status=hr.status,
            metric_id=validation.metric_id,
            metric_key=metric_key,
            grains=validation.requested_grains,
            filters=filters_dict,
            validation=val_dict,
            invariants_applied=hr.invariants_applied,
            data_vintage=hr.data_vintage,
            value=hr.value,
            rows=hr.rows,
            series=hr.series,
            scorecard=hr.scorecard,
            message=hr.message or validation.message,
            handler=handler_name,
            explain=hr.explain,
            cache=None,
            period_grain=effective_pg,
        )

    key = cache_key(
        tenant_id=tid,
        metric=metric_key,
        grains=validation.requested_grains,
        filters=filters_dict,
        catalog_version=cat.version,
        period_grain=effective_pg,
    )

    if not skip_cache:
        cached = get_cached(key)
        if cached is not None:
            cached = dict(cached)
            cached["cache"] = CacheMeta(hit=True, ttl_seconds=DEFAULT_TTL_SECONDS, key=key).as_dict()
            # Rebuild QueryResult from cached envelope
            return QueryResult(
                ok=bool(cached.get("ok")),
                status=cached.get("status") or "ok",  # type: ignore[arg-type]
                metric_id=cached.get("metric_id"),
                metric_key=cached.get("metric_key"),
                grains=list(cached.get("grains") or []),
                filters=dict(cached.get("filters") or {}),
                validation=dict(cached.get("validation") or val_dict),
                invariants_applied=list(cached.get("invariants_applied") or []),
                data_vintage=cached.get("data_vintage"),
                value=cached.get("value"),
                rows=cached.get("rows"),
                series=cached.get("series"),
                scorecard=cached.get("scorecard"),
                cache=CacheMeta(hit=True, ttl_seconds=DEFAULT_TTL_SECONDS, key=key),
                message=cached.get("message"),
                handler=cached.get("handler"),
                explain=cached.get("explain"),
                period_grain=cached.get("period_grain") or effective_pg,
            )

    handler_name, hr = await _run(explain=False)

    result = QueryResult(
        ok=hr.status == "ok",
        status=hr.status,
        metric_id=validation.metric_id,
        metric_key=metric_key,
        grains=validation.requested_grains,
        filters=filters_dict,
        validation=val_dict,
        invariants_applied=hr.invariants_applied,
        data_vintage=hr.data_vintage,
        value=hr.value,
        rows=hr.rows,
        series=hr.series,
        scorecard=hr.scorecard,
        cache=CacheMeta(hit=False, ttl_seconds=DEFAULT_TTL_SECONDS, key=key),
        message=hr.message or validation.message,
        handler=handler_name,
        explain=hr.explain,
        period_grain=effective_pg,
    )

    if hr.status == "ok":
        set_cached(key, result.as_dict(), ttl_seconds=DEFAULT_TTL_SECONDS)

    return result
