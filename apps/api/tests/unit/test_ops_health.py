"""Wave 3 Phase C: operations health rules (no database, no files)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.services.ops_health import (
    FLAP_LIMIT,
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


def test_reports_monday_rule_states():
    received = NOW - timedelta(days=2)
    assert (
        reports_health(late=0, missing=0, newest_received=received, expected_customers=3, now=NOW)[
            "state"
        ]
        == "ok"
    )
    late = reports_health(
        late=2, missing=0, newest_received=received, expected_customers=3, now=NOW
    )
    assert late["state"] == "late" and late["days_since_newest"] == 2.0
    assert (
        reports_health(late=1, missing=1, newest_received=None, expected_customers=3, now=NOW)[
            "state"
        ]
        == "missing"
    )
    assert (
        reports_health(late=0, missing=0, newest_received=None, expected_customers=0, now=NOW)[
            "state"
        ]
        == "unknown"
    )


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
