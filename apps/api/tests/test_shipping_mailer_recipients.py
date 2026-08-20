"""Shipping-mailer recipient store + admin API (U1). Isolated SQLite — no cip writes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import Role, get_current_user
from app.main import app
from app.models.shipping_mailer_recipient import ShippingMailerRecipient
from app.services.shipping_digest.recipients import DEFAULT_SHIPPING_MAILER_RECIPIENTS
from app.services.shipping_digest.recipients_store import (
    add_recipient_sync,
    ensure_seeded_sync,
    list_recipients_sync,
    patch_recipient_sync,
    resolve_shipping_recipients_sync,
)

_MIG = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260818_0019_shipping_mailer_recipient.py"
)


def test_migration_creates_functional_unique_index() -> None:
    src = _MIG.read_text(encoding="utf-8")
    assert "20260818_0018" in src
    assert "shipping_mailer_recipient" in src
    assert "lower(address)" in src
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO cip" in src
    assert "{table}_id_seq" in src
    assert "_grant_cip" in src


@compiles(BigInteger, "sqlite")
def _bigint_as_integer_on_sqlite(type_, compiler, **kw):
    return "INTEGER"


def _sqlite_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ShippingMailerRecipient.__table__.create(engine)
    return sessionmaker(bind=engine)()


class _RunSyncDb:
    def __init__(self, session):
        self._session = session

    async def run_sync(self, fn, *args, **kwargs):
        return fn(self._session, *args, **kwargs)

    async def commit(self):
        self._session.commit()


def _stub_user(role: Role = Role.ADMIN):
    async def _fake_user():
        return {
            "id": "test-admin",
            "role": role,
            "tenant_id": "default",
            "email": "admin@example.com",
            "display_name": "Admin",
        }

    return _fake_user


@pytest.fixture
def db():
    session = _sqlite_session()
    try:
        yield session
    finally:
        session.close()


def test_empty_table_seeds_five_and_second_call_is_idempotent(db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIP_SHIPPING_MAILER_RECIPIENTS", raising=False)
    first = resolve_shipping_recipients_sync(db, "default")
    assert first == DEFAULT_SHIPPING_MAILER_RECIPIENTS
    n = ensure_seeded_sync(db, "default")
    assert n == 0
    listed = list_recipients_sync(db, "default")
    assert len(listed) == 5
    assert [r["address"] for r in listed] == list(DEFAULT_SHIPPING_MAILER_RECIPIENTS)


def test_disabled_row_excluded_from_resolve_stable_order(db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIP_SHIPPING_MAILER_RECIPIENTS", raising=False)
    resolve_shipping_recipients_sync(db, "default")
    rows = list_recipients_sync(db, "default")
    patch_recipient_sync(db, "default", rows[0]["id"], enabled=False)
    enabled = resolve_shipping_recipients_sync(db, "default")
    assert rows[0]["address"] not in enabled
    assert len(enabled) == 4
    assert list(enabled) == [r["address"] for r in rows[1:]]


def test_all_disabled_is_mute_does_not_reseed(db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIP_SHIPPING_MAILER_RECIPIENTS", raising=False)
    resolve_shipping_recipients_sync(db, "default")
    for row in list_recipients_sync(db, "default"):
        patch_recipient_sync(db, "default", row["id"], enabled=False)
    assert resolve_shipping_recipients_sync(db, "default") == ()
    assert len(list_recipients_sync(db, "default")) == 5


def test_env_seeds_when_table_empty(db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIP_SHIPPING_MAILER_RECIPIENTS", "ops@example.com, other@example.com")
    rec = resolve_shipping_recipients_sync(db, "default")
    assert rec == ("ops@example.com", "other@example.com")
    assert DEFAULT_SHIPPING_MAILER_RECIPIENTS[0] not in rec


def test_env_ignored_when_table_has_rows(db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIP_SHIPPING_MAILER_RECIPIENTS", raising=False)
    resolve_shipping_recipients_sync(db, "default")
    monkeypatch.setenv("CIP_SHIPPING_MAILER_RECIPIENTS", "only-env@example.com")
    rec = resolve_shipping_recipients_sync(db, "default")
    assert rec == DEFAULT_SHIPPING_MAILER_RECIPIENTS
    assert "only-env@example.com" not in rec


def test_case_insensitive_unique_preserves_stored_casing(db) -> None:
    db.add(
        ShippingMailerRecipient(
            tenant_id="default",
            address="Foo@ASUS.com",
            enabled=True,
            added_by="test",
        )
    )
    db.commit()
    db.add(
        ShippingMailerRecipient(
            tenant_id="default",
            address="foo@asus.com",
            enabled=True,
            added_by="test",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    remaining = db.execute(
        select(ShippingMailerRecipient).where(ShippingMailerRecipient.tenant_id == "default")
    ).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].address == "Foo@ASUS.com"


def test_post_add_upserts_same_address_case_insensitive(db) -> None:
    first = add_recipient_sync(db, "default", "Foo@ASUS.com ", None, "admin")
    second = add_recipient_sync(db, "default", "foo@asus.com", "Ops", "admin")
    assert first["id"] == second["id"]
    assert second["address"] == "Foo@ASUS.com"
    assert second["display_name"] == "Ops"
    assert second["enabled"] is True
    assert len(list_recipients_sync(db, "default")) == 1


@pytest.mark.anyio
async def test_build_digest_uses_async_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    async def _fake_resolve(db, tenant_id: str):
        captured["tenant_id"] = tenant_id
        return ("wired@example.com",)

    monkeypatch.setattr(
        "app.services.shipping_digest.build.resolve_shipping_recipients",
        _fake_resolve,
    )
    monkeypatch.setattr(
        "app.services.shipping_digest.build.latest_inbound_shipment_job_id",
        AsyncMock(return_value=None),
    )
    from app.services.shipping_digest.build import build_shipping_digest

    digest = await build_shipping_digest(AsyncMock(), tenant_id="default")
    assert digest["intended_recipients"] == ["wired@example.com"]
    assert captured["tenant_id"] == "default"


def test_dispatch_send_list_does_not_fall_back_to_env() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "shipping_digest"
        / "dispatch.py"
    ).read_text(encoding="utf-8")
    assert "mailer_recipients()" not in src
    assert "mailer_send_enabled()" in src
    assert 'digest.get("intended_recipients") or []' in src


def test_dispatch_still_gates_smtp_on_send_flag() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "shipping_digest"
        / "dispatch.py"
    ).read_text(encoding="utf-8")
    assert "if sending:" in src
    assert "send_digest_to_recipients" in src


@pytest.fixture
def api_client():
    session = _sqlite_session()

    async def _get_db():
        yield _RunSyncDb(session)

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _stub_user()
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_list_seeds_and_non_admin_forbidden(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIP_SHIPPING_MAILER_RECIPIENTS", raising=False)
    client, _session = api_client
    r = client.get("/api/v1/shipping-mailer/recipients")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["address"] for i in items] == list(DEFAULT_SHIPPING_MAILER_RECIPIENTS)

    app.dependency_overrides[get_current_user] = _stub_user(Role.VIEWER)
    denied = client.post(
        "/api/v1/shipping-mailer/recipients",
        json={"address": "extra@example.com"},
    )
    assert denied.status_code == 403
    denied_patch = client.patch(
        f"/api/v1/shipping-mailer/recipients/{items[0]['id']}",
        json={"enabled": False},
    )
    assert denied_patch.status_code == 403
    denied_del = client.delete(f"/api/v1/shipping-mailer/recipients/{items[0]['id']}")
    assert denied_del.status_code == 403


def test_api_add_disable_delete(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIP_SHIPPING_MAILER_RECIPIENTS", raising=False)
    client, _session = api_client
    listed = client.get("/api/v1/shipping-mailer/recipients")
    assert listed.status_code == 200
    created = client.post(
        "/api/v1/shipping-mailer/recipients",
        json={"address": "extra@example.com", "display_name": "Extra"},
    )
    assert created.status_code == 201
    rid = created.json()["id"]
    patched = client.patch(
        f"/api/v1/shipping-mailer/recipients/{rid}",
        json={"enabled": False},
    )
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False
    deleted = client.delete(f"/api/v1/shipping-mailer/recipients/{rid}")
    assert deleted.status_code == 204
    leftover = {i["address"] for i in client.get("/api/v1/shipping-mailer/recipients").json()["items"]}
    assert "extra@example.com" not in leftover


def test_api_rejects_invalid_address(api_client) -> None:
    client, _session = api_client
    r = client.post("/api/v1/shipping-mailer/recipients", json={"address": "not-an-email"})
    assert r.status_code == 400
