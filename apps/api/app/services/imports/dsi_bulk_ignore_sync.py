"""Batch ignore DSI mapping candidates (one commit)."""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.dsi_bulk_db_commit import commit_session_with_transient_retry
from app.services.imports.dsi_steward_candidate_ops import StewardOpError, _is_dsi_steward_terminal_status


def run_dsi_bulk_ignore_sync(
    session: Session,
    job_id: int,
    candidate_ids: list[int],
    *,
    notes: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    job = session.get(ImportJob, int(job_id))
    if not job:
        raise ValueError("Import job not found")

    results: list[dict[str, Any]] = []
    pending_commit = 0
    total = len(candidate_ids)

    for idx, cid in enumerate(candidate_ids):
        if on_progress is not None:
            on_progress(idx + 1, total)
        cand = session.get(ImportEntityMappingCandidate, int(cid))
        if cand is None or cand.import_job_id != int(job_id):
            results.append({"candidate_id": int(cid), "ok": False, "detail": "Candidate not found for this job"})
            continue
        if cand.entity_type not in {"customer_dealer_token", "distributor_token", "product_identifier"}:
            results.append({"candidate_id": int(cid), "ok": False, "detail": "Unsupported entity_type for ignore"})
            continue
        if _is_dsi_steward_terminal_status(cand.status):
            results.append({"candidate_id": int(cid), "ok": False, "detail": "Candidate already terminal"})
            continue
        cand.status = "ignored"
        if notes:
            ctx = dict(cand.context) if isinstance(cand.context, dict) else {}
            ctx["steward_ignore_notes"] = notes[:2000]
            cand.context = ctx
        pending_commit += 1
        results.append({"candidate_id": int(cid), "ok": True, "result": {"ok": True, "candidate_id": cand.id}})

    if pending_commit > 0:
        commit_session_with_transient_retry(session)

    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "import_job_id": job_id,
        "action": "ignore",
        "applied": ok_n,
        "failed": len(results) - ok_n,
        "results": results,
    }
