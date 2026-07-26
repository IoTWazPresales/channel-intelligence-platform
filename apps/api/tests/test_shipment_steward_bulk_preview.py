"""Shipment steward bulk preview/apply validation (no database I/O)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError


def _customer_cand(**kwargs) -> SimpleNamespace:
    defaults = {
        "id": 10,
        "import_job_id": 1,
        "entity_type": "shipment_customer_token",
        "status": "needs_review",
        "row_count": 5,
        "total_units": 2.0,
        "total_reported_value": 100.0,
        "sample_raw_values": ["ACME LTD"],
        "context": {"source_tokens": ["ACME LTD"], "line_ids": [1, 2]},
        "match_reason": None,
        "suggested_entity_id": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _distributor_cand(**kwargs) -> SimpleNamespace:
    defaults = {
        "id": 20,
        "import_job_id": 1,
        "entity_type": "shipment_distributor",
        "status": "needs_review",
        "row_count": 3,
        "total_units": None,
        "total_reported_value": None,
        "sample_raw_values": ["DIST-A"],
        "context": {"line_ids": [9]},
        "match_reason": None,
        "suggested_entity_id": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_shipment_bulk_totals_helper() -> None:
    from app.services.imports.shipment_steward_bulk_preview import shipment_bulk_totals_from_rows

    rows = [
        {"ok": True, "row_count": 10, "total_units": 2.5, "total_reported_value": 100.0},
        {"ok": False, "row_count": 99},
        {"ok": True, "row_count": 3, "total_units": None, "total_reported_value": None},
    ]
    t = shipment_bulk_totals_from_rows(rows)
    assert t["ok_count"] == 2
    assert t["not_ok_count"] == 1
    assert t["staging_rows_affected"] == 13


def test_preview_ignore_ok() -> None:
    from app.services.imports.shipment_steward_bulk_preview import preview_reject_shipment_candidate

    pv = preview_reject_shipment_candidate(_customer_cand())
    assert pv["ok"] is True
    assert "steward_rejected" in pv["detail"]


def test_preview_ignore_terminal_skip() -> None:
    from app.services.imports.shipment_steward_bulk_preview import preview_reject_shipment_candidate

    pv = preview_reject_shipment_candidate(_customer_cand(status="steward_rejected"))
    assert pv["ok"] is False
    assert pv["skip_reason"] == "terminal_status"


def test_preview_map_customer_wrong_entity() -> None:
    from app.services.imports.shipment_steward_bulk_preview import preview_map_shipment_customer

    db = MagicMock()
    pv = preview_map_shipment_customer(db, _distributor_cand(), customer_id=1, raw_token=None)
    assert pv["ok"] is False
    assert pv["skip_reason"] == "wrong_entity_type"


def test_preview_map_customer_ok_mock_db() -> None:
    from unittest.mock import patch

    from app.services.imports.shipment_steward_bulk_preview import preview_map_shipment_customer

    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=1, code="C1", name="Customer One")
    with patch(
        "app.services.imports.shipment_steward_bulk_preview._verify_line_scope",
        return_value=None,
    ):
        pv = preview_map_shipment_customer(db, _customer_cand(), customer_id=1, raw_token=None)
    assert pv["ok"] is True
    assert pv["customer_id"] == 1


def test_shipment_bulk_body_ignore_ok() -> None:
    from app.api.v1.endpoints.shipment_evidence import ShipmentBulkStewardBody

    b = ShipmentBulkStewardBody(action="ignore", candidate_ids=[1, 2])
    assert b.action == "ignore"


def test_shipment_bulk_body_ignore_rejects_over_1000() -> None:
    from app.api.v1.endpoints.shipment_evidence import ShipmentBulkStewardBody

    with pytest.raises(ValidationError):
        ShipmentBulkStewardBody(action="ignore", candidate_ids=list(range(1, 1002)))


def test_shipment_bulk_body_map_customer_capped_at_200() -> None:
    from app.api.v1.endpoints.shipment_evidence import ShipmentBulkStewardBody

    with pytest.raises(ValidationError):
        ShipmentBulkStewardBody(action="map_customer", candidate_ids=list(range(1, 202)), customer_id=1)


def test_shipment_steward_bulk_apply_rejects_ignore() -> None:
    from fastapi import HTTPException

    from app.api.v1.endpoints.shipment_evidence import ShipmentBulkStewardBody, shipment_steward_bulk_apply

    async def _run() -> None:
        body = ShipmentBulkStewardBody(action="ignore", candidate_ids=[1, 2])
        try:
            await shipment_steward_bulk_apply(43, body)
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 400
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            assert detail.get("code") == "use_async_bulk_ignore"

    asyncio.run(_run())


def test_shipment_steward_bulk_apply_rejects_provisional_customer() -> None:
    from fastapi import HTTPException

    from app.api.v1.endpoints.shipment_evidence import ShipmentBulkStewardBody, shipment_steward_bulk_apply

    async def _run() -> None:
        body = ShipmentBulkStewardBody(action="create_provisional_customer", candidate_ids=[1])
        try:
            await shipment_steward_bulk_apply(43, body)
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 400
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            assert detail.get("code") == "use_async_bulk_provisional"

    asyncio.run(_run())


def test_shipment_bulk_ignore_payload_from_body() -> None:
    from app.api.v1.endpoints.shipment_evidence import (
        ShipmentBulkStewardBody,
        _shipment_bulk_ignore_payload_from_body,
    )

    b = ShipmentBulkStewardBody(action="ignore", candidate_ids=[1, 2], notes="nope")
    p = _shipment_bulk_ignore_payload_from_body(b)
    assert p == {"candidate_ids": [1, 2]}


def test_shipment_steward_bulk_preview_merges_candidate_meta() -> None:
    from app.api.v1.endpoints.shipment_evidence import ShipmentBulkStewardBody, shipment_steward_bulk_preview

    cand = _customer_cand(id=55)

    async def _run() -> dict:
        with patch("app.api.v1.endpoints.shipment_evidence.SessionLocal") as mock_local:
            session = MagicMock()
            mock_local.return_value.__enter__.return_value = session
            session.get.return_value = SimpleNamespace(template_slug="inbound_shipments")
            session.execute.return_value.scalars.return_value.all.return_value = [cand]
            body = ShipmentBulkStewardBody(action="ignore", candidate_ids=[55])
            return await shipment_steward_bulk_preview(1, body)

    out = asyncio.run(_run())
    assert out["import_job_id"] == 1
    row = out["results"][0]
    assert row["candidate_id"] == 55
    assert row["entity_type"] == "shipment_customer_token"
    assert row["row_count"] == 5
    assert row["ok"] is True
