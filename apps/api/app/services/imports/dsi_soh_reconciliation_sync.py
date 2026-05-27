"""Celery/sync runner for DSI SOH reconciliation."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.db.session_sync import SessionLocal
from app.services.imports.dsi_soh_reconciliation import reconcile_distributor_soh

logger = logging.getLogger(__name__)


def run_dsi_soh_reconciliation_sync(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    dist_id = int(payload["distributor_id"])
    period_end = date.fromisoformat(str(payload["period_end_date"]))
    with SessionLocal() as db:
        try:
            out = reconcile_distributor_soh(
                db,
                distributor_id=dist_id,
                period_end_date=period_end,
                import_job_id=int(job_id),
            )
            db.commit()
            return out
        except Exception:
            db.rollback()
            logger.exception("run_dsi_soh_reconciliation_sync failed job_id=%s", job_id)
            raise
