"""Master bulk delete preview/confirm for products and customers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app

client = TestClient(app)


def test_customers_bulk_delete_preview_route_accepts_post():
    """Literal /bulk-delete-preview must be registered for POST (not shadowed by /{customer_id})."""
    found = False
    for route in app.routes:
        if getattr(route, "path", None) != "/api/v1/customers/bulk-delete-preview":
            continue
        methods = getattr(route, "methods", None) or set()
        if "POST" in methods:
            found = True
            break
    assert found


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


@pytest.mark.parametrize(
    ("path", "patch_target", "kind"),
    [
        (
            "/api/v1/catalog/channels/bulk-delete-preview",
            "app.api.v1.endpoints.catalog.preview_master_bulk_delete",
            "channels",
        ),
        (
            "/api/v1/catalog/regions/bulk-delete-preview",
            "app.api.v1.endpoints.catalog.preview_master_bulk_delete",
            "regions",
        ),
        (
            "/api/v1/distributors/bulk-delete-preview",
            "app.api.v1.endpoints.distributors.preview_master_bulk_delete",
            "distributors",
        ),
    ],
)
def test_catalog_and_distributor_bulk_delete_preview(path: str, patch_target: str, kind: str):
    async def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db

    preview_payload = {
        "entity_type": kind,
        "entity_ids": [10],
        "missing_entity_ids": [],
        "rows": [{"id": 10, "missing": False, "label": "X", "references": [], "blocked": False}],
        "blocked_count": 0,
        "deletable_count": 1,
        "deletable_ids": [10],
    }
    with patch(patch_target, new=AsyncMock(return_value=preview_payload)):
        r = client.post(path, json={"entity_ids": [10]})

    assert r.status_code == 200
    assert r.json()["entity_type"] == kind
    assert r.json()["deletable_ids"] == [10]
