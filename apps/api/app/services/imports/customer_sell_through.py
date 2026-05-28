"""Customer sell-through import pipeline (Phase 0 skeleton — parsers in Phase 1)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.models.customer_report_config import CustomerReportConfig
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.ingestion import ImportJob, ImportTemplate
from app.utils.json_safe import to_jsonable

logger = logging.getLogger(__name__)

# Matches ``STAGE_FAILED`` in ``app.ingestion.pipeline`` (avoid circular import).
_STAGE_FAILED = "failed"

STRUCTURE_FLAT = "flat"
STRUCTURE_PIVOTED = "pivoted"
STRUCTURE_MULTI_SHEET = "multi_sheet"
STRUCTURE_MTD_DELTA = "mtd_delta"
STRUCTURE_WIDE_EXTRACT = "wide_extract"

_RETAILERS_BY_STRUCTURE: dict[str, str] = {
    STRUCTURE_FLAT: "Evetech, Takealot",
    STRUCTURE_PIVOTED: "Game, Makro",
    STRUCTURE_MULTI_SHEET: "Computer Mania",
    STRUCTURE_MTD_DELTA: "FNB",
    STRUCTURE_WIDE_EXTRACT: "IC (Incredible Connections)",
}


def customer_sellthrough_source_key(
    *,
    customer_id: int,
    customer_location_id: int | None,
    product_id: int,
    period_start_date: date,
) -> str:
    """Natural upsert key: ``ct:{customer_id}:{location_id|0}:{product_id}:{period_start_date}``."""
    loc_part = int(customer_location_id) if customer_location_id is not None else 0
    return f"ct:{customer_id}:{loc_part}:{product_id}:{period_start_date.isoformat()}"


def new_customer_sellthrough_staging_line(
    *,
    import_job_id: int,
    source_row_number: int,
    raw_row_payload: dict[str, Any] | None = None,
) -> ImportCustomerSellthroughStagingLine:
    """Create a pending staging row (resolution applied in Phase 1)."""
    return ImportCustomerSellthroughStagingLine(
        import_job_id=import_job_id,
        source_row_number=source_row_number,
        raw_row_payload=raw_row_payload or {},
        resolution_status="pending",
    )


def customer_report_config_defaults(*, customer_id: int) -> CustomerReportConfig:
    """In-memory config row with Phase 0 defaults (not persisted)."""
    return CustomerReportConfig(
        customer_id=customer_id,
        reports_expected=False,
        expected_cadence="weekly",
        overdue_threshold_days=10,
    )


def _parser_not_implemented_message(structure_type: str) -> str:
    retailers = _RETAILERS_BY_STRUCTURE.get(structure_type, "see documentation")
    return (
        f"Parser not yet implemented for structure type: {structure_type}. "
        f"Phase 1 will implement this handler. Supported retailers: {retailers}"
    )


def _handle_flat(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
) -> int:
    raise NotImplementedError(_parser_not_implemented_message(STRUCTURE_FLAT))


def _handle_pivoted(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
) -> int:
    raise NotImplementedError(_parser_not_implemented_message(STRUCTURE_PIVOTED))


def _handle_multi_sheet(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
) -> int:
    raise NotImplementedError(_parser_not_implemented_message(STRUCTURE_MULTI_SHEET))


def _handle_mtd_delta(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
) -> int:
    raise NotImplementedError(_parser_not_implemented_message(STRUCTURE_MTD_DELTA))


def _handle_wide_extract(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
) -> int:
    raise NotImplementedError(_parser_not_implemented_message(STRUCTURE_WIDE_EXTRACT))


def _write_parser_not_implemented(job: ImportJob, structure_type: str, message: str) -> None:
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta["customer_sellthrough_error"] = {
        "reason": "parser_not_implemented",
        "structure_type": structure_type,
        "message": message,
    }
    job.staged_metadata = to_jsonable(meta)
    job.stage = _STAGE_FAILED
    job.status = "completed_with_errors"
    job.error_summary = message[:500]


def process_customer_sell_through(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None = None,
) -> int:
    """Dispatch on report structure type; Phase 0 handlers are not implemented yet.

    ``df`` is the parsed tabular file from the import pipeline (equivalent to decoded file bytes).
    Returns blocking error count (0 success path, 1 when parser skeleton stops the job).
    """
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    structure_type = meta.get("report_structure_type")
    if not isinstance(structure_type, str) or not structure_type.strip():
        structure_type = STRUCTURE_FLAT
        logger.warning(
            "customer_sell_through job_id=%s missing report_structure_type; defaulting to flat",
            job.id,
        )
    structure_type = structure_type.strip()

    handlers = {
        STRUCTURE_FLAT: _handle_flat,
        STRUCTURE_PIVOTED: _handle_pivoted,
        STRUCTURE_MULTI_SHEET: _handle_multi_sheet,
        STRUCTURE_MTD_DELTA: _handle_mtd_delta,
        STRUCTURE_WIDE_EXTRACT: _handle_wide_extract,
    }
    handler = handlers.get(structure_type)
    if handler is None:
        msg = f"Unknown structure type: {structure_type}"
        _write_parser_not_implemented(job, structure_type, msg)
        return 1

    try:
        return handler(db, job, df, mapping, template)
    except NotImplementedError as exc:
        _write_parser_not_implemented(job, structure_type, str(exc))
        return 1
