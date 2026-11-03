"""Observation writer for bitemporal shipment evidence (Plan D).

D4: the observation is the only place the parsed payload is written. The payload comes from the validate pass
(``staged``, keyed by ``source_key``) or, when an observation is re-appended later, from the line's newest observation;
the steward state (resolution ids, ``purchase_order_id``) comes from the line.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.models.shipment_water import WATER_DATE_FIELDS, WATER_FIELDS
from app.services.imports.shipment_evidence_line_identity import (
    observation_payload_hash,
    stable_line_identity_key_from_mapping,
)
from app.services.imports.shipment_evidence_read import shipment_evidence_read_relation
from app.services.imports.shipment_evidence_rows import EvidenceRow, load_evidence_rows

try:  # psycopg 3 raises its own DataError type through SQLAlchemy's DBAPIError wrapper
    from psycopg.errors import DataError as PsycopgDataError
except ImportError:  # pragma: no cover
    PsycopgDataError = ()  # type: ignore[assignment,misc]

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
    "purchase_order_id",
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
    # On the water (20261101_0049). Not in the observation hash (_OBSERVATION_HASH_COLS), so hashes
    # of observations written before the columns existed are unchanged.
    *WATER_FIELDS,
)


def corroboration_evidence_relation() -> str:
    """SQL relation for DSI shipment corroboration reads."""
    return shipment_evidence_read_relation()


def _job_transaction_times(job: ImportJob) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    observed_at = job.created_at if job.created_at is not None else now
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    valid_from = job.completed_at if job.completed_at is not None else observed_at
    if valid_from.tzinfo is None:
        valid_from = valid_from.replace(tzinfo=timezone.utc)
    return valid_from, observed_at


_NUMERIC_COLS = ("quantity", "unit_price", "amount")
_OBSERVATION_DATE_COLS = (
    "ship_confirm_date",
    "schedule_ship_date",
    "promise_date",
    "exwork_date",
    "erd_date",
    "est_pod_date",
    "pod_date",
    *WATER_DATE_FIELDS,
)
_FOUR_PLACES = Decimal("0.0001")


def _as_numeric_4(value: Any) -> Any:
    """The Numeric(18,4) a stored row would read back as, so the payload hash is the same from a staged float."""
    if value is None or isinstance(value, Decimal):
        return value
    return Decimal(str(value)).quantize(_FOUR_PLACES)


def _row_to_observation_values(
    row: EvidenceRow,
    *,
    valid_from: datetime,
    observed_at: datetime,
) -> dict[str, Any]:
    # A stub line without the voyage attributes reads as empty there (the columns are new and nullable).
    base = {col: getattr(row, col, None) if col in WATER_FIELDS else getattr(row, col) for col in _LINE_TO_OBSERVATION_COLS}
    for col in _NUMERIC_COLS:
        base[col] = _as_numeric_4(base[col])
    base["import_job_id"] = int(row.import_job_id)
    base["evidence_line_id"] = int(row.id)
    base["line_identity_key"] = stable_line_identity_key_from_mapping(base)
    base["valid_from"] = valid_from
    base["observed_at"] = observed_at
    base["source_row_hash"] = observation_payload_hash(base)
    return base


# Written on the observation but not part of ``source_row_hash``. A re-validate of the same commercial row used to
# refresh these on the line (ON CONFLICT DO UPDATE). The hash stays stable for rows already on cip; these columns
# refresh in place so a corrected PO, raw row or voyage is what the fact reads.
_REFRESH_ON_SAME_HASH = (
    "customer_po",
    "raw_source_row",
    "purchase_order_id",
    "evidence_line_id",
    *WATER_FIELDS,
)


def _observation_insert_statement(rows: list[dict[str, Any]]):
    t = ShipmentEvidenceObservation.__table__
    ins = pg_insert(t).values(rows)
    excluded = ins.excluded
    return ins.on_conflict_do_update(
        constraint="uq_shipment_ev_obs_job_row_hash",
        set_={col: getattr(excluded, col) for col in _REFRESH_ON_SAME_HASH},
    )


def _expire_loaded_observations(db: Session) -> None:
    """The upsert writes through Core. Observations already in this session would otherwise keep the pre-update payload."""
    for obj in list(db.identity_map.values()):
        if isinstance(obj, ShipmentEvidenceObservation):
            db.expire(obj)


def _prior_pod_by_identity_keys(db: Session, identity_keys: list[str]) -> dict[str, date]:
    """Last non-null POD per ``line_identity_key`` (any observation history)."""
    keys = sorted({k for k in identity_keys if k})
    if not keys:
        return {}
    rows = db.execute(
        select(ShipmentEvidenceObservation.line_identity_key, ShipmentEvidenceObservation.pod_date)
        .where(
            ShipmentEvidenceObservation.line_identity_key.in_(keys),
            ShipmentEvidenceObservation.pod_date.is_not(None),
        )
        .order_by(
            ShipmentEvidenceObservation.line_identity_key,
            ShipmentEvidenceObservation.valid_from.desc().nulls_last(),
            ShipmentEvidenceObservation.id.desc(),
        )
        .distinct(ShipmentEvidenceObservation.line_identity_key)
    ).all()
    return {str(k): pod for k, pod in rows if pod is not None}


def _apply_sticky_observation_pods(db: Session, values: list[dict[str, Any]]) -> None:
    need = [str(v["line_identity_key"]) for v in values if v.get("pod_date") is None and v.get("line_identity_key")]
    prior = _prior_pod_by_identity_keys(db, need)
    for v in values:
        if v.get("pod_date") is not None:
            continue
        key = str(v.get("line_identity_key") or "")
        if key in prior:
            v["pod_date"] = prior[key]


def _is_data_error(exc: BaseException) -> bool:
    if PsycopgDataError and isinstance(exc, PsycopgDataError):
        return True
    return bool(PsycopgDataError) and isinstance(exc, DBAPIError) and isinstance(getattr(exc, "orig", None), PsycopgDataError)


def _insert_observation_chunk(db: Session, chunk: list[dict[str, Any]]) -> None:
    """One multi-row insert; on a Postgres DataError (an out-of-range date) retry row by row with the dates cleared.

    A chunk is de-duplicated on ``(import_job_id, source_row_hash)`` (last wins). Postgres rejects an
    ``ON CONFLICT DO UPDATE`` that touches one key twice.
    """
    deduped: dict[tuple[Any, Any], dict[str, Any]] = {}
    for values in chunk:
        deduped[(values.get("import_job_id"), values.get("source_row_hash"))] = values
    chunk = list(deduped.values())
    try:
        with db.begin_nested():
            db.execute(_observation_insert_statement(chunk))
    except Exception as exc:
        if not _is_data_error(exc):
            raise
        for values in chunk:
            cleared = {**values, **{c: None for c in _OBSERVATION_DATE_COLS}}
            with db.begin_nested():
                db.execute(_observation_insert_statement([cleared]))


def append_observations_for_job_lines(
    db: Session,
    job: ImportJob,
    rows: list[EvidenceRow] | None = None,
    *,
    staged: Mapping[str, Mapping[str, Any]] | None = None,
) -> int:
    """Append one observation per job line (idempotent per source_row_hash).

    Payload: ``staged[source_key]`` when the validate pass supplies it, else the line's newest observation. A line with
    neither is skipped (logged): there is nothing to observe.

    Sticky POD: if the payload omits ``pod_date`` but a prior observation for the same
    ``line_identity_key`` had one, carry it forward (P1-D004 / BACKLOG-088).
    """
    if rows is None:
        rows = load_evidence_rows(db, job_id=int(job.id), staged=staged)
    observable = [r for r in rows if r.has_payload]
    if len(observable) != len(rows):
        logger.warning(
            "shipment observations: job_id=%s skipped %d line(s) with no payload", job.id, len(rows) - len(observable)
        )
    if not observable:
        return 0

    valid_from, observed_at = _job_transaction_times(job)
    values = [_row_to_observation_values(r, valid_from=valid_from, observed_at=observed_at) for r in observable]
    _apply_sticky_observation_pods(db, values)

    attempted = 0
    for i in range(0, len(values), _OBSERVATION_UPSERT_CHUNK):
        chunk = values[i : i + _OBSERVATION_UPSERT_CHUNK]
        attempted += len(chunk)
        _insert_observation_chunk(db, chunk)
    db.flush()
    _expire_loaded_observations(db)
    logger.info(
        "shipment observations: appended up to %d rows for job_id=%s",
        attempted,
        job.id,
    )
    return attempted


def sync_job_observations_after_validate(
    db: Session,
    job: ImportJob,
    *,
    staged: Mapping[str, Mapping[str, Any]] | None = None,
) -> int:
    """Append the job's observations once the lines are final, then run invoice graduation."""
    appended = append_observations_for_job_lines(db, job, staged=staged)
    if appended:
        from app.services.imports.shipment_invoice_graduation import process_invoice_graduation_after_job

        process_invoice_graduation_after_job(db, job)
    return appended
