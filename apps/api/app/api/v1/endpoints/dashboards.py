"""P3 dashboards API — first-class governed widgets (Unit 14B)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.core.tenant_scope import tenant_id_from_user
from app.models.saved_reports import Dashboard, DashboardWidget, SavedReport
from app.services.dashboard_widgets import (
    default_layout,
    validate_widget_query,
    widget_to_dict,
)
from app.services.saved_report_access import (
    can_edit_owned_item,
    can_view_owned_item,
    item_to_dict,
    normalize_shared_roles,
    parse_user_id,
    user_role_str,
)

router = APIRouter()

Visibility = Literal["personal", "published"]
Visual = Literal["kpi", "table", "bar", "line", "area"]
PeriodGrain = Literal["week", "month", "quarter"]


class WidgetSpec(BaseModel):
    id: int | None = None
    title: str = Field(..., min_length=1, max_length=200)
    visual: Visual = "kpi"
    metric_key: str = Field(..., min_length=1)
    grains: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    period_grain: PeriodGrain | None = None
    layout_json: dict[str, Any] | None = None
    saved_report_id: int | None = None
    sort_order: int = 0


class WidgetCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    visual: Visual = "kpi"
    metric_key: str = Field(..., min_length=1)
    grains: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    period_grain: PeriodGrain | None = None
    layout_json: dict[str, Any] | None = None
    saved_report_id: int | None = None
    sort_order: int | None = None


class WidgetUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    visual: Visual | None = None
    metric_key: str | None = None
    grains: list[str] | None = None
    filters: dict[str, Any] | None = None
    period_grain: PeriodGrain | None = None
    layout_json: dict[str, Any] | None = None
    sort_order: int | None = None


class WidgetsBody(BaseModel):
    widgets: list[WidgetSpec] = Field(default_factory=list)


class DashboardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    visibility: Visibility = "personal"
    shared_roles: list[str] = Field(default_factory=list)
    saved_report_ids: list[int] = Field(default_factory=list)
    widgets: list[WidgetSpec] = Field(default_factory=list)


class DashboardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    visibility: Visibility | None = None
    shared_roles: list[str] | None = None


class PublishBody(BaseModel):
    shared_roles: list[str] = Field(default_factory=list)


def _widget_load():
    return selectinload(Dashboard.widgets).selectinload(DashboardWidget.saved_report)


def _dashboard_dict(row: Dashboard) -> dict[str, Any]:
    out = item_to_dict(row, kind="dashboard")
    widgets = [widget_to_dict(w) for w in (row.widgets or [])]
    out["widgets"] = widgets
    # Temporary alias so a stale client listing still sees a collection.
    out["tiles"] = widgets
    return out


def _visible_clause(user: dict | None):
    uid = parse_user_id(user)
    role = user_role_str(user)
    if role == "admin":
        return True
    if uid is not None:
        return or_(Dashboard.owner_user_id == uid, Dashboard.visibility == "published")
    return Dashboard.visibility == "published"


def _apply_widget_fields(
    w: DashboardWidget,
    *,
    title: str,
    visual: str,
    metric_key: str,
    grains: list[str],
    filters: dict[str, Any],
    period_grain: str | None,
    layout_json: dict[str, Any] | None,
    sort_order: int,
    saved_report_id: int | None,
    tenant_id: str,
) -> None:
    validation = validate_widget_query(
        metric=metric_key,
        grains=grains,
        period_grain=period_grain,
        visual=visual,
        tenant_id=tenant_id,
    )
    w.title = title.strip()
    w.visual = visual
    w.metric_key = validation.metric_key or metric_key
    w.grains = list(validation.requested_grains)
    w.filters = dict(filters or {})
    w.period_grain = validation.period_grain
    w.layout_json = layout_json
    w.sort_order = sort_order
    w.saved_report_id = saved_report_id
    w.updated_at = datetime.now(timezone.utc)


async def _widget_from_saved_report(
    db: AsyncSession,
    *,
    dashboard_id: int,
    tenant_id: str,
    report_id: int,
    index: int,
    user: dict | None,
) -> DashboardWidget:
    report = await db.get(SavedReport, report_id)
    if report is None or report.tenant_id != tenant_id:
        raise HTTPException(status_code=400, detail=f"Saved report {report_id} not found in tenant")
    if not can_view_owned_item(
        visibility=report.visibility,
        owner_user_id=report.owner_user_id,
        shared_roles=report.shared_roles,
        user=user,
    ):
        raise HTTPException(status_code=403, detail=f"Cannot add report {report_id} to dashboard")
    validation = validate_widget_query(
        metric=report.metric_key,
        grains=list(report.grains or []),
        period_grain=report.period_grain,
        visual=report.visual,
        tenant_id=tenant_id,
    )
    return DashboardWidget(
        dashboard_id=dashboard_id,
        tenant_id=tenant_id,
        title=report.name,
        visual=report.visual,
        metric_key=validation.metric_key or report.metric_key,
        grains=list(validation.requested_grains),
        filters=dict(report.filters or {}),
        period_grain=validation.period_grain,
        layout_json=default_layout(index),
        saved_report_id=report.id,
        sort_order=index,
    )


async def _get_editable_dashboard(
    db: AsyncSession,
    dashboard_id: int,
    tid: str,
    user: dict | None,
) -> Dashboard:
    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == dashboard_id, Dashboard.tenant_id == tid)
        .options(_widget_load())
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if not can_edit_owned_item(owner_user_id=row.owner_user_id, user=user):
        raise HTTPException(status_code=403, detail="Not allowed to edit this dashboard")
    return row


async def _reload(db: AsyncSession, dashboard_id: int) -> Dashboard:
    result = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id).options(_widget_load())
    )
    return result.scalar_one()


@router.get("")
async def list_dashboards(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    q = (
        select(Dashboard)
        .where(Dashboard.tenant_id == tid)
        .options(_widget_load())
        .order_by(Dashboard.updated_at.desc())
    )
    clause = _visible_clause(user)
    if clause is not True:
        q = q.where(clause)
    rows = (await db.execute(q)).scalars().unique().all()
    items = [
        _dashboard_dict(r)
        for r in rows
        if can_view_owned_item(
            visibility=r.visibility,
            owner_user_id=r.owner_user_id,
            shared_roles=r.shared_roles,
            user=user,
        )
    ]
    return {"items": items, "count": len(items)}


@router.post("")
async def create_dashboard(
    body: DashboardCreate,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    row = Dashboard(
        tenant_id=tid,
        owner_user_id=parse_user_id(user),
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        visibility=body.visibility,
        shared_roles=normalize_shared_roles(body.shared_roles),
    )
    db.add(row)
    await db.flush()

    index = 0
    for spec in body.widgets:
        validate_widget_query(
            metric=spec.metric_key,
            grains=spec.grains,
            period_grain=spec.period_grain,
            visual=spec.visual,
            tenant_id=tid,
        )
        w = DashboardWidget(
            dashboard_id=row.id,
            tenant_id=tid,
            title=spec.title.strip(),
            visual=spec.visual,
            metric_key=spec.metric_key,
            grains=list(spec.grains or []),
            filters=dict(spec.filters or {}),
            period_grain=spec.period_grain,
            layout_json=spec.layout_json or default_layout(index),
            saved_report_id=spec.saved_report_id,
            sort_order=spec.sort_order if spec.sort_order else index,
        )
        _apply_widget_fields(
            w,
            title=spec.title,
            visual=spec.visual,
            metric_key=spec.metric_key,
            grains=spec.grains,
            filters=spec.filters,
            period_grain=spec.period_grain,
            layout_json=spec.layout_json or default_layout(index),
            sort_order=spec.sort_order if spec.sort_order else index,
            saved_report_id=spec.saved_report_id,
            tenant_id=tid,
        )
        db.add(w)
        index += 1

    for rid in body.saved_report_ids:
        db.add(
            await _widget_from_saved_report(
                db,
                dashboard_id=row.id,
                tenant_id=tid,
                report_id=rid,
                index=index,
                user=user,
            )
        )
        index += 1

    await db.commit()
    return _dashboard_dict(await _reload(db, row.id))


@router.get("/{dashboard_id}")
async def get_dashboard(
    dashboard_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == dashboard_id, Dashboard.tenant_id == tid)
        .options(_widget_load())
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if not can_view_owned_item(
        visibility=row.visibility,
        owner_user_id=row.owner_user_id,
        shared_roles=row.shared_roles,
        user=user,
    ):
        raise HTTPException(status_code=403, detail="Not allowed to view this dashboard")
    return _dashboard_dict(row)


@router.patch("/{dashboard_id}")
async def update_dashboard(
    dashboard_id: int,
    body: DashboardUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    row = await _get_editable_dashboard(db, dashboard_id, tid, user)
    if body.name is not None:
        row.name = body.name.strip()
    if body.description is not None:
        row.description = body.description.strip() or None
    if body.visibility is not None:
        row.visibility = body.visibility
    if body.shared_roles is not None:
        row.shared_roles = normalize_shared_roles(body.shared_roles)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _dashboard_dict(await _reload(db, row.id))


@router.put("/{dashboard_id}/widgets")
async def replace_dashboard_widgets(
    dashboard_id: int,
    body: WidgetsBody,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    row = await _get_editable_dashboard(db, dashboard_id, tid, user)
    existing = {int(w.id): w for w in (row.widgets or [])}
    seen: set[int] = set()
    for i, spec in enumerate(body.widgets):
        layout = spec.layout_json or default_layout(i)
        if spec.id is not None and spec.id in existing:
            w = existing[spec.id]
            _apply_widget_fields(
                w,
                title=spec.title,
                visual=spec.visual,
                metric_key=spec.metric_key,
                grains=spec.grains,
                filters=spec.filters,
                period_grain=spec.period_grain,
                layout_json=layout,
                sort_order=spec.sort_order if spec.sort_order else i,
                saved_report_id=spec.saved_report_id if spec.saved_report_id is not None else w.saved_report_id,
                tenant_id=tid,
            )
            seen.add(spec.id)
        else:
            w = DashboardWidget(dashboard_id=row.id, tenant_id=tid, title=spec.title.strip())
            _apply_widget_fields(
                w,
                title=spec.title,
                visual=spec.visual,
                metric_key=spec.metric_key,
                grains=spec.grains,
                filters=spec.filters,
                period_grain=spec.period_grain,
                layout_json=layout,
                sort_order=spec.sort_order if spec.sort_order else i,
                saved_report_id=spec.saved_report_id,
                tenant_id=tid,
            )
            db.add(w)
    for wid, w in existing.items():
        if wid not in seen:
            await db.delete(w)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _dashboard_dict(await _reload(db, row.id))


@router.post("/{dashboard_id}/widgets")
async def add_dashboard_widget(
    dashboard_id: int,
    body: WidgetCreate,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    row = await _get_editable_dashboard(db, dashboard_id, tid, user)
    index = len(row.widgets or [])
    w = DashboardWidget(dashboard_id=row.id, tenant_id=tid, title=body.title.strip())
    _apply_widget_fields(
        w,
        title=body.title,
        visual=body.visual,
        metric_key=body.metric_key,
        grains=body.grains,
        filters=body.filters,
        period_grain=body.period_grain,
        layout_json=body.layout_json or default_layout(index),
        sort_order=body.sort_order if body.sort_order is not None else index,
        saved_report_id=body.saved_report_id,
        tenant_id=tid,
    )
    db.add(w)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _dashboard_dict(await _reload(db, row.id))


@router.patch("/{dashboard_id}/widgets/{widget_id}")
async def update_dashboard_widget(
    dashboard_id: int,
    widget_id: int,
    body: WidgetUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    row = await _get_editable_dashboard(db, dashboard_id, tid, user)
    w = next((x for x in (row.widgets or []) if int(x.id) == widget_id), None)
    if w is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    metric = body.metric_key if body.metric_key is not None else w.metric_key
    grains = body.grains if body.grains is not None else list(w.grains or [])
    visual = body.visual if body.visual is not None else w.visual
    period_grain = body.period_grain if body.period_grain is not None else w.period_grain
    if body.period_grain is None and body.grains is not None and "period" not in grains:
        period_grain = None
    _apply_widget_fields(
        w,
        title=body.title if body.title is not None else w.title,
        visual=visual,
        metric_key=metric,
        grains=grains,
        filters=body.filters if body.filters is not None else dict(w.filters or {}),
        period_grain=period_grain,
        layout_json=body.layout_json if body.layout_json is not None else w.layout_json,
        sort_order=body.sort_order if body.sort_order is not None else int(w.sort_order or 0),
        saved_report_id=w.saved_report_id,
        tenant_id=tid,
    )
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _dashboard_dict(await _reload(db, row.id))


@router.delete("/{dashboard_id}/widgets/{widget_id}")
async def delete_dashboard_widget(
    dashboard_id: int,
    widget_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    row = await _get_editable_dashboard(db, dashboard_id, tid, user)
    w = next((x for x in (row.widgets or []) if int(x.id) == widget_id), None)
    if w is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    await db.delete(w)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _dashboard_dict(await _reload(db, row.id))


@router.post("/{dashboard_id}/widgets/{widget_id}/promote")
async def promote_widget_to_saved_report(
    dashboard_id: int,
    widget_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """P3-5 path: copy widget spec onto saved_report and link (schedules stay on saved_report)."""
    tid = tenant_id_from_user(user)
    row = await _get_editable_dashboard(db, dashboard_id, tid, user)
    w = next((x for x in (row.widgets or []) if int(x.id) == widget_id), None)
    if w is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    validation = validate_widget_query(
        metric=w.metric_key,
        grains=list(w.grains or []),
        period_grain=w.period_grain,
        visual=w.visual,
        tenant_id=tid,
    )
    report = SavedReport(
        tenant_id=tid,
        owner_user_id=parse_user_id(user),
        name=w.title,
        visibility="personal",
        shared_roles=[],
        metric_key=validation.metric_key or w.metric_key,
        grains=list(validation.requested_grains),
        filters=dict(w.filters or {}),
        visual=w.visual,
        period_grain=validation.period_grain,
    )
    db.add(report)
    await db.flush()
    w.saved_report_id = report.id
    w.updated_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    loaded = await _reload(db, row.id)
    widget = next(x for x in loaded.widgets if int(x.id) == widget_id)
    return {
        "dashboard": _dashboard_dict(loaded),
        "saved_report": item_to_dict(widget.saved_report, kind="report") if widget.saved_report else item_to_dict(report, kind="report"),
    }


@router.post("/{dashboard_id}/publish")
async def publish_dashboard(
    dashboard_id: int,
    body: PublishBody,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    row = await _get_editable_dashboard(db, dashboard_id, tid, user)
    row.visibility = "published"
    row.shared_roles = normalize_shared_roles(body.shared_roles)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _dashboard_dict(await _reload(db, row.id))


@router.delete("/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    row = await db.get(Dashboard, dashboard_id)
    if row is None or row.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if not can_edit_owned_item(owner_user_id=row.owner_user_id, user=user):
        raise HTTPException(status_code=403, detail="Not allowed to delete this dashboard")
    await db.delete(row)
    await db.commit()
    return {"ok": True, "id": dashboard_id}
