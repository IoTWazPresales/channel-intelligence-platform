"""Master bulk delete preview/confirm for products and customers."""

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


def test_products_bulk_delete_preview():
    async def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db

    preview_payload = {
        "entity_type": "products",
        "entity_ids": [1, 2],
        "missing_entity_ids": [],
        "rows": [
            {"id": 1, "missing": False, "label": "SKU-1", "references": [], "blocked": False},
            {
                "id": 2,
                "missing": False,
                "label": "SKU-2",
                "references": [{"label": "Sell-out", "count": 1}],
                "blocked": True,
            },
        ],
        "blocked_count": 1,
        "deletable_count": 1,
        "deletable_ids": [1],
    }
    with patch(
        "app.api.v1.endpoints.products.preview_master_bulk_delete",
        new=AsyncMock(return_value=preview_payload),
    ):
        r = client.post("/api/v1/products/bulk-delete-preview", json={"entity_ids": [1, 2]})

    assert r.status_code == 200
    assert r.json()["blocked_count"] == 1
    assert r.json()["deletable_ids"] == [1]
