"""Sync runners for report schedules (Celery beat + import-complete fan-out).

Calendar cadence (``weekly_monday_0700`` / ``daily_0700``) still owns *when a run
is due* via ``next_run_at``. A missed due instant is caught up the next time a
poller runs — API startup, in-process interval, or Celery beat — not only at
exactly 07:00 UTC while a beat process happens to be alive.

Async ``deliver_saved_report`` is reused via ``asyncio.run`` in a fresh event loop —
same pattern as lineup parse worker. Never call from inside an already-running loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select, text, update
from sqlalchemy.orm import Session

from app.db.session import AsyncSessionLocal
from app.models.report_delivery import ReportDelivery, ReportSchedule
from app.models.saved_reports import SavedReport
from app.services.report_delivery import deliver_saved_report, next_run_for_cadence

logger = logging.getLogger(__name__)

CALENDAR_CADENCES = frozenset({"weekly_monday_0700", "daily_0700"})
IMPORT_CADENCE = "on_import_complete"

_DEFAULT_POLL_SECONDS = 60
_DEFAULT_STATEMENT_TIMEOUT_MS = 90_000

_poller_lock = threading.Lock()
_poller_started = False


def report_schedule_poll_enabled() -> bool:
    """Startup/interval catch-up. Off in pytest; ``CIP_REPORT_SCHEDULE_CATCHUP=0`` disables."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    raw = (os.environ.get("CIP_REPORT_SCHEDULE_CATCHUP") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def report_schedule_poll_interval_seconds() -> int:
    try:
        raw = int(os.environ.get("CIP_REPORT_SCHEDULE_POLL_SECONDS") or _DEFAULT_POLL_SECONDS)
    except ValueError:
        raw = _DEFAULT_POLL_SECONDS
    return max(15, min(raw, 3600))


def report_schedule_statement_timeout_ms() -> int:
    try:
        raw = int(
            os.environ.get("CIP_REPORT_SCHEDULE_STATEMENT_TIMEOUT_MS")
            or _DEFAULT_STATEMENT_TIMEOUT_MS
        )
    except ValueError:
        raw = _DEFAULT_STATEMENT_TIMEOUT_MS
    return max(5_000, min(raw, 300_000))


def list_due_calendar_schedules(
    db: Session,
    *,
    now: datetime | None = None,
    for_update: bool = False,
) -> list[ReportSchedule]:
    now = now or datetime.now(timezone.utc)
    stmt = select(ReportSchedule).where(
        ReportSchedule.enabled.is_(True),
        ReportSchedule.cadence.in_(tuple(CALENDAR_CADENCES)),
        or_(ReportSchedule.next_run_at.is_(None), ReportSchedule.next_run_at <= now),
    )
    if for_update:
        stmt = stmt.with_for_update(skip_locked=True)
    return list(db.scalars(stmt).all())


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


def claim_due_calendar_schedule_ids(db: Session, *, now: datetime | None = None) -> list[int]:
    """Advance ``next_run_at`` for due rows so two pollers cannot double-deliver.

    One missed Monday is one catch-up attempt. Timeout/failure still writes a
    failed inbox row — missing data is the alert.
    """
    now = now or datetime.now(timezone.utc)
    due = list_due_calendar_schedules(db, now=now, for_update=True)
    claimed: list[int] = []
    for sched in due:
        nxt = next_run_for_cadence(str(sched.cadence), now=now)
        result = db.execute(
            update(ReportSchedule)
            .where(
                ReportSchedule.id == int(sched.id),
                ReportSchedule.enabled.is_(True),
                or_(ReportSchedule.next_run_at.is_(None), ReportSchedule.next_run_at <= now),
            )
            .values(last_run_at=now, next_run_at=nxt, updated_at=now)
        )
        if int(result.rowcount or 0) > 0:
            claimed.append(int(sched.id))
    if claimed:
        db.commit()
    return claimed


async def _write_failed_delivery(
    db,
    *,
    sched: ReportSchedule,
    report: SavedReport | None,
    trigger: str,
    error: str,
) -> None:
    now = datetime.now(timezone.utc)
    name = report.name if report is not None else f"schedule {sched.id}"
    metric = report.metric_key if report is not None else None
    recipients = list(sched.subscriber_user_ids or [])
    if not recipients:
        recipients = [sched.owner_user_id] if sched.owner_user_id is not None else [None]
    timeoutish = "timeout" in error.lower() or "canceling statement" in error.lower()
    prefix = "[TIMEOUT]" if timeoutish else "[FAILED]"
    for rid in recipients:
        db.add(
            ReportDelivery(
                tenant_id=sched.tenant_id,
                recipient_user_id=int(rid) if rid is not None else None,
                saved_report_id=int(report.id) if report is not None else sched.saved_report_id,
                channel="inbox",
                trigger=trigger,  # type: ignore[arg-type]
                format=sched.format,  # type: ignore[arg-type]
                status="failed",
                subject=f"{prefix} {name}",
                body_summary=error[:2000],
                data_vintage={"as_of_utc": now.isoformat(), "catchup": True},
                missing_data_alert=True,
                metric_key=metric,
                value_preview=None,
                error_message=error[:2000],
            )
        )
    await db.commit()


async def _deliver_schedule_async(
    schedule_id: int,
    *,
    trigger: str,
    advance_clock: bool = True,
) -> dict[str, Any]:
    timeout_ms = report_schedule_statement_timeout_ms()
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
        cadence = sched.cadence

        try:
            delivery_ids: list[int] = []
            for rid in recipients:
                # LOCAL so the cap applies to execute_query and does not leak onto pooled connections.
                await db.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
                d = await deliver_saved_report(
                    db,
                    report=report,
                    user=None,
                    fmt=sched.format,  # type: ignore[arg-type]
                    trigger=trigger,  # type: ignore[arg-type]
                    recipient_user_id=int(rid) if rid is not None else None,
                )
                delivery_ids.append(int(d.id))
        except Exception as exc:
            logger.exception("report schedule delivery failed schedule_id=%s", schedule_id)
            await db.rollback()
            sched = await db.get(ReportSchedule, schedule_id)
            report = None
            if sched is not None and sched.saved_report_id:
                report = await db.get(SavedReport, sched.saved_report_id)
            if sched is not None:
                await _write_failed_delivery(
                    db,
                    sched=sched,
                    report=report,
                    trigger=trigger,
                    error=f"{type(exc).__name__}: {exc} (statement_timeout_ms={timeout_ms})",
                )
            if advance_clock:
                now = datetime.now(timezone.utc)
                sched = await db.get(ReportSchedule, schedule_id)
                if sched is not None:
                    sched.last_run_at = now
                    sched.next_run_at = next_run_for_cadence(sched.cadence, now=now)
                    sched.updated_at = now
                    await db.commit()
            return {
                "schedule_id": schedule_id,
                "ok": False,
                "error": str(exc),
                "cadence": cadence,
                "trigger": trigger,
            }

        if advance_clock:
            now = datetime.now(timezone.utc)
            sched.last_run_at = now
            sched.next_run_at = next_run_for_cadence(sched.cadence, now=now)
            sched.updated_at = now
            await db.commit()
        return {
            "schedule_id": schedule_id,
            "ok": True,
            "deliveries": delivery_ids,
            "cadence": cadence,
            "trigger": trigger,
        }


def run_schedule_delivery_sync(schedule_id: int, *, trigger: str) -> dict[str, Any]:
    return asyncio.run(_deliver_schedule_async(schedule_id, trigger=trigger, advance_clock=True))


def run_due_schedules_sync(*, now: datetime | None = None) -> dict[str, Any]:
    """Deliver every calendar schedule whose ``next_run_at`` is due (including catch-up)."""
    from app.db.session_sync import SessionLocal

    now = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        ids = claim_due_calendar_schedule_ids(db, now=now)

    results: list[dict[str, Any]] = []
    for sid in ids:
        try:
            results.append(
                asyncio.run(
                    _deliver_schedule_async(sid, trigger="schedule", advance_clock=False)
                )
            )
        except Exception as exc:
            logger.exception("report schedule delivery failed schedule_id=%s", sid)
            results.append({"schedule_id": sid, "error": str(exc)})

    return {"ok": True, "due_count": len(ids), "claimed": ids, "results": results}


def run_due_schedules_safe(*, reason: str) -> dict[str, Any]:
    try:
        out = run_due_schedules_sync()
        logger.warning("report schedule poll reason=%s %s", reason, out)
        return out
    except Exception:
        logger.exception("report schedule poll failed reason=%s", reason)
        return {"ok": False, "reason": reason}


def spawn_report_schedule_poller() -> None:
    """Catch up missed due rows immediately, then poll while this process stays up.

    Does not require Celery beat (Windows solo leaves beat off — BACKLOG-038).
    """
    global _poller_started
    if not report_schedule_poll_enabled():
        logger.warning("report schedule poller skipped (pytest or CIP_REPORT_SCHEDULE_CATCHUP=0)")
        return
    with _poller_lock:
        if _poller_started:
            return
        _poller_started = True
    interval = report_schedule_poll_interval_seconds()

    def _loop() -> None:
        run_due_schedules_safe(reason="startup")
        while True:
            time.sleep(interval)
            run_due_schedules_safe(reason="interval")

    threading.Thread(target=_loop, name="cip-report-schedule-poll", daemon=True).start()
    logger.warning(
        "report schedule poller started interval=%ss (missed due rows fire on startup)",
        interval,
    )


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
