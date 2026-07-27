"""CST import mapping candidate management.

Aggregates unresolved product/location tokens from CST staging lines into
``ImportEntityMappingCandidate`` rows so the shared steward UI can surface and
resolve them before the apply pass.

Entity types:
  ``cst_product_token``   — raw product token that didn't resolve against DimProduct
  ``cst_location_token``  — raw location token that didn't resolve against CustomerLocation
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.cst_candidate_suggestions import (
    build_cst_suggestions_for_candidate,
    load_product_index,
)
from app.services.imports.customer_sell_through import resolve_customer_id_for_job
from app.services.imports.distributor_sales_inventory import _product_token_key
from app.utils.json_safe import to_jsonable

logger = logging.getLogger(__name__)

CST_PRODUCT_ENTITY = "cst_product_token"
CST_LOCATION_ENTITY = "cst_location_token"
_CST_ENTITY_TYPES = (CST_PRODUCT_ENTITY, CST_LOCATION_ENTITY)
_CST_TERMINAL_STATUSES = frozenset({"resolved", "ignored"})


class CstCandidateOpError(Exception):
    """HTTP-mappable steward operation error."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _location_token_key(raw: str | None) -> str:
    if raw is None:
        return ""
    t = str(raw).strip().lower()
    return t if t and t != "nan" else ""


def _apply_suggestions_to_candidate(
    cand: ImportEntityMappingCandidate, suggestions: list[dict[str, Any]]
) -> None:
    ctx = dict(cand.context) if isinstance(cand.context, dict) else {}
    if suggestions:
        top = suggestions[0]
        cand.suggested_entity_id = int(top["dim_id"])
        cand.match_reason = str(top["reason"])
        cand.confidence_score = float(top["score"])
        ctx["suggestions"] = to_jsonable(suggestions)
    else:
        cand.suggested_entity_id = None
        cand.match_reason = None
        cand.confidence_score = None
        ctx.pop("suggestions", None)
    cand.context = to_jsonable(ctx)


def enrich_cst_open_candidates(db: Session, job_id: int) -> None:
    """Enrich open CST candidates with deterministic product/location suggestions."""
    job = db.get(ImportJob, job_id)
    if job is None:
        return

    customer_id = resolve_customer_id_for_job(db, job)
    product_index = load_product_index(db)

    open_candidates = list(
        db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == job_id,
                ImportEntityMappingCandidate.entity_type.in_(_CST_ENTITY_TYPES),
                ImportEntityMappingCandidate.status.notin_(tuple(_CST_TERMINAL_STATUSES)),
            )
        ).all()
    )
    if not open_candidates:
        return

    for cand in open_candidates:
        samples = cand.sample_raw_values if isinstance(cand.sample_raw_values, list) else None
        suggestions = build_cst_suggestions_for_candidate(
            db,
            entity_type=str(cand.entity_type),
            normalized_key=str(cand.normalized_key),
            product_index=product_index,
            customer_id=customer_id,
            sample_raw_values=samples,
        )
        _apply_suggestions_to_candidate(cand, suggestions)

    db.flush()


def upsert_cst_mapping_candidates(db: Session, job_id: int) -> None:
    """Aggregate unresolved staging tokens into ImportEntityMappingCandidate rows.

    Preserves terminal-status candidates (resolved/ignored) so steward resolutions
    survive pipeline re-runs.  Updates aggregate counts for open candidates.
    Cleans up stale needs_review candidates for tokens now resolved deterministically.
    """
    lines = db.scalars(
        select(ImportCustomerSellthroughStagingLine).where(
            ImportCustomerSellthroughStagingLine.import_job_id == job_id
        )
    ).all()

    product_agg: dict[str, dict[str, Any]] = {}
    location_agg: dict[str, dict[str, Any]] = {}

    for line in lines:
        if line.resolved_product_id is None and line.raw_product_token:
            key = _product_token_key(line.raw_product_token)
            if key:
                agg = product_agg.setdefault(key, {"row_count": 0, "total_units": None, "samples": []})
                agg["row_count"] += 1
                if line.units_sold is not None:
                    agg["total_units"] = (agg["total_units"] or 0.0) + float(line.units_sold)
                if len(agg["samples"]) < 5 and line.raw_product_token not in agg["samples"]:
                    agg["samples"].append(line.raw_product_token)

        if line.resolved_location_id is None and line.raw_location_token:
            key = _location_token_key(line.raw_location_token)
            if key:
                agg = location_agg.setdefault(key, {"row_count": 0, "samples": []})
                agg["row_count"] += 1
                if len(agg["samples"]) < 5 and line.raw_location_token not in agg["samples"]:
                    agg["samples"].append(line.raw_location_token)

    existing = {
        (r.entity_type, r.normalized_key): r
        for r in db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == job_id,
                ImportEntityMappingCandidate.entity_type.in_(_CST_ENTITY_TYPES),
            )
        ).all()
    }

    for key, data in product_agg.items():
        ex = existing.get((CST_PRODUCT_ENTITY, key))
        if ex is None:
            db.add(
                ImportEntityMappingCandidate(
                    import_job_id=job_id,
                    entity_type=CST_PRODUCT_ENTITY,
                    normalized_key=key[:512],
                    row_count=data["row_count"],
                    total_units=data["total_units"],
                    sample_raw_values=to_jsonable(data["samples"]),
                    status="needs_review",
                )
            )
        elif ex.status not in _CST_TERMINAL_STATUSES:
            ex.row_count = data["row_count"]
            ex.total_units = data["total_units"]
            ex.sample_raw_values = to_jsonable(data["samples"])

    for (etype, key), ex in list(existing.items()):
        if etype == CST_PRODUCT_ENTITY and key not in product_agg and ex.status not in _CST_TERMINAL_STATUSES:
            db.delete(ex)

    for key, data in location_agg.items():
        ex = existing.get((CST_LOCATION_ENTITY, key))
        if ex is None:
            db.add(
                ImportEntityMappingCandidate(
                    import_job_id=job_id,
                    entity_type=CST_LOCATION_ENTITY,
                    normalized_key=key[:512],
                    row_count=data["row_count"],
                    sample_raw_values=to_jsonable(data["samples"]),
                    status="needs_review",
                )
            )
        elif ex.status not in _CST_TERMINAL_STATUSES:
            ex.row_count = data["row_count"]
            ex.sample_raw_values = to_jsonable(data["samples"])

    for (etype, key), ex in list(existing.items()):
        if etype == CST_LOCATION_ENTITY and key not in location_agg and ex.status not in _CST_TERMINAL_STATUSES:
            db.delete(ex)

    db.flush()
    enrich_cst_open_candidates(db, job_id)


def load_resolved_cst_candidates(
    db: Session, job_id: int
) -> tuple[dict[str, int], dict[str, int]]:
    """Return (product_map, location_map) of steward-resolved candidates.

    Keys are normalized_key strings; values are suggested_entity_id integers.
    Only includes candidates where status='resolved' and suggested_entity_id is set.
    """
    resolved = db.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.import_job_id == job_id,
            ImportEntityMappingCandidate.entity_type.in_(_CST_ENTITY_TYPES),
            ImportEntityMappingCandidate.status == "resolved",
            ImportEntityMappingCandidate.suggested_entity_id.isnot(None),
        )
    ).all()

    product_map: dict[str, int] = {}
    location_map: dict[str, int] = {}
    for cand in resolved:
        if cand.entity_type == CST_PRODUCT_ENTITY:
            product_map[cand.normalized_key] = int(cand.suggested_entity_id)
        else:
            location_map[cand.normalized_key] = int(cand.suggested_entity_id)

    return product_map, location_map


def cst_mapping_state_dict(job: ImportJob) -> dict[str, Any]:
    """Return CST mapping wizard state for the steward endpoint."""
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    parse_error = meta.get("customer_sellthrough_error")
    blocking_errors: list[str] = []
    if parse_error and isinstance(parse_error, dict) and parse_error.get("message"):
        blocking_errors.append(str(parse_error["message"])[:500])

    customer_id: int | None = None
    raw_cid = meta.get("customer_id")
    if raw_cid is not None:
        try:
            customer_id = int(raw_cid)
        except (TypeError, ValueError):
            customer_id = None
    if customer_id is None:
        source = getattr(job, "source", None)
        if source is not None:
            expected = getattr(source, "expected_template", None)
            if isinstance(expected, dict) and expected.get("customer_id") is not None:
                try:
                    customer_id = int(expected["customer_id"])
                except (TypeError, ValueError):
                    customer_id = None

    return {
        "job_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "import_mode": job.import_mode,
        "customer_id": customer_id,
        "blocking_errors": blocking_errors,
        "staged_metadata": meta,
    }


def _suggestions_from_candidate(r: ImportEntityMappingCandidate) -> list[dict[str, Any]]:
    ctx = r.context if isinstance(r.context, dict) else {}
    stored = ctx.get("suggestions")
    if isinstance(stored, list):
        return list(stored)
    if r.suggested_entity_id is not None:
        return [
            {
                "dim_id": int(r.suggested_entity_id),
                "label": str(r.suggested_entity_id),
                "score": float(r.confidence_score) if r.confidence_score is not None else 1.0,
                "reason": str(r.match_reason or "steward"),
            }
        ]
    return []


def serialize_cst_candidate(r: ImportEntityMappingCandidate) -> dict[str, Any]:
    """Public serializer for API responses."""
    return _serialize_cst_candidate(r)


def _serialize_cst_candidate(r: ImportEntityMappingCandidate) -> dict[str, Any]:
    return {
        "id": r.id,
        "import_job_id": r.import_job_id,
        "entity_type": r.entity_type,
        "normalized_key": r.normalized_key,
        "row_count": r.row_count,
        "total_units": float(r.total_units) if r.total_units is not None else None,
        "sample_raw_values": r.sample_raw_values,
        "suggested_entity_id": r.suggested_entity_id,
        "match_reason": r.match_reason,
        "confidence_score": float(r.confidence_score) if r.confidence_score is not None else None,
        "status": r.status,
        "context": r.context,
        "suggestions": _suggestions_from_candidate(r),
        "created_at": r.created_at.isoformat() if r.created_at is not None else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at is not None else None,
    }


def _get_cst_candidate_or_raise(
    session: Session, job_id: int, candidate_id: int
) -> ImportEntityMappingCandidate:
    cand = session.get(ImportEntityMappingCandidate, candidate_id)
    if cand is None or int(cand.import_job_id) != int(job_id):
        raise CstCandidateOpError(404, "CST mapping candidate not found for this job")
    if cand.entity_type not in _CST_ENTITY_TYPES:
        raise CstCandidateOpError(400, f"Unsupported entity_type: {cand.entity_type}")
    return cand


def _patch_staging_for_resolved_candidate(
    session: Session, cand: ImportEntityMappingCandidate
) -> None:
    entity_id = cand.suggested_entity_id
    if entity_id is None:
        return

    lines = session.scalars(
        select(ImportCustomerSellthroughStagingLine).where(
            ImportCustomerSellthroughStagingLine.import_job_id == cand.import_job_id
        )
    ).all()

    if cand.entity_type == CST_PRODUCT_ENTITY:
        for line in lines:
            if line.resolved_product_id is not None:
                continue
            if _product_token_key(line.raw_product_token) == cand.normalized_key:
                line.resolved_product_id = int(entity_id)
    elif cand.entity_type == CST_LOCATION_ENTITY:
        for line in lines:
            if line.resolved_location_id is not None:
                continue
            if _location_token_key(line.raw_location_token) == cand.normalized_key:
                line.resolved_location_id = int(entity_id)


def resolve_cst_candidate_sync(
    session: Session,
    job_id: int,
    candidate_id: int,
    entity_id: int,
) -> dict[str, Any]:
    cand = _get_cst_candidate_or_raise(session, job_id, candidate_id)
    cand.status = "resolved"
    cand.suggested_entity_id = int(entity_id)
    cand.match_reason = "steward_resolve"
    cand.confidence_score = 1.0
    ctx = dict(cand.context) if isinstance(cand.context, dict) else {}
    ctx["steward_resolved_entity_id"] = int(entity_id)
    cand.context = to_jsonable(ctx)
    _patch_staging_for_resolved_candidate(session, cand)
    session.flush()
    return serialize_cst_candidate(cand)


def ignore_cst_candidate_sync(
    session: Session,
    job_id: int,
    candidate_id: int,
) -> dict[str, Any]:
    cand = _get_cst_candidate_or_raise(session, job_id, candidate_id)
    if cand.status != "ignored":
        cand.status = "ignored"
        session.flush()
    return serialize_cst_candidate(cand)


def bulk_resolve_cst_candidates_sync(
    session: Session,
    job_id: int,
    candidate_ids: list[int],
    entity_id: int,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for cid in candidate_ids:
        items.append(resolve_cst_candidate_sync(session, job_id, int(cid), entity_id))
    return {"items": items, "count": len(items)}


def list_cst_mapping_candidates_sync(
    session: Session,
    job_id: int,
    *,
    skip: int = 0,
    limit: int = 200,
    entity: str = "all",
    status: str = "all",
) -> dict[str, Any]:
    """Paginated CST candidate listing, filtered by entity type and status."""
    base = select(ImportEntityMappingCandidate).where(
        ImportEntityMappingCandidate.import_job_id == job_id,
        ImportEntityMappingCandidate.entity_type.in_(_CST_ENTITY_TYPES),
    )

    if entity == "product":
        base = base.where(ImportEntityMappingCandidate.entity_type == CST_PRODUCT_ENTITY)
    elif entity == "location":
        base = base.where(ImportEntityMappingCandidate.entity_type == CST_LOCATION_ENTITY)

    if status == "open":
        base = base.where(ImportEntityMappingCandidate.status.notin_(tuple(_CST_TERMINAL_STATUSES)))
    elif status == "needs_review":
        base = base.where(ImportEntityMappingCandidate.status == "needs_review")
    elif status == "terminal":
        base = base.where(ImportEntityMappingCandidate.status.in_(tuple(_CST_TERMINAL_STATUSES)))

    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = list(
        session.scalars(
            base.order_by(
                ImportEntityMappingCandidate.entity_type,
                ImportEntityMappingCandidate.normalized_key,
                ImportEntityMappingCandidate.id,
            )
            .offset(skip)
            .limit(limit)
        ).all()
    )

    return {
        "items": [_serialize_cst_candidate(r) for r in rows],
        "total": total,
        "skip": skip,
        "limit": limit,
    }
