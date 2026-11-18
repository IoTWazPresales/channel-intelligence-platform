"""Wave 3 Phase C: operations health rules (no database, no files)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.services.ops_health import (
    FLAP_LIMIT,
    REPORT_RECEIPT_WINDOW_DAYS,
    backups_health,
    file_health,
    reports_health,
    services_health,
)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


def _local(dt: datetime) -> str:
    """The scripts write local 's' timestamps without a zone."""
    return dt.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")


def _status(*, beat_age=10, **comps):
    return {
        "supervisor": {"heartbeat": _local(NOW - timedelta(seconds=beat_age))},
        "components": {k: v for k, v in comps.items()},
    }


def test_services_ok_flapping_degraded_stale_unknown():
    healthy = {"state": "healthy", "launches": 2, "launches_30m": 1}
    ok = services_health(_status(api=healthy, worker=healthy, web=healthy), now=NOW)
    assert ok["state"] == "ok" and [c["name"] for c in ok["components"]] == ["api", "worker", "web"]

    flap = services_health(
        _status(
            api=healthy, worker={"state": "starting", "launches": 9, "launches_30m": FLAP_LIMIT + 1}
        ),
        now=NOW,
    )
    assert flap["state"] == "flapping" and "worker" in flap["detail"]
    at_limit = services_health(_status(api={**healthy, "launches_30m": FLAP_LIMIT}), now=NOW)
    assert at_limit["state"] == "ok"

    degraded = services_health(
        _status(api=healthy, web={"state": "needs build", "launches_30m": 0}), now=NOW
    )
    assert degraded["state"] == "degraded" and "web" in degraded["detail"]

    stale = services_health(_status(beat_age=600, api=healthy), now=NOW)
    assert stale["state"] == "stale" and stale["heartbeat_age_seconds"] >= 599

    assert services_health(None, now=NOW)["state"] == "unknown"


def test_backups_ok_stale_failed_unknown():
    good = {
        "result": "ok",
        "finished": _local(NOW - timedelta(hours=9)),
        "bytes": 10,
        "verified": True,
        "pruned": ["a"],
    }
    restore = {"result": "ok", "finished": _local(NOW - timedelta(days=3))}
    h = backups_health(good, restore, now=NOW)
    assert h["state"] == "ok" and h["backup"]["pruned"] == 1 and h["backup"]["age_hours"] == 9.0

    old = {**good, "finished": _local(NOW - timedelta(hours=30))}
    assert backups_health(old, restore, now=NOW)["backup"]["state"] == "stale"
    failed = {"result": "failed", "finished": _local(NOW), "error": "pg_dump failed with exit 1"}
    fh = backups_health(failed, restore, now=NOW)
    assert fh["state"] == "failed" and "pg_dump" in fh["backup"]["detail"]

    old_restore = {"result": "ok", "finished": _local(NOW - timedelta(days=9))}
    assert backups_health(good, old_restore, now=NOW)["state"] == "stale"
    assert (
        backups_health(good, {"result": "failed", "detail": "x"}, now=NOW)["restore"]["state"]
        == "failed"
    )
    none = backups_health(None, None, now=NOW)
    assert none["state"] == "unknown" and none["backup"]["state"] == "unknown"


def _reports(**kw):
    base = dict(
        late=0,
        missing=0,
        due=0,
        untracked_customers=0,
        newest_received=NOW - timedelta(days=2),
        expected_customers=3,
        now=NOW,
    )
    return reports_health(**{**base, **kw})


def test_reports_monday_rule_states():
    ok = _reports()
    assert ok["state"] == "ok" and ok["detail"] == "Every expected report has arrived."
    late = _reports(late=2)
    assert late["state"] == "late" and late["days_since_newest"] == 2.0
    assert _reports(late=1, missing=1, newest_received=None)["state"] == "missing"
    assert _reports(newest_received=None, expected_customers=0)["state"] == "unknown"


def test_reports_ok_needs_receipt_evidence():
    # Review finding P2: nothing late/missing is not proof that reports arrived.
    no_receipt = _reports(newest_received=None)
    assert no_receipt["state"] == "untracked"
    assert "Every expected report has arrived" not in no_receipt["detail"]
    assert "No report receipt has been recorded" in no_receipt["detail"]

    old = _reports(newest_received=NOW - timedelta(days=REPORT_RECEIPT_WINDOW_DAYS + 1))
    assert old["state"] == "untracked" and "outside" in old["detail"]
    edge = _reports(newest_received=NOW - timedelta(days=REPORT_RECEIPT_WINDOW_DAYS))
    assert edge["state"] == "ok"
    # A naive timestamp is read as UTC, not rejected.
    assert _reports(newest_received=(NOW - timedelta(days=1)).replace(tzinfo=None))["state"] == "ok"


def test_reports_due_is_pending_not_ok():
    pending = _reports(due=2)
    assert pending["state"] == "pending" and pending["due"] == 2
    assert "2 expected reports are due" in pending["detail"]
    assert _reports(due=2, newest_received=None)["state"] == "pending"


def test_reports_untracked_customers_are_reported_separately():
    untracked = _reports(untracked_customers=1)
    assert untracked["state"] == "untracked" and untracked["untracked_customers"] == 1
    assert "no tracking slot" in untracked["detail"]
    # Real problems outrank the unknowns; pending ranks below untracked.
    assert _reports(untracked_customers=1, late=1)["state"] == "late"
    assert _reports(untracked_customers=1, missing=1, late=1)["state"] == "missing"
    assert _reports(untracked_customers=1, due=1)["state"] == "untracked"
    for case in (untracked, _reports(due=1), _reports(late=1), _reports()):
        assert {"due", "late", "missing", "untracked_customers"} <= set(case)


def test_file_health_reads_the_script_files(tmp_path):
    (tmp_path / "always-on").mkdir()
    (tmp_path / "backups").mkdir()
    (tmp_path / "always-on" / "status.json").write_text(
        json.dumps(_status(api={"state": "healthy", "launches_30m": 0})), encoding="utf-8-sig"
    )
    (tmp_path / "backups" / "last_backup.json").write_text(
        json.dumps(
            {"result": "ok", "finished": _local(NOW - timedelta(hours=1)), "verified": True}
        ),
        encoding="utf-8",
    )
    (tmp_path / "backups" / "last_restore.json").write_text("not json", encoding="utf-8")
    h = file_health(tmp_path, now=NOW)
    assert h["services"]["state"] == "ok"
    assert h["backups"]["backup"]["state"] == "ok"
    assert h["backups"]["restore"]["state"] == "unknown"
    assert file_health(None, now=NOW)["services"]["state"] == "unknown"


@pytest.mark.parametrize(
    "receipt",
    [
        NOW + timedelta(seconds=1),
        NOW - timedelta(days=REPORT_RECEIPT_WINDOW_DAYS, seconds=1),
        NOW - timedelta(days=REPORT_RECEIPT_WINDOW_DAYS, hours=1),
    ],
)
def test_reports_reject_future_and_just_expired_receipts(receipt):
    report = _reports(newest_received=receipt)
    assert report["state"] == "untracked"
    assert report["detail"] != "Every expected report has arrived."


def test_overview_reads_due_and_current_tracking_without_database(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from app.api.v1.endpoints import ops

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(ops, "datetime", Clock)
    monkeypatch.setattr(ops, "get_settings", lambda: SimpleNamespace(cip_ops_state_dir=""))
    monkeypatch.setattr(ops, "file_health", lambda *args, **kwargs: {})
    db = SimpleNamespace(
        scalar=AsyncMock(side_effect=["forbidden_unit", 0, 0, 0, NOW, 2, 1]),
        execute=AsyncMock(side_effect=[
            Mock(), Mock(all=lambda: []), Mock(all=lambda: [("due", 1)]),
        ]),
    )
    out = asyncio.run(ops.ops_overview(
        db=db, user={"id": "1", "tenant_id": "ops-unit", "role": "admin"}, failed_limit=5,
    ))
    report = out["health"]["reports"]
    assert report["due"] == 1
    assert report["untracked_customers"] == 1
    assert report["state"] == "untracked"

    # Contract checks on the emitted queries: include pending slots and require this Monday's
    # report period. A loose recent-weeks range would allow an unadvanced tracker to read healthy.
    slots_query = db.execute.await_args_list[2].args[0].compile()
    assert ["due", "late", "missing"] in list(slots_query.params.values())
    tracking_query = db.scalar.await_args_list[-1].args[0].compile()
    today = NOW.astimezone().date()
    expected_week = today - timedelta(days=today.weekday() + 7)
    assert expected_week in tracking_query.params.values()
    assert "week_start_date =" in str(tracking_query)
