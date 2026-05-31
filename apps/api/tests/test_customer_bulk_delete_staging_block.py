"""Customer bulk delete: DSI staging blockers, bounded preview queries, confirm 409."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import union_all
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError

import pytest

from app.api.deps import get_db
from app.api.v1.master_bulk_delete_http import raise_bulk_delete_http_error
from app.main import app
from app.models.import_distributor_si import ImportDistributorSiStagingLine
from app.services.customer_usage import (
    DSI_STAGING_REF_LABEL,
    _SPECS,
    customer_hard_reference_breakdown_batch,
)
from app.services.master_entity_bulk_delete import (
    MasterBulkDeleteIntegrityError,
    MasterBulkDeleteTimeoutError,
    confirm_master_bulk_delete,
    is_db_integrity_error,
    preview_master_bulk_delete,
)
from app.services.master_usage_batch import batch_counts_multi_table, count_subquery_for_columns

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_customer_specs_include_dsi_staging_table_column():
    """import_distributor_si_staging_line.resolved_customer_id must be in the UNION ALL specs."""
    labels = {label for label, _ in _SPECS}
    assert DSI_STAGING_REF_LABEL in labels
    cols = [col for label, col in _SPECS if label == DSI_STAGING_REF_LABEL]
    assert len(cols) == 1
    assert cols[0] is ImportDistributorSiStagingLine.resolved_customer_id


def test_customer_union_sql_includes_dsi_staging_table():
    ids = [2]
    subqueries = [
        count_subquery_for_columns(label, [col], ids) for label, col in _SPECS if label == DSI_STAGING_REF_LABEL
    ]
    sql = str(
        union_all(*subqueries).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "import_distributor_si_staging_line" in sql
    assert "resolved_customer_id" in sql


def test_customer_batch_breakdown_surfaces_dsi_staging_from_union():
    db = MagicMock()

    async def fake_multi_table(_db, subqueries, entity_ids):
        assert len(subqueries) >= 20
        return {2: [{"label": DSI_STAGING_REF_LABEL, "count": 11}]}

    async def _run():
        with patch(
            "app.services.customer_usage.batch_counts_multi_table",
            new=AsyncMock(side_effect=fake_multi_table),
        ):
            result = await customer_hard_reference_breakdown_batch(db, [2])
        assert result[2][0]["count"] == 11

    asyncio.run(_run())


def test_customer_breakdown_single_db_execute():
    """Reference breakdown must issue exactly one UNION ALL execute (not per-table loop)."""
    db = MagicMock()
    execute_count = 0

    async def track_execute(*_args, **_kwargs):
        nonlocal execute_count
        execute_count += 1
        result = MagicMock()
        mapping = {DSI_STAGING_REF_LABEL: DSI_STAGING_REF_LABEL, "entity_id": 2, "cnt": 11}
        row = MagicMock()
        row._mapping = mapping
        result.all.return_value = [row]
        return result

    db.execute = track_execute

    async def _run():
        result = await customer_hard_reference_breakdown_batch(db, [2])
        assert execute_count == 1
        assert result[2][0]["count"] == 11

    asyncio.run(_run())


def test_preview_calls_batch_refs_once_for_six_customers():
    """Full preview must call batched reference check once for all ids."""
    db = MagicMock()
    batch_refs = AsyncMock(return_value={i: [] for i in range(1, 7)})
    batch_labels = AsyncMock(return_value={i: f"CUST-{i}" for i in range(1, 7)})

    async def _run():
        with patch(
            "app.services.master_entity_bulk_delete._batch_refs",
            new=batch_refs,
        ), patch(
            "app.services.master_entity_bulk_delete._batch_entity_labels",
            new=batch_labels,
        ):
            await preview_master_bulk_delete(db, "customers", [1, 2, 3, 4, 5, 6])
        batch_refs.assert_awaited_once()
        assert batch_refs.await_args[0][2] == [1, 2, 3, 4, 5, 6]
        batch_labels.assert_awaited_once()

    asyncio.run(_run())


def test_preview_blocks_customer_with_dsi_staging_refs():
    db = MagicMock()

    async def _run():
        with patch(
            "app.services.master_entity_bulk_delete._batch_refs",
            new=AsyncMock(return_value={2: [{"label": DSI_STAGING_REF_LABEL, "count": 11}]}),
        ), patch(
            "app.services.master_entity_bulk_delete._batch_entity_labels",
            new=AsyncMock(return_value={2: "CUST-1001"}),
        ):
            payload = await preview_master_bulk_delete(db, "customers", [2])
        assert 2 not in payload["deletable_ids"]
        assert payload["blocked_count"] == 1
        row = next(r for r in payload["rows"] if r["id"] == 2)
        assert row["references"][0]["label"] == DSI_STAGING_REF_LABEL

    asyncio.run(_run())


def test_confirm_rechecks_refs_when_deletable_ids_provided():
    db = MagicMock()
    db.commit = AsyncMock()

    async def _run():
        with patch(
            "app.services.master_entity_bulk_delete._batch_entity_labels",
            new=AsyncMock(return_value={2: "CUST-1001"}),
        ), patch(
            "app.services.master_entity_bulk_delete._batch_refs",
            new=AsyncMock(return_value={2: [{"label": DSI_STAGING_REF_LABEL, "count": 11}]}),
        ), patch(
            "app.services.master_entity_bulk_delete._delete_one",
            new=AsyncMock(),
        ) as delete_mock, patch(
            "app.services.master_entity_bulk_delete.preview_master_bulk_delete",
            new=AsyncMock(),
        ) as preview_mock:
            with pytest.raises(MasterBulkDeleteIntegrityError) as exc_info:
                await confirm_master_bulk_delete(db, "customers", [2], deletable_ids=[2])
        preview_mock.assert_not_called()
        delete_mock.assert_not_called()
        assert exc_info.value.references[0]["label"] == DSI_STAGING_REF_LABEL

    asyncio.run(_run())


def test_confirm_integrity_error_maps_to_409_via_http_helper():
    exc = MasterBulkDeleteIntegrityError(
        "blocked",
        [{"label": DSI_STAGING_REF_LABEL, "count": 11}],
    )
    with pytest.raises(HTTPException) as raised:
        raise_bulk_delete_http_error(exc, entity_label="customer")
    assert raised.value.status_code == 409
    assert raised.value.detail["references"][0]["count"] == 11


def test_is_db_integrity_error_detects_pg_fk_sqlstate():
    class Orig:
        sqlstate = "23503"

    assert is_db_integrity_error(DBAPIError("stmt", {}, Orig()))


def test_confirm_commit_integrity_raises_structured_conflict():
    db = MagicMock()
    db.commit = AsyncMock(side_effect=IntegrityError("fk", {}, Exception()))
    db.rollback = AsyncMock()

    async def _run():
        with patch(
            "app.services.master_entity_bulk_delete._batch_entity_labels",
            new=AsyncMock(return_value={1: "CUST-1"}),
        ), patch(
            "app.services.master_entity_bulk_delete._batch_refs",
            new=AsyncMock(side_effect=[
                {1: []},
                {1: [{"label": "Sell-out", "count": 3}]},
            ]),
        ), patch(
            "app.services.master_entity_bulk_delete._delete_one",
            new=AsyncMock(return_value=True),
        ):
            with pytest.raises(MasterBulkDeleteIntegrityError) as exc_info:
                await confirm_master_bulk_delete(db, "customers", [1], deletable_ids=[1])
        assert exc_info.value.references
        db.rollback.assert_awaited()

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
                [{"label": DSI_STAGING_REF_LABEL, "count": 11}],
            )
        ),
    ):
        r = client.post(
            "/api/v1/customers/bulk-delete-confirm",
            json={"entity_ids": [2], "deletable_ids": [2]},
        )

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["references"][0]["label"] == DSI_STAGING_REF_LABEL
    assert detail["references"][0]["count"] == 11


def test_bulk_delete_confirm_timeout_returns_504_not_500():
    exc = MasterBulkDeleteTimeoutError("timed out", phase="reference_union")
    with pytest.raises(HTTPException) as raised:
        raise_bulk_delete_http_error(exc, entity_label="customer")
    assert raised.value.status_code == 504
    assert raised.value.detail["error"] == "statement_timeout"


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
