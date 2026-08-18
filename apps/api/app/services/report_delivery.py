"""P3-5 deliver saved reports into the in-app inbox (with vintage + missing-data alert)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_delivery import ReportDelivery, ReportSchedule
from app.models.saved_reports import SavedReport
from app.query.engine import execute_query
from app.services.report_export import detect_missing_data
from app.services.saved_report_access import parse_user_id

Format = Literal["xlsx", "pdf"]
Trigger = Literal["manual", "schedule", "import_event"]


def next_run_for_cadence(cadence: str, *, now: datetime | None = None) -> datetime:
    """Compute next run instant (UTC). weekly_monday_0700 = next Monday 07:00 UTC."""
    now = now or datetime.now(timezone.utc)
    if cadence == "daily_0700":
        candidate = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate = candidate + timedelta(days=1)
        return candidate
    if cadence == "on_import_complete":
        return now  # event-driven — next_run is informational
    # weekly_monday_0700
    candidate = now.replace(hour=7, minute=0, second=0, microsecond=0)
    days_ahead = (0 - candidate.weekday()) % 7  # Monday=0
    if days_ahead == 0 and candidate <= now:
        days_ahead = 7
    return candidate + timedelta(days=days_ahead)


async def deliver_saved_report(
    db: AsyncSession,
    *,
    report: SavedReport,
    user: dict | None,
    fmt: Format = "xlsx",
    trigger: Trigger = "manual",
    recipient_user_id: int | None = None,
) -> ReportDelivery:
    tid = report.tenant_id
    result = await execute_query(
        db,
        metric=report.metric_key,
        grains=list(report.grains or []),
        filters=dict(report.filters or {}),
        tenant_id=tid,
        skip_cache=False,
    )
    payload = result.as_dict()
    missing = detect_missing_data(payload)
    vintage = payload.get("data_vintage") or {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
    }
    value = payload.get("value")
    subject = f"{report.name} ({report.metric_key})"
    if missing:
        subject = f"[MISSING DATA] {subject}"
    summary = (
        f"status={payload.get('status')} value={value!r} "
        f"vintage={vintage} missing_data_alert={missing}"
    )
    rid = recipient_user_id if recipient_user_id is not None else parse_user_id(user)
    row = ReportDelivery(
        tenant_id=tid,
        recipient_user_id=rid,
        saved_report_id=int(report.id),
        channel="inbox",
        trigger=trigger,
        format=fmt,
        status="delivered" if payload.get("ok") else "failed",
        subject=subject,
        body_summary=summary[:2000],
        data_vintage=dict(vintage) if isinstance(vintage, dict) else {"raw": str(vintage)},
        missing_data_alert=bool(missing),
        metric_key=report.metric_key,
        value_preview=str(value) if value is not None else None,
        error_message=None if payload.get("ok") else (payload.get("message") or payload.get("status")),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def delivery_to_dict(row: ReportDelivery) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "tenant_id": row.tenant_id,
        "recipient_user_id": int(row.recipient_user_id) if row.recipient_user_id is not None else None,
        "saved_report_id": int(row.saved_report_id) if row.saved_report_id is not None else None,
        "dashboard_id": int(row.dashboard_id) if row.dashboard_id is not None else None,
        "channel": row.channel,
        "trigger": row.trigger,
        "format": row.format,
        "status": row.status,
        "subject": row.subject,
        "body_summary": row.body_summary,
        "data_vintage": row.data_vintage,
        "missing_data_alert": bool(row.missing_data_alert),
        "metric_key": row.metric_key,
        "value_preview": row.value_preview,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "recipient_email": row.recipient_email,
        "has_html_preview": bool((row.data_vintage or {}).get("html_preview"))
        or (row.metric_key == "shipping_digest" and row.channel == "inbox"),
    }


def schedule_to_dict(row: ReportSchedule) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "tenant_id": row.tenant_id,
        "owner_user_id": int(row.owner_user_id) if row.owner_user_id is not None else None,
        "saved_report_id": int(row.saved_report_id) if row.saved_report_id is not None else None,
        "dashboard_id": int(row.dashboard_id) if row.dashboard_id is not None else None,
        "name": row.name,
        "cadence": row.cadence,
        "format": row.format,
        "enabled": bool(row.enabled),
        "subscriber_user_ids": list(row.subscriber_user_ids or []),
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
