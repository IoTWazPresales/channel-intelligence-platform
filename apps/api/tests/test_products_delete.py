"""DELETE /products/{id} conflict shape and success path (mocked DB + usage)."""

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


def test_delete_product_409_detail_shape():
    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=MagicMock(id=9, sku="SKU-BLOCKED"))
        yield sess

    app.dependency_overrides[get_db] = fake_db

    cleanup = AsyncMock()
    with patch(
        "app.api.v1.endpoints.products.product_hard_reference_breakdown",
        new=AsyncMock(return_value=[{"label": "Sell-out", "count": 3}]),
    ), patch("app.api.v1.endpoints.products.cleanup_soft_product_references", cleanup):
        r = client.delete("/api/v1/products/9")

    cleanup.assert_not_called()
    assert r.status_code == 409
    body = r.json()
    assert "detail" in body
    d = body["detail"]
    assert isinstance(d, dict)
    assert "references" in d
    assert d["references"] == [{"label": "Sell-out", "count": 3}]
    assert "message" in d


def test_delete_product_204_when_no_references():
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
        r = client.delete("/api/v1/products/id/11")

    cleanup.assert_awaited_once()
    assert r.status_code == 204
    assert r.content == b""


def test_delete_product_404_when_missing():
    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=None)
        yield sess

    app.dependency_overrides[get_db] = fake_db

    r = client.delete("/api/v1/products/999")
    assert r.status_code == 404
