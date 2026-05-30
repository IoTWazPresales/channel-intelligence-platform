"""Customer bulk delete must block DSI staging FKs (preview + confirm 409, never 500)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import pytest

from app.api.deps import get_db
from app.main import app
from app.services.customer_usage import customer_hard_reference_breakdown_batch
from app.services.master_entity_bulk_delete import MasterBulkDeleteIntegrityError

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_customer_batch_breakdown_includes_dsi_staging_label():
    from app.models.import_distributor_si import ImportDistributorSiStagingLine

    db = MagicMock()
    open_result = MagicMock()
    open_result.scalars.return_value.all.return_value = []

    async def fake_batch(_db, col, ids):
        if col is ImportDistributorSiStagingLine.resolved_customer_id:
            return {ids[0]: 2}
        return {}

    async def _run():
        db.execute = AsyncMock(return_value=open_result)
        with patch(
            "app.services.customer_usage.batch_counts_for_column",
            new=AsyncMock(side_effect=fake_batch),
        ), patch(
            "app.services.customer_usage._batch_mapping_candidate_counts",
            new=AsyncMock(return_value={}),
        ):
            result = await customer_hard_reference_breakdown_batch(db, [99])
        labels = [r["label"] for r in result.get(99, [])]
        assert "DSI import staging (resolved customer)" in labels

    asyncio.run(_run())


def test_bulk_delete_confirm_staging_blocked_returns_409_not_500():
    async def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db

    with patch(
        "app.api.v1.endpoints.customers.confirm_master_bulk_delete",
        new=AsyncMock(
            side_effect=MasterBulkDeleteIntegrityError(
                "blocked",
                [{"label": "DSI import staging (resolved customer)", "count": 1}],
            )
        ),
    ):
        r = client.post(
            "/api/v1/customers/bulk-delete-confirm",
            json={"entity_ids": [2], "deletable_ids": [2]},
        )

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["references"][0]["label"] == "DSI import staging (resolved customer)"


def test_bulk_delete_confirm_with_deletable_ids_skips_full_preview():
    async def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db
    confirm = AsyncMock(
        return_value={
            "entity_type": "customers",
            "deleted_ids": [1],
            "deleted_count": 1,
            "skipped_blocked_count": 0,
            "skipped_blocked_ids": [],
        }
    )
    preview = AsyncMock()

    with patch("app.api.v1.endpoints.customers.confirm_master_bulk_delete", new=confirm), patch(
        "app.api.v1.endpoints.customers.preview_master_bulk_delete", new=preview
    ):
        r = client.post(
            "/api/v1/customers/bulk-delete-confirm",
            json={"entity_ids": [1, 2], "deletable_ids": [1]},
        )

    assert r.status_code == 200
    confirm.assert_awaited_once()
    assert confirm.await_args.kwargs.get("deletable_ids") == [1]
    preview.assert_not_called()
