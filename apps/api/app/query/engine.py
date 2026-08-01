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
) -> QueryResult:
    grains_list = list(grains or [])
    filters_dict = dict(filters or {})
    tid = (tenant_id or "default").strip() or "default"

    validation = validate_metric_grain(metric, grains_list, tenant_id=tid)
    val_dict = validation.as_dict()

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
            handler=handler_name_for(validation.metric_key or metric),
        )

    metric_key = validation.metric_key or metric
    cat = catalog_for_tenant_cached(tid)
    req = QueryRequest(
        metric=metric_key,
        grains=validation.requested_grains,
        filters=filters_dict,
        tenant_id=tid,
    )

    if explain_only:
        handler_name, hr = await dispatch_handler(
            db, req, metric_key=metric_key, explain_only=True
        )
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
            scorecard=hr.scorecard,
            message=hr.message or validation.message,
            handler=handler_name,
            explain=hr.explain,
            cache=None,
        )

    key = cache_key(
        tenant_id=tid,
        metric=metric_key,
        grains=validation.requested_grains,
        filters=filters_dict,
        catalog_version=cat.version,
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
                scorecard=cached.get("scorecard"),
                cache=CacheMeta(hit=True, ttl_seconds=DEFAULT_TTL_SECONDS, key=key),
                message=cached.get("message"),
                handler=cached.get("handler"),
                explain=cached.get("explain"),
            )

    handler_name, hr = await dispatch_handler(
        db, req, metric_key=metric_key, explain_only=False
    )

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
        scorecard=hr.scorecard,
        cache=CacheMeta(hit=False, ttl_seconds=DEFAULT_TTL_SECONDS, key=key),
        message=hr.message or validation.message,
        handler=handler_name,
        explain=hr.explain,
    )

    if hr.status == "ok":
        set_cached(key, result.as_dict(), ttl_seconds=DEFAULT_TTL_SECONDS)

    return result
