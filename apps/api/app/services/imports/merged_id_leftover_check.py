"""Import-complete check: leftover FKs still pointing at merged customer or distributor ids.

Reuses ``customer_leftover_repair.leftover_row_total_across_merged_losers`` for customers
(that scan already includes ``customer_source_token_alias`` via FK discovery and skips
``dim_customer.merged_into_customer_id``). Distributor leftovers use the same skip rule
on ``dim_distributor.merged_into_distributor_id``; ``distributor_source_token_alias`` is
included when FK discovery sees it.

A non-zero total is a warning flag on the job. It does not change ``status`` or ``stage``
and it does not repoint rows.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob, ImportRowResult
from app.services.customer_leftover_repair import leftover_row_total_across_merged_losers
from app.services.distributor_fk_discovery import discover_distributor_fk_columns

logger = logging.getLogger(__name__)

MERGED_ID_LEFTOVER_CODE = "merged_id_leftover"
_DISTRIBUTOR_SKIP = {("dim_distributor", "merged_into_distributor_id")}


def distributor_leftover_row_total(db: Session) -> int:
    """Sum FK rows that still point at a merged distributor, excluding the merge pointer itself."""
    losers = db.execute(
        text(
            """
            SELECT id
            FROM dim_distributor
            WHERE merged_into_distributor_id IS NOT NULL
               OR lower(coalesce(distributor_status, '')) = 'merged'
            ORDER BY id
            """
        )
    ).all()
    total = 0
    columns = discover_distributor_fk_columns(db)
    for row in losers:
        lid = int(row[0])
        for table, column in columns:
            if (table, column) in _DISTRIBUTOR_SKIP:
                continue
            n = int(
                db.execute(
                    text(f"SELECT count(*) FROM {table} WHERE {column} = :lid"),
                    {"lid": lid},
                ).scalar()
                or 0
            )
            total += n
    return total


def measure_merged_id_leftovers(db: Session) -> dict[str, int]:
    customer_rows = int(leftover_row_total_across_merged_losers(db))
    distributor_rows = int(distributor_leftover_row_total(db))
    return {
        "customer_leftover_rows": customer_rows,
        "distributor_leftover_rows": distributor_rows,
        "total": customer_rows + distributor_rows,
    }


def apply_merged_id_leftover_flag(db: Session, job: ImportJob, report: dict[str, int]) -> dict[str, Any]:
    """Record the check. Non-zero writes a warning row. Status and stage stay as they were."""
    status_before = job.status
    stage_before = job.stage
    customer_rows = int(report["customer_leftover_rows"])
    distributor_rows = int(report["distributor_leftover_rows"])
    total = int(report["total"])
    stamped = {
        "customer_leftover_rows": customer_rows,
        "distributor_leftover_rows": distributor_rows,
        "total": total,
        "flagged": total > 0,
        "blocks_apply": False,
    }
    meta = dict(job.staged_metadata or {})
    meta["merged_id_leftover"] = stamped
    job.staged_metadata = meta
    job.status = status_before
    job.stage = stage_before
    if total > 0:
        db.add(
            ImportRowResult(
                job_id=int(job.id),
                row_number=0,
                severity="warning",
                code=MERGED_ID_LEFTOVER_CODE,
                message=(
                    f"Merged-id leftovers remain: {customer_rows} customer row(s), "
                    f"{distributor_rows} distributor row(s). Apply was not blocked."
                ),
            )
        )
    db.add(job)
    db.commit()
    return stamped


def run_import_complete_rail(db: Session, job: ImportJob | None) -> None:
    """Import-complete side effects. A leftover flag or a fan-out failure leaves apply complete."""
    if job is not None:
        try:
            report = measure_merged_id_leftovers(db)
            apply_merged_id_leftover_flag(db, job, report)
        except Exception:
            logger.exception(
                "merged-id leftover check failed job_id=%s; apply remains complete",
                getattr(job, "id", None),
            )
            try:
                db.rollback()
            except Exception:
                logger.exception("merged-id leftover rollback failed job_id=%s", getattr(job, "id", None))
    try:
        from app.services.report_schedule_runner import dispatch_import_complete_report_fanout

        tid = getattr(job, "tenant_id", None) if job is not None else None
        dispatch_import_complete_report_fanout(tenant_id=str(tid or "default"))
    except Exception:
        logger.exception(
            "import-complete report fan-out failed job_id=%s; apply remains complete",
            getattr(job, "id", None) if job is not None else None,
        )
