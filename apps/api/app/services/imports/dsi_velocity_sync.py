"""Celery/sync runner for DSI velocity compute."""

from __future__ import annotations

import logging
from typing import Any

from app.db.session_sync import SessionLocal
from app.services.imports.dsi_velocity_intelligence import compute_distributor_velocity

logger = logging.getLogger(__name__)


def run_dsi_velocity_compute_sync(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    dist_id = int(payload["distributor_id"])
    with SessionLocal() as db:
        try:
            count = compute_distributor_velocity(db, dist_id, int(job_id))
            db.commit()
            from app.services.imports.dsi_forecasting_enqueue import enqueue_dsi_forecasting

            enqueue_dsi_forecasting(
                int(job_id),
                distributor_id=dist_id,
                detach_from_caller=False,
            )
            return {"rows_upserted": count, "distributor_id": dist_id}
        except Exception:
            db.rollback()
            logger.exception("run_dsi_velocity_compute_sync failed job_id=%s", job_id)
            raise
