"""CST steward list pagination — envelope + limit/offset (no cip)."""

from __future__ import annotations

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


class _ScalarList:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


@pytest.fixture
def client():
    return TestClient(app)


def _cust(i: int, name: str | None = None):
    return SimpleNamespace(
        id=i,
        code=f"C{i:03d}",
        name=name or f"Customer {i:03d}",
        is_key_account=i % 2 == 0,
    )


def test_key_accounts_envelope_and_offset_window(client: TestClient):
    customers = [_cust(i) for i in range(1, 6)]
    pairs = [(c, None) for c in customers]

    session = MagicMock()
    session.scalar.return_value = 5
    session.execute.return_value = _ExecResult(pairs[2:4])  # offset 2 limit 2
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    with patch("app.api.v1.endpoints.cst_steward.SessionLocal", return_value=session):
        res = client.get("/api/v1/cst-steward/key-accounts?limit=2&offset=2")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["items"][0]["customer_id"] == 3
    assert body["items"][1]["customer_id"] == 4


def test_key_accounts_limit_ceiling_rejected(client: TestClient):
    res = client.get("/api/v1/cst-steward/key-accounts?limit=501")
    assert res.status_code == 422


def test_key_accounts_total_independent_of_page(client: TestClient):
    session = MagicMock()
    session.scalar.return_value = 42
    session.execute.return_value = _ExecResult([])
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    with patch("app.api.v1.endpoints.cst_steward.SessionLocal", return_value=session):
        res = client.get("/api/v1/cst-steward/key-accounts?limit=10&offset=30")
    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 42}


def test_article_aliases_envelope_and_offset(client: TestClient):
    aliases = [
        SimpleNamespace(
            id=i,
            customer_id=1,
            product_id=2,
            article_no_normalized=f"art-{i}",
            status="proposed",
            evidence_json=None,
            updated_at=None,
        )
        for i in (10, 9)
    ]
    session = MagicMock()
    session.scalar.return_value = 2
    session.scalars.side_effect = [
        _ScalarList(aliases),  # page rows
        _ScalarList([SimpleNamespace(id=1, code="C1", name="Cust")]),  # customers
        _ScalarList([SimpleNamespace(id=2, sku="SKU", name="Prod")]),  # products
    ]
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    with patch("app.api.v1.endpoints.cst_steward.SessionLocal", return_value=session):
        res = client.get("/api/v1/cst-steward/article-aliases?status=proposed&limit=2&offset=0")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["items"][0]["id"] == 10
