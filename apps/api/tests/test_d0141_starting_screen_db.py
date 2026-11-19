"""D-0141 on cip_test with test-only users (rolled back): /auth/me starting screen and the
request filter, under both CIP_STARTING_SCREEN_POLICY values. No account is added to cip."""

from __future__ import annotations

import secrets

import httpx
import pytest
from app.api.deps import get_db
from app.core.config import get_settings
from app.core.my_accounts import bind_my_accounts, request_my_account_ids, reset_my_accounts
from app.main import app
from app.models.saved_reports import Dashboard
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

TAG = secrets.token_hex(3)


@pytest.fixture()
async def tx():
    from app.db.session import engine

    async with engine.connect() as conn:
        outer = await conn.begin()
        name = (await conn.execute(text("select current_database()"))).scalar_one()
        print(f"current_database={name}", flush=True)
        if name != "cip_test":
            await outer.rollback()
            pytest.skip("cip_test only")
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )

        async def _db():
            s = AsyncSession(
                bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
            try:
                yield s
            finally:
                await s.close()

        app.dependency_overrides[get_db] = _db
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                yield client, session
        finally:
            app.dependency_overrides.pop(get_db, None)
            await session.close()
            await outer.rollback()


async def _user(session: AsyncSession, label: str, *, job: str | None, accounts: int) -> int:
    uid = (
        await session.execute(
            text(
                "insert into app_user (tenant_id, email, password_hash, display_name, role, job) "
                "values ('default', :e, 'x', :e, 'planner', :j) returning id"
            ),
            {"e": f"d0141-{TAG}-{label}@example.test", "j": job},
        )
    ).scalar_one()
    for i in range(accounts):
        cid = (
            await session.execute(
                text(
                    "insert into dim_customer (code, name, customer_status, is_key_account, "
                    "tenant_id) values (:c, :n, 'active', false, 'default') returning id"
                ),
                {"c": f"d0141-{TAG}-{label}-{i}", "n": f"D0141 {TAG} {label} {i}"},
            )
        ).scalar_one()
        await session.execute(
            text(
                "insert into user_customer_account (tenant_id, user_id, customer_id) "
                "values ('default', :u, :c)"
            ),
            {"u": uid, "c": cid},
        )
    await session.flush()
    return int(uid)


async def _me(client, uid: int, choice: str | None = None) -> dict:
    headers = {"X-User-Id": str(uid)}
    if choice:
        headers["X-Cip-My-Accounts"] = choice
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _bound(session, uid: int, headers: dict) -> frozenset | None:
    token = await bind_my_accounts(session, {"id": str(uid), "tenant_id": "default"}, headers)
    try:
        return request_my_account_ids.get()
    finally:
        reset_my_accounts(token)


@pytest.mark.anyio
async def test_d0141_policy_lands_only_an_account_manager_on_my_accounts(tx, monkeypatch) -> None:
    client, session = tx
    monkeypatch.setattr(get_settings(), "cip_starting_screen_policy", "d0141")
    am = await _user(session, "am", job="account_manager", accounts=2)
    am_empty = await _user(session, "am0", job="account_manager", accounts=0)
    finance = await _user(session, "fin", job="finance", accounts=1)
    nojob = await _user(session, "none", job=None, accounts=1)

    me = await _me(client, am)
    assert me["starting_screen"] == {"path": "/dashboards?start=my_accounts", "policy": "d0141"}
    assert me["my_accounts"] == {"assigned_count": 2, "filter_default_on": True, "filter_on": True}
    assert len(await _bound(session, am, {}) or ()) == 2
    assert await _bound(session, am, {"x-cip-my-accounts": "off"}) is None

    for uid in (am_empty, finance, nojob):
        m = await _me(client, uid)
        assert m["starting_screen"]["path"] == "/brief"
        assert (
            m["my_accounts"]["filter_default_on"] is False
            and m["my_accounts"]["filter_on"] is False
        )
        assert await _bound(session, uid, {}) is None
    # A finance user may still choose their accounts for this sign-in.
    chosen = await _me(client, finance, "on")
    assert chosen["my_accounts"]["filter_on"] is True
    assert len(await _bound(session, finance, {"x-cip-my-accounts": "on"}) or ()) == 1
    assert await _bound(session, am_empty, {"x-cip-my-accounts": "on"}) is None


@pytest.mark.anyio
async def test_default_policy_is_unchanged_behaviour(tx, monkeypatch) -> None:
    client, session = tx
    monkeypatch.setattr(get_settings(), "cip_starting_screen_policy", "assigned")
    finance = await _user(session, "fin2", job="finance", accounts=1)
    none = await _user(session, "none2", job=None, accounts=0)
    me = await _me(client, finance)
    assert me["starting_screen"] == {"path": "/brief", "policy": "assigned"}
    assert me["my_accounts"]["filter_on"] is True
    assert len(await _bound(session, finance, {}) or ()) == 1
    assert (await _me(client, finance, "off"))["my_accounts"]["filter_on"] is False
    assert (await _me(client, none))["my_accounts"]["filter_on"] is False

@pytest.mark.anyio
async def test_starting_screen_list_stays_owner_scoped_after_switching_users(tx, monkeypatch) -> None:
    """B1 API contract: one client can switch users without losing either saved starter."""
    client, session = tx
    monkeypatch.setattr(get_settings(), "cip_auth_mode", "stub")
    monkeypatch.setattr(get_settings(), "cip_starting_screen_policy", "d0141")
    first = await _user(session, "switch-first", job="finance", accounts=0)
    second = await _user(session, "switch-second", job="account_manager", accounts=1)
    starters = [
        Dashboard(
            tenant_id="default",
            owner_user_id=uid,
            name=f"D0141 {TAG} starter {uid}",
            visibility="personal",
            shared_roles=[],
            filters_json={},
            template_key="my_accounts",
        )
        for uid in (first, second)
    ]
    session.add_all(starters)
    await session.flush()
    expected = {row.owner_user_id: row.id for row in starters}

    for uid in (first, second, first):
        response = await client.get("/api/v1/dashboards", headers={"X-User-Id": str(uid)})
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        own = [
            row for row in items
            if row["template_key"] == "my_accounts" and row["owner_user_id"] == uid
        ]
        assert [row["id"] for row in own] == [expected[uid]]
        assert not any(row["id"] == expected[second if uid == first else first] for row in items)

    assert (await _me(client, second))["starting_screen"]["path"] == "/dashboards?start=my_accounts"
    count = await session.scalar(
        select(func.count()).select_from(Dashboard).where(
            Dashboard.owner_user_id.in_([first, second]),
            Dashboard.template_key == "my_accounts",
        )
    )
    assert count == 2
