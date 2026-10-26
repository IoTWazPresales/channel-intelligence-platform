"""E3: current recipient permissions, real auth/runner/SQL, fictional rollback data."""
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from tests.test_dashboard_v2_authenticated import signed_in  # noqa: F401


@pytest.fixture
async def scheduled(signed_in, monkeypatch, tmp_path):
    from app.api.deps import get_db
    from app.core.product_line_scope import request_product_lines, request_editable_product_lines, request_role
    from app.core.tenant_scope import request_tenant_id
    from app.main import app
    from app.models.cpor import CporCase, CporCaseLine
    from app.models.dimensions import DimCustomer
    from app.models.iam import AppUser
    from app.models.saved_reports import SavedReport
    from app.services import report_schedule_runner as runner

    factory = asynccontextmanager(app.dependency_overrides[get_db])
    fixture = signed_in
    async with factory() as db:
        users = list((await db.scalars(select(AppUser).where(AppUser.tenant_id.in_({p.tenant_id for p in fixture.products})))).all())
        users = {user.email.split("-")[0]: user.id for user in users}
        for i, product in enumerate(fixture.products):
            customer = (await db.scalars(select(DimCustomer).where(DimCustomer.tenant_id == product.tenant_id))).first()
            case = CporCase(tenant_id=product.tenant_id, case_code=f"E3-{uuid4().hex[:18]}", customer_id=customer.id,
                            promotion_type="Fictional", window_start=date(2026, 1, 1), window_end=date(2026, 1, 31))
            db.add(case)
            await db.flush()
            db.add(CporCaseLine(case_id=case.id, product_id=product.id, window_start=case.window_start,
                               window_end=case.window_end, srp=100, vat_rate=15, dealer_margin_pct=10,
                               estimate_qty=10, result_qty=5, ttl_support_usd=[10, 60, 1000][i], ttl_support=180))
        reports = []
        for owner, tenant in [("admin", fixture.products[0].tenant_id), ("other", fixture.products[2].tenant_id)]:
            report = SavedReport(tenant_id=tenant, owner_user_id=users[owner], name="E3 fictional published",
                                 visibility="published", shared_roles=[], metric_key="support_spend", grains=["customer"], filters={})
            db.add(report)
            reports.append(report)
        await db.commit()  # Fixture savepoint; outer rollback owns all rows.

    monkeypatch.setattr(runner, "AsyncSessionLocal", factory)
    monkeypatch.setenv("CIP_TASK_FAILURE_ALERT_PATH", str(tmp_path / "alerts.log"))
    contexts = [request_tenant_id, request_product_lines, request_editable_product_lines, request_role]
    tokens = [context.set(None) for context in contexts]
    try:
        yield SimpleNamespace(auth=fixture, factory=factory, users=users, reports=reports, runner=runner, contexts=contexts)
    finally:
        for context, token in zip(contexts, tokens):
            context.reset(token)


async def schedule(s, report, recipients):
    from app.models.report_delivery import ReportSchedule
    async with s.factory() as db:
        row = ReportSchedule(tenant_id=report.tenant_id, saved_report_id=report.id, owner_user_id=report.owner_user_id,
                             name="E3 fictional", subscriber_user_ids=recipients, cadence="daily_0700", format="xlsx")
        db.add(row)
        await db.commit()
        return row.id


async def deliveries(s, report):
    from app.models.report_delivery import ReportDelivery
    async with s.factory() as db:
        return list((await db.scalars(select(ReportDelivery).where(ReportDelivery.saved_report_id == report.id).order_by(ReportDelivery.id))).all())


@pytest.mark.anyio
async def test_background_governed_and_model_queries_use_each_current_recipient_scope(scheduled):
    from app.services.dashboard_definitions import check_definition
    s = scheduled
    for model, expected in [(False, [70, 10, 0, 10]), (True, [1012, 913, 0, 913])]:
        report = s.reports[0]
        if model:
            async with s.factory() as db:
                row = await db.get(type(report), report.id)
                checked = check_definition({"query": {"measures": ["dsi_sellout.units", "dsi_sellout.lines"]}}, tenant_id=row.tenant_id)
                row.definition_v2, row.metric_key = checked.definition, checked.v1.metric_key
                await db.commit()
        sid = await schedule(s, report, [s.users[key] for key in ("admin", "viewer", "none", "viewer")])
        result = await s.runner._deliver_schedule_async(sid, trigger="schedule", advance_clock=False)
        assert result["ok"], result
        rows = (await deliveries(s, report))[-4:]
        assert [float(row.value_preview) for row in rows] == expected
        assert all(context.get() is None for context in s.contexts)
    sid = await schedule(s, s.reports[1], [s.users["other"]])
    assert (await s.runner._deliver_schedule_async(sid, trigger="import_event", advance_clock=False))["ok"]
    assert float((await deliveries(s, s.reports[1]))[-1].value_preview) == 1000


@pytest.mark.anyio
async def test_permission_revocation_is_reloaded_for_the_next_background_execution(scheduled):
    from app.models.product_line_access import UserProductLineAccess
    s = scheduled
    sid = await schedule(s, s.reports[0], [s.users["viewer"]])
    assert (await s.runner._deliver_schedule_async(sid, trigger="schedule", advance_clock=False))["ok"]
    assert float((await deliveries(s, s.reports[0]))[-1].value_preview) == 10
    async with s.factory() as db:
        await db.execute(delete(UserProductLineAccess).where(UserProductLineAccess.user_id == s.users["viewer"]))
        await db.commit()
    assert (await s.runner._deliver_schedule_async(sid, trigger="import_event", advance_clock=False))["ok"]
    assert float((await deliveries(s, s.reports[0]))[-1].value_preview) == 0


@pytest.mark.anyio
@pytest.mark.parametrize("invalid", ["foreign", "inactive", "private", "no_identity", "wrong_report_tenant"])
async def test_background_refuses_invalid_recipients_and_does_not_notify_them(scheduled, invalid):
    from app.models.iam import AppUser
    from app.models.report_delivery import ReportSchedule
    s = scheduled
    rid = s.users["other"] if invalid == "foreign" else s.users["viewer"]
    sid = await schedule(s, s.reports[0], [rid])
    async with s.factory() as db:
        if invalid == "inactive":
            (await db.get(AppUser, rid)).is_active = False
        elif invalid == "private":
            (await db.get(type(s.reports[0]), s.reports[0].id)).visibility = "personal"
        elif invalid == "no_identity":
            row = await db.get(ReportSchedule, sid)
            row.subscriber_user_ids, row.owner_user_id = [], None
        elif invalid == "wrong_report_tenant":
            (await db.get(ReportSchedule, sid)).saved_report_id = s.reports[1].id
        await db.commit()
    result = await s.runner._deliver_schedule_async(sid, trigger="schedule", advance_clock=False)
    assert not result.get("ok"), result
    assert not await deliveries(s, s.reports[0])
    assert not await deliveries(s, s.reports[1])
    assert all(context.get() is None for context in s.contexts)


@pytest.mark.anyio
async def test_schedule_http_rejects_foreign_subscribers_and_run_now_honours_recipient_access(scheduled):
    s = scheduled
    body = {"name": "E3", "saved_report_id": s.reports[0].id, "subscriber_user_ids": [s.users["other"]]}
    response = await s.auth.client.post("/api/v1/reports/schedules", json=body, headers=s.auth.headers["admin"])
    assert response.status_code == 403, response.text
    body["subscriber_user_ids"] = [s.users["viewer"], s.users["none"]]
    response = await s.auth.client.post("/api/v1/reports/schedules", json=body, headers=s.auth.headers["admin"])
    assert response.status_code == 200, response.text
    response = await s.auth.client.post(f"/api/v1/reports/schedules/{response.json()['id']}/run-now", headers=s.auth.headers["admin"])
    assert response.status_code == 200, response.text
    assert [float(row["value_preview"]) for row in response.json()["deliveries"]] == [10, 0]


@pytest.mark.anyio
async def test_real_pooled_transaction_resets_product_scope_and_role():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.product_line_scope import apply_product_line_guc, request_product_lines, request_editable_product_lines, request_role
    from app.db.session import engine, _asyncpg_connect_args

    assert engine.url.database == "cip_test"
    pool = create_async_engine(engine.url, pool_size=1, max_overflow=0, connect_args=_asyncpg_connect_args(str(engine.url)))
    sessions = async_sessionmaker(pool)
    try:
        async with sessions() as db:
            assert (await db.execute(text("select current_database()"))).scalar_one() == "cip_test"
            pid = (await db.execute(text("select pg_backend_pid()"))).scalar_one()
            contexts = [request_product_lines, request_editable_product_lines, request_role]
            tokens = [context.set(value) for context, value in zip(contexts, [frozenset({"NB"}), frozenset(), "viewer"])]
            try:
                await apply_product_line_guc(db)
                row = (await db.execute(text("select current_setting('cip.product_lines',true), current_setting('cip.request_role',true)"))).one()
                assert tuple(row) == ("NB", "viewer")
                await db.rollback()
            finally:
                for context, token in zip(contexts, tokens):
                    context.reset(token)
        async with sessions() as db:
            row = (await db.execute(text("select pg_backend_pid(), current_setting('cip.product_lines',true), current_setting('cip.request_role',true)"))).one()
            assert row[0] == pid  # Same physical pooled backend, a new root transaction.
            assert row[1] in (None, "", "*") and row[2] in (None, "")
            await db.rollback()
    finally:
        await pool.dispose()


@pytest.mark.anyio
async def test_run_now_cannot_return_another_recipients_broader_result(scheduled):
    s = scheduled
    response = await s.auth.client.post(
        "/api/v1/reports/schedules",
        json={"name": "E3 viewer sends to admin", "saved_report_id": s.reports[0].id,
              "subscriber_user_ids": [s.users["admin"], s.users["viewer"]]},
        headers=s.auth.headers["viewer"],
    )
    assert response.status_code == 200, response.text
    response = await s.auth.client.post(
        f"/api/v1/reports/schedules/{response.json()['id']}/run-now",
        headers=s.auth.headers["viewer"],
    )
    assert response.status_code == 200, response.text
    assert [float(row["value_preview"]) for row in response.json()["deliveries"]] == [10]
    assert [float(row.value_preview) for row in await deliveries(s, s.reports[0])] == [70, 10]


@pytest.mark.anyio
@pytest.mark.parametrize("fail", [False, "query", "aborted_sql"])
async def test_recipient_scope_restores_live_transaction_and_caller_context(scheduled, monkeypatch, fail):
    from sqlalchemy import text
    from app.core.product_line_scope import apply_product_line_guc
    from app.services import report_delivery

    s = scheduled
    # A scoped caller schedules a broader recipient. The query refresh opens
    # another transaction; restoring ContextVars alone does not restore its GUCs.
    values = [s.reports[0].tenant_id, frozenset({s.auth.line_a}), frozenset(), "viewer"]
    tokens = [context.set(value) for context, value in zip(s.contexts, values)]
    try:
        async with s.factory() as db:
            await apply_product_line_guc(db)
            sql = text("select current_setting('cip.product_lines',true), "
                       "current_setting('cip.editable_product_lines',true), current_setting('cip.request_role',true)")
            before = tuple((await db.execute(sql)).one())
            if fail:
                async def rejected(*args, **kwargs):
                    assert tuple((await db.execute(sql)).one()) == ("*", "*", "admin")
                    if fail == "aborted_sql":
                        await db.execute(text("SELECT 1 / 0"))
                    raise RuntimeError("Fictional query rejection")
                monkeypatch.setattr(report_delivery, "_deliver_saved_report", rejected)
                from sqlalchemy.exc import DBAPIError
                with pytest.raises(DBAPIError if fail == "aborted_sql" else RuntimeError):
                    await report_delivery.deliver_saved_report(
                        db, report=s.reports[0], user=None, trigger="schedule", recipient_user_id=s.users["admin"])
            else:
                await report_delivery.deliver_saved_report(
                    db, report=s.reports[0], user=None, trigger="schedule", recipient_user_id=s.users["admin"])
            assert [context.get() for context in s.contexts] == values
            assert tuple((await db.execute(sql)).one()) == before
    finally:
        for context, token in zip(s.contexts, tokens):
            context.reset(token)
