"""Product DSI maintenance endpoints (dependency detail + clear facts)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.product_dsi_maintenance import CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_dsi_detail_requires_admin_header():
    r = client.get(
        "/api/v1/products/id/1/dependencies/distributor-inventory",
        headers={"X-User-Role": "viewer"},
    )
    assert r.status_code == 403
    assert r.json().get("detail") == "Insufficient role"


def test_dsi_clear_requires_admin_header():
    r = client.request(
        "DELETE",
        "/api/v1/products/id/1/dependencies/distributor-inventory",
        headers={"X-User-Role": "viewer"},
        json={"confirm": CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT},
    )
    assert r.status_code == 403
    assert r.json().get("detail") == "Insufficient role"


def test_dsi_clear_rejects_wrong_confirm():
    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=MagicMock(id=3, sku="SKU-3"))
        yield sess

    app.dependency_overrides[get_db] = fake_db

    r = client.request(
        "DELETE",
        "/api/v1/products/id/3/dependencies/distributor-inventory",
        headers={"X-User-Role": "admin"},
        json={"confirm": "WRONG"},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["expected_confirm"] == CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT


def test_dsi_clear_deletes_rows_and_commits():
    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=MagicMock(id=7, sku="SKU-7"))
        sess.execute = AsyncMock(side_effect=[MagicMock(rowcount=2), MagicMock(rowcount=1)])
        sess.commit = AsyncMock()
        sess.rollback = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db

    with patch(
        "app.api.v1.endpoints.products.clear_dsi_facts_for_product",
        new=AsyncMock(return_value={"fact_inventory_distributor_deleted": 2, "fact_sales_sellout_deleted": 1}),
    ) as clear_mock:
        r = client.request(
            "DELETE",
            "/api/v1/products/id/7/dependencies/distributor-inventory",
            headers={"X-User-Role": "admin"},
            json={"confirm": CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["product_id"] == 7
    assert body["deleted"]["fact_inventory_distributor_deleted"] == 2
    clear_mock.assert_awaited_once()


def test_dsi_detail_404_missing_product():
    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=None)
        yield sess

    app.dependency_overrides[get_db] = fake_db

    r = client.get(
        "/api/v1/products/id/404/dependencies/distributor-inventory",
        headers={"X-User-Role": "admin"},
    )
    assert r.status_code == 404


def test_delete_product_still_blocked_when_dsi_refs_present():
    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=MagicMock(id=9, sku="SKU-BLOCKED"))
        yield sess

    app.dependency_overrides[get_db] = fake_db

    cleanup = AsyncMock()
    with patch(
        "app.api.v1.endpoints.products.product_hard_reference_breakdown",
        new=AsyncMock(
            return_value=[
                {"label": "Distributor inventory", "count": 4},
                {"label": "Sell-out", "count": 1},
            ]
        ),
    ), patch("app.api.v1.endpoints.products.cleanup_soft_product_references", cleanup):
        r = client.delete("/api/v1/products/id/9", headers={"X-User-Role": "admin"})

    cleanup.assert_not_called()
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["references"][0]["label"] == "Distributor inventory"


def test_delete_product_204_after_dsi_refs_cleared():
    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=MagicMock(id=11, sku="SKU-OK"))
        sess.delete = AsyncMock()
        sess.commit = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db

    cleanup = AsyncMock()
    with patch(
        "app.api.v1.endpoints.products.product_hard_reference_breakdown",
        new=AsyncMock(return_value=[]),
    ), patch("app.api.v1.endpoints.products.cleanup_soft_product_references", cleanup):
        r = client.delete("/api/v1/products/id/11", headers={"X-User-Role": "admin"})

    cleanup.assert_awaited_once()
    assert r.status_code == 204
