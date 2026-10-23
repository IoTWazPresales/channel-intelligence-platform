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
from app.core.security import get_current_user, get_optional_current_user
from app.core.tenant_scope import tenant_id_from_user
from app.models.saved_reports import Dashboard, DashboardWidget, SavedReport
from app.services.dashboard_definitions import (
    CheckedDefinition,
    DefinitionRefused,
    check_dashboard_filters,
    check_definition,
)
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
# Same set as WIDGET_VISUALS and the 0048 check constraints.
Visual = Literal[
    "kpi", "table", "bar", "hbar", "stacked_bar", "line", "area", "pie", "donut",
    "combo", "dual_axis", "scatter", "pivot",
]
PeriodGrain = Literal["week", "month", "quarter"]
_V1_QUERY_FIELDS = frozenset({"metric_key", "grains", "period_grain", "filters"})


class WidgetSpec(BaseModel):
    id: int | None = None
    title: str = Field(..., min_length=1, max_length=200)
    visual: Visual = "kpi"
    metric_key: str | None = Field(default=None, min_length=1)
    grains: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    period_grain: PeriodGrain | None = None
    layout_json: dict[str, Any] | None = None
    saved_report_id: int | None = None
    sort_order: int = 0
    # N-0116: the v2 definition. When given, it is checked with the v2 planner and the v1 columns
    # are mirrored from it; metric_key / grains / period_grain / filters are then ignored.
    definition_v2: dict[str, Any] | None = None


class WidgetCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    visual: Visual = "kpi"
    metric_key: str | None = Field(default=None, min_length=1)
    grains: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    period_grain: PeriodGrain | None = None
    layout_json: dict[str, Any] | None = None
    saved_report_id: int | None = None
    sort_order: int | None = None
    definition_v2: dict[str, Any] | None = None


class WidgetUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    visual: Visual | None = None
    metric_key: str | None = None
    grains: list[str] | None = None
    filters: dict[str, Any] | None = None
    period_grain: PeriodGrain | None = None
    layout_json: dict[str, Any] | None = None
    sort_order: int | None = None
    # Sent: checked and stored (v1 columns mirrored). Sent as null: back to the v1 path.
    # Not sent: kept, unless v1 query fields are sent (then the widget becomes v1 again).
    definition_v2: dict[str, Any] | None = None


class LayoutItem(BaseModel):
    id: int
    x: int = Field(..., ge=0, le=1000)
    y: int = Field(..., ge=0, le=100000)
    w: int = Field(..., ge=1, le=12)
    h: int = Field(..., ge=1, le=1000)


class FromTemplateBody(BaseModel):
    key: str = Field(..., min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)


class WidgetsBody(BaseModel):
    widgets: list[WidgetSpec] = Field(default_factory=list)


class DashboardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    visibility: Visibility = "personal"
    shared_roles: list[str] = Field(default_factory=list)
    saved_report_ids: list[int] = Field(default_factory=list)
    widgets: list[WidgetSpec] = Field(default_factory=list)
    filters_json: dict[str, Any] | None = None


class DashboardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    visibility: Visibility | None = None
    shared_roles: list[str] | None = None
    filters_json: dict[str, Any] | None = None  # N-0116 s.2.3; validated, replaces the saved bar


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


def _checked(definition_v2: dict[str, Any], tenant_id: str) -> CheckedDefinition:
    try:
        return check_definition(definition_v2, tenant_id=tenant_id)
    except DefinitionRefused as exc:
        raise exc.http() from exc


def _apply_widget_fields(
    w: DashboardWidget,
    *,
    title: str,
    visual: str,
    metric_key: str | None,
    grains: list[str],
    filters: dict[str, Any],
    period_grain: str | None,
    layout_json: dict[str, Any] | None,
    sort_order: int,
    saved_report_id: int | None,
    tenant_id: str,
    definition_v2: dict[str, Any] | None = None,
    keep_v2: bool = False,
) -> None:
    """Set a widget's fields. Three query paths, decided by the caller:

    - ``definition_v2`` given: v2 planner check (400 on any refusal); v1 columns mirrored from it;
    - ``keep_v2``: the stored v2 definition and its mirrored v1 columns stay; no query check;
    - otherwise: v1 validation as before, and ``definition_v2`` is cleared (NULL = v1 path).
    """
    if definition_v2 is not None:
        checked = _checked(definition_v2, tenant_id)
        w.metric_key = checked.v1.metric_key
        w.grains = list(checked.v1.grains)
        w.filters = dict(checked.v1.filters)
        w.period_grain = checked.v1.period_grain
        w.definition_v2 = checked.definition
    elif not keep_v2:
        if not metric_key:
            raise HTTPException(status_code=400, detail="Send metric_key (v1 widget) or definition_v2 (v2 widget).")
        validation = validate_widget_query(
            metric=metric_key,
            grains=grains,
            period_grain=period_grain,
            visual=visual,
            tenant_id=tenant_id,
        )
        w.metric_key = validation.metric_key or metric_key
        w.grains = list(validation.requested_grains)
        w.filters = dict(filters or {})
        w.period_grain = validation.period_grain
        w.definition_v2 = None
    w.title = title.strip()
    w.visual = visual
    w.layout_json = layout_json
    w.sort_order = sort_order
    w.saved_report_id = saved_report_id
    w.updated_at = datetime.now(timezone.utc)


def _spec_keeps_v2(spec: WidgetSpec, w: DashboardWidget) -> bool:
    """PUT body without definition_v2 for a v2 widget whose mirrored v1 fields are unchanged."""
    if w.definition_v2 is None or spec.definition_v2 is not None:
        return False
    return (
        spec.metric_key in (None, w.metric_key)
        and list(spec.grains or []) == list(w.grains or [])
        and (spec.period_grain or None) == (w.period_grain or None)
        and dict(spec.filters or {}) == dict(w.filters or {})
    )


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
    if report.definition_v2 is not None:
        checked = _checked(report.definition_v2, tenant_id)
        return DashboardWidget(
            dashboard_id=dashboard_id,
            tenant_id=tenant_id,
            title=report.name,
            visual=report.visual,
            metric_key=checked.v1.metric_key,
            grains=list(checked.v1.grains),
            filters=dict(checked.v1.filters),
            period_grain=checked.v1.period_grain,
            definition_v2=checked.definition,
            layout_json=default_layout(index),
            saved_report_id=report.id,
            sort_order=index,
        )
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
    # populate_existing: the dashboard is already in this session with the widget list it had before
    # the write (expire_on_commit=False), so without it the response showed the old widgets (N-0116 F).
    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == dashboard_id)
        .options(_widget_load())
        .execution_options(populate_existing=True)
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
        filters_json=check_dashboard_filters(body.filters_json) if body.filters_json is not None else {},
    )
    db.add(row)
    await db.flush()

    index = 0
    for spec in body.widgets:
        w = DashboardWidget(dashboard_id=row.id, tenant_id=tid, title=spec.title.strip())
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
            definition_v2=spec.definition_v2,
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


@router.get("/templates")
async def list_dashboard_templates(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """N-0116 S14: the starter dashboards (key, title, description, what is left out and why)."""
    from app.services.dashboard_templates import template_list

    items = template_list()
    return {"items": items, "count": len(items)}


@router.post("/from-template")
async def create_dashboard_from_template(
    body: FromTemplateBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """N-0116 S14: a personal dashboard for the caller from a starter; every widget planner-checked first."""
    from app.services.dashboard_templates import TEMPLATE_BY_KEY

    t = TEMPLATE_BY_KEY.get(body.key.strip())
    if t is None:
        raise HTTPException(status_code=404, detail=f"Unknown starter {body.key!r}. Use GET /dashboards/templates.")
    uid = parse_user_id(user)
    if uid is None:
        raise HTTPException(status_code=401, detail="Sign in to create a dashboard from a starter")
    tid = tenant_id_from_user(user)
    checked = [(tw, _checked(tw.definition(), tid)) for tw in t.widgets]  # every widget checked before any write
    row = Dashboard(
        tenant_id=tid,
        owner_user_id=uid,
        name=(body.name or t.title).strip(),
        description=t.description,
        visibility="personal",
        shared_roles=[],
        filters_json=check_dashboard_filters(t.filters_json),
        template_key=t.key,
    )
    db.add(row)
    await db.flush()
    for i, (tw, c) in enumerate(checked):
        db.add(
            DashboardWidget(
                dashboard_id=row.id,
                tenant_id=tid,
                title=tw.title,
                visual=tw.visual,
                metric_key=c.v1.metric_key,
                grains=list(c.v1.grains),
                filters=dict(c.v1.filters),
                period_grain=c.v1.period_grain,
                definition_v2=c.definition,
                layout_json=tw.layout_json(),
                sort_order=i,
            )
        )
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
    if body.filters_json is not None:
        row.filters_json = check_dashboard_filters(body.filters_json)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _dashboard_dict(await _reload(db, row.id))


@router.patch("/{dashboard_id}/layout")
async def update_dashboard_layout(
    dashboard_id: int,
    body: list[LayoutItem],
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """N-0116 S3: write only ``layout_json`` (x, y, w, h). No query check, no deletes, nothing else."""
    tid = tenant_id_from_user(user)
    row = await _get_editable_dashboard(db, dashboard_id, tid, user)
    existing = {int(w.id): w for w in (row.widgets or [])}
    ids = [item.id for item in body]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise HTTPException(status_code=400, detail=f"Widget ids sent more than once: {dupes}. Nothing was written.")
    unknown = sorted(i for i in ids if i not in existing)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Widgets not on this dashboard: {unknown}. Nothing was written.")
    for item in body:
        w = existing[item.id]
        old = dict(w.layout_json) if isinstance(w.layout_json, dict) else {}
        w.layout_json = {**old, "x": item.x, "y": item.y, "w": item.w, "h": item.h}
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
                definition_v2=spec.definition_v2,
                keep_v2=_spec_keeps_v2(spec, w),
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
                definition_v2=spec.definition_v2,
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
        definition_v2=body.definition_v2,
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
    sent = body.model_fields_set
    new_v2 = body.definition_v2 if "definition_v2" in sent else None
    keep_v2 = "definition_v2" not in sent and w.definition_v2 is not None and not (_V1_QUERY_FIELDS & sent)
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
        definition_v2=new_v2,
        keep_v2=keep_v2,
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
    if w.definition_v2 is not None:
        # N-0116: the report carries the same v2 definition (re-checked) and its v1 mirror.
        checked = _checked(w.definition_v2, tid)
        report = SavedReport(
            tenant_id=tid,
            owner_user_id=parse_user_id(user),
            name=w.title,
            visibility="personal",
            shared_roles=[],
            metric_key=checked.v1.metric_key,
            grains=list(checked.v1.grains),
            filters=dict(checked.v1.filters),
            visual=w.visual,
            period_grain=checked.v1.period_grain,
            definition_v2=checked.definition,
        )
    else:
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
