"""PR #105 Round 1: account routing and shared-stock adaptation, with no database."""

from contextlib import nullcontext
from datetime import date
from unittest.mock import Mock

import pytest

import app.services.listing_capture.stock_not_listed as worklist


def test_stock_uses_the_shared_reader_with_explicit_tenant_and_accounts(monkeypatch):
    session = Mock()
    positions = {
        (3, 81): {"date": date(2026, 11, 9), "soh": 5.0},
        (9, 81): {"date": date(2026, 11, 2), "soh": 7.0},
        (3, 82): {"date": date(2026, 11, 9), "soh": 0.0},
        (3, 83): {"date": date(2026, 11, 9), "soh": -2.0},
    }
    reader = Mock(return_value=(positions, {3: date(2026, 11, 9), 9: date(2026, 11, 2)}))
    monkeypatch.setattr(worklist, "load_stock_positions", reader)

    assert worklist._latest_stock(session, "unit-tenant", [3, 9]) == {
        (3, 81): (date(2026, 11, 9), 5.0),
        (9, 81): (date(2026, 11, 2), 7.0),
    }
    reader.assert_called_once()
    actual_session, filters, as_of = reader.call_args.args
    assert actual_session is session
    assert filters.tenant_id == "unit-tenant"
    assert filters.customer_ids == [3, 9]
    assert filters.product_ids == [] and filters.sites == []
    assert filters.date_from == date.min and filters.date_to == as_of == date.max
    # Adaptation must not prune or alter the shared helper's returned positions.
    assert positions[(3, 82)]["soh"] == 0.0
    assert positions[(3, 83)]["soh"] == -2.0
    session.execute.assert_not_called()


def test_no_eligible_accounts_never_becomes_an_unfiltered_stock_read(monkeypatch):
    reader = Mock(side_effect=AssertionError("empty accounts must not read all tenant stock"))
    monkeypatch.setattr(worklist, "load_stock_positions", reader)
    assert worklist._latest_stock(Mock(), "unit-tenant", []) == {}
    reader.assert_not_called()


def test_shared_reader_failure_remains_data_unavailable(monkeypatch):
    session = Mock()
    session.begin_nested.return_value = nullcontext()
    monkeypatch.setattr(worklist, "_reporting_customers", lambda *_args: {3: ("c3", "Account")})
    monkeypatch.setattr(worklist, "load_stock_positions", Mock(side_effect=RuntimeError("read failed")))

    out = worklist.stock_not_listed(session, "unit-tenant", customer_id=3)
    assert out["data_unavailable"] is True and out["rows"] == []
    session.commit.assert_not_called()


@pytest.mark.parametrize("customer_id", [None, 9])
def test_route_forwards_account_filter_limit_and_authenticated_tenant(monkeypatch, customer_id):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.endpoints import listing_capture as endpoint
    from app.core.security import get_current_user

    session = Mock()
    monkeypatch.setattr(endpoint, "SessionLocal", lambda: nullcontext(session))
    reader = Mock(return_value={"data_unavailable": False, "rows": [], "total": 0})
    monkeypatch.setattr(worklist, "stock_not_listed", reader)
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/listing-capture")
    app.dependency_overrides[get_current_user] = lambda: {"tenant_id": "authenticated-tenant"}
    params = {"limit": 17}
    if customer_id is not None:
        params["customer_id"] = customer_id
    with TestClient(app) as client:
        response = client.get("/listing-capture/stock-not-listed", params=params)

    assert response.status_code == 200
    reader.assert_called_once_with(
        session, "authenticated-tenant", customer_id=customer_id, limit=17
    )
    session.commit.assert_not_called()
