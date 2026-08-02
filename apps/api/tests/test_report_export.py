"""P3-5 report export + delivery helpers (no DB required)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.report_delivery import next_run_for_cadence
from app.services.report_export import build_pdf_bytes, build_xlsx_bytes, detect_missing_data


def test_xlsx_cover_declares_vintage():
    data = build_xlsx_bytes(
        title="WoC",
        metric_key="weeks_of_cover",
        grains=["distributor", "product"],
        value=13.6,
        rows=None,
        data_vintage={"as_of_utc": "2026-08-01T12:00:00+00:00", "pair_count": 2481},
        invariants=["latest_per_distributor_product_soh"],
        missing_data_alert=False,
    )
    assert data[:2] == b"PK"  # zip/xlsx
    from openpyxl import load_workbook
    from io import BytesIO

    wb = load_workbook(BytesIO(data))
    cover = wb["Cover"]
    assert "weeks_of_cover" in str(cover["A2"].value)
    assert "pair_count" in str(cover["A7"].value)
    assert "no" in str(cover["A8"].value).lower()


def test_pdf_starts_with_pdf_header_and_vintage():
    data = build_pdf_bytes(
        title="Fill rate",
        metric_key="fill_rate",
        grains=["period"],
        value=0.465,
        rows=[{"period": "26Q2", "value": 0.465}],
        data_vintage={"as_of_utc": "2026-08-01T12:00:00+00:00"},
        missing_data_alert=True,
    )
    assert data.startswith(b"%PDF-1.4")
    assert b"MISSING-DATA ALERT" in data
    assert b"Data vintage" in data


def test_detect_missing_data():
    assert detect_missing_data({"ok": False}) is True
    assert detect_missing_data({"ok": True, "value": None, "rows": []}) is True
    assert detect_missing_data({"ok": True, "value": 1.0, "rows": [], "data_vintage": {}}) is False
    assert (
        detect_missing_data(
            {"ok": True, "value": 0, "rows": [], "data_vintage": {"pair_count": 0}}
        )
        is True
    )


def test_next_run_weekly_monday():
    # Wednesday 2026-08-05 10:00 UTC → next Monday 2026-08-10 07:00
    now = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)
    nxt = next_run_for_cadence("weekly_monday_0700", now=now)
    assert nxt.weekday() == 0
    assert nxt.hour == 7
    assert nxt.date().isoformat() == "2026-08-10"


def test_next_run_daily_rolls_forward():
    now = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    nxt = next_run_for_cadence("daily_0700", now=now)
    assert nxt.hour == 7
    assert nxt.date().isoformat() == "2026-08-02"


def test_list_due_calendar_schedules_filters_cadence_and_next_run():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.report_schedule_runner import list_due_calendar_schedules

    now = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    due = SimpleNamespace(
        id=1,
        enabled=True,
        cadence="daily_0700",
        next_run_at=datetime(2026, 8, 2, 7, 0, tzinfo=timezone.utc),
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [due]
    rows = list_due_calendar_schedules(db, now=now)
    assert rows == [due]
    assert db.scalars.called


def test_list_import_complete_schedules_scoped_to_tenant():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.report_schedule_runner import list_import_complete_schedules

    row = SimpleNamespace(id=9, cadence="on_import_complete", tenant_id="default", enabled=True)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    assert list_import_complete_schedules(db, tenant_id="default") == [row]


def test_reports_beat_task_registered():
    from app.worker.celery_app import celery_app

    assert "reports.run_due_schedules" in celery_app.tasks
    assert "reports.fanout_import_complete" in celery_app.tasks
