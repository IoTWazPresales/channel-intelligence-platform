"""Background CPOR historical resolution-plan compute (read-only plan generation off the HTTP path)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.db.session_sync import SessionLocal
from app.services.cpor.historical_import.resolution_plan import build_cpor_historical_resolution_plan_sync

logger = logging.getLogger(__name__)


def run_cpor_historical_resolution_plan_compute_sync(
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    candidate_ids = payload.get("candidate_ids")
    with SessionLocal() as db:
        try:
            out = build_cpor_historical_resolution_plan_sync(db, job_id, candidate_ids=candidate_ids)
            db.commit()  # persist any newly get-or-created token surrogate ids (D-014)
            if on_progress is not None:
                total = int((out.get("summary") or {}).get("total") or len(out.get("rows") or []))
                on_progress(total, total)
            return out
        except Exception:
            logger.exception("cpor_historical_resolution_plan_compute failed job_id=%s", job_id)
            raise
