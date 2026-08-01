"""CST import steward resolution-plan engine (Unit E2, mirror D-013 / D-019).

Transient, job-scoped plan built from ``ImportEntityMappingCandidate`` rows for
``cst_product_token`` / ``cst_location_token``. Never persisted — regenerate on demand.

Locked ready rule: open status (not resolved/ignored), exactly one suggestion with
score >= 0.90. Multiple suggestions (collisions) are never ready.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.cst_mapping_candidates import (
    CST_LOCATION_ENTITY,
    CST_PRODUCT_ENTITY,
    _CST_ENTITY_TYPES,
    _CST_TERMINAL_STATUSES,
    classify_cst_candidate_plan_class,
    serialize_cst_candidate,
)

TEMPLATE_SLUG = "customer_sell_through"

_ACTION_BY_ENTITY: dict[str, str] = {
    "product": "map_product",
    "location": "map_location",
}

_ENTITY_FROM_TYPE: dict[str, str] = {
    CST_PRODUCT_ENTITY: "product",
    CST_LOCATION_ENTITY: "location",
}


def _entity_label(entity_type: str) -> str:
    return _ENTITY_FROM_TYPE.get(entity_type, "")


def _plan_row_from_candidate(cand: dict[str, Any]) -> dict[str, Any]:
    entity_type = str(cand.get("entity_type") or "")
    entity = _entity_label(entity_type)
    suggestions = cand.get("suggestions") or []
    plan_class, ready = classify_cst_candidate_plan_class(cand)
    top = suggestions[0] if suggestions else None
    target_id = int(top["dim_id"]) if ready and top is not None else None
    return {
        "candidate_id": int(cand["id"]),
        "entity": entity,
        "token": cand.get("normalized_key"),
        "row_count": cand.get("row_count"),
        "plan_class": plan_class,
        "confidence": float(top["score"]) if top is not None and top.get("score") is not None else cand.get(
            "confidence_score"
        ),
        "ready": ready,
        "suggested_action": _ACTION_BY_ENTITY.get(entity, "none") if ready else "none",
        "suggested_target_id": target_id,
        "suggested_target_label": (top.get("label") if ready and top is not None else None),
        "reason": cand.get("match_reason") or (top.get("reason") if top is not None else None),
        "resolution_blockers": [] if ready else [plan_class],
    }


def build_cst_resolution_plan_sync(
    db: Session,
    job_id: int,
    *,
    candidate_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Build the resolution plan for open CST mapping candidates on this job."""
    job = db.get(ImportJob, job_id)
    if job is None or (job.template_slug or "") != TEMPLATE_SLUG:
        raise ValueError("Import job not found")

    base = select(ImportEntityMappingCandidate).where(
        ImportEntityMappingCandidate.import_job_id == job_id,
        ImportEntityMappingCandidate.entity_type.in_(_CST_ENTITY_TYPES),
        ImportEntityMappingCandidate.status.notin_(tuple(_CST_TERMINAL_STATUSES)),
    )
    if candidate_ids is not None:
        wanted = {int(c) for c in candidate_ids}
        base = base.where(ImportEntityMappingCandidate.id.in_(wanted))

    rows_db = list(
        db.scalars(
            base.order_by(
                ImportEntityMappingCandidate.entity_type,
                ImportEntityMappingCandidate.normalized_key,
                ImportEntityMappingCandidate.id,
            )
        ).all()
    )

    if candidate_ids is not None:
        order = {int(c): i for i, c in enumerate(candidate_ids)}
        rows_db.sort(key=lambda r: order.get(int(r.id), 10_000))

    serialized = [serialize_cst_candidate(r) for r in rows_db]
    rows = [_plan_row_from_candidate(c) for c in serialized]
    ready_n = sum(1 for r in rows if r["ready"])
    return {
        "import_job_id": job_id,
        "rows": rows,
        "summary": {
            "total": len(rows),
            "ready": ready_n,
            "not_ready": len(rows) - ready_n,
        },
    }
