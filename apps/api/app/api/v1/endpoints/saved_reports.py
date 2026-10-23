"""P3-4 saved reports API — personal vs published, role-aware share."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.core.tenant_scope import tenant_id_from_user
from app.models.saved_reports import OverviewReportPin, SavedReport
from app.services.saved_report_access import (
    can_edit_owned_item,
    can_view_owned_item,
    item_to_dict,
    normalize_shared_roles,
    parse_user_id,
)
from app.semantics.registry import validate_metric_grain
from app.services.dashboard_definitions import CheckedDefinition, DefinitionRefused, check_definition

router = APIRouter()

# Same set as WIDGET_VISUALS and the 0048 check constraints.
Visual = Literal[
    "kpi", "table", "bar", "hbar", "stacked_bar", "line", "area", "pie", "donut",
    "combo", "dual_axis", "scatter", "pivot",
]
Visibility = Literal["personal", "published"]
PeriodGrain = Literal["week", "month", "quarter"]
_V1_QUERY_FIELDS = frozenset({"metric", "grains", "period_grain", "filters"})


class SavedReportCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    metric: str | None = Field(default=None, min_length=1)
    grains: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    visual: Visual = "kpi"
    period_grain: PeriodGrain | None = None
    visibility: Visibility = "personal"
    shared_roles: list[str] = Field(default_factory=list)
    # N-0116: v2 definition; when given, metric / grains / period_grain / filters are mirrored from it.
    definition_v2: dict[str, Any] | None = None


class SavedReportUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    metric: str | None = None
    grains: list[str] | None = None
    filters: dict[str, Any] | None = None
    visual: Visual | None = None
    period_grain: PeriodGrain | None = None
    visibility: Visibility | None = None
    shared_roles: list[str] | None = None
    # Sent: checked and stored. Sent as null: back to the v1 path. Not sent: kept, unless v1 query
    # fields (metric, grains, period_grain, filters) are sent, which make the report v1 again.
    definition_v2: dict[str, Any] | None = None


def _checked(definition_v2: dict[str, Any], tenant_id: str) -> CheckedDefinition:
    try:
        return check_definition(definition_v2, tenant_id=tenant_id)
    except DefinitionRefused as exc:
        raise exc.http() from exc


def _mirror_onto(row: SavedReport, checked: CheckedDefinition) -> None:
    row.metric_key = checked.v1.metric_key
    row.grains = list(checked.v1.grains)
    row.filters = dict(checked.v1.filters)
    row.period_grain = checked.v1.period_grain
    row.definition_v2 = checked.definition


class PublishBody(BaseModel):
    shared_roles: list[str] = Field(
        default_factory=list,
        description="Roles that may view when published; empty = all roles in tenant",
    )


def _visible_clause(user: dict | None):
    uid = parse_user_id(user)
    from app.services.saved_report_access import user_role_str

    role = user_role_str(user)
    if role == "admin":
        return True  # filtered only by tenant
    # personal owned OR published (role filter applied in Python for JSONB simplicity)
    if uid is not None:
        return or_(
            SavedReport.owner_user_id == uid,
            SavedReport.visibility == "published",
        )
    return SavedReport.visibility == "published"


@router.get("")
async def list_saved_reports(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
    visibility: str | None = Query(default=None),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    q = select(SavedReport).where(SavedReport.tenant_id == tid).order_by(SavedReport.updated_at.desc())
    clause = _visible_clause(user)
    if clause is not True:
        q = q.where(clause)
    if visibility in ("personal", "published"):
        q = q.where(SavedReport.visibility == visibility)
    rows = (await db.execute(q)).scalars().all()
    visible = [
        r
        for r in rows
        if can_view_owned_item(
            visibility=r.visibility,
            owner_user_id=r.owner_user_id,
            shared_roles=r.shared_roles,
            user=user,
        )
    ]
    pinned_ids: set[int] = set()
    uid = parse_user_id(user)
    if uid is not None and visible:
        pinned_ids = set(
            (
                await db.execute(
                    select(OverviewReportPin.saved_report_id).where(OverviewReportPin.user_id == uid)
                )
            ).scalars().all()
        )
    items = [
        {**item_to_dict(r, kind="report"), "overview_pinned": int(r.id) in pinned_ids}
        for r in visible
    ]
    return {"items": items, "count": len(items)}


@router.post("")
async def create_saved_report(
    body: SavedReportCreate,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    row = SavedReport(
        tenant_id=tid,
        owner_user_id=parse_user_id(user),
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        visibility=body.visibility,
        shared_roles=normalize_shared_roles(body.shared_roles),
        visual=body.visual,
    )
    if body.definition_v2 is not None:
        _mirror_onto(row, _checked(body.definition_v2, tid))
    else:
        if not body.metric:
            raise HTTPException(status_code=400, detail="Send metric (v1 report) or definition_v2 (v2 report).")
        validation = validate_metric_grain(
            body.metric, body.grains, tenant_id=tid, period_grain=body.period_grain
        )
        if not validation.ok:
            raise HTTPException(status_code=400, detail=validation.as_dict())
        row.metric_key = validation.metric_key or body.metric
        row.grains = list(validation.requested_grains)
        row.filters = dict(body.filters or {})
        row.period_grain = validation.period_grain
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return item_to_dict(row, kind="report")


@router.get("/{report_id}")
async def get_saved_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
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
        raise HTTPException(status_code=403, detail="Not allowed to view this report")
    return item_to_dict(row, kind="report")


async def _viewable_report(db: AsyncSession, report_id: int, user: dict | None) -> SavedReport:
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
        raise HTTPException(status_code=403, detail="Not allowed to view this report")
    return row


@router.put("/{report_id}/overview-pin")
async def pin_saved_report_on_overview(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    uid = parse_user_id(user)
    if uid is None:
        raise HTTPException(status_code=401, detail="Sign in to pin a report")
    row = await _viewable_report(db, report_id, user)
    existing = (
        await db.execute(
            select(OverviewReportPin).where(
                OverviewReportPin.user_id == uid,
                OverviewReportPin.saved_report_id == row.id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(OverviewReportPin(user_id=uid, saved_report_id=int(row.id)))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
    return {"saved_report_id": int(row.id), "overview_pinned": True}


@router.delete("/{report_id}/overview-pin")
async def unpin_saved_report_from_overview(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    uid = parse_user_id(user)
    if uid is None:
        raise HTTPException(status_code=401, detail="Sign in to unpin a report")
    row = await _viewable_report(db, report_id, user)
    existing = (
        await db.execute(
            select(OverviewReportPin).where(
                OverviewReportPin.user_id == uid,
                OverviewReportPin.saved_report_id == row.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.commit()
    return {"saved_report_id": int(row.id), "overview_pinned": False}


@router.patch("/{report_id}")
async def update_saved_report(
    report_id: int,
    body: SavedReportUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    row = await db.get(SavedReport, report_id)
    if row is None or row.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Saved report not found")
    if not can_edit_owned_item(owner_user_id=row.owner_user_id, user=user):
        raise HTTPException(status_code=403, detail="Not allowed to edit this report")

    sent = body.model_fields_set
    v2_sent = "definition_v2" in sent
    checked = _checked(body.definition_v2, tid) if v2_sent and body.definition_v2 is not None else None
    back_to_v1 = row.definition_v2 is not None and (
        (v2_sent and body.definition_v2 is None) or (not v2_sent and bool(_V1_QUERY_FIELDS & sent))
    )
    if body.name is not None:
        row.name = body.name.strip()
    if body.description is not None:
        row.description = body.description.strip() or None
    if body.visual is not None:
        row.visual = body.visual
    if body.visibility is not None:
        row.visibility = body.visibility
    if body.shared_roles is not None:
        row.shared_roles = normalize_shared_roles(body.shared_roles)
    if checked is not None:
        _mirror_onto(row, checked)
    elif row.definition_v2 is not None and not back_to_v1:
        pass  # v2 report, no query change: the definition and its v1 mirror stay as they are
    else:
        if body.filters is not None:
            row.filters = dict(body.filters)
        if back_to_v1:
            row.definition_v2 = None
    if checked is None and (back_to_v1 or (row.definition_v2 is None and (
        body.metric is not None or body.grains is not None or body.period_grain is not None
    ))):
        metric = body.metric or row.metric_key
        grains = body.grains if body.grains is not None else list(row.grains or [])
        period_grain = body.period_grain if body.period_grain is not None else row.period_grain
        if body.grains is not None and "period" not in grains:
            period_grain = None
        validation = validate_metric_grain(
            metric, grains, tenant_id=tid, period_grain=period_grain
        )
        if not validation.ok:
            raise HTTPException(status_code=400, detail=validation.as_dict())
        row.metric_key = validation.metric_key or metric
        row.grains = list(validation.requested_grains)
        row.period_grain = validation.period_grain

    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return item_to_dict(row, kind="report")


@router.post("/{report_id}/publish")
async def publish_saved_report(
    report_id: int,
    body: PublishBody,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    row = await db.get(SavedReport, report_id)
    if row is None or row.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Saved report not found")
    if not can_edit_owned_item(owner_user_id=row.owner_user_id, user=user):
        raise HTTPException(status_code=403, detail="Not allowed to publish this report")
    row.visibility = "published"
    row.shared_roles = normalize_shared_roles(body.shared_roles)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return item_to_dict(row, kind="report")


@router.delete("/{report_id}")
async def delete_saved_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    row = await db.get(SavedReport, report_id)
    if row is None or row.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Saved report not found")
    if not can_edit_owned_item(owner_user_id=row.owner_user_id, user=user):
        raise HTTPException(status_code=403, detail="Not allowed to delete this report")
    await db.delete(row)
    await db.commit()
    return {"ok": True, "id": report_id}
