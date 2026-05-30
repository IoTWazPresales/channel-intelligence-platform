"""Master bulk delete preview/confirm for products and customers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_db
from app.main import app
from app.services.master_entity_bulk_delete import (
    MasterBulkDeleteIntegrityError,
    confirm_master_bulk_delete,
    preview_master_bulk_delete,
)

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


def test_confirm_with_deletable_ids_does_not_call_preview():
    db = MagicMock()
    db.get = AsyncMock(return_value=MagicMock(code="CUST-1"))
    db.commit = AsyncMock()

    async def _run():
        with patch(
            "app.services.master_entity_bulk_delete._batch_refs",
            new=AsyncMock(return_value={1: []}),
        ), patch(
            "app.services.master_entity_bulk_delete._delete_one",
            new=AsyncMock(return_value=True),
        ), patch(
            "app.services.master_entity_bulk_delete.preview_master_bulk_delete",
            new=AsyncMock(),
        ) as preview_mock:
            result = await confirm_master_bulk_delete(
                db, "customers", [1, 2], deletable_ids=[1]
            )
        preview_mock.assert_not_called()
        assert result["deleted_ids"] == [1]

    asyncio.run(_run())


def test_confirm_integrity_error_raises_structured_conflict():
    db = MagicMock()
    db.get = AsyncMock(return_value=MagicMock(code="CUST-1"))
    db.commit = AsyncMock(side_effect=IntegrityError("fk", {}, Exception()))
    db.rollback = AsyncMock()

    async def _run():
        with patch(
            "app.services.master_entity_bulk_delete._batch_refs",
            new=AsyncMock(return_value={1: []}),
        ), patch(
            "app.services.master_entity_bulk_delete._delete_one",
            new=AsyncMock(return_value=True),
        ):
            with pytest.raises(MasterBulkDeleteIntegrityError) as exc_info:
                await confirm_master_bulk_delete(db, "customers", [1], deletable_ids=[1])
        assert exc_info.value.references
        db.rollback.assert_awaited_once()

    asyncio.run(_run())


def test_preview_uses_batch_breakdown():
    db = MagicMock()

    async def _run():
        with patch(
            "app.services.master_entity_bulk_delete._batch_refs",
            new=AsyncMock(return_value={5: [{"label": "Sell-out", "count": 2}]}),
        ), patch(
            "app.services.master_entity_bulk_delete._entity_label",
            new=AsyncMock(return_value="CUST-5"),
        ):
            payload = await preview_master_bulk_delete(db, "customers", [5])
        assert payload["blocked_count"] == 1
        assert payload["deletable_ids"] == []

    asyncio.run(_run())
