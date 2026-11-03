"""Build shipment evidence the way the D4 loader stores it: the line holds job scope and steward state, the observation holds the payload.

``add_evidence_line`` takes the keyword arguments a test used to pass to ``ShipmentEvidenceLine(...)``. Payload arguments
(``item_code``, ``quantity``, ``pod_date``, ``raw_source_row`` ...) go to the observation; the rest go to the line.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.imports.shipment_evidence_observations import (
    _apply_sticky_observation_pods,
    _insert_observation_chunk,
    _row_to_observation_values,
)
from app.services.imports.shipment_evidence_rows import PAYLOAD_COLUMNS, EvidenceRow

_PAYLOAD = frozenset(PAYLOAD_COLUMNS)
_LINE_DEFAULTS: dict[str, Any] = {
    "source_row_number": 1,
    "product_resolution_status": "no_identifier",
    "distributor_resolution_status": "unresolved",
}


def split_fields(fields: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = {k: v for k, v in fields.items() if k in _PAYLOAD}
    line = {k: v for k, v in fields.items() if k not in _PAYLOAD}
    payload.setdefault("report_type", "shipped")
    payload.setdefault("line_state", "shipped")
    payload.setdefault("raw_source_row", {})
    for k in PAYLOAD_COLUMNS:
        payload.setdefault(k, None)
    return line, payload


def make_row(**fields: Any) -> EvidenceRow:
    """An ``EvidenceRow`` with no database: for unit tests that only read attributes."""
    line_kw, payload = split_fields(fields)
    line_kw.setdefault("import_job_id", 1)
    line_kw.setdefault("source_key", "k")
    for k, v in _LINE_DEFAULTS.items():
        line_kw.setdefault(k, v)
    return EvidenceRow(ShipmentEvidenceLine(**line_kw), payload)


def add_evidence_line(
    db: Session,
    *,
    observe: bool = True,
    valid_from: datetime | None = None,
    **fields: Any,
) -> ShipmentEvidenceLine:
    """Insert a line (scope + state) and, unless ``observe`` is False, its observation (payload). Flushes."""
    line_kw, payload = split_fields(fields)
    for k, v in _LINE_DEFAULTS.items():
        line_kw.setdefault(k, v)
    line = ShipmentEvidenceLine(**line_kw)
    db.add(line)
    db.flush()
    if observe:
        when = valid_from or datetime.now(timezone.utc)
        values = _row_to_observation_values(EvidenceRow(line, payload), valid_from=when, observed_at=when)
        _apply_sticky_observation_pods(db, [values])
        db.add(ShipmentEvidenceObservation(**values))
        db.flush()
    return line


def reobserve(db: Session, line: ShipmentEvidenceLine, **payload_changes: Any) -> ShipmentEvidenceObservation:
    """Append a newer observation of ``line`` with some payload fields changed (the line's payload moves on)."""
    from app.services.imports.shipment_evidence_rows import load_evidence_rows

    row = load_evidence_rows(db, where=(ShipmentEvidenceLine.id == int(line.id),))[0]
    payload = {c: getattr(row, c) for c in PAYLOAD_COLUMNS}
    payload.update(payload_changes)
    when = datetime.now(timezone.utc)
    values = _row_to_observation_values(EvidenceRow(line, payload), valid_from=when, observed_at=when)
    _apply_sticky_observation_pods(db, [values])
    _insert_observation_chunk(db, [values])
    db.flush()
    from sqlalchemy import select

    obs = db.scalar(
        select(ShipmentEvidenceObservation)
        .where(
            ShipmentEvidenceObservation.import_job_id == int(line.import_job_id),
            ShipmentEvidenceObservation.source_row_hash == values["source_row_hash"],
        )
        .order_by(ShipmentEvidenceObservation.id.desc())
        .execution_options(populate_existing=True)
    )
    assert obs is not None
    return obs


def row_of(db: Session, line: ShipmentEvidenceLine) -> EvidenceRow:
    """The line read the way the apply reads it: its state plus its newest observation's payload."""
    from app.services.imports.shipment_evidence_rows import load_evidence_rows

    return load_evidence_rows(db, where=(ShipmentEvidenceLine.id == int(line.id),))[0]
