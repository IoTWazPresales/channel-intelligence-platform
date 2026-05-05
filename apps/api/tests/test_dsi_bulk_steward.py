"""DSI bulk steward request validation and totals (no database)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
def test_dsi_bulk_totals_helper() -> None:
    from app.api.v1.endpoints.mappings import _dsi_bulk_totals_from_rows

    rows = [
        {"ok": True, "row_count": 10, "total_units": 2.5, "total_reported_value": 100.0},
        {"ok": False, "row_count": 99, "total_units": 9.0, "total_reported_value": 50.0},
        {"ok": True, "row_count": 3, "total_units": None, "total_reported_value": None},
    ]
    t = _dsi_bulk_totals_from_rows(rows)
    assert t["ok_count"] == 2
    assert t["not_ok_count"] == 1
    assert t["staging_rows_affected"] == 13
    assert t["total_units_affected"] == 2.5
    assert t["total_reported_value_affected"] == 100.0


def test_dsi_bulk_body_ignore_ok() -> None:
    from app.api.v1.endpoints.mappings import DsiBulkStewardBody

    b = DsiBulkStewardBody(action="ignore", candidate_ids=[1, 2])
    assert b.action == "ignore"


def test_dsi_bulk_body_map_customer_requires_customer_id() -> None:
    from app.api.v1.endpoints.mappings import DsiBulkStewardBody

    with pytest.raises(ValidationError):
        DsiBulkStewardBody(action="map_customer", candidate_ids=[1])


def test_dsi_bulk_body_resolve_requires_product_id() -> None:
    from app.api.v1.endpoints.mappings import DsiBulkStewardBody

    with pytest.raises(ValidationError):
        DsiBulkStewardBody(action="resolve_product", candidate_ids=[1])


def test_dsi_bulk_body_resolve_with_payload() -> None:
    from app.api.v1.endpoints.mappings import DsiBulkStewardBody

    b = DsiBulkStewardBody(
        action="resolve_product",
        candidate_ids=[7],
        product_id=42,
        confirm_ineligible_product=True,
        audit_note="steward bulk historical evidence ok",
    )
    assert b.product_id == 42
