"""DSI import: finalize apply — refresh staging resolutions, upsert facts, promote job to loaded."""

from __future__ import annotations

import logging
from typing import Any

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.pipeline import STAGE_LOADED, STAGE_VALIDATED
from app.models.import_distributor_si import ImportDistributorSiStagingLine
from app.models.ingestion import ImportJob
from app.services.imports.distributor_sales_inventory import (
    _load_product_resolution_index,
    refresh_dsi_staging_line_resolution,
    upsert_dsi_facts_for_staging_job,
)

logger = logging.getLogger(__name__)


class DsiApplyCompletionError(ValueError):
    """Business-rule failure for DSI apply completion."""


def complete_dsi_import_job_to_loaded(db: Session, job_id: int) -> dict[str, Any]:
    """Re-resolve staging lines, upsert facts, set job to ``loaded`` when rules pass.

    Completion rules:
    - Template ``distributor_inventory``
    - Stage ``validated``
    - ``import_mode == apply``
    - No human-fixable staging line with ``resolution_status == blocked`` after refresh
      (structural / master-data exclusions and auto-excludes do not gate apply)
    - Fact upsert completes without recorded errors
    """
    job = db.get(ImportJob, int(job_id))
    if not job:
        raise DsiApplyCompletionError("Import job not found")
    if (job.template_slug or "") != "distributor_inventory":
        raise DsiApplyCompletionError("Job is not a distributor_inventory (DSI) import")
    if (job.stage or "") != STAGE_VALIDATED:
        raise DsiApplyCompletionError(f"Job stage must be {STAGE_VALIDATED!r}; current is {job.stage!r}")
    if (job.import_mode or "") != "apply":
        raise DsiApplyCompletionError("import_mode must be apply to complete DSI fact apply")

    prod_idx = _load_product_resolution_index(db)
    lines = list(
        db.scalars(
            select(ImportDistributorSiStagingLine)
            .where(ImportDistributorSiStagingLine.import_job_id == job.id)
            .order_by(ImportDistributorSiStagingLine.source_row_number)
        ).all()
    )
    if not lines:
        raise DsiApplyCompletionError("No DSI staging lines for this job")

    for line in lines:
        refresh_dsi_staging_line_resolution(db, job, line, prod_idx)

    from app.services.imports.dsi_product_running_change import (
        build_dsi_apply_exclusion_summary,
        is_human_fixable_dsi_blocked_staging_line,
        reapply_dsi_steward_ignored_customer_staging_lines,
        reapply_dsi_steward_ignored_product_staging_lines,
    )

    reapply_dsi_steward_ignored_product_staging_lines(db, int(job.id))
    reapply_dsi_steward_ignored_customer_staging_lines(db, int(job.id))
    db.flush()

    blocked = [ln for ln in lines if is_human_fixable_dsi_blocked_staging_line(ln)]
    if blocked:
        raise DsiApplyCompletionError(
            f"{len(blocked)} staging line(s) still human-fixable blocked after refresh "
            f"(e.g. row {blocked[0].source_row_number})"
        )

    apply_exclusion = build_dsi_apply_exclusion_summary(db, int(job.id), lines)

    db.flush()
    _sell, _inv, _ret, apply_errors = upsert_dsi_facts_for_staging_job(db, job)
    if apply_errors:
        msg = "; ".join(apply_errors[:12])
        logger.warning("DSI fact apply reported errors job_id=%s: %s", job.id, msg)
        raise DsiApplyCompletionError(f"Fact upsert errors: {msg}")

    job.stage = STAGE_LOADED
    job.status = "completed"
    db.add(job)
    db.commit()
    db.refresh(job)

    dist_id = db.scalar(
        select(func.max(ImportDistributorSiStagingLine.resolved_distributor_id)).where(
            ImportDistributorSiStagingLine.import_job_id == job.id,
            ImportDistributorSiStagingLine.resolved_distributor_id.isnot(None),
        )
    )
    period_end = db.scalar(
        select(func.max(ImportDistributorSiStagingLine.snapshot_date)).where(
            ImportDistributorSiStagingLine.import_job_id == job.id,
            ImportDistributorSiStagingLine.snapshot_date.isnot(None),
        )
    )
    if period_end is None:
        period_end = db.scalar(
            select(func.max(ImportDistributorSiStagingLine.transaction_date)).where(
                ImportDistributorSiStagingLine.import_job_id == job.id,
                ImportDistributorSiStagingLine.transaction_date.isnot(None),
            )
        )
    if dist_id is not None and period_end is not None:
        # Facts are already committed and the job is LOADED (above). Downstream
        # derivation dispatch (SOH reconciliation, velocity) is best-effort: any
        # failure here must NOT revert a successfully loaded job, so it is isolated
        # in its own try/except. A derivation hiccup leaves the job ``loaded`` with
        # facts applied — never ``failed``.
        try:
            from app.services.imports.dsi_soh_reconciliation_enqueue import (
                dispatch_dsi_soh_reconciliation_after_apply,
            )

            dispatch_dsi_soh_reconciliation_after_apply(
                db,
                job,
                distributor_id=int(dist_id),
                period_end_date=period_end if isinstance(period_end, date) else period_end,
            )
            from app.services.imports.dsi_velocity_enqueue import dispatch_dsi_velocity_after_apply

            dispatch_dsi_velocity_after_apply(db, job, int(dist_id))
            db.commit()
            db.refresh(job)
        except Exception:
            logger.exception(
                "DSI post-load derivation dispatch failed job_id=%s; facts applied and "
                "job remains loaded",
                job.id,
            )
            try:
                db.rollback()
            except Exception:
                logger.exception("DSI post-load rollback failed job_id=%s", job.id)

    # BACKLOG-098: fan-out on_import_complete report schedules (best-effort).
    # Only delivers ReportSchedule rows with enabled=True (config/opt-in).
    try:
        from app.services.report_schedule_runner import dispatch_import_complete_report_fanout

        tid = getattr(job, "tenant_id", None) or "default"
        dispatch_import_complete_report_fanout(tenant_id=str(tid))
    except Exception:
        logger.exception(
            "DSI post-load report schedule fan-out failed job_id=%s; job remains loaded",
            job.id,
        )

    return {
        "ok": True,
        "import_job_id": int(job.id),
        "stage": job.stage,
        "status": job.status,
        "staging_rows": len(lines),
        "apply_exclusion": apply_exclusion,
    }
