"""Celery/sync runner for DSI forecasting."""

from __future__ import annotations

import logging
from typing import Any

from app.db.session_sync import SessionLocal
from app.services.demand_forecast.velocity_compute import generate_velocity_demand_forecasts
from app.services.imports.dsi_forecasting import generate_distributor_forecasts

logger = logging.getLogger(__name__)


def run_dsi_forecasting_sync(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    dist_id = int(payload["distributor_id"])
    with SessionLocal() as db:
        try:
            count = generate_distributor_forecasts(db, dist_id, int(job_id))
            demand = generate_velocity_demand_forecasts(db, distributor_id=dist_id)
            db.commit()
            return {
                "rows_upserted": count,
                "distributor_id": dist_id,
                "demand_forecast": demand,
            }
        except Exception:
            db.rollback()
            logger.exception("run_dsi_forecasting_sync failed job_id=%s", job_id)
            raise
