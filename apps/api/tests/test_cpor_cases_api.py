"""CPOR U3 — lifecycle + API contract tests (mocked SessionLocal; no cip)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.cpor.lifecycle import allowed_next, can_transition
from app.services.cpor.waterfall import compute_dealer_price, quantize_money

client = TestClient(app)


def test_lifecycle_legal_and_illegal():
    assert can_transition("draft", "propose")
    assert can_transition("proposed", "approve")
    assert can_transition("proposed", "reject")
    assert can_transition("rejected", "resend")
    assert can_transition("approved", "activate")
    assert not can_transition("draft", "approve")
    assert not can_transition("settled", "cancel")
    assert "proposed" in allowed_next("draft")


def test_workbook_dealer_still_10347_via_u2():
    assert quantize_money(compute_dealer_price("13999", "0.15", "0.15")) == Decimal("10347.09")


def test_meta_promotion_types():
    r = client.get("/api/v1/cpor/meta/promotion-types")
    assert r.status_code == 200
    assert "Sell out PP" in r.json()["promotion_types"]


def test_meta_lifecycle():
    r = client.get("/api/v1/cpor/meta/lifecycle")
    assert r.status_code == 200
    assert "draft" in r.json()["statuses"]
    assert r.json()["actions"]["propose"] == "proposed"


def test_create_case_mocked():
    cust = SimpleNamespace(id=1, code="C1", name="Cust")

    case = SimpleNamespace(
        id=10,
        case_code="C26C00001",
        case_name=None,
        customer_id=1,
        promotion_type="Sell out PP",
        window_start=date(2026, 1, 1),
        window_end=date(2026, 1, 31),
        status="draft",
        roe_snapshot=None,
        currency_code="ZAR",
        channel="reseller",
        notes=None,
        created_by="warren",
        export_version=1,
        workflow_status="draft",
        last_comment=None,
        submitted_at=None,
        decided_at=None,
        decided_by=None,
        superseded_by_case_id=None,
        created_at=None,
    )

    session = MagicMock()
    session.get = MagicMock(return_value=cust)
    session.scalar = MagicMock(side_effect=[0, None])  # count then uniqueness
    session.add = MagicMock()
    session.flush = MagicMock(side_effect=lambda: setattr(case, "id", 10))
    session.commit = MagicMock()
    session.refresh = MagicMock()

    # When create assigns fields onto CporCase(), capture via side_effect on constructor is hard;
    # instead patch CporCase to return our case object.
    with patch("app.api.v1.endpoints.cpor_cases.SessionLocal") as SL:
        SL.return_value.__enter__.return_value = session
        SL.return_value.__exit__.return_value = None
        with patch("app.api.v1.endpoints.cpor_cases.CporCase", return_value=case):
            with patch("app.api.v1.endpoints.cpor_cases._record_event"):
                with patch("app.api.v1.endpoints.cpor_cases.apply_create_fx"):
                    r = client.post(
                    "/api/v1/cpor/cases",
                    json={
                        "customer_id": 1,
                        "promotion_type": "Sell out PP",
                        "window_start": "2026-01-01",
                        "window_end": "2026-01-31",
                        "case_code": "C26C00001",
                    },
                    headers={"X-User-Id": "warren"},
                )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["case_code"] == "C26C00001"
    assert body["status"] == "draft"
    assert body["allowed_next"] == ["cancelled", "proposed"]


def test_transition_illegal_returns_409():
    case = SimpleNamespace(
        id=10,
        status="draft",
        customer_id=1,
        case_code="X",
        case_name=None,
        promotion_type="Sell out PP",
        window_start=date(2026, 1, 1),
        window_end=date(2026, 1, 7),
        roe_snapshot=None,
        currency_code="ZAR",
        channel="reseller",
        notes=None,
        created_by=None,
        export_version=1,
        workflow_status="draft",
        last_comment=None,
        submitted_at=None,
        decided_at=None,
        decided_by=None,
        superseded_by_case_id=None,
        created_at=None,
    )
    session = MagicMock()
    session.get = MagicMock(return_value=case)
    with patch("app.api.v1.endpoints.cpor_cases.SessionLocal") as SL:
        SL.return_value.__enter__.return_value = session
        SL.return_value.__exit__.return_value = None
        r = client.post("/api/v1/cpor/cases/10/transition", json={"action": "approve"})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["current"] == "draft"


def test_reject_requires_comment():
    case = SimpleNamespace(id=10, status="proposed", customer_id=1)
    session = MagicMock()
    session.get = MagicMock(return_value=case)
    with patch("app.api.v1.endpoints.cpor_cases.SessionLocal") as SL:
        SL.return_value.__enter__.return_value = session
        SL.return_value.__exit__.return_value = None
        r = client.post("/api/v1/cpor/cases/10/transition", json={"action": "reject"})
    assert r.status_code == 400


def test_case_line_aggregates_use_ttl_support_not_owed():
    """I1: list support is the line waterfall sum, never payment-recon owed."""
    from app.api.v1.endpoints.cpor_cases import _case_line_aggregates

    session = MagicMock()
    session.execute.return_value.all.return_value = [
        (41, 4, 1820, 368_640, None),
    ]
    out = _case_line_aggregates(session, [41, 99])
    assert out[41]["line_count"] == 4
    assert out[41]["estimate_qty_sum"] == 1820.0
    assert out[41]["ttl_support"] == 368_640.0
    assert 99 not in out
    empty = _case_line_aggregates(session, [])
    assert empty == {}


def test_no_delete_route():
    # FastAPI should 405/404 for DELETE — no hard-delete route registered
    r = client.delete("/api/v1/cpor/cases/1")
    assert r.status_code in (404, 405, 422)
