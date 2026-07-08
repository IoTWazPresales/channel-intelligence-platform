"""CPOR v1 Unit 1 — model import smoke + customer-terms CRUD contract tests.

No DB writes to cip. Terms CRUD uses the same mocked AsyncSession pattern as
test_commercial_planner_api (standard fixture for this suite).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app

client = TestClient(app)


def test_cpor_models_import_smoke():
    from app.models.cpor import CporCase, CporCaseEvent, CporCaseLine, CporClaimEvidenceLine
    from app.services.cpor.promotion_type_vocab import (
        CPOR_CASE_STATUS_SET,
        CPOR_PROMOTION_TYPES,
    )

    assert CporCase.__tablename__ == "cpor_case"
    assert CporCaseLine.__tablename__ == "cpor_case_line"
    assert CporCaseEvent.__tablename__ == "cpor_case_event"
    assert CporClaimEvidenceLine.__tablename__ == "cpor_claim_evidence_line"
    assert "case_code" in CporCase.__table__.c
    assert "source_key" in CporClaimEvidenceLine.__table__.c
    assert "dealer_price" in CporCaseLine.__table__.c
    assert "cancelled" in CPOR_CASE_STATUS_SET
    assert "Sell out PP" in CPOR_PROMOTION_TYPES


def test_cpor_models_exported_from_app_models():
    from app.models import CporCase, CporCaseEvent, CporCaseLine, CporClaimEvidenceLine

    assert CporCase is not None
    assert CporCaseLine is not None
    assert CporCaseEvent is not None
    assert CporClaimEvidenceLine is not None


def test_create_customer_term_happy_path():
    from app.models.commercial_planner import CommercialCustomerTerm
    from app.models.dimensions import DimCustomer

    cust = SimpleNamespace(id=7, code="C7", name="Customer Seven")

    async def fake_db():
        sess = MagicMock()

        async def _get(model, pk):
            if model is DimCustomer and pk == 7:
                return cust
            return None

        sess.get = AsyncMock(side_effect=_get)
        dup_res = MagicMock()
        dup_res.scalars = MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        sess.execute = AsyncMock(return_value=dup_res)
        sess.add = MagicMock()
        sess.commit = AsyncMock()

        async def _refresh(row):
            row.id = 99
            row.customer_id = 7
            row.customer_margin_pct = 0.12
            row.customer_rebate_pct = 0.03

        sess.refresh = AsyncMock(side_effect=_refresh)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        r = client.post(
            "/api/v1/commercial-planner/customer-terms",
            json={"customer_id": 7, "customer_margin_pct": 0.12, "customer_rebate_pct": 0.03},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["customer_id"] == 7
        assert body["customer_code"] == "C7"
        assert body["customer_margin_pct"] == 0.12
    finally:
        app.dependency_overrides.clear()


def test_patch_customer_term_happy_path():
    from app.models.commercial_planner import CommercialCustomerTerm
    from app.models.dimensions import DimCustomer

    term = SimpleNamespace(
        id=5,
        customer_id=9,
        customer_margin_pct=0.10,
        customer_rebate_pct=0.02,
    )
    cust = SimpleNamespace(id=9, code="C9", name="Customer Nine")

    async def fake_db():
        sess = MagicMock()

        async def _get(model, pk):
            if model is CommercialCustomerTerm and pk == 5:
                return term
            if model is DimCustomer and pk == 9:
                return cust
            return None

        sess.get = AsyncMock(side_effect=_get)
        sess.commit = AsyncMock()
        sess.refresh = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        r = client.patch(
            "/api/v1/commercial-planner/customer-terms/5",
            json={"customer_margin_pct": 0.15, "customer_rebate_pct": 0.02},
        )
        assert r.status_code == 200
        assert r.json()["customer_margin_pct"] == 0.15
        assert term.customer_margin_pct == 0.15
    finally:
        app.dependency_overrides.clear()


def test_list_customer_terms_returns_rows():
    term = SimpleNamespace(id=1, customer_id=2, customer_margin_pct=0.11, customer_rebate_pct=0.02)
    fake_row = (term, "C2", "Cust Two")

    async def fake_db():
        sess = MagicMock()
        res = MagicMock()
        res.all = MagicMock(return_value=[fake_row])
        sess.execute = AsyncMock(return_value=res)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        r = client.get("/api/v1/commercial-planner/customer-terms")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["customer_code"] == "C2"
    finally:
        app.dependency_overrides.clear()
