"""Read-source helpers for shipment evidence (Plan D current-state reads).

D4: the legacy ``CIP_SHIPMENT_BITEMPORAL_READ=0`` branch (reading the payload off ``shipment_evidence_line``) is gone, because the
line no longer carries a payload. Every read goes through the ``shipment_evidence_current`` view.
"""

from __future__ import annotations

from sqlalchemy import Select
from sqlalchemy.sql import ColumnElement


def shipment_evidence_read_relation() -> str:
    """SQL relation for read paths (the current-state view)."""
    return "shipment_evidence_current"


def shipment_evidence_read_model():
    """ORM class for read queries."""
    from app.models.shipment_evidence_current import ShipmentEvidenceCurrent

    return ShipmentEvidenceCurrent


def apply_active_evidence_filter(stmt: Select, model=None) -> Select:
    """The current view already excludes superseded observations; nothing to add."""
    return stmt


def active_evidence_line_predicate(model=None) -> ColumnElement[bool] | None:
    """The current view already excludes superseded observations; no extra predicate."""
    return None
