"""Sync runners for report schedules (Celery beat + import-complete fan-out).

Async ``deliver_saved_report`` is reused via ``asyncio.run`` in a fresh event loop —
same pattern as lineup parse worker. Never call from inside an already-running loop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import AsyncSessionLocal
from app.models.report_delivery import ReportSchedule
from app.models.saved_reports import SavedReport
from app.services.report_delivery import deliver_saved_report, next_run_for_cadence

logger = logging.getLogger(__name__)

CALENDAR_CADENCES = frozenset({"weekly_monday_0700", "daily_0700"})
IMPORT_CADENCE = "on_import_complete"


def list_due_calendar_schedules(db: Session, *, now: datetime | None = None) -> list[ReportSchedule]:
    now = now or datetime.now(timezone.utc)
    return list(
        db.scalars(
            select(ReportSchedule).where(
                ReportSchedule.enabled.is_(True),
                ReportSchedule.cadence.in_(tuple(CALENDAR_CADENCES)),
                or_(ReportSchedule.next_run_at.is_(None), ReportSchedule.next_run_at <= now),
            )
        ).all()
    )


def list_import_complete_schedules(db: Session, *, tenant_id: str) -> list[ReportSchedule]:
    return list(
        db.scalars(
            select(ReportSchedule).where(
                ReportSchedule.enabled.is_(True),
                ReportSchedule.cadence == IMPORT_CADENCE,
                ReportSchedule.tenant_id == tenant_id,
            )
        ).all()
    )


async def _deliver_schedule_async(
    schedule_id: int,
    *,
    trigger: str,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        sched = await db.get(ReportSchedule, schedule_id)
        if sched is None or not sched.enabled:
            return {"schedule_id": schedule_id, "skipped": True, "reason": "missing_or_disabled"}
        if not sched.saved_report_id:
            return {"schedule_id": schedule_id, "skipped": True, "reason": "no_saved_report"}
        report = await db.get(SavedReport, sched.saved_report_id)
        if report is None:
            return {"schedule_id": schedule_id, "skipped": True, "reason": "saved_report_missing"}

        recipients = list(sched.subscriber_user_ids or [])
        if not recipients:
            recipients = [sched.owner_user_id] if sched.owner_user_id is not None else [None]

        delivery_ids: list[int] = []
        for rid in recipients:
            d = await deliver_saved_report(
                db,
                report=report,
                user=None,
                fmt=sched.format,  # type: ignore[arg-type]
                trigger=trigger,  # type: ignore[arg-type]
                recipient_user_id=int(rid) if rid is not None else None,
            )
            delivery_ids.append(int(d.id))

        now = datetime.now(timezone.utc)
        sched.last_run_at = now
        sched.next_run_at = next_run_for_cadence(sched.cadence, now=now)
        sched.updated_at = now
        await db.commit()
        return {
            "schedule_id": schedule_id,
            "deliveries": delivery_ids,
            "cadence": sched.cadence,
            "trigger": trigger,
        }


def run_schedule_delivery_sync(schedule_id: int, *, trigger: str) -> dict[str, Any]:
    return asyncio.run(_deliver_schedule_async(schedule_id, trigger=trigger))


def run_due_schedules_sync(*, now: datetime | None = None) -> dict[str, Any]:
    """Beat entrypoint: deliver all calendar cadences that are due."""
    from app.db.session_sync import SessionLocal

    now = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        due = list_due_calendar_schedules(db, now=now)
        ids = [int(s.id) for s in due]

    results: list[dict[str, Any]] = []
    for sid in ids:
        try:
            results.append(run_schedule_delivery_sync(sid, trigger="schedule"))
        except Exception as exc:
            logger.exception("report schedule delivery failed schedule_id=%s", sid)
            results.append({"schedule_id": sid, "error": str(exc)})

    return {"ok": True, "due_count": len(ids), "results": results}


def fanout_on_import_complete_sync(*, tenant_id: str) -> dict[str, Any]:
    """Event entrypoint: deliver all enabled on_import_complete schedules for tenant."""
    from app.db.session_sync import SessionLocal

    with SessionLocal() as db:
        rows = list_import_complete_schedules(db, tenant_id=tenant_id)
        ids = [int(s.id) for s in rows]

    results: list[dict[str, Any]] = []
    for sid in ids:
        try:
            results.append(run_schedule_delivery_sync(sid, trigger="import_event"))
        except Exception as exc:
            logger.exception("import_complete schedule delivery failed schedule_id=%s", sid)
            results.append({"schedule_id": sid, "error": str(exc)})

    return {"ok": True, "tenant_id": tenant_id, "schedule_count": len(ids), "results": results}


def dispatch_import_complete_report_fanout(*, tenant_id: str) -> None:
    """Best-effort enqueue (broker → in-process → sync inline). Never raises to caller."""
    try:
        from app.worker.celery_app import celery_app

        celery_app.send_task("reports.fanout_import_complete", args=[tenant_id])
        return
    except Exception:
        logger.exception(
            "reports.fanout_import_complete enqueue failed tenant_id=%s; running inline",
            tenant_id,
        )
    try:
        fanout_on_import_complete_sync(tenant_id=tenant_id)
    except Exception:
        logger.exception("reports.fanout_import_complete inline failed tenant_id=%s", tenant_id)
