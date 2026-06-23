"""Paginated shipment evidence mapping candidate listing (import job scope)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer, DimDistributor
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.schemas.shipment_mapping_candidates import ShipmentMappingCandidatesListParams
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CANDIDATE_TERMINAL_STATUSES,
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
)

_ENTITY_MAP = {
    "customer": SHIPMENT_CUSTOMER_ENTITY,
    "distributor": SHIPMENT_DISTRIBUTOR_ENTITY,
}


def is_shipment_mapping_candidate_terminal_status(status: str | None) -> bool:
    return (status or "").strip() in SHIPMENT_CANDIDATE_TERMINAL_STATUSES


def _serialize_candidate(
    r: ImportEntityMappingCandidate,
    *,
    dist_names: dict[int, dict[str, str]],
    cust_names: dict[int, dict[str, str]],
) -> dict[str, Any]:
    sid = int(r.suggested_entity_id) if r.suggested_entity_id is not None else None
    dh = dist_names.get(sid) if r.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY and sid is not None else None
    ch = cust_names.get(sid) if r.entity_type == SHIPMENT_CUSTOMER_ENTITY and sid is not None else None
    ctx = r.context if isinstance(r.context, dict) else {}
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
        "suggested_distributor_code": dh["distributor_code"] if dh else None,
        "suggested_distributor_name": dh["distributor_name"] if dh else None,
        "suggested_customer_code": ch["customer_code"] if ch else None,
        "suggested_customer_name": ch["customer_name"] if ch else None,
        "suggested_action": ctx.get("suggested_action"),
        "match_reason": r.match_reason,
        "confidence_score": float(r.confidence_score) if r.confidence_score is not None else None,
        "status": r.status,
        "context": r.context,
        "created_at": r.created_at.isoformat() if r.created_at is not None else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at is not None else None,
    }


def _apply_list_filters(q, params: ShipmentMappingCandidatesListParams):
    q = q.where(
        ImportEntityMappingCandidate.entity_type.in_((SHIPMENT_DISTRIBUTOR_ENTITY, SHIPMENT_CUSTOMER_ENTITY))
    )
    if params.entity != "all":
        q = q.where(ImportEntityMappingCandidate.entity_type == _ENTITY_MAP[params.entity])

    if params.status == "open":
        q = q.where(ImportEntityMappingCandidate.status.notin_(tuple(SHIPMENT_CANDIDATE_TERMINAL_STATUSES)))
    elif params.status == "needs_review":
        q = q.where(ImportEntityMappingCandidate.status == "needs_review")
    elif params.status == "terminal":
        q = q.where(ImportEntityMappingCandidate.status.in_(tuple(SHIPMENT_CANDIDATE_TERMINAL_STATUSES)))

    if params.party == "bill_to":
        q = q.where(
            ImportEntityMappingCandidate.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY,
            ImportEntityMappingCandidate.context["party"].astext == "bill_to",
        )
    elif params.party == "ship_to":
        q = q.where(
            ImportEntityMappingCandidate.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY,
            ImportEntityMappingCandidate.context["party"].astext == "ship_to",
        )

    if params.verify_name_only:
        q = q.where(
            (ImportEntityMappingCandidate.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY)
            | (
                (ImportEntityMappingCandidate.entity_type == SHIPMENT_CUSTOMER_ENTITY)
                & (ImportEntityMappingCandidate.context["needs_name_review"].astext == "true")
            )
        )

    if params.special_category_only:
        q = q.where(ImportEntityMappingCandidate.context["special_category"].astext.isnot(None))

    if params.possible_duplicates_only or params.duplicate_unresolved_only:
        q = q.where(
            ImportEntityMappingCandidate.context["possible_duplicate_of"].isnot(None),
            ImportEntityMappingCandidate.context["duplicate_review"]["decision"].astext.is_(None),
        )

    return q


def list_shipment_mapping_candidates_sync(
    session: Session,
    job_id: int,
    params: ShipmentMappingCandidatesListParams,
) -> dict[str, Any]:
    base = select(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job_id)
    filtered = _apply_list_filters(base, params)

    count_stmt = select(func.count(ImportEntityMappingCandidate.id)).where(
        ImportEntityMappingCandidate.import_job_id == job_id
    )
    count_stmt = _apply_list_filters(count_stmt, params)
    total = int(session.scalar(count_stmt) or 0)

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

    sug_dist_ids = [
        int(r.suggested_entity_id)
        for r in rows
        if r.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY and r.suggested_entity_id
    ]
    sug_cust_ids = [
        int(r.suggested_entity_id)
        for r in rows
        if r.entity_type == SHIPMENT_CUSTOMER_ENTITY and r.suggested_entity_id
    ]
    dist_names: dict[int, dict[str, str]] = {}
    cust_names: dict[int, dict[str, str]] = {}
    if sug_dist_ids:
        for d in session.scalars(select(DimDistributor).where(DimDistributor.id.in_(sug_dist_ids))).all():
            dist_names[int(d.id)] = {"distributor_code": d.code or "", "distributor_name": d.name or ""}
    if sug_cust_ids:
        for c in session.scalars(select(DimCustomer).where(DimCustomer.id.in_(sug_cust_ids))).all():
            cust_names[int(c.id)] = {"customer_code": c.code or "", "customer_name": c.name or ""}

    return {
        "items": [_serialize_candidate(r, dist_names=dist_names, cust_names=cust_names) for r in rows],
        "total": total,
        "skip": params.skip,
        "limit": params.limit,
    }
