"""Shipment apply failure writeback — mirrors Product Master commit worker pattern."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import STAGE_FAILED
from app.models.ingestion import ImportJob, ImportRowResult
from app.services.imports.import_job_background_metadata import persist_clear_background_task_metadata
from app.utils.json_safe import to_jsonable

logger = logging.getLogger(__name__)


class ShipmentApplyRowError(Exception):
    """Apply-time fact write failure for a single evidence line."""

    def __init__(
        self,
        message: str,
        *,
        evidence_line_id: int | None = None,
        source_key: str | None = None,
        source_row_number: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.evidence_line_id = evidence_line_id
        self.source_key = source_key
        self.source_row_number = source_row_number
        self.cause = cause


def record_shipment_apply_failure(
    job_id: int,
    exc: BaseException,
    *,
    evidence_line_id: int | None = None,
    source_key: str | None = None,
    source_row_number: int | None = None,
) -> dict[str, Any]:
    """Rollback-safe failure writeback on a clean session (never re-raises)."""
    msg = str(exc).strip() or exc.__class__.__name__
    if isinstance(exc, ShipmentApplyRowError):
        evidence_line_id = evidence_line_id or exc.evidence_line_id
        source_key = source_key or exc.source_key
        source_row_number = source_row_number or exc.source_row_number
        if exc.cause is not None and not msg:
            msg = str(exc.cause).strip() or exc.cause.__class__.__name__

    outcome: dict[str, Any] = {
        "id": int(job_id),
        "outcome": "failed",
        "error": msg[:500],
        "recorded": False,
    }
    try:
        with SessionLocal() as db:
            job = db.get(ImportJob, job_id)
            if job is None:
                return outcome
            row_number = int(source_row_number or evidence_line_id or 0)
            db.add(
                ImportRowResult(
                    job_id=int(job_id),
                    row_number=row_number,
                    severity="error",
                    code="shipment_apply_fact_write_failed",
                    message=f"Shipment apply failed: {msg[:1200]}",
                    raw_payload=to_jsonable(
                        {
                            "error_type": exc.__class__.__name__,
                            "evidence_line_id": evidence_line_id,
                            "source_key": source_key,
                            "source_row_number": source_row_number,
                        }
                    ),
                )
            )
            job.status = "failed"
            job.stage = STAGE_FAILED
            job.error_summary = msg[:2000]
            job.completed_at = datetime.now(timezone.utc)
            persist_clear_background_task_metadata(db, job)
            db.commit()
            outcome["recorded"] = True
    except Exception:
        logger.exception("shipment apply failure writeback failed job_id=%s", job_id)
    return outcome
