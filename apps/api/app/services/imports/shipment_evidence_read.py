"""Read-source helpers for shipment evidence (Plan D current-state cutover)."""

from __future__ import annotations

from sqlalchemy import Select
from sqlalchemy.sql import ColumnElement

from app.core.feature_flags import shipment_bitemporal_read_enabled
from app.models.shipment_evidence import ShipmentEvidenceLine


def shipment_evidence_read_relation() -> str:
    """SQL relation for read paths (current-state view or legacy lines)."""
    if shipment_bitemporal_read_enabled():
        return "shipment_evidence_current"
    return "shipment_evidence_line"


def shipment_evidence_read_model():
    """ORM class for read queries."""
    if shipment_bitemporal_read_enabled():
        from app.models.shipment_evidence_current import ShipmentEvidenceCurrent

        return ShipmentEvidenceCurrent
    return ShipmentEvidenceLine


def apply_active_evidence_filter(stmt: Select, model=ShipmentEvidenceLine) -> Select:
    """Exclude soft-superseded legacy rows when reading ``shipment_evidence_line``."""
    if shipment_bitemporal_read_enabled():
        return stmt
    col = getattr(model, "corpus_superseded_at", None)
    if col is None:
        return stmt
    return stmt.where(col.is_(None))


def active_evidence_line_predicate(model=ShipmentEvidenceLine) -> ColumnElement[bool] | None:
    if shipment_bitemporal_read_enabled():
        return None
    col = getattr(model, "corpus_superseded_at", None)
    if col is None:
        return None
    return col.is_(None)
