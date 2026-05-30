"""DELETE /customers/{id} conflict shape and references."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_delete_customer_409_detail_shape():
    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=MagicMock(id=3, code="CUST-X"))
        yield sess

    app.dependency_overrides[get_db] = fake_db

    with patch(
        "app.api.v1.endpoints.customers.customer_hard_reference_breakdown",
        new=AsyncMock(return_value=[{"label": "Sell-out", "count": 2}]),
    ), patch("app.api.v1.endpoints.customers.cleanup_soft_customer_references", new=AsyncMock()), patch(
        "app.api.v1.endpoints.customers.delete_customer_children", new=AsyncMock()
    ):
        r = client.delete("/api/v1/customers/3")

    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["references"] == [{"label": "Sell-out", "count": 2}]


def test_get_customer_references():
    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=MagicMock(id=5, code="CUST-5"))
        yield sess

    app.dependency_overrides[get_db] = fake_db

    with patch(
        "app.api.v1.endpoints.customers.customer_hard_reference_breakdown",
        new=AsyncMock(return_value=[{"label": "Forecasts", "count": 1}]),
    ):
        r = client.get("/api/v1/customers/references?customer_id=5")

    assert r.status_code == 200
    body = r.json()
    assert body["customer_code"] == "CUST-5"
    assert body["blocked"] is True
    assert body["references"][0]["label"] == "Forecasts"
