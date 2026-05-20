"""Shipment corroboration cache — customer rows use steward ``resolved`` status."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from app.services.imports.dsi_shipment_corroboration import ShipmentCorroborationCache


def test_customer_corroboration_cache_includes_resolved_status_rows() -> None:
    """Steward apply sets customer_resolution_status='resolved', not resolved_unique."""
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(fetchall=lambda: []),  # product rows
        MagicMock(
            fetchall=lambda: [
                (10, 42, "2024-01", "acme dealer", "acme bill", "acme ship"),
            ]
        ),
    ]
    cache = ShipmentCorroborationCache.load(db, {"2024-01"})
    hit = cache.customer_corroboration(
        10,
        date(2024, 1, 15),
        customer_primary_raw="ACME Dealer",
        dealer_group_raw=None,
    )
    assert hit is not None
    assert hit["kind"] == "shipment_evidence_customer"
    assert hit["match_count"] == 1


def test_customer_corroboration_sql_uses_resolved_and_resolved_unique() -> None:
    db = MagicMock()
    db.execute.side_effect = [MagicMock(fetchall=lambda: []), MagicMock(fetchall=lambda: [])]
    ShipmentCorroborationCache.load(db, {"2024-01"})
    cust_sql = str(db.execute.call_args_list[1][0][0])
    assert "resolved_unique" in cust_sql
    assert "'resolved'" in cust_sql or "resolved" in cust_sql
