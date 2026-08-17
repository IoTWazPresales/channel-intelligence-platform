"""P3-5 governed report export + delivery inbox + schedules."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.core.tenant_scope import tenant_id_from_user
from app.models.report_delivery import ReportDelivery, ReportSchedule
from app.models.saved_reports import SavedReport
from app.query.engine import execute_query
from app.services.report_delivery import (
    deliver_saved_report,
    delivery_to_dict,
    next_run_for_cadence,
    schedule_to_dict,
)
from app.services.report_export import build_pdf_bytes, build_xlsx_bytes, detect_missing_data
from app.services.saved_report_access import can_view_owned_item, parse_user_id

router = APIRouter()

Format = Literal["xlsx", "pdf"]
Cadence = Literal["weekly_monday_0700", "daily_0700", "on_import_complete"]


class ExportBody(BaseModel):
    metric: str = Field(..., min_length=1)
    grains: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    format: Format = "xlsx"
    title: str | None = None


class DeliverBody(BaseModel):
    format: Format = "xlsx"


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    saved_report_id: int
    cadence: Cadence = "weekly_monday_0700"
    format: Format = "xlsx"
    enabled: bool = True
    subscriber_user_ids: list[int] = Field(default_factory=list)


def _filename(stem: str, fmt: Format) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)[:80] or "report"
    return f"{safe}.{fmt}"


def _file_response(data: bytes, filename: str, fmt: Format) -> StreamingResponse:
    media = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if fmt == "xlsx"
        else "application/pdf"
    )
    return StreamingResponse(
        BytesIO(data),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _export_from_result(
    *,
    title: str,
    metric_key: str,
    grains: list[str],
    result_payload: dict[str, Any],
    fmt: Format,
) -> StreamingResponse:
    missing = detect_missing_data(result_payload)
    kwargs = dict(
        title=title,
        metric_key=metric_key,
        grains=grains,
        value=result_payload.get("value"),
        rows=result_payload.get("rows"),
        data_vintage=result_payload.get("data_vintage"),
        invariants=result_payload.get("invariants_applied") or [],
        missing_data_alert=missing,
    )
    data = build_xlsx_bytes(**kwargs) if fmt == "xlsx" else build_pdf_bytes(**kwargs)
    return _file_response(data, _filename(title or metric_key, fmt), fmt)


@router.post("/export")
async def export_ad_hoc(
    body: ExportBody,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
):
    """Export governed metric query as xlsx/pdf — vintage declared on cover."""
    tid = tenant_id_from_user(user)
    result = await execute_query(
        db,
        metric=body.metric,
        grains=body.grains,
        filters=body.filters,
        tenant_id=tid,
    )
    if result.status == "refused":
        raise HTTPException(status_code=400, detail=result.as_dict())
    payload = result.as_dict()
    title = body.title or f"{result.metric_key} report"
    return await _export_from_result(
        title=title,
        metric_key=result.metric_key or body.metric,
        grains=result.grains,
        result_payload=payload,
        fmt=body.format,
    )


@router.get("/saved/{report_id}/export")
async def export_saved_report(
    report_id: int,
    format: Format = Query(default="xlsx"),
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
):
    tid = tenant_id_from_user(user)
    row = await db.get(SavedReport, report_id)
    if row is None or row.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Saved report not found")
    if not can_view_owned_item(
        visibility=row.visibility,
        owner_user_id=row.owner_user_id,
        shared_roles=row.shared_roles,
        user=user,
    ):
        raise HTTPException(status_code=403, detail="Not allowed")
    result = await execute_query(
        db,
        metric=row.metric_key,
        grains=list(row.grains or []),
        filters=dict(row.filters or {}),
        tenant_id=tid,
    )
    return await _export_from_result(
        title=row.name,
        metric_key=row.metric_key,
        grains=list(row.grains or []),
        result_payload=result.as_dict(),
        fmt=format,
    )


@router.post("/saved/{report_id}/deliver")
async def deliver_saved_report_endpoint(
    report_id: int,
    body: DeliverBody,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Run report and land a vintage-stamped message in the recipient inbox."""
    tid = tenant_id_from_user(user)
    row = await db.get(SavedReport, report_id)
    if row is None or row.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Saved report not found")
    if not can_view_owned_item(
        visibility=row.visibility,
        owner_user_id=row.owner_user_id,
        shared_roles=row.shared_roles,
        user=user,
    ):
        raise HTTPException(status_code=403, detail="Not allowed")
    delivery = await deliver_saved_report(
        db, report=row, user=user, fmt=body.format, trigger="manual"
    )
    return delivery_to_dict(delivery)


@router.get("/inbox")
async def list_inbox(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    uid = parse_user_id(user)
    q = (
        select(ReportDelivery)
        .where(ReportDelivery.tenant_id == tid)
        .order_by(ReportDelivery.created_at.desc())
        .limit(limit)
    )
    if uid is not None:
        from sqlalchemy import or_

        role = (user or {}).get("role")
        role_s = role.value if hasattr(role, "value") else str(role or "viewer")
        if role_s != "admin":
            q = q.where(
                or_(
                    ReportDelivery.recipient_user_id == uid,
                    ReportDelivery.recipient_user_id.is_(None),
                )
            )
    rows = (await db.execute(q)).scalars().all()
    return {"items": [delivery_to_dict(r) for r in rows], "count": len(rows)}


@router.get("/schedules")
async def list_schedules(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    rows = (
        await db.execute(
            select(ReportSchedule)
            .where(ReportSchedule.tenant_id == tid)
            .order_by(ReportSchedule.updated_at.desc())
        )
    ).scalars().all()
    return {"items": [schedule_to_dict(r) for r in rows], "count": len(rows)}


@router.post("/schedules")
async def create_schedule(
    body: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    report = await db.get(SavedReport, body.saved_report_id)
    if report is None or report.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Saved report not found")
    row = ReportSchedule(
        tenant_id=tid,
        owner_user_id=parse_user_id(user),
        saved_report_id=body.saved_report_id,
        name=body.name.strip(),
        cadence=body.cadence,
        format=body.format,
        enabled=body.enabled,
        subscriber_user_ids=list(body.subscriber_user_ids or []),
        next_run_at=next_run_for_cadence(body.cadence),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return schedule_to_dict(row)


@router.post("/schedules/{schedule_id}/run-now")
async def run_schedule_now(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Manual/ops trigger. Calendar catch-up is the API poller + beat interval, not this path."""
    tid = tenant_id_from_user(user)
    sched = await db.get(ReportSchedule, schedule_id)
    if sched is None or sched.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if not sched.saved_report_id:
        raise HTTPException(status_code=400, detail="Schedule has no saved_report_id")
    report = await db.get(SavedReport, sched.saved_report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Saved report missing")

    deliveries = []
    recipients = list(sched.subscriber_user_ids or [])
    if not recipients:
        recipients = [parse_user_id(user)]
    for rid in recipients:
        d = await deliver_saved_report(
            db,
            report=report,
            user=user,
            fmt=sched.format,  # type: ignore[arg-type]
            trigger="schedule",
            recipient_user_id=int(rid) if rid is not None else None,
        )
        deliveries.append(delivery_to_dict(d))

    sched.last_run_at = datetime.now(timezone.utc)
    sched.next_run_at = next_run_for_cadence(sched.cadence)
    sched.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"schedule": schedule_to_dict(sched), "deliveries": deliveries}
