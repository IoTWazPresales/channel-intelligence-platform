"""Batch reject (ignore) shipment mapping candidates — one commit per candidate via execute_reject."""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.shipment_evidence_steward_ops import (
    ShipmentStewardOpError,
    execute_reject_shipment_mapping_candidate,
)


def run_shipment_bulk_ignore_sync(
    session: Session,
    job_id: int,
    candidate_ids: list[int],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    job = session.get(ImportJob, int(job_id))
    if not job:
        raise ValueError("Import job not found")

    results: list[dict[str, Any]] = []
    total = len(candidate_ids)

    for idx, cid in enumerate(candidate_ids):
        if on_progress is not None:
            on_progress(idx + 1, total)
        cand = session.get(ImportEntityMappingCandidate, int(cid))
        if cand is None or cand.import_job_id != int(job_id):
            results.append(
                {
                    "candidate_id": int(cid),
                    "ok": False,
                    "detail": "Candidate not found for this job",
                    "row_count": None,
                    "total_units": None,
                    "total_reported_value": None,
                }
            )
            continue
        row_count = cand.row_count
        tu = float(cand.total_units) if cand.total_units is not None else None
        trv = float(cand.total_reported_value) if cand.total_reported_value is not None else None
        try:
            out = execute_reject_shipment_mapping_candidate(session, cand)
            results.append(
                {
                    "candidate_id": int(cid),
                    "ok": True,
                    "entity_type": cand.entity_type,
                    "result": out,
                    "row_count": row_count,
                    "total_units": tu,
                    "total_reported_value": trv,
                }
            )
        except ShipmentStewardOpError as exc:
            results.append(
                {
                    "candidate_id": int(cid),
                    "ok": False,
                    "detail": exc.detail,
                    "row_count": row_count,
                    "total_units": tu,
                    "total_reported_value": trv,
                }
            )

    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "import_job_id": job_id,
        "action": "ignore",
        "applied": ok_n,
        "failed": len(results) - ok_n,
        "results": results,
    }
