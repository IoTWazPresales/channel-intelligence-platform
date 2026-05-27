"""Post-run hook for DSI validate — historical workflow auto-applies ready resolution candidates.

Original disable reason: calling ``apply_dsi_resolution_plan_rows`` via ``asyncio.run()`` from inside
the ``process_import_job`` Celery task hung on Windows solo pool.

Fix: enqueue ``imports.dsi_resolution_plan_apply`` (or a detached daemon thread when Celery is
unavailable) so ``asyncio.run`` runs outside the validate pipeline thread.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob
from app.services.imports.distributor_sales_inventory import dsi_historical_workflow_from_import_job
from app.services.imports.dsi_resolution_plan import build_dsi_resolution_plan_sync
from app.services.imports.dsi_resolution_plan_enqueue import enqueue_dsi_resolution_plan_apply
from app.utils.json_safe import to_jsonable

logger = logging.getLogger(__name__)


def _ready_candidate_ids_for_historical_auto_apply(plan: dict) -> list[int]:
    ids: list[int] = []
    for row in plan.get("rows") or []:
        if not isinstance(row, dict):
            continue
        if row.get("hold_for_manual_review"):
            continue
        if (row.get("plan_status") or "").strip() != "ready":
            continue
        cid = row.get("candidate_id")
        if cid is not None:
            ids.append(int(cid))
    return ids


def run_dsi_validate_post_import_orchestration(sync_db: Session, job_id: int) -> None:
    job = sync_db.get(ImportJob, job_id)
    if job is None:
        logger.warning("run_dsi_validate_post_import_orchestration: job_id=%s not found", job_id)
        return
    if not dsi_historical_workflow_from_import_job(job):
        logger.debug(
            "run_dsi_validate_post_import_orchestration: skip non-historical job_id=%s mode=%s",
            job_id,
            (job.staged_metadata or {}).get("dsi_workflow_mode"),
        )
        return

    try:
        plan = build_dsi_resolution_plan_sync(
            sync_db,
            job_id,
            candidate_ids=None,
            default_region_id=None,
            default_channel_id=None,
        )
    except Exception:
        logger.exception("DSI post-validate plan build failed job_id=%s", job_id)
        return

    candidate_ids = _ready_candidate_ids_for_historical_auto_apply(plan)
    if not candidate_ids:
        logger.info("DSI post-validate auto-apply: no ready candidates job_id=%s", job_id)
        return

    payload = {"candidate_ids": candidate_ids}
    task_id, async_poll = enqueue_dsi_resolution_plan_apply(
        job_id,
        payload,
        detach_from_caller=True,
    )
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta["dsi_post_validate_auto_apply"] = to_jsonable(
        {
            "task_id": task_id,
            "async_poll": async_poll,
            "candidate_count": len(candidate_ids),
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    job.staged_metadata = to_jsonable(meta)
    sync_db.add(job)
    sync_db.flush()
    logger.info(
        "DSI post-validate enqueued historical auto-apply job_id=%s task_id=%s candidates=%d",
        job_id,
        task_id,
        len(candidate_ids),
    )
