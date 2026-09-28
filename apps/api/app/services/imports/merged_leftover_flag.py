"""Import-complete FLAG: rows still pointing at merged customer/distributor ids (BACKLOG-133/134).

Read-only detection on the import-complete rail. A non-zero count is a FLAG on the job
(``staged_metadata`` summary + one job-level ``warning`` row result), never a BLOCK: the
import still completes. Nothing is repointed, merged or minted here; leftover repair stays
the explicit ops path (``customer_leftover_repair``).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob, ImportRowResult
from app.services.customer_leftover_repair import merged_id_leftover_check

logger = logging.getLogger(__name__)

MERGED_LEFTOVER_FLAG_CODE = "merged_id_leftover"
MERGED_LEFTOVER_META_KEY = "merged_id_leftover_check"


def flag_merged_id_leftovers(db: Session, job: ImportJob) -> dict[str, Any] | None:
    """Run the leftover check and record the result on ``job``; caller commits.

    The scan runs in a SAVEPOINT so a failing check never aborts the caller's
    transaction (best-effort, returns ``None`` on error).
    """
    try:
        with db.begin_nested():
            result = merged_id_leftover_check(db)
    except Exception:
        logger.exception("merged-id leftover check failed job_id=%s; import unaffected", job.id)
        return None

    total = int(result["total_leftover_rows"])
    meta = dict(job.staged_metadata) if isinstance(job.staged_metadata, dict) else {}
    meta[MERGED_LEFTOVER_META_KEY] = {
        **result,
        "flag": total > 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    job.staged_metadata = meta
    db.add(job)
    if total > 0:
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="warning",
                code=MERGED_LEFTOVER_FLAG_CODE,
                message=(
                    f"{total} row(s) still point at a merged-away id "
                    f"(customer {result['customer_leftover_rows']}, "
                    f"distributor {result['distributor_leftover_rows']}), database-wide after "
                    "this import. Import completed; run the leftover repair script to repoint."
                ),
                raw_payload={
                    "customer_fk_counts": result["customer_fk_counts"],
                    "distributor_fk_counts": result["distributor_fk_counts"],
                },
            )
        )
        logger.warning(
            "merged-id leftover FLAG job_id=%s total=%s customer=%s distributor=%s",
            job.id,
            total,
            result["customer_fk_counts"],
            result["distributor_fk_counts"],
        )
    return result
