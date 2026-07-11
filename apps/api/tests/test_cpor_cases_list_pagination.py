"""CPOR case list pagination — envelope + limit/offset (no cip)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


class _ExecResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.fixture
def client():
    return TestClient(app)


def _case(i: int):
    return SimpleNamespace(
        id=i,
        case_code=f"C26C{i:05d}",
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


def _cust():
    return SimpleNamespace(id=1, code="C001", name="Customer 1")


def test_list_cases_envelope_and_offset_window(client: TestClient):
    cases = [_case(i) for i in range(1, 6)]
    cust = _cust()
    pairs = [(c, cust) for c in cases]

    session = MagicMock()
    session.scalar.return_value = 5
    session.execute.side_effect = [
        _ExecResult(pairs[2:4]),  # paginated cases
        _ExecResult([(3, 2, 100.0, 50.0), (4, 1, 200.0, None)]),  # line aggregates
    ]
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    with patch("app.api.v1.endpoints.cpor_cases.SessionLocal", return_value=session):
        res = client.get("/api/v1/cpor/cases?limit=2&offset=2")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["items"][0]["id"] == 3
    assert body["items"][0]["line_count"] == 2
    assert body["items"][0]["ttl_support_zar"] == 100.0
    assert body["items"][1]["id"] == 4
    assert body["items"][1]["line_count"] == 1
    assert "lines" not in body["items"][0]


def test_list_cases_limit_ceiling_rejected(client: TestClient):
    res = client.get("/api/v1/cpor/cases?limit=201")
    assert res.status_code == 422


def test_list_cases_total_independent_of_page(client: TestClient):
    session = MagicMock()
    session.scalar.return_value = 42
    session.execute.side_effect = [
        _ExecResult([]),
        _ExecResult([]),
    ]
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    with patch("app.api.v1.endpoints.cpor_cases.SessionLocal", return_value=session):
        res = client.get("/api/v1/cpor/cases?limit=10&offset=30")
    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 42}


def test_list_cases_unknown_status_rejected(client: TestClient):
    res = client.get("/api/v1/cpor/cases?status=not_a_status")
    assert res.status_code == 400
