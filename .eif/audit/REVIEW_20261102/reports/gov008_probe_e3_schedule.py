"""GOV-008 independent probe (2026-11-02), E3 background delivery scope.

Reuses the committed rolled-back fixtures (two tenants, admin/viewer/none in tenant A, other in B,
CPOR cases 10 (A, line A), 60 (A, line B), 1000 (B)). No real email; inbox rows only, rolled back.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select, text

from tests.test_dashboard_v2_authenticated import signed_in  # noqa: F401
from tests.test_report_schedule_recipient_scope import scheduled, schedule, deliveries  # noqa: F401

OUT: dict = {}
GUC = text("select current_setting('cip.product_lines',true), current_setting('cip.editable_product_lines',true), "
           "current_setting('cip.request_role',true)")


@pytest.mark.anyio
async def test_one_invalid_recipient_among_valid_ones(scheduled):
    """Scenario: weekly schedule with [viewer, deactivated user, admin]."""
    from app.models.iam import AppUser
    s = scheduled
    sid = await schedule(s, s.reports[0], [s.users["viewer"], s.users["none"], s.users["admin"]])
    async with s.factory() as db:
        (await db.get(AppUser, s.users["none"])).is_active = False
        await db.commit()
    result = await s.runner._deliver_schedule_async(sid, trigger="schedule", advance_clock=False)
    rows = await deliveries(s, s.reports[0])
    OUT["mixed_recipients"] = {
        "runner_result": {k: v for k, v in result.items() if k != "error"},
        "runner_error": result.get("error"),
        "deliveries": [{"recipient": r.recipient_user_id, "status": r.status, "subject": r.subject,
                        "value": r.value_preview, "error": r.error_message} for r in rows],
        "users": {k: v for k, v in s.users.items()},
    }
    # Record, do not assert a policy: whether one bad recipient should block the others.


@pytest.mark.anyio
async def test_cache_order_viewer_first_then_admin(scheduled):
    """Cache filled under a narrow scope must not be served to a broader one (and vice versa)."""
    s = scheduled
    out = {}
    for order in (["viewer", "admin", "none", "viewer"], ["none", "admin", "viewer"]):
        from app.query.cache import clear_query_cache
        clear_query_cache()
        sid = await schedule(s, s.reports[0], [s.users[k] for k in order])
        result = await s.runner._deliver_schedule_async(sid, trigger="schedule", advance_clock=False)
        rows = (await deliveries(s, s.reports[0]))[-len(order):]
        out["/".join(order)] = {"ok": result.get("ok"), "values": [r.value_preview for r in rows]}
    sid = await schedule(s, s.reports[1], [s.users["other"]])
    await s.runner._deliver_schedule_async(sid, trigger="schedule", advance_clock=False)
    out["tenant_b_other"] = (await deliveries(s, s.reports[1]))[-1].value_preview
    OUT["cache_order"] = out
    assert out["viewer/admin/none/viewer"]["values"] == ["10.0", "70.0", "0.0", "10.0"] or \
        [float(v) for v in out["viewer/admin/none/viewer"]["values"]] == [10, 70, 0, 10]
    assert [float(v) for v in out["none/admin/viewer"]["values"]] == [0, 70, 10]
    assert float(out["tenant_b_other"]) == 1000


@pytest.mark.anyio
async def test_runner_aborted_sql_restores_connection_scope(scheduled, monkeypatch):
    """Runner path (not only the context manager): a recipient query aborts the transaction."""
    from app.services import report_delivery
    s = scheduled
    sid = await schedule(s, s.reports[0], [s.users["viewer"]])
    seen = {}

    async def aborting(db, **kwargs):
        seen["inside"] = tuple((await db.execute(GUC)).one())
        await db.execute(text("SELECT 1/0"))

    monkeypatch.setattr(report_delivery, "execute_query", aborting)
    result = await s.runner._deliver_schedule_async(sid, trigger="schedule", advance_clock=False)
    async with s.factory() as db:
        after = tuple((await db.execute(GUC)).one())
        rows = await deliveries(s, s.reports[0])
    OUT["aborted_sql_runner"] = {"inside": seen.get("inside"), "after": after, "result_ok": result.get("ok"),
                                 "error_head": (result.get("error") or "")[:160],
                                 "failed_rows": [(r.recipient_user_id, r.status, (r.error_message or "")[:300]) for r in rows]}
    assert seen["inside"][0] == s.auth.line_a and seen["inside"][2] == "viewer"
    assert after[0] in (None, "", "*") and after[2] in (None, "")
    assert all(c.get() is None for c in s.contexts)


@pytest.mark.anyio
async def test_import_event_fanout_skips_cache_and_scopes(scheduled):
    """import_event trigger uses the same recipient scope; cache bypass gives fresh value."""
    from app.models.cpor import CporCaseLine, CporCase
    s = scheduled
    sid = await schedule(s, s.reports[0], [s.users["viewer"]])
    async with s.factory() as db:
        from app.models.report_delivery import ReportSchedule
        (await db.get(ReportSchedule, sid)).cadence = "on_import_complete"
        await db.commit()
    first = await s.runner._deliver_schedule_async(sid, trigger="schedule", advance_clock=False)
    async with s.factory() as db:
        line = (await db.scalars(select(CporCaseLine).join(CporCase).where(
            CporCase.tenant_id == s.reports[0].tenant_id, CporCaseLine.ttl_support_usd == 10))).first()
        line.ttl_support_usd = 15
        await db.commit()
    cached = await s.runner._deliver_schedule_async(sid, trigger="schedule", advance_clock=False)
    fresh = await s.runner._deliver_schedule_async(sid, trigger="import_event", advance_clock=False)
    rows = (await deliveries(s, s.reports[0]))[-3:]
    OUT["import_event"] = {"values": [r.value_preview for r in rows], "ok": [first.get("ok"), cached.get("ok"), fresh.get("ok")]}
    assert float(rows[-1].value_preview) == 15


@pytest.mark.anyio
async def test_tenant_binding_is_load_bearing_mutation(scheduled, monkeypatch):
    """Mutation check: remove the report-tenant ContextVar binding and see whether results change."""
    from contextvars import ContextVar
    from app.services import report_delivery
    s = scheduled
    out = {}
    for label, mutate in (("bound", False), ("binding_removed", True)):
        if mutate:
            monkeypatch.setattr(report_delivery, "request_tenant_id", ContextVar("decoy_tenant", default=None))
        from app.query.cache import clear_query_cache
        clear_query_cache()
        sid = await schedule(s, s.reports[0], [s.users["admin"]])
        result = await s.runner._deliver_schedule_async(sid, trigger="import_event", advance_clock=False)
        rows = await deliveries(s, s.reports[0])
        out[label] = {"ok": result.get("ok"), "value": rows[-1].value_preview if rows else None, "error": (result.get("error") or "")[:200]}
    OUT["tenant_binding_mutation"] = out


def teardown_module(module):
    with open(__file__.replace(".py", "_output.json"), "w", encoding="utf-8") as fh:
        json.dump(OUT, fh, indent=1, default=str)
