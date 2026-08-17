"""Sync runner for WoC observation reconstruct (apply path + 097-D ops replay)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.db.session_sync import SessionLocal
from app.services.imports.woc_observation import (
    WOC_TRIGGER_AS_OF_BACKFILL,
    persist_woc_observations_for_distributor,
    reconstruct_woc_observations,
    shipment_distributor_ids_for_job,
    mark_woc_reconstruct_on_job,
)

logger = logging.getLogger(__name__)


def _mark(job_id: int | None, payload: dict[str, Any]) -> None:
    if job_id is None:
        return
    with SessionLocal() as db:
        try:
            mark_woc_reconstruct_on_job(db, int(job_id), payload)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("woc observation marker write failed job_id=%s", job_id)


def run_woc_observation_for_distributor_sync(
    *,
    tenant_id: str,
    distributor_id: int,
    import_job_id: int | None,
    trigger: str,
    file_period_end: date | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    with SessionLocal() as db:
        try:
            out = persist_woc_observations_for_distributor(
                db,
                tenant_id=tenant_id,
                distributor_id=int(distributor_id),
                import_job_id=import_job_id,
                trigger=trigger,
                file_period_end=file_period_end,
                as_of=as_of,
            )
            db.commit()
            _mark(
                import_job_id,
                {
                    "status": "ok",
                    "retryable": False,
                    "distributor_id": int(distributor_id),
                    "trigger": trigger,
                    "reconstruct": out.get("reconstruct"),
                    "decision": out.get("decision"),
                },
            )
            return out
        except Exception as exc:
            db.rollback()
            logger.exception(
                "woc observation persist failed distributor_id=%s job_id=%s",
                distributor_id,
                import_job_id,
            )
            _mark(
                import_job_id,
                {
                    "status": "failed",
                    "retryable": True,
                    "distributor_id": int(distributor_id),
                    "trigger": trigger,
                    "error": str(exc)[:800],
                },
            )
            raise


def run_woc_observation_after_apply_sync(
    job_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Celery/ops entry: payload.distributor_id or payload.distributor_ids + trigger."""
    tenant_id = str(payload.get("tenant_id") or "default")
    trigger = str(payload.get("trigger") or WOC_TRIGGER_AS_OF_BACKFILL)
    period_raw = payload.get("file_period_end")
    file_period_end: date | None = None
    if period_raw:
        file_period_end = date.fromisoformat(str(period_raw)[:10])
    dist_ids = payload.get("distributor_ids")
    if dist_ids is None and payload.get("distributor_id") is not None:
        dist_ids = [payload["distributor_id"]]
    if not dist_ids and trigger != WOC_TRIGGER_AS_OF_BACKFILL:
        with SessionLocal() as db:
            dist_ids = shipment_distributor_ids_for_job(db, int(job_id))
    results = []
    for dist_id in dist_ids or []:
        results.append(
            run_woc_observation_for_distributor_sync(
                tenant_id=tenant_id,
                distributor_id=int(dist_id),
                import_job_id=int(job_id) if job_id else None,
                trigger=trigger,
                file_period_end=file_period_end,
            )
        )
    if not results and trigger == WOC_TRIGGER_AS_OF_BACKFILL:
        # Ops replay of a single distributor without apply trigger.
        dist_id = payload.get("distributor_id")
        if dist_id is not None:
            results.append(
                run_woc_observation_for_distributor_sync(
                    tenant_id=tenant_id,
                    distributor_id=int(dist_id),
                    import_job_id=int(job_id) if job_id else None,
                    trigger=WOC_TRIGGER_AS_OF_BACKFILL,
                    file_period_end=file_period_end,
                )
            )
    return {"ok": True, "results": results, "job_id": job_id}


def replay_woc_observations_sync(
    *,
    tenant_id: str = "default",
    distributor_id: int,
    as_of: date | None = None,
) -> dict[str, Any]:
    """097-D: same reconstruct function as apply, no decision row."""
    with SessionLocal() as db:
        try:
            out = reconstruct_woc_observations(
                db,
                tenant_id=tenant_id,
                distributor_id=int(distributor_id),
                as_of=as_of,
                import_job_id=None,
            )
            db.commit()
            return out
        except Exception:
            db.rollback()
            logger.exception("woc observation ops replay failed distributor_id=%s", distributor_id)
            raise
