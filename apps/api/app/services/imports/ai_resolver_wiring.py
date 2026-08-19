# Plan (AI resolver wiring for existing import handlers):
# - Deterministic resolution runs first; these helpers run only after it fails.
# - All API calls gated by Settings.ai_assist_enabled; disabled path is a no-op.
# - Never raise on AI failure; return None and leave entity unresolved.

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.ingestion import ImportJob
from app.services.imports.ai_import_resolver import (
    AI_AUTO_RESOLVE_THRESHOLD,
    TokenResolutionSuggestion,
    detect_format_drift,
    suggest_token_resolution,
)
from app.services.imports.distributor_sales_inventory import DSIResolutionCache, ProductResolutionIndex
from app.utils.json_safe import to_jsonable


def stored_mapping_headers(column_mapping_memory: dict | None) -> list[str]:
    if not isinstance(column_mapping_memory, dict):
        return []
    known = column_mapping_memory.get("known_headers")
    if isinstance(known, list):
        return [str(h) for h in known if h]
    bh = column_mapping_memory.get("by_header_norm")
    if isinstance(bh, dict):
        return list(bh.keys())
    return []


def record_format_drift_on_job(
    job: ImportJob,
    *,
    current_headers: list[str],
    column_mapping_memory: dict | None,
    field_mapping: dict,
) -> None:
    if not get_settings().ai_assist_enabled:
        return
    stored_headers = stored_mapping_headers(column_mapping_memory)
    if not stored_headers:
        return
    drift = detect_format_drift(current_headers, stored_headers, field_mapping or {})
    if drift is None or not drift.has_drift:
        return
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta["format_drift_detected"] = to_jsonable(
        {
            "new_columns": drift.new_columns,
            "missing_columns": drift.missing_columns,
            "confidence": drift.confidence,
        }
    )
    job.staged_metadata = to_jsonable(meta)


def _dim_record_candidates(
    rows: list[Any],
    *,
    code_attr: str = "code",
    name_attr: str = "name",
) -> list[dict[str, Any]]:
    from app.services.merge_redirect import is_merged_customer_row, is_merged_distributor_row

    out: list[dict[str, Any]] = []
    for row in rows:
        if is_merged_customer_row(row) or is_merged_distributor_row(row):
            continue
        rid = getattr(row, "id", None)
        if rid is None:
            continue
        out.append(
            {
                "id": int(rid),
                "code": str(getattr(row, code_attr, "") or ""),
                "name": str(getattr(row, name_attr, "") or ""),
            }
        )
    return out


def distributor_candidates_from_dim_list(
    distributors: list[Any],
    raw_token: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """In-memory distributor candidates (e.g. distributor_master preload) — no DB round-trip."""
    key = (raw_token or "").strip().lower()
    rows = list(distributors)
    if key:
        filtered = [
            d
            for d in rows
            if key in (getattr(d, "code", None) or "").lower() or key in (getattr(d, "name", None) or "").lower()
        ]
        rows = filtered[:limit] if filtered else rows[:limit]
    else:
        rows = rows[:limit]
    return _dim_record_candidates(rows, code_attr="code", name_attr="name")


def distributor_candidates(db: Session, raw_token: str, *, limit: int = 20) -> list[dict[str, Any]]:
    from app.services.merge_redirect import living_distributor_clause

    key = (raw_token or "").strip().lower()
    q = select(DimDistributor).where(living_distributor_clause()).limit(limit * 3)
    rows = list(db.scalars(q).all())
    if key:
        filtered = [
            d
            for d in rows
            if key in (d.code or "").lower() or key in (d.name or "").lower()
        ]
        if filtered:
            rows = filtered[:limit]
        else:
            rows = rows[:limit]
    else:
        rows = rows[:limit]
    return _dim_record_candidates(rows, code_attr="code", name_attr="name")


def customer_candidates(db: Session, raw_token: str, *, limit: int = 20) -> list[dict[str, Any]]:
    from app.services.merge_redirect import living_customer_clause

    key = (raw_token or "").strip().lower()
    rows = list(db.scalars(select(DimCustomer).where(living_customer_clause()).limit(limit * 3)).all())
    if key:
        filtered = [
            c
            for c in rows
            if key in (c.code or "").lower() or key in (c.name or "").lower()
        ]
        rows = (filtered or rows)[:limit]
    else:
        rows = rows[:limit]
    return _dim_record_candidates(rows, code_attr="code", name_attr="name")


def customer_candidates_from_cache(
    res_cache: DSIResolutionCache,
    raw_token: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """In-memory ``customer_candidates`` — no per-row ``SELECT dim_customer``."""
    key = (raw_token or "").strip().lower()
    rows = res_cache.all_customers
    if key:
        filtered = [
            c
            for c in rows
            if key in (c.code or "").lower() or key in (c.name or "").lower()
        ]
        rows = (filtered or rows)[:limit]
    else:
        rows = rows[:limit]
    return _dim_record_candidates(rows, code_attr="code", name_attr="name")


def distributor_candidates_from_cache(
    res_cache: DSIResolutionCache,
    raw_token: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """In-memory ``distributor_candidates`` — no per-row ``SELECT dim_distributor``."""
    key = (raw_token or "").strip().lower()
    rows = res_cache.all_distributors
    if key:
        filtered = [
            d
            for d in rows
            if key in (d.code or "").lower() or key in (d.name or "").lower()
        ]
        if filtered:
            rows = filtered[:limit]
        else:
            rows = rows[:limit]
    else:
        rows = rows[:limit]
    return _dim_record_candidates(rows, code_attr="code", name_attr="name")


def product_candidates_from_index(
    idx: ProductResolutionIndex,
    raw_token: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    from app.services.imports.distributor_sales_inventory import _product_token_key

    key = _product_token_key(raw_token)
    out: list[dict[str, Any]] = []
    if key:
        for sku, pid in idx.sku_to_id.items():
            if key in sku or sku in key:
                out.append({"id": int(pid), "code": sku, "name": sku})
                if len(out) >= limit:
                    return out
    for sku, pid in list(idx.sku_to_id.items())[:limit]:
        out.append({"id": int(pid), "code": sku, "name": sku})
    return out[:limit]


def product_candidates_from_db(db: Session, raw_token: str, *, limit: int = 20) -> list[dict[str, Any]]:
    key = (raw_token or "").strip().lower()
    rows = list(db.scalars(select(DimProduct).where(DimProduct.is_active.is_(True)).limit(limit * 3)).all())
    if key:
        filtered = [
            p
            for p in rows
            if key in (p.sku or "").lower()
            or key in (p.part_number or "").lower()
            or key in (p.name or "").lower()
        ]
        rows = (filtered or rows)[:limit]
    else:
        rows = rows[:limit]
    return [
        {
            "id": int(p.id),
            "code": p.sku or p.part_number or "",
            "name": p.name or "",
        }
        for p in rows
    ]


def append_ai_diagnostic(
    diagnostic_codes: list[Any] | None,
    *,
    token_type: str,
    suggestion: TokenResolutionSuggestion,
) -> list[Any]:
    codes: list[Any] = list(diagnostic_codes or [])
    codes.append(
        {
            "type": "ai_suggestion",
            "token_type": token_type,
            "suggested_id": suggestion.best_match_id,
            "confidence": suggestion.confidence,
            "reasoning": suggestion.reasoning,
            "alternatives": suggestion.alternatives,
        }
    )
    return codes


def try_ai_token_resolution(
    *,
    raw_token: str | None,
    token_type: str,
    candidates: list[dict],
    import_type: str,
    job_id: int,
    extra_context: dict[str, Any] | None = None,
) -> tuple[int | None, str | None, TokenResolutionSuggestion | None]:
    """After deterministic failure. Returns (entity_id, status_tag, suggestion)."""
    if not raw_token or not str(raw_token).strip():
        return None, None, None
    if not get_settings().ai_assist_enabled:
        return None, None, None

    ctx: dict[str, Any] = {"import_type": import_type, "job_id": job_id}
    if extra_context:
        ctx.update(extra_context)

    suggestion = suggest_token_resolution(
        str(raw_token).strip(),
        token_type,
        candidates,
        ctx,
    )
    if suggestion is None:
        return None, None, None

    if suggestion.best_match_id is not None and suggestion.confidence >= AI_AUTO_RESOLVE_THRESHOLD:
        return int(suggestion.best_match_id), "ai_auto_resolved", suggestion
    return None, "ai_suggested", suggestion


def stash_ai_suggestion_on_payload(
    payload: dict[str, Any] | None,
    *,
    token_type: str,
    suggestion: TokenResolutionSuggestion,
) -> dict[str, Any]:
    base = dict(payload or {})
    block = base.get("_ai_resolution")
    if not isinstance(block, dict):
        block = {}
    block[token_type] = {
        "suggested_id": suggestion.best_match_id,
        "confidence": suggestion.confidence,
        "reasoning": suggestion.reasoning,
        "alternatives": suggestion.alternatives,
    }
    base["_ai_resolution"] = block
    return to_jsonable(base)  # type: ignore[return-value]
