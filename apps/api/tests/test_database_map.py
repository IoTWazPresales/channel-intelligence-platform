"""Database-map contracts; real SQL runs only on cip_test and fixtures roll back."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from app.api.deps import get_db
from app.api.v1.endpoints import database_map as endpoint
from app.core.security import Role, get_current_user
from app.models.iam import AppUser, Tenant
from app.services import database_map as catalog
from app.services.database_map import DatabaseMap, DatabaseMapReader, readonly_catalog_connection
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.rolled_back_async_session import rolled_back_async_session


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def api():
    application = FastAPI()
    application.include_router(endpoint.router, prefix="/api/v1")
    return application


def set_user(api, *, role=Role.ADMIN, user_id="1", tenant_id="default"):
    async def current_user():
        return {"id": user_id, "role": role, "tenant_id": tenant_id}

    api.dependency_overrides[get_current_user] = current_user


@pytest.fixture
async def client(api):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://test"
    ) as session:
        yield session


@pytest.fixture
def test_engine():
    from app.db.session import engine

    # Check the configured destination BEFORE opening any connection.
    if engine.url.database != "cip_test":
        pytest.skip("Database-map integration tests require cip_test")
    return engine


@pytest.fixture
async def tx(test_engine):
    # Create storage using the real migration, on the same rolled-back connection
    # the endpoint receives. No permanent migration or Alembic stamp is needed.
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20261120_0065_user_ui_layout.py"
    )
    spec = importlib.util.spec_from_file_location("_db_map_layout_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def prepare_storage(connection):
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()  # Exercise idempotent creation and conditional grants.

    async with rolled_back_async_session() as session:
        connection = await session.connection()
        await connection.run_sync(prepare_storage)
        yield session


@pytest.mark.anyio
@pytest.mark.parametrize("role", [Role.STEWARD, Role.PLANNER, Role.VIEWER])
async def test_non_admin_cannot_read_metadata(api, client, monkeypatch, role):
    reader = AsyncMock()
    monkeypatch.setattr(endpoint, "map_reader", reader)
    set_user(api, role=role)
    response = await client.get("/api/v1/admin/db-map")
    assert response.status_code == 403
    reader.read.assert_not_awaited()


@pytest.mark.anyio
async def test_admin_endpoint_shape_and_private_response(api, client, monkeypatch):
    reader = AsyncMock()
    reader.read.return_value = DatabaseMap(
        generated_at=datetime.now(UTC),
        tables=[
            {
                "id": "public.example",
                "name": "example",
                "approx_rows": None,
                "columns": [
                    {"name": "id", "type": "bigint", "nullable": False, "pk": True, "fk": False}
                ],
            }
        ],
        foreign_keys=[],
    )
    monkeypatch.setattr(endpoint, "map_reader", reader)
    set_user(api)
    response = await client.get("/api/v1/admin/db-map")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    payload = response.json()
    assert payload["schema_name"] == "public"
    assert payload["row_count_kind"] == "approx rows"
    assert payload["tables"][0]["approx_rows"] is None
    assert set(payload["tables"][0]["columns"][0]) == {"name", "type", "nullable", "pk", "fk"}
    reader.read.assert_awaited_once()


@pytest.mark.anyio
async def test_catalog_endpoint_real_shape_and_cache(
    api, client, monkeypatch, test_engine
):
    reader = DatabaseMapReader(test_engine)
    monkeypatch.setattr(endpoint, "map_reader", reader)
    set_user(api)
    first = await client.get("/api/v1/admin/db-map")
    assert first.status_code == 200, first.text
    payload = first.json()
    tables = {table["id"]: table for table in payload["tables"]}
    assert "public.app_user" in tables
    assert "public.alembic_version" not in tables
    assert all(key.startswith("public.") for key in tables)
    assert all(
        table["approx_rows"] is None or table["approx_rows"] >= 0
        for table in tables.values()
    )
    columns = {column["name"]: column for column in tables["public.app_user"]["columns"]}
    assert columns["id"]["pk"] is True
    assert columns["id"]["nullable"] is False
    assert any(
        fk["from_table"] == "public.auth_session"
        and fk["from_column"] == "user_id"
        and fk["to_table"] == "public.app_user"
        and fk["to_column"] == "id"
        for fk in payload["foreign_keys"]
    )
    for fk in payload["foreign_keys"]:
        assert fk["from_column"] in {
            column["name"] for column in tables[fk["from_table"]]["columns"]
        }
        assert fk["to_column"] in {
            column["name"] for column in tables[fk["to_table"]]["columns"]
        }
        assert fk["ordinal"] >= 1

    def connection_forbidden(_engine):
        raise AssertionError("A cache hit must not open another connection")

    monkeypatch.setattr(catalog, "readonly_catalog_connection", connection_forbidden)
    second = await client.get("/api/v1/admin/db-map")
    assert second.status_code == 200
    assert second.json() == payload


@pytest.mark.anyio
async def test_catalog_transaction_rejects_writes(test_engine):
    async with readonly_catalog_connection(test_engine) as connection:
        assert (await connection.execute(text("SHOW transaction_read_only"))).scalar_one() == "on"
        isolation = await connection.execute(text("SHOW transaction_isolation"))
        assert isolation.scalar_one() == "repeatable read"
        with pytest.raises(DBAPIError) as caught:
            async with connection.begin_nested():
                # No row can change even if the read-only guard regresses.
                await connection.execute(text("UPDATE public.tenant SET name = name WHERE false"))
        assert getattr(caught.value.orig, "sqlstate", None) == "25006"


@pytest.mark.anyio
async def test_composite_foreign_key_columns_keep_their_ordinal_pairing(test_engine):
    from app.services.database_map import FOREIGN_KEYS_SQL

    async with readonly_catalog_connection(test_engine) as connection:
        rows = (await connection.execute(text(FOREIGN_KEYS_SQL))).mappings().all()
        for row in rows:
            pair = (
                await connection.execute(
                    text(
                        "SELECT source.attname, target.attname "
                        "FROM pg_catalog.pg_constraint AS c "
                        "JOIN pg_catalog.pg_attribute AS source "
                        "ON source.attrelid = c.conrelid "
                        "AND source.attnum = c.conkey[CAST(:ordinal AS integer)] "
                        "JOIN pg_catalog.pg_attribute AS target "
                        "ON target.attrelid = c.confrelid "
                        "AND target.attnum = c.confkey[CAST(:ordinal AS integer)] "
                        "WHERE c.oid = CAST(:oid AS oid)"
                    ),
                    {
                        "ordinal": int(row["ordinal"]),
                        "oid": int(row["id"].split(":")[0]),
                    },
                )
            ).one()
            assert tuple(pair) == (row["from_column"], row["to_column"])


@pytest.mark.anyio
@pytest.mark.parametrize("identity_type", [str, int], ids=["string-id", "integer-id"])
async def test_layouts_are_scoped_to_real_user_and_tenant(api, client, tx, identity_type):
    tag = uuid4().hex
    tenants = [f"db-map-{tag}-a", f"db-map-{tag}-b"]
    tx.add_all([Tenant(id=tenant, name=tenant) for tenant in tenants])
    await tx.flush()
    users = []
    for index, tenant in enumerate([tenants[0], tenants[0], tenants[1]]):
        user = AppUser(
            tenant_id=tenant,
            email=f"layout-{tag}-{index}@example.test",
            password_hash="test-only",
            display_name="Layout fixture",
            role="admin",
        )
        tx.add(user)
        users.append(user)
    await tx.flush()

    async def database():
        yield tx

    api.dependency_overrides[get_db] = database

    def sign_in(index, *, tenant=None):
        set_user(
            api,
            user_id=identity_type(users[index].id),
            tenant_id=tenant or users[index].tenant_id,
        )

    path = "/api/v1/me/ui-layout/admin.db-map.v1"
    sign_in(0)
    empty = await client.get(path)
    assert empty.status_code == 200, empty.text
    assert empty.json()["value"] is None

    value = {"version": 1, "nodes": {"public.example": {"x": 12, "y": 34, "collapsed": True}}}
    saved = await client.put(path, json={"value": value})
    assert saved.status_code == 200, saved.text
    assert saved.json()["value"] == value
    assert saved.json()["updated_at"] is not None

    sign_in(1)
    assert (await client.get(path)).json()["value"] is None
    sign_in(2)
    assert (await client.get(path)).json()["value"] is None

    # A mismatched tenant cannot read or overwrite the original user's preference.
    sign_in(0, tenant=tenants[1])
    assert (await client.get(path)).status_code == 403
    assert (await client.put(path, json={"value": {}})).status_code == 403

    sign_in(0)
    assert (await client.get(path)).json()["value"] == value
    replacement = {"version": 1, "nodes": {}}
    assert (await client.put(path, json={"value": replacement})).status_code == 200
    assert (await client.get(path)).json()["value"] == replacement
    stored = await tx.scalar(
        text(
            "SELECT value FROM public.user_ui_layout "
            "WHERE tenant_id = :tenant AND user_id = :user AND key = :key"
        ),
        {"tenant": tenants[0], "user": users[0].id, "key": "admin.db-map.v1"},
    )
    assert stored == replacement


@pytest.mark.anyio
async def test_layout_validation_does_not_accept_owner_fields(api, client, tx):
    async def database():
        yield tx

    api.dependency_overrides[get_db] = database
    api.dependency_overrides[endpoint.layout_owner] = lambda: ("unused", 1)
    path = "/api/v1/me/ui-layout/admin.db-map.v1"
    response = await client.put(
        path, json={"value": {}, "tenant_id": "another-tenant", "user_id": 2}
    )
    assert response.status_code == 422
    oversized = await client.put(path, json={"value": {"large": "x" * 262_145}})
    assert oversized.status_code == 422
    invalid_key = await client.put("/api/v1/me/ui-layout/INVALID", json={"value": {}})
    assert invalid_key.status_code == 422


@pytest.mark.anyio
async def test_unresolved_stub_identity_cannot_store_layouts(api, client, tx):
    async def database():
        yield tx

    api.dependency_overrides[get_db] = database
    set_user(api, user_id="demo-user")
    response = await client.get("/api/v1/me/ui-layout/admin.db-map.v1")
    assert response.status_code == 403
