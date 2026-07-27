"""CPOR historical steward resolution-plan engine (Unit C, D-013).

Mirrors ``app.services.imports.shipment_resolution_plan`` / ``dsi_resolution_plan``: a
transient, job-scoped plan built from the same suggestion intelligence already used by the
steward candidates list (:func:`app.services.cpor.historical_import.resolve.list_unresolved_candidates`).
Never persisted — regenerate on demand.

Locked (D-013): plan apply maps **per-token → its own top suggestion target**, never a bulk
single target across many different tokens. Ready means the candidate's ``plan_class`` is
``ready_to_map`` (a single high-confidence suggestion) with a resolvable dim id — no new
threshold is invented here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob
from app.services.cpor.historical_import.resolve import list_unresolved_candidates

TEMPLATE_SLUG = "cpor_historical_cases"

_ACTION_BY_ENTITY: dict[str, str] = {
    "product": "map_product",
    "customer": "map_customer",
    "distributor": "map_distributor",
}


def _plan_row_from_candidate(cand: dict[str, Any]) -> dict[str, Any]:
    entity = str(cand.get("entity") or "")
    suggestions = cand.get("suggestions") or []
    top = suggestions[0] if suggestions else None
    ready = bool(top) and cand.get("plan_class") == "ready_to_map"
    target_id = int(top["dim_id"]) if ready and top is not None else None
    return {
        "candidate_id": int(cand["id"]),
        "entity": entity,
        "token": cand.get("token"),
        "row_count": cand.get("row_count"),
        "plan_class": cand.get("plan_class"),
        "confidence": cand.get("confidence"),
        "ready": ready,
        "suggested_action": _ACTION_BY_ENTITY.get(entity, "none") if ready else "none",
        "suggested_target_id": target_id,
        "suggested_target_label": (top.get("label") if ready and top is not None else None),
        "reason": cand.get("match_reason"),
        "resolution_blockers": [] if ready else [str(cand.get("plan_class") or "not_ready")],
    }


def build_cpor_historical_resolution_plan_sync(
    db: Session,
    job_id: int,
    *,
    candidate_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Build the resolution plan for unresolved CPOR historical steward candidates.

    ``candidate_ids`` (token-surrogate ids, D-014) scope the plan to a subset; omit for the
    full unresolved set. Caller owns commit — this calls
    :func:`list_unresolved_candidates`, which may get-or-create token-surrogate rows.
    """
    job = db.get(ImportJob, job_id)
    if job is None or (job.template_slug or "") != TEMPLATE_SLUG:
        raise ValueError("Import job not found")

    all_c = list_unresolved_candidates(db, job_id=job_id)
    flat = [row for rows in all_c.values() for row in rows]
    if candidate_ids is not None:
        wanted = {int(c) for c in candidate_ids}
        flat = [r for r in flat if int(r.get("id") or 0) in wanted]

    rows = [_plan_row_from_candidate(r) for r in flat]
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
