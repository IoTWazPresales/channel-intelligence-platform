"""Aggregated DSI mapping candidate tab counts (single query per job)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.import_distributor_si import ImportEntityMappingCandidate

from app.services.imports.dsi_mapping_candidates_list import TERMINAL_STATUSES, _ENTITY_MAP

_TAB_ENTITY_TYPES: dict[str, str] = {
    "distributor": _ENTITY_MAP["distributor"],
    "customer": _ENTITY_MAP["customer"],
    "product": _ENTITY_MAP["product"],
}


def dsi_mapping_candidate_tab_counts_sync(session: Session, job_id: int) -> dict[str, Any]:
    """Return open + needs_review counts per entity tab in one grouped query."""
    rows = session.execute(
        select(
            ImportEntityMappingCandidate.entity_type,
            ImportEntityMappingCandidate.status,
            func.count(ImportEntityMappingCandidate.id),
        )
        .where(ImportEntityMappingCandidate.import_job_id == job_id)
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
            if st in TERMINAL_STATUSES:
                continue
            open_n += n
            if st == "needs_review":
                needs_review_n = n
        counts[tab_id] = {"open": open_n, "needs_review": needs_review_n}

    return {"import_job_id": job_id, "counts": counts}
