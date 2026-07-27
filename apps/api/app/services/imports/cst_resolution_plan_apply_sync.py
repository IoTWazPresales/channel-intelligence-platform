"""CST resolution-plan apply (Unit E2, mirror D-013).

Locked: per-candidate → its own suggested target via ``resolve_cst_candidate_sync`` —
never a bulk single target across many different tokens. Not-ready candidates are skipped.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.db.session_sync import SessionLocal
from app.services.imports.cst_mapping_candidates import resolve_cst_candidate_sync
from app.services.imports.cst_resolution_plan import build_cst_resolution_plan_sync

logger = logging.getLogger(__name__)


def _empty_combined(job_id: int) -> dict[str, Any]:
    return {
        "import_job_id": job_id,
        "applied": 0,
        "failed": 0,
        "skipped_not_ready": 0,
        "results": [],
    }


def run_cst_resolution_plan_apply_orchestrator(
    session: Session,
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    candidate_ids: list[int] = [int(x) for x in payload.get("candidate_ids") or []]
    total = len(candidate_ids)
    combined = _empty_combined(job_id)

    plan = build_cst_resolution_plan_sync(session, job_id, candidate_ids=candidate_ids)
    rows_by_cid = {int(r["candidate_id"]): r for r in plan.get("rows") or []}

    for idx, cid in enumerate(candidate_ids):
        row = rows_by_cid.get(cid)
        if row is None:
            combined["failed"] += 1
            combined["results"].append(
                {"candidate_id": cid, "status": "failed", "detail": "candidate_not_found"}
            )
        elif not row.get("ready") or row.get("suggested_target_id") is None:
            combined["skipped_not_ready"] += 1
            combined["results"].append(
                {
                    "candidate_id": cid,
                    "status": "skipped_not_ready",
                    "detail": str(row.get("plan_class") or "not_ready"),
                }
            )
        else:
            try:
                resolve_cst_candidate_sync(
                    session,
                    job_id,
                    cid,
                    int(row["suggested_target_id"]),
                )
                combined["applied"] += 1
                combined["results"].append({"candidate_id": cid, "status": "applied"})
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "cst_resolution_plan_apply failed candidate_id=%s job_id=%s", cid, job_id
                )
                combined["failed"] += 1
                combined["results"].append(
                    {"candidate_id": cid, "status": "failed", "detail": str(exc)[:400]}
                )
        if on_progress is not None:
            on_progress(idx + 1, total or 1)

    session.commit()
    combined["processed"] = total
    combined["partial_success"] = False
    return combined


def run_cst_resolution_plan_apply_sync(
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    with SessionLocal() as session:
        return run_cst_resolution_plan_apply_orchestrator(
            session, job_id, payload, on_progress=on_progress
        )
