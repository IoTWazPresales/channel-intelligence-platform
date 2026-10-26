"""E3 preparation only: observe real background context with rolled-back fixtures.

No production, broker, services, privileges or product-source edits. This records
what the current runner does; it does not decide owner versus recipient policy.
"""
from contextlib import asynccontextmanager
from datetime import date
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests.test_dashboard_v2_authenticated import signed_in  # noqa: F401


@pytest.mark.anyio
async def test_record_background_cpor_scope(signed_in, monkeypatch):
    from app.api.deps import get_db
    from app.core.product_line_scope import request_product_lines, request_editable_product_lines, request_role
    from app.core.tenant_scope import request_tenant_id
    from app.main import app
    from app.models.cpor import CporCase, CporCaseLine
    from app.models.dimensions import DimCustomer
    from app.models.iam import AppUser
    from app.models.report_delivery import ReportDelivery
    from app.services import report_schedule_runner as runner

    fixture = signed_in
    factory = app.dependency_overrides[get_db]
    tenant = fixture.products[0].tenant_id
    async for db in factory():
        users = list((await db.scalars(select(AppUser).where(AppUser.tenant_id.in_({p.tenant_id for p in fixture.products})))).all())
        users = {user.email.split("-")[0]: user.id for user in users}
        for i, product in enumerate(fixture.products):
            customer = (await db.scalars(select(DimCustomer).where(DimCustomer.tenant_id == product.tenant_id))).first()
            case = CporCase(tenant_id=product.tenant_id, case_code=f"E3-probe-{uuid4().hex[:15]}", customer_id=customer.id,
                            promotion_type="Fictional", window_start=date(2026, 1, 1), window_end=date(2026, 1, 31))
            db.add(case)
            await db.flush()
            db.add(CporCaseLine(case_id=case.id, product_id=product.id, window_start=case.window_start,
                               window_end=case.window_end, srp=100, vat_rate=15, dealer_margin_pct=10,
                               estimate_qty=10, result_qty=5, ttl_support_usd=[10, 60, 1000][i], ttl_support=180))
        await db.commit()  # Fixture savepoint only; outer rollback owns all records.
    query = {"metric": "support_spend", "grains": ["customer"]}
    manual = {}
    for key in ["admin", "viewer", "none", "other"]:
        answer = await fixture.client.post("/api/v1/query/execute", json=query, headers=fixture.headers[key])
        assert answer.status_code == 200 and answer.json()["ok"]
        manual[key] = answer.json()["value"]
    assert manual == {"admin": 70, "viewer": 10, "none": 0, "other": 1000}
    report = await fixture.client.post("/api/v1/saved-reports", json={"name": "E3 fictional risk probe", **query}, headers=fixture.headers["admin"])
    assert report.status_code == 200, report.text
    schedule = await fixture.client.post("/api/v1/reports/schedules", json={
        "name": "E3 fictional risk probe", "saved_report_id": report.json()["id"],
        "subscriber_user_ids": [users["viewer"], users["none"], users["other"]]}, headers=fixture.headers["admin"])
    assert schedule.status_code == 200, schedule.text

    @asynccontextmanager
    async def background_db():
        async for db in factory():
            yield db
    monkeypatch.setattr(runner, "AsyncSessionLocal", background_db)
    contexts = [request_tenant_id, request_product_lines, request_editable_product_lines, request_role]
    tokens = [context.set(None) for context in contexts]
    try:
        result = await runner._deliver_schedule_async(schedule.json()["id"], trigger="schedule", advance_clock=False)
        assert result["ok"], result
        async for db in factory():
            rows = list((await db.scalars(select(ReportDelivery).where(ReportDelivery.saved_report_id == report.json()["id"]))).all())
            observed = [{"recipient": next(key for key, uid in users.items() if uid == row.recipient_user_id),
                         "tenant_is_report_tenant": row.tenant_id == tenant, "value": row.value_preview, "status": row.status} for row in rows]
        output = {"kind": "fictional rolled-back E3 investigation", "manual_authorized_values": manual,
                  "background_context": {context.name: context.get() for context in contexts}, "deliveries": observed,
                  "limit": "No production leak asserted. Recipient policy is not decided by this probe."}
        Path(__file__).with_name("background-scope-observed.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(output, indent=2))
    finally:
        for context, token in zip(contexts, tokens):
            context.reset(token)
