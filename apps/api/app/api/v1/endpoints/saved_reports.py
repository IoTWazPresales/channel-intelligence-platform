"""P3-4 saved reports API — personal vs published, role-aware share."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.core.tenant_scope import tenant_id_from_user
from app.models.saved_reports import SavedReport
from app.services.saved_report_access import (
    can_edit_owned_item,
    can_view_owned_item,
    item_to_dict,
    normalize_shared_roles,
    parse_user_id,
)
from app.semantics.registry import validate_metric_grain

router = APIRouter()

Visual = Literal["kpi", "table", "bar"]
Visibility = Literal["personal", "published"]


class SavedReportCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    metric: str = Field(..., min_length=1)
    grains: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    visual: Visual = "kpi"
    visibility: Visibility = "personal"
    shared_roles: list[str] = Field(default_factory=list)


class SavedReportUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    metric: str | None = None
    grains: list[str] | None = None
    filters: dict[str, Any] | None = None
    visual: Visual | None = None
    visibility: Visibility | None = None
    shared_roles: list[str] | None = None


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
    items = [
        item_to_dict(r, kind="report")
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
async def create_saved_report(
    body: SavedReportCreate,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    validation = validate_metric_grain(body.metric, body.grains, tenant_id=tid)
    if not validation.ok:
        raise HTTPException(status_code=400, detail=validation.as_dict())

    row = SavedReport(
        tenant_id=tid,
        owner_user_id=parse_user_id(user),
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        visibility=body.visibility,
        shared_roles=normalize_shared_roles(body.shared_roles),
        metric_key=validation.metric_key or body.metric,
        grains=list(validation.requested_grains),
        filters=dict(body.filters or {}),
        visual=body.visual,
    )
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
    if body.filters is not None:
        row.filters = dict(body.filters)
    if body.metric is not None or body.grains is not None:
        metric = body.metric or row.metric_key
        grains = body.grains if body.grains is not None else list(row.grains or [])
        validation = validate_metric_grain(metric, grains, tenant_id=tid)
        if not validation.ok:
            raise HTTPException(status_code=400, detail=validation.as_dict())
        row.metric_key = validation.metric_key or metric
        row.grains = list(validation.requested_grains)

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
