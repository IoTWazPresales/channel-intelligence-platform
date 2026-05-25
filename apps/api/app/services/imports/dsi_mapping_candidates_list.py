"""Paginated DSI import mapping candidate listing (import job scope)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.schemas.dsi_mapping_candidates import DsiMappingCandidatesListParams

TERMINAL_STATUSES = frozenset({"resolved", "ignored", "waived_open_channel"})

_ENTITY_MAP = {
    "customer": "customer_dealer_token",
    "distributor": "distributor_token",
    "product": "product_identifier",
}


def _serialize_candidate(r: ImportEntityMappingCandidate) -> dict[str, Any]:
    return {
        "id": r.id,
        "import_job_id": r.import_job_id,
        "source_definition_id": r.source_definition_id,
        "entity_type": r.entity_type,
        "normalized_key": r.normalized_key,
        "dealer_group_token": r.dealer_group_token,
        "row_count": r.row_count,
        "total_units": float(r.total_units) if r.total_units is not None else None,
        "total_reported_value": float(r.total_reported_value) if r.total_reported_value is not None else None,
        "sample_raw_values": r.sample_raw_values,
        "suggested_entity_id": r.suggested_entity_id,
        "match_reason": r.match_reason,
        "confidence_score": float(r.confidence_score) if r.confidence_score is not None else None,
        "status": r.status,
        "context": r.context,
        "created_at": r.created_at.isoformat() if r.created_at is not None else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at is not None else None,
    }


def _apply_list_filters(q, params: DsiMappingCandidatesListParams):
    if params.entity != "all":
        q = q.where(ImportEntityMappingCandidate.entity_type == _ENTITY_MAP[params.entity])

    if params.status == "open":
        q = q.where(ImportEntityMappingCandidate.status.notin_(tuple(TERMINAL_STATUSES)))
    elif params.status == "needs_review":
        q = q.where(ImportEntityMappingCandidate.status == "needs_review")
    elif params.status == "terminal":
        q = q.where(ImportEntityMappingCandidate.status.in_(tuple(TERMINAL_STATUSES)))

    if params.party == "bill_to":
        q = q.where(
            ImportEntityMappingCandidate.entity_type == "distributor_token",
            ImportEntityMappingCandidate.context["party"].astext == "bill_to",
        )
    elif params.party == "ship_to":
        q = q.where(
            ImportEntityMappingCandidate.entity_type == "distributor_token",
            ImportEntityMappingCandidate.context["party"].astext == "ship_to",
        )

    if params.verify_name_only:
        q = q.where(
            (ImportEntityMappingCandidate.entity_type == "distributor_token")
            | (
                (ImportEntityMappingCandidate.entity_type == "customer_dealer_token")
                & (ImportEntityMappingCandidate.context["needs_name_review"].astext == "true")
            )
        )

    if params.special_category_only:
        q = q.where(ImportEntityMappingCandidate.context["special_category"].astext.isnot(None))

    if params.possible_duplicates_only:
        q = q.where(
            ImportEntityMappingCandidate.context["possible_duplicate_of"].isnot(None),
            ImportEntityMappingCandidate.context["duplicate_review"]["decision"].astext.is_(None),
        )

    if params.duplicate_unresolved_only:
        q = q.where(
            ImportEntityMappingCandidate.context["possible_duplicate_of"].isnot(None),
            ImportEntityMappingCandidate.context["duplicate_review"]["decision"].astext.is_(None),
        )

    return q


def list_dsi_mapping_candidates_sync(
    session: Session,
    job_id: int,
    params: DsiMappingCandidatesListParams,
) -> dict[str, Any]:
    base = select(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job_id)
    filtered = _apply_list_filters(base, params)

    total = int(session.scalar(select(func.count()).select_from(filtered.subquery())) or 0)

    rows = list(
        session.scalars(
            filtered.order_by(
                ImportEntityMappingCandidate.entity_type,
                ImportEntityMappingCandidate.normalized_key,
                ImportEntityMappingCandidate.id,
            )
            .offset(params.skip)
            .limit(params.limit)
        ).all()
    )

    return {
        "items": [_serialize_candidate(r) for r in rows],
        "total": total,
        "skip": params.skip,
        "limit": params.limit,
    }
