"""Defer historical DSI post-validate auto-apply until interactive steward work is idle (BACKLOG-040)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ingestion import ImportJob
from app.services.imports.background_tasks import _read_celery_safe
from app.services.imports.dsi_resolution_plan_enqueue import enqueue_dsi_resolution_plan_apply
from app.services.imports.import_background_slots import (
    KIND_DSI_BULK_IGNORE,
    KIND_DSI_BULK_PROVISIONAL,
    KIND_DSI_RESOLUTION_PLAN_APPLY,
    KIND_DSI_RESOLUTION_PLAN_COMPUTE,
    iter_active_slots,
)
from app.services.imports.import_job_background_metadata import ACTIVE_CELERY_STATES
from app.utils.json_safe import to_jsonable
from app.worker.celery_app import celery_app
from app.worker.celery_queues import CELERY_QUEUE_BATCH, defer_dsi_post_validate_auto_apply

logger = logging.getLogger(__name__)

_DEFERRED_META_KEY = "dsi_post_validate_auto_apply_deferred"
_FLUSH_TASK = "imports.flush_deferred_dsi_post_validate_auto_apply"
_INTERACTIVE_KINDS = frozenset(
    {
        KIND_DSI_RESOLUTION_PLAN_COMPUTE,
        KIND_DSI_RESOLUTION_PLAN_APPLY,
        KIND_DSI_BULK_PROVISIONAL,
        KIND_DSI_BULK_IGNORE,
    }
)
_MAX_FLUSH_RESCHEDULES = 120


def job_has_active_interactive_steward_tasks(sync_db: Session, job_id: int) -> bool:
    job = sync_db.get(ImportJob, job_id)
    if job is None:
        return False
    for slot in iter_active_slots(job):
        if slot.kind not in _INTERACTIVE_KINDS:
            continue
        task_state, _info = _read_celery_safe(slot.task_id)
        if task_state in ACTIVE_CELERY_STATES:
            return True
    return False


def schedule_or_enqueue_dsi_post_validate_auto_apply(
    sync_db: Session,
    job: ImportJob,
    *,
    candidate_ids: list[int],
    detach_from_caller: bool,
) -> None:
    """Enqueue apply immediately, or defer until steward idle when configured."""
    payload = {"candidate_ids": candidate_ids}
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}

    if not defer_dsi_post_validate_auto_apply():
        task_id, async_poll = enqueue_dsi_resolution_plan_apply(
            job.id,
            payload,
            detach_from_caller=detach_from_caller,
        )
        meta["dsi_post_validate_auto_apply"] = to_jsonable(
            {
                "task_id": task_id,
                "async_poll": async_poll,
                "candidate_count": len(candidate_ids),
                "queued_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        meta.pop(_DEFERRED_META_KEY, None)
        job.staged_metadata = to_jsonable(meta)
        sync_db.add(job)
        sync_db.flush()
        logger.info(
            "DSI post-validate enqueued historical auto-apply job_id=%s task_id=%s candidates=%d",
            job.id,
            task_id,
            len(candidate_ids),
        )
        return

    meta[_DEFERRED_META_KEY] = to_jsonable(
        {
            "candidate_ids": candidate_ids,
            "candidate_count": len(candidate_ids),
            "deferred_at": datetime.now(timezone.utc).isoformat(),
            "reschedule_count": 0,
        }
    )
    job.staged_metadata = to_jsonable(meta)
    sync_db.add(job)
    sync_db.flush()

    settings = get_settings()
    if settings.cip_dev_celery_dispatch == "in_process_thread":
        logger.info(
            "DSI post-validate deferred auto-apply job_id=%s — flushing in-process (no Celery broker)",
            job.id,
        )
        try_flush_deferred_dsi_post_validate_auto_apply(sync_db, int(job.id))
        sync_db.commit()
        return

    try:
        celery_app.send_task(
            _FLUSH_TASK,
            args=[int(job.id)],
            queue=CELERY_QUEUE_BATCH,
            countdown=15,
        )
    except Exception:
        logger.exception(
            "DSI post-validate flush schedule failed job_id=%s — running sync flush",
            job.id,
        )
        run_flush_deferred_dsi_post_validate_auto_apply_sync(int(job.id))
        return
    logger.info(
        "DSI post-validate deferred historical auto-apply job_id=%s candidates=%d",
        job.id,
        len(candidate_ids),
    )


def try_flush_deferred_dsi_post_validate_auto_apply(sync_db: Session, job_id: int) -> bool:
    """Enqueue deferred auto-apply when steward is idle. Returns True if flushed."""
    job = sync_db.get(ImportJob, job_id)
    if job is None:
        return False
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    deferred = meta.get(_DEFERRED_META_KEY)
    if not isinstance(deferred, dict):
        return False
    if job_has_active_interactive_steward_tasks(sync_db, job_id):
        return False

    candidate_ids = deferred.get("candidate_ids") or []
    if not isinstance(candidate_ids, list) or not candidate_ids:
        meta.pop(_DEFERRED_META_KEY, None)
        job.staged_metadata = to_jsonable(meta) if meta else None
        sync_db.add(job)
        sync_db.flush()
        return False

    payload = {"candidate_ids": [int(x) for x in candidate_ids]}
    task_id, async_poll = enqueue_dsi_resolution_plan_apply(
        job_id,
        payload,
        detach_from_caller=True,
    )
    meta.pop(_DEFERRED_META_KEY, None)
    meta["dsi_post_validate_auto_apply"] = to_jsonable(
        {
            "task_id": task_id,
            "async_poll": async_poll,
            "candidate_count": len(payload["candidate_ids"]),
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "flushed_from_deferred": True,
        }
    )
    job.staged_metadata = to_jsonable(meta)
    sync_db.add(job)
    sync_db.flush()
    logger.info(
        "DSI post-validate flushed deferred auto-apply job_id=%s task_id=%s candidates=%d",
        job_id,
        task_id,
        len(payload["candidate_ids"]),
    )
    return True


def run_flush_deferred_dsi_post_validate_auto_apply_sync(job_id: int) -> dict[str, Any]:
    from app.db.session_sync import SessionLocal

    with SessionLocal() as sync_db:
        if try_flush_deferred_dsi_post_validate_auto_apply(sync_db, job_id):
            sync_db.commit()
            return {"flushed": True, "job_id": job_id}

        job = sync_db.get(ImportJob, job_id)
        if job is None:
            return {"flushed": False, "job_id": job_id, "reason": "job_not_found"}

        meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
        deferred = meta.get(_DEFERRED_META_KEY)
        if not isinstance(deferred, dict):
            return {"flushed": False, "job_id": job_id, "reason": "nothing_deferred"}

        if job_has_active_interactive_steward_tasks(sync_db, job_id):
            count = int(deferred.get("reschedule_count") or 0) + 1
            if count > _MAX_FLUSH_RESCHEDULES:
                logger.warning(
                    "DSI deferred auto-apply exceeded reschedule cap job_id=%s — forcing enqueue",
                    job_id,
                )
                sync_db.commit()
                with SessionLocal() as force_db:
                    job2 = force_db.get(ImportJob, job_id)
                    if job2 is not None:
                        meta2 = dict(job2.staged_metadata or {})
                        meta2.pop(_DEFERRED_META_KEY, None)
                        job2.staged_metadata = to_jsonable(meta2) if meta2 else None
                        force_db.add(job2)
                        force_db.commit()
                payload = {"candidate_ids": [int(x) for x in deferred.get("candidate_ids") or []]}
                task_id, _async_poll = enqueue_dsi_resolution_plan_apply(
                    job_id, payload, detach_from_caller=True
                )
                return {"flushed": True, "job_id": job_id, "forced": True, "task_id": task_id}

            deferred["reschedule_count"] = count
            meta[_DEFERRED_META_KEY] = to_jsonable(deferred)
            job.staged_metadata = to_jsonable(meta)
            sync_db.add(job)
            sync_db.commit()
            settings = get_settings()
            if settings.cip_dev_celery_dispatch == "in_process_thread":
                # No delayed Celery countdown without a broker — leave deferred for a later flush.
                return {"flushed": False, "job_id": job_id, "reason": "steward_busy", "reschedule": count}
            try:
                celery_app.send_task(
                    _FLUSH_TASK,
                    args=[job_id],
                    queue=CELERY_QUEUE_BATCH,
                    countdown=30,
                )
            except Exception:
                logger.exception(
                    "DSI deferred auto-apply reschedule failed job_id=%s — leaving deferred",
                    job_id,
                )
            return {"flushed": False, "job_id": job_id, "reason": "steward_busy", "reschedule": count}

        sync_db.commit()
        return {"flushed": False, "job_id": job_id, "reason": "unknown"}
