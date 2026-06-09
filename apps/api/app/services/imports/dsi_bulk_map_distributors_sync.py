"""Batch map DSI distributor candidates to existing dim_distributor (one commit per group)."""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.dimensions import DimDistributor
from app.models.import_distributor_si import DistributorSourceTokenAlias, ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.dsi_bulk_db_commit import commit_session_with_transient_retry
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_steward_candidate_ops import (
    StewardOpError,
    _first_sample_raw,
    _is_dsi_steward_terminal_status,
)


def _apply_map_dsi_distributor_without_commit_sync(
    session: Session,
    cand: ImportEntityMappingCandidate,
    *,
    distributor_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    if cand.entity_type != "distributor_token":
        raise StewardOpError("Not distributor_token", status_code=400)
    if _is_dsi_steward_terminal_status(cand.status):
        raise StewardOpError("Candidate already terminal", status_code=400)
    dist = session.get(DimDistributor, distributor_id)
    if not dist:
        raise StewardOpError("distributor_id not found", status_code=400)
    raw = (raw_token or _first_sample_raw(cand)).strip()
    if not raw:
        raise StewardOpError("raw_token required", status_code=400)
    nt = _norm_key(raw)
    if not nt:
        raise StewardOpError("raw_token empty after normalization", status_code=400)
    alias = DistributorSourceTokenAlias(
        distributor_id=distributor_id,
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        status="approved",
        notes=f"Mapped from import candidate {cand.id} (job {cand.import_job_id})",
        created_from_import_job_id=cand.import_job_id,
    )
    session.add(alias)
    session.flush()
    cand.status = "resolved"
    cand.suggested_entity_id = distributor_id
    cand.match_reason = "steward_map_existing_distributor"
    return {"ok": True, "alias_id": alias.id, "distributor_id": distributor_id, "candidate_id": cand.id}


def run_dsi_bulk_map_distributors_sync(
    session: Session,
    job_id: int,
    *,
    distributor_id: int,
    candidate_ids: list[int],
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    job = session.get(ImportJob, int(job_id))
    if not job:
        raise ValueError("Import job not found")

    found = {
        int(c.id): c
        for c in session.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == int(job_id),
                ImportEntityMappingCandidate.id.in_(candidate_ids),
            )
        ).all()
    }

    results: list[dict[str, Any]] = []
    pending_commit = 0
    total = len(candidate_ids)

    for idx, cid in enumerate(candidate_ids):
        if on_progress is not None:
            on_progress(idx + 1, total)
        cand = found.get(int(cid))
        if cand is None:
            results.append({"candidate_id": int(cid), "ok": False, "detail": "Candidate not found for this job"})
            continue
        try:
            out = _apply_map_dsi_distributor_without_commit_sync(
                session, cand, distributor_id=int(distributor_id), raw_token=None
            )
            pending_commit += 1
            results.append({"candidate_id": int(cid), "ok": True, "result": out})
        except StewardOpError as exc:
            results.append({"candidate_id": int(cid), "ok": False, "detail": exc.detail})

    if pending_commit > 0:
        try:
            commit_session_with_transient_retry(session)
        except IntegrityError as exc:
            session.rollback()
            raise StewardOpError("Could not commit bulk distributor map", status_code=409) from exc

    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "import_job_id": job_id,
        "action": "map_distributor",
        "distributor_id": int(distributor_id),
        "applied": ok_n,
        "failed": len(results) - ok_n,
        "results": results,
    }
