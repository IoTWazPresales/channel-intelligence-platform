"""One read model for a shipment evidence line: job scope and steward state from the line, payload from the observation.

Plan D step D4. The parsed payload of a shipment row (item, quantity, dates, tokens, raw row) is written once, to
``shipment_evidence_observation``. ``shipment_evidence_line`` keeps the job scope (``source_key`` and the sheet/row it
came from) and the steward state (resolution ids/status, ``purchase_order_id``, ``resolved_*``, ``crad_date``,
``corpus_superseded_at``). Everything that used to read a payload column off the line reads it through ``EvidenceRow``.

The payload of a line is its **latest observation by id** (``evidence_line_id = line.id``). During validate the payload
is also available in memory (``staged``, keyed by ``source_key``) before the observation exists.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import ColumnElement, select, true
from sqlalchemy.orm import Session, aliased

from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.models.shipment_water import WATER_FIELDS

logger = logging.getLogger(__name__)

# Columns of the line that mirror the observation payload. D4 stops writing them; D5 drops them.
PAYLOAD_COLUMNS: tuple[str, ...] = (
    "report_type",
    "line_state",
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
    "customer_dealer_token",
    *WATER_FIELDS,
)
_PAYLOAD_SET = frozenset(PAYLOAD_COLUMNS)

# Line columns that stay on the line (job scope + steward state) and are readable from SQL next to the payload.
_LINE_SQL_COLUMNS: tuple[str, ...] = (
    "id",
    "import_job_id",
    "source_key",
    "source_sheet",
    "source_row_number",
    "purchase_order_id",
    "product_id",
    "product_resolution_status",
    "product_resolution_token",
    "product_resolution_detail",
    "distributor_id",
    "distributor_resolution_status",
    "distributor_resolution_token",
    "customer_id",
    "customer_resolution_status",
    "resolved_customer_id",
    "resolved_distributor_id",
    "crad_date",
    "corpus_superseded_at",
    "created_at",
    "updated_at",
)

# The line table as it read before D4, for raw-SQL readers: every line with the payload of its newest observation, under the
# same column names. Use it where a query read ``shipment_evidence_line l``:
#     FROM {EVIDENCE_LINES_WITH_PAYLOAD_SQL} l
# Postgres pulls the subquery up, so a predicate on ``l.import_job_id`` still uses the line index and the lateral probe
# (``ix_shipment_ev_obs_evidence_line``) runs once per surviving line.
EVIDENCE_LINES_WITH_PAYLOAD_SQL = (
    "(SELECT "
    + ", ".join(f"sel.{c}" for c in _LINE_SQL_COLUMNS)
    + ", "
    + ", ".join(f"obs.{c}" for c in PAYLOAD_COLUMNS)
    + """
     FROM shipment_evidence_line sel
     LEFT JOIN LATERAL (
         SELECT o.*
         FROM shipment_evidence_observation o
         WHERE o.evidence_line_id = sel.id
         ORDER BY o.id DESC
         LIMIT 1
     ) obs ON TRUE)"""
)


class MissingEvidencePayload(RuntimeError):
    """A line has no observation, so its payload is unknown."""


class EvidenceRow:
    """A line plus its payload. Payload attributes read the observation (or the staged dict); the rest read the line.

    Writes go to the line only, and only for non-payload attributes: payload is never written through a row.
    """

    __slots__ = ("line", "_payload")

    def __init__(self, line: ShipmentEvidenceLine, payload: Mapping[str, Any] | None) -> None:
        object.__setattr__(self, "line", line)
        object.__setattr__(self, "_payload", payload)

    @property
    def has_payload(self) -> bool:
        return self._payload is not None

    def __getattr__(self, name: str) -> Any:
        if name in _PAYLOAD_SET:
            payload = object.__getattribute__(self, "_payload")
            if payload is None:
                raise MissingEvidencePayload(
                    f"shipment evidence line {self.line.id} has no observation, so '{name}' is unknown"
                )
            return payload.get(name)
        return getattr(object.__getattribute__(self, "line"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _PAYLOAD_SET:
            raise AttributeError(f"'{name}' is observation payload; D4 does not write it on the line")
        setattr(self.line, name, value)


def observation_payload(obs: ShipmentEvidenceObservation) -> dict[str, Any]:
    return {col: getattr(obs, col) for col in PAYLOAD_COLUMNS}


def latest_observation_lateral():
    """``(lateral, observation_alias)``: the newest observation of ``ShipmentEvidenceLine.id`` (one index probe per line)."""
    sub = (
        select(ShipmentEvidenceObservation)
        .where(ShipmentEvidenceObservation.evidence_line_id == ShipmentEvidenceLine.id)
        .order_by(ShipmentEvidenceObservation.id.desc())
        .limit(1)
        .lateral("latest_obs")
    )
    return sub, aliased(ShipmentEvidenceObservation, sub)


def load_evidence_rows(
    db: Session,
    *,
    job_id: int | None = None,
    where: Iterable[ColumnElement[bool]] = (),
    staged: Mapping[str, Mapping[str, Any]] | None = None,
    order_by_id: bool = True,
) -> list[EvidenceRow]:
    """Lines (``job_id`` and/or ``where``) with their payload.

    ``staged`` (``source_key`` → payload) wins over the stored observation: it is the payload of the validate pass that
    is still running. A line with neither has ``has_payload`` False.
    """
    lateral, obs = latest_observation_lateral()
    stmt = select(ShipmentEvidenceLine, obs).outerjoin(lateral, true())
    if job_id is not None:
        stmt = stmt.where(ShipmentEvidenceLine.import_job_id == int(job_id))
    for clause in where:
        stmt = stmt.where(clause)
    if order_by_id:
        stmt = stmt.order_by(ShipmentEvidenceLine.id)
    rows: list[EvidenceRow] = []
    for line, observation in db.execute(stmt).all():
        payload: Mapping[str, Any] | None = None
        if staged is not None and line.source_key in staged:
            payload = staged[line.source_key]
        elif observation is not None and observation.id is not None:
            payload = observation_payload(observation)
        rows.append(EvidenceRow(line, payload))
    return rows


def latest_observation_payload_for_line_ids(
    db: Session, line_ids: Iterable[int]
) -> dict[int, dict[str, Any]]:
    """Payload of the newest observation per line id (lines with no observation are absent)."""
    ids = sorted({int(i) for i in line_ids})
    if not ids:
        return {}
    lateral, obs = latest_observation_lateral()
    stmt = (
        select(ShipmentEvidenceLine.id, obs)
        .select_from(ShipmentEvidenceLine)
        .outerjoin(lateral, true())
        .where(ShipmentEvidenceLine.id.in_(ids))
    )
    out: dict[int, dict[str, Any]] = {}
    for line_id, observation in db.execute(stmt).all():
        if observation is not None and observation.id is not None:
            out[int(line_id)] = observation_payload(observation)
    return out
