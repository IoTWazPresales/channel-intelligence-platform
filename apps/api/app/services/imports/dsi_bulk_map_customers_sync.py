"""Batch map DSI customer candidates to existing dim_customer (one commit per group)."""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.dsi_bulk_db_commit import commit_session_with_transient_retry
from app.services.imports.dsi_customer_alias_scope import (
    apply_map_dsi_customer_scoped_sync,
    load_approved_customer_aliases_for_scopes,
    scope_key_for_dsi_candidate,
)
from app.services.imports.dsi_steward_candidate_ops import StewardOpError


def _fail_results_on_rollback(results: list[dict[str, Any]], detail: str) -> None:
    for row in results:
        if row.get("ok"):
            row["ok"] = False
            row["detail"] = detail
            row.pop("result", None)


def run_dsi_bulk_map_customers_sync(
    session: Session,
    job_id: int,
    *,
    customer_id: int,
    candidate_ids: list[int],
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Map many customer_dealer_token candidates to one dim_customer; commit once at end."""
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

    scope_keys: set[tuple[str, int, int]] = set()
    for cand in found.values():
        meta = scope_key_for_dsi_candidate(cand)
        if meta is not None:
            scope_keys.add(meta[0])
    approved_alias_by_scope = load_approved_customer_aliases_for_scopes(session, scope_keys)
    batch_scope_claimed: set[tuple[str, int, int]] = set()

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
            out = apply_map_dsi_customer_scoped_sync(
                session,
                cand,
                customer_id=int(customer_id),
                raw_token=None,
                approved_alias_by_scope=approved_alias_by_scope,
                batch_scope_claimed=batch_scope_claimed,
            )
            pending_commit += 1
            results.append({"candidate_id": int(cid), "ok": True, "result": out})
        except StewardOpError as exc:
            results.append({"candidate_id": int(cid), "ok": False, "detail": exc.detail})

    if pending_commit > 0:
        try:
            commit_session_with_transient_retry(session)
        except IntegrityError:
            session.rollback()
            _fail_results_on_rollback(
                results,
                "Could not commit bulk customer map (alias scope conflict)",
            )

    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "import_job_id": job_id,
        "action": "map_customer",
        "customer_id": int(customer_id),
        "applied": ok_n,
        "failed": len(results) - ok_n,
        "results": results,
    }
