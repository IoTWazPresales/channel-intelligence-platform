"""N-0100 part B: a user's job is stored apart from the role, and only an admin edits it.

Runs through the real app on cip_test. The request session is bound to one connection whose outer
transaction is rolled back at the end, so nothing persists.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import Role, normalize_role
from app.core.user_job import JOBS, normalize_job
from app.main import app


def test_normalize_job_accepts_the_five_jobs_and_empty() -> None:
    assert JOBS == ("account_manager", "product_manager", "finance", "country_manager", "admin")
    for job in JOBS:
        assert normalize_job(job) == job
    assert normalize_job("Account Manager") == "account_manager"
    assert normalize_job("country-manager") == "country_manager"
    assert normalize_job(None) is None
    assert normalize_job("  ") is None
    with pytest.raises(ValueError):
        normalize_job("planner")


def test_role_aliases_are_unchanged_by_jobs() -> None:
    # A job string is not a role: the role aliases still map as before.
    assert normalize_role("admin") == Role.ADMIN
    assert normalize_role("viewer") == Role.VIEWER


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
        has_job = (
            await conn.execute(
                text("select count(*) from information_schema.columns where table_name = 'app_user' and column_name = 'job'")
            )
        ).scalar_one()
        if not has_job:
            await outer.rollback()
            pytest.skip("app_user.job is not on cip_test (migration 20261110_0061 not applied)")
        session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")

        async def _db():
            s = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
            try:
                yield s
            finally:
                await s.close()

        app.dependency_overrides[get_db] = _db
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                yield client, session
        finally:
            app.dependency_overrides.pop(get_db, None)
            await session.close()
            await outer.rollback()


async def _user(session: AsyncSession, email: str, role: str = "viewer", tenant: str = "default", job: str | None = None) -> int:
    uid = (
        await session.execute(
            text(
                "insert into app_user (tenant_id, email, password_hash, display_name, role, job) "
                "values (:t, :e, 'x', :e, :r, :j) returning id"
            ),
            {"e": email, "r": role, "t": tenant, "j": job},
        )
    ).scalar_one()
    await session.flush()
    return int(uid)


def _h(uid: int) -> dict[str, str]:
    return {"X-User-Id": str(uid)}


async def _row(session: AsyncSession, uid: int):
    return (await session.execute(text("select role, job from app_user where id = :i"), {"i": uid})).one()


@pytest.mark.anyio
async def test_admin_sets_and_clears_a_job_and_the_role_stays(tx) -> None:
    client, session = tx
    admin = await _user(session, "n0100b-admin@example.test", role="admin")
    target = await _user(session, "n0100b-target@example.test", role="planner")

    r = await client.put(f"/api/v1/auth/users/{target}/job", json={"job": "account_manager"}, headers=_h(admin))
    assert r.status_code == 200, r.text
    assert r.json() == {"user_id": str(target), "job": "account_manager", "role": "planner"}
    assert tuple(await _row(session, target)) == ("planner", "account_manager")

    listed = await client.get("/api/v1/auth/users", headers=_h(admin))
    assert listed.status_code == 200, listed.text
    mine = [u for u in listed.json()["users"] if u["id"] == str(target)]
    assert mine and mine[0]["job"] == "account_manager" and mine[0]["role"] == "planner"

    me = await client.get("/api/v1/auth/me", headers=_h(target))
    assert me.status_code == 200, me.text
    assert me.json()["job"] == "account_manager"

    cleared = await client.put(f"/api/v1/auth/users/{target}/job", json={"job": None}, headers=_h(admin))
    assert cleared.status_code == 200 and cleared.json()["job"] is None
    assert tuple(await _row(session, target)) == ("planner", None)


@pytest.mark.anyio
async def test_an_unknown_job_is_refused_and_nothing_changes(tx) -> None:
    client, session = tx
    admin = await _user(session, "n0100b-admin2@example.test", role="admin")
    target = await _user(session, "n0100b-target2@example.test", role="viewer", job="finance")
    r = await client.put(f"/api/v1/auth/users/{target}/job", json={"job": "planner"}, headers=_h(admin))
    assert r.status_code == 422
    assert tuple(await _row(session, target)) == ("viewer", "finance")


@pytest.mark.anyio
async def test_only_an_admin_role_edits_a_job_and_a_job_named_admin_grants_nothing(tx) -> None:
    client, session = tx
    viewer_with_admin_job = await _user(session, "n0100b-viewer@example.test", role="viewer", job="admin")
    target = await _user(session, "n0100b-target3@example.test", role="viewer")
    r = await client.put(f"/api/v1/auth/users/{target}/job", json={"job": "finance"}, headers=_h(viewer_with_admin_job))
    assert r.status_code == 403
    assert (await client.get("/api/v1/auth/users", headers=_h(viewer_with_admin_job))).status_code == 403
    assert tuple(await _row(session, target)) == ("viewer", None)


@pytest.mark.anyio
async def test_another_tenants_user_is_not_found(tx) -> None:
    client, session = tx
    exists = (await session.execute(text("select count(*) from tenant where id = 'n0100b_other'"))).scalar_one()
    if not exists:
        await session.execute(text("insert into tenant (id, name) values ('n0100b_other', 'n0100b other')"))
    admin = await _user(session, "n0100b-admin4@example.test", role="admin")
    other = await _user(session, "n0100b-other@example.test", role="viewer", tenant="n0100b_other")
    r = await client.put(f"/api/v1/auth/users/{other}/job", json={"job": "finance"}, headers=_h(admin))
    assert r.status_code == 404
    assert tuple(await _row(session, other)) == ("viewer", None)


@pytest.mark.anyio
async def test_create_user_stores_the_job(tx) -> None:
    client, session = tx
    admin = await _user(session, "n0100b-admin5@example.test", role="admin")
    r = await client.post(
        "/api/v1/auth/users",
        json={"email": "n0100b-new@example.test", "display_name": "New", "role": "steward", "job": "Country Manager"},
        headers=_h(admin),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == "steward" and body["job"] == "country_manager"
    assert tuple(await _row(session, int(body["id"]))) == ("steward", "country_manager")


@pytest.mark.anyio
async def test_the_database_refuses_a_job_outside_the_five(tx) -> None:
    _client, session = tx
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await _user(session, "n0100b-bad@example.test", job="planner")
