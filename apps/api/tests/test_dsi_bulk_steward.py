"""DSI bulk steward request validation and totals (no database)."""

from __future__ import annotations

import asyncio

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


def test_dsi_steward_bulk_apply_ignore_uses_batch_writer() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.api.v1.endpoints.mappings import DsiBulkStewardBody, dsi_steward_bulk_apply

    async def _run() -> None:
        db = MagicMock()
        db.run_sync = AsyncMock(
            return_value={
                "import_job_id": 43,
                "action": "ignore",
                "applied": 2,
                "failed": 0,
                "results": [
                    {
                        "candidate_id": 1,
                        "ok": True,
                        "entity_type": "product_identifier",
                        "result": {"ok": True, "candidate_id": 1, "status": "ignored"},
                        "row_count": 1,
                        "total_units": None,
                        "total_reported_value": None,
                    },
                    {
                        "candidate_id": 2,
                        "ok": True,
                        "entity_type": "product_identifier",
                        "result": {"ok": True, "candidate_id": 2, "status": "ignored"},
                        "row_count": 2,
                        "total_units": None,
                        "total_reported_value": None,
                    },
                ],
            }
        )

        with patch("app.api.v1.endpoints.mappings._assert_dsi_import_job", new=AsyncMock()):
            body = DsiBulkStewardBody(action="ignore", candidate_ids=[1, 2])
            out = await dsi_steward_bulk_apply(43, body, db)

        assert out["applied"] == 2
        assert out["failed"] == 0
        db.run_sync.assert_awaited_once()
        assert db.get.call_count == 0

    asyncio.run(_run())


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


def test_dsi_bulk_body_create_provisional_customer_allows_optional_geo() -> None:
    from app.api.v1.endpoints.mappings import DsiBulkStewardBody

    b = DsiBulkStewardBody(action="create_provisional_customer", candidate_ids=[1], region_id=10, channel_id=None)
    assert b.region_id == 10
    assert b.channel_id is None


def test_dsi_bulk_body_create_provisional_customer_ok() -> None:
    from app.api.v1.endpoints.mappings import DsiBulkStewardBody

    b = DsiBulkStewardBody(
        action="create_provisional_customer",
        candidate_ids=[1, 2],
        region_id=10,
        channel_id=20,
        provisional_notes_summary="batch note",
    )
    assert b.region_id == 10
    assert b.provisional_notes_summary == "batch note"


def test_dsi_bulk_provisional_payload_from_body() -> None:
    from app.api.v1.endpoints.mappings import DsiBulkStewardBody, _dsi_bulk_provisional_payload_from_body

    b = DsiBulkStewardBody(
        action="create_provisional_customer",
        candidate_ids=[1, 2],
        region_id=10,
        channel_id=20,
        partner_tier="tier_1",
        provisional_notes_summary="note",
    )
    p = _dsi_bulk_provisional_payload_from_body(b)
    assert p["candidate_ids"] == [1, 2]
    assert p["region_id"] == 10
    assert p["channel_id"] == 20
    assert p["partner_tier"] == "tier_1"
    assert p["provisional_notes_summary"] == "note"


def test_dsi_bulk_body_create_provisional_distributor_ok() -> None:
    from app.api.v1.endpoints.mappings import DsiBulkStewardBody

    b = DsiBulkStewardBody(
        action="create_provisional_distributor",
        candidate_ids=[3],
        confirm_for_suspicious_distributor_token=True,
    )
    assert b.confirm_for_suspicious_distributor_token is True


def test_effective_geo_prefers_explicit_over_fallback() -> None:
    from app.services.imports.dsi_bulk_provisional_customers_sync import _effective_geo_for_bulk

    er, ec = _effective_geo_for_bulk(
        None,
        None,
        None,
        None,
        fallback_region_id=99,
        fallback_channel_id=88,
        explicit_region_id=5,
        explicit_channel_id=6,
    )
    assert er == 5
    assert ec == 6
