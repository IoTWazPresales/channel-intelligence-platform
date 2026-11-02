"""GOV-008 M4: one failing schedule recipient never stops the others; failure text is honest and safe."""
import pytest
from sqlalchemy.exc import ProgrammingError

from tests.test_report_schedule_recipient_scope import deliveries, schedule, scheduled  # noqa: F401
from tests.test_dashboard_v2_authenticated import signed_in  # noqa: F401


def _by_recipient(rows):
    out = {}
    for row in rows:
        out.setdefault(row.recipient_user_id, []).append(row)
    return out


@pytest.mark.anyio
async def test_deactivated_middle_recipient_does_not_stop_the_admin(scheduled):
    """The review's probe: [viewer, deactivated, admin] -> admin still gets the report."""
    from app.models.iam import AppUser
    s = scheduled
    sid = await schedule(s, s.reports[0], [s.users["viewer"], s.users["none"], s.users["admin"]])
    async with s.factory() as db:
        (await db.get(AppUser, s.users["none"])).is_active = False
        await db.commit()
    result = await s.runner._deliver_schedule_async(sid, trigger="schedule", advance_clock=False)
    rows = _by_recipient(await deliveries(s, s.reports[0]))
    assert [r.status for r in rows[s.users["viewer"]]] == ["delivered"]
    assert [r.status for r in rows[s.users["admin"]]] == ["delivered"], rows
    assert s.users["none"] not in rows  # a deactivated user is never notified
    assert result["ok"] is False and result["failed_recipients"] == [s.users["none"]]
    assert len(result["deliveries"]) == 2
    assert all(context.get() is None for context in s.contexts)


def _failing_for(real, user_id, error):
    async def deliver(db, **kwargs):
        if kwargs.get("recipient_user_id") == user_id:
            raise error
        return await real(db, **kwargs)
    return deliver


@pytest.mark.anyio
async def test_query_failure_gives_a_failed_row_only_to_that_recipient_without_sql_text(scheduled, monkeypatch):
    s = scheduled
    leak = ProgrammingError("SELECT secret_col FROM fact_x WHERE tenant_id = %(t)s", {"t": "default"},
                            Exception("relation fact_x does not exist"))
    assert "[SQL:" in str(leak)
    monkeypatch.setattr(s.runner, "deliver_saved_report", _failing_for(s.runner.deliver_saved_report, s.users["viewer"], leak))
    sid = await schedule(s, s.reports[0], [s.users["viewer"], s.users["admin"]])
    result = await s.runner._deliver_schedule_async(sid, trigger="schedule", advance_clock=False)
    rows = _by_recipient(await deliveries(s, s.reports[0]))
    assert [r.status for r in rows[s.users["admin"]]] == ["delivered"]
    failed = rows[s.users["viewer"]]
    assert [r.status for r in failed] == ["failed"]
    shown = " ".join([failed[0].subject or "", failed[0].body_summary or "", failed[0].error_message or ""])
    assert "[SQL" not in shown and "secret_col" not in shown and "parameters" not in shown
    assert failed[0].subject.startswith("[FAILED]")  # not a timeout
    assert "timeout" not in shown.lower()
    assert result["ok"] is False and result["failed_recipients"] == [s.users["viewer"]]


@pytest.mark.anyio
async def test_a_real_statement_timeout_is_labelled_timeout(scheduled, monkeypatch):
    s = scheduled
    error = ProgrammingError("SELECT 1", {}, Exception("canceling statement due to statement timeout"))
    monkeypatch.setattr(s.runner, "deliver_saved_report", _failing_for(s.runner.deliver_saved_report, s.users["viewer"], error))
    sid = await schedule(s, s.reports[0], [s.users["viewer"], s.users["admin"]])
    await s.runner._deliver_schedule_async(sid, trigger="schedule", advance_clock=False)
    rows = _by_recipient(await deliveries(s, s.reports[0]))
    assert rows[s.users["viewer"]][0].subject.startswith("[TIMEOUT]")
    assert "[SQL" not in (rows[s.users["viewer"]][0].body_summary or "")
    assert [r.status for r in rows[s.users["admin"]]] == ["delivered"]


def test_recipient_safe_error_strips_driver_detail():
    from app.services.report_schedule_runner import is_statement_timeout, recipient_safe_error
    exc = RuntimeError("boom [SQL: select 1] [parameters: {'a': 1}] (Background on this error at: https://x)")
    text = recipient_safe_error(exc, timed_out=False, timeout_ms=90_000)
    assert text == "RuntimeError: boom"
    assert not is_statement_timeout(exc) and is_statement_timeout(TimeoutError())
    assert "90-second" in recipient_safe_error(exc, timed_out=True, timeout_ms=90_000)
