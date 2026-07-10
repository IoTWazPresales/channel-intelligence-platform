"""Aggregated shipment mapping candidate tab counts (single query per job)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
)
from app.services.imports.shipment_mapping_candidates_list import is_shipment_mapping_candidate_terminal_status

_TAB_ENTITY_TYPES: dict[str, str] = {
    "distributor": SHIPMENT_DISTRIBUTOR_ENTITY,
    "customer": SHIPMENT_CUSTOMER_ENTITY,
}


def shipment_mapping_candidate_tab_counts_sync(session: Session, job_id: int) -> dict[str, Any]:
    rows = session.execute(
        select(
            ImportEntityMappingCandidate.entity_type,
            ImportEntityMappingCandidate.status,
            func.count(ImportEntityMappingCandidate.id),
        )
        .where(
            ImportEntityMappingCandidate.import_job_id == job_id,
            ImportEntityMappingCandidate.entity_type.in_((SHIPMENT_DISTRIBUTOR_ENTITY, SHIPMENT_CUSTOMER_ENTITY)),
        )
        .group_by(ImportEntityMappingCandidate.entity_type, ImportEntityMappingCandidate.status)
    ).all()

    by_entity_status: dict[str, dict[str, int]] = {}
    for entity_type, status, cnt in rows:
        et = str(entity_type or "")
        st = str(status or "")
        by_entity_status.setdefault(et, {})[st] = int(cnt or 0)

    counts: dict[str, dict[str, int]] = {}
    for tab_id, entity_type in _TAB_ENTITY_TYPES.items():
        status_map = by_entity_status.get(entity_type, {})
        open_n = 0
        needs_review_n = 0
        for st, n in status_map.items():
            if is_shipment_mapping_candidate_terminal_status(st):
                continue
            open_n += n
            if (st or "").strip() == "needs_review":
                needs_review_n += n
        counts[tab_id] = {
            "open": open_n,
            "needs_work": open_n,
            "needs_review": needs_review_n,
        }

    return {"import_job_id": job_id, "counts": counts}
