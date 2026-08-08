"""BACKLOG-076 — inbound fact amount / unit-price scale sanity check.

Flags fact_inbound_shipment rows whose implied unit price (``amount / quantity``)
is implausibly high — the signature of an OEM export mapping amount/currency at
the wrong scale (e.g. an extra zero, or cents mapped as whole units) rather than a
genuinely high-value line. Confirmed on ``cip``: 17 ``acza_workbook_unship``
scheduled lines with quantity 36 and amount ~$36M each (implied unit price ~$1M).

FLAG != BLOCK — suspect rows are excluded from KPI valuation only. Nothing here
mutates `fact_inbound_shipment.amount`; see BACKLOG-076 for the mapping audit /
corrective re-import track, which stays separate and requires explicit approval.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, and_, func, or_

from app.models.facts import FactInboundShipment

UNIT_PRICE_SUSPECT_THRESHOLD = 100_000


def is_unit_price_scale_suspect(amount: float | None, quantity: float | None) -> bool:
    """True when the implied unit price (``amount / quantity``) exceeds the sanity threshold.

    Requires a positive quantity to compute a unit price — rows with missing or
    zero/negative quantity are never flagged by this check (nothing to divide by).
    """
    if amount is None or quantity is None:
        return False
    try:
        amt = float(amount)
        qty = float(quantity)
    except (TypeError, ValueError):
        return False
    if qty <= 0:
        return False
    return (abs(amt) / qty) > UNIT_PRICE_SUSPECT_THRESHOLD


def amount_scale_suspect_clause() -> ColumnElement[bool]:
    """SQL mirror of :func:`is_unit_price_scale_suspect` for set-based filtering."""
    qty = FactInboundShipment.quantity
    amt = FactInboundShipment.amount
    return and_(
        qty.is_not(None),
        qty > 0,
        amt.is_not(None),
        func.abs(amt) / qty > UNIT_PRICE_SUSPECT_THRESHOLD,
    )


def amount_scale_not_suspect_clause() -> ColumnElement[bool]:
    """Inverse of :func:`amount_scale_suspect_clause` — use to exclude suspect rows (FLAG != BLOCK)."""
    qty = FactInboundShipment.quantity
    amt = FactInboundShipment.amount
    return or_(
        qty.is_(None),
        qty <= 0,
        amt.is_(None),
        func.abs(amt) / qty <= UNIT_PRICE_SUSPECT_THRESHOLD,
    )
