"""Dual-write and read-source helpers for bitemporal shipment evidence (Plan D)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.feature_flags import (
    shipment_bitemporal_dual_write_enabled,
    shipment_bitemporal_read_enabled,
)
from app.models.ingestion import ImportJob
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.imports.shipment_evidence_line_identity import (
    observation_payload_hash,
    stable_line_identity_key_from_mapping,
)

logger = logging.getLogger(__name__)

_OBSERVATION_UPSERT_CHUNK = 500

_LINE_TO_OBSERVATION_COLS = (
    "source_sheet",
    "source_row_number",
    "report_type",
    "line_state",
    "source_key",
    "raw_source_row",
    "operating_unit",
    "bill_to_raw",
    "ship_to_raw",
    "order_no",
    "customer_po",
    "order_line",
    "delivery_no",
    "invoice_line",
    "item_code",
    "sales_model_name",
    "customer_item",
    "ean_code",
    "upc_code",
    "mpor_item_no",
    "quantity",
    "unit_price",
    "amount",
    "currency_code",
    "ship_confirm_date",
    "schedule_ship_date",
    "promise_date",
    "exwork_date",
    "erd_date",
    "est_pod_date",
    "pod_date",
    "product_id",
    "product_resolution_status",
    "product_resolution_token",
    "product_resolution_detail",
    "distributor_id",
    "distributor_resolution_status",
    "distributor_resolution_token",
    "customer_dealer_token",
    "customer_id",
    "customer_resolution_status",
)


def corroboration_evidence_relation() -> str:
    """SQL relation for DSI shipment corroboration reads."""
    if shipment_bitemporal_read_enabled():
        return "shipment_evidence_current"
    return "shipment_evidence_line"


def _job_transaction_times(job: ImportJob) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    observed_at = job.created_at if job.created_at is not None else now
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    valid_from = job.completed_at if job.completed_at is not None else observed_at
    if valid_from.tzinfo is None:
        valid_from = valid_from.replace(tzinfo=timezone.utc)
    return valid_from, observed_at


def _line_to_observation_values(
    line: ShipmentEvidenceLine,
    *,
    valid_from: datetime,
    observed_at: datetime,
) -> dict[str, Any]:
    base = {col: getattr(line, col) for col in _LINE_TO_OBSERVATION_COLS}
    base["import_job_id"] = int(line.import_job_id)
    base["evidence_line_id"] = int(line.id)
    base["line_identity_key"] = stable_line_identity_key_from_mapping(base)
    base["valid_from"] = valid_from
    base["observed_at"] = observed_at
    base["source_row_hash"] = observation_payload_hash(base)
    return base


def _observation_insert_statement(rows: list[dict[str, Any]]):
    t = ShipmentEvidenceObservation.__table__
    ins = pg_insert(t).values(rows)
    return ins.on_conflict_do_nothing(constraint="uq_shipment_ev_obs_job_row_hash")


def append_observations_for_job_lines(
    db: Session,
    job: ImportJob,
    lines: list[ShipmentEvidenceLine] | None = None,
) -> int:
    """Append observations for job lines (idempotent per source_row_hash)."""
    if not lines:
        lines = list(
            db.scalars(
                select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id == int(job.id))
            ).all()
        )
    if not lines:
        return 0

    valid_from, observed_at = _job_transaction_times(job)
    values = [
        _line_to_observation_values(line, valid_from=valid_from, observed_at=observed_at) for line in lines
    ]

    attempted = 0
    for i in range(0, len(values), _OBSERVATION_UPSERT_CHUNK):
        chunk = values[i : i + _OBSERVATION_UPSERT_CHUNK]
        attempted += len(chunk)
        db.execute(_observation_insert_statement(chunk))
    db.flush()
    logger.info(
        "shipment observations: appended up to %d rows for job_id=%s",
        attempted,
        job.id,
    )
    return attempted


def sync_job_observations_after_validate(db: Session, job: ImportJob) -> int:
    """When dual-write flag is on, append observations after legacy lines are final."""
    if not shipment_bitemporal_dual_write_enabled():
        return 0
    return append_observations_for_job_lines(db, job)
