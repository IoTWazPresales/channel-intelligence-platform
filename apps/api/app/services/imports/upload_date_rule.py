"""Rows dated after the day their file was uploaded are not loaded (Warren 2026-10-22, N-0113).

A sell-through row whose period starts, or a distributor row whose sale or stock date falls, after
the upload day is almost always a wrong year (a week number read into the wrong year, or a typo). It
stays staged and is counted in the job's load report as ``dated_after_upload``. This holds for day,
week and month grains and for weeks dated through a confirmed year: the check is on the staged date.

The upload day is the job's creation date in the tenant's reporting timezone. With no timezone set
the upload day is unknown, so no row is held back by this rule (``reporting_timezone_not_configured``).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.services.commercial_tenant_profile import reporting_timezone

DATED_AFTER_UPLOAD = "dated_after_upload"
DATED_AFTER_UPLOAD_LABEL = "Dated after the upload date (check the year)"

# The same day in SQL, for a query that joins ``import_job j`` and binds ``:reporting_tz``.
# A NULL zone gives a NULL day, which no comparison passes.
UPLOAD_DAY_SQL = "(j.created_at AT TIME ZONE CAST(:reporting_tz AS text))::date"


def upload_day(job: Any) -> date | None:
    created = getattr(job, "created_at", None)
    if not isinstance(created, datetime):
        return None
    zone = reporting_timezone(str(getattr(job, "tenant_id", None) or "default"))
    if zone is None:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created.astimezone(ZoneInfo(zone)).date()


def dated_after(value: date | datetime | None, day: date | None) -> bool:
    if not isinstance(value, date) or day is None:
        return False
    d = value.date() if isinstance(value, datetime) else value
    return d > day
