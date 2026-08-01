"""P3-4 dashboards API — compose saved reports; personal vs published."""

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
from app.models.saved_reports import Dashboard, DashboardTile, SavedReport
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


class DashboardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    visibility: Visibility = "personal"
    shared_roles: list[str] = Field(default_factory=list)
    saved_report_ids: list[int] = Field(default_factory=list)


class DashboardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    visibility: Visibility | None = None
    shared_roles: list[str] | None = None


class TileSpec(BaseModel):
    saved_report_id: int
    sort_order: int = 0
    title_override: str | None = None
    layout_json: dict[str, Any] | None = None


class TilesBody(BaseModel):
    tiles: list[TileSpec] = Field(default_factory=list)


class PublishBody(BaseModel):
    shared_roles: list[str] = Field(default_factory=list)


def _dashboard_dict(row: Dashboard) -> dict[str, Any]:
    out = item_to_dict(row, kind="dashboard")
    tiles = []
    for t in row.tiles or []:
        tiles.append(
            {
                "id": int(t.id),
                "saved_report_id": int(t.saved_report_id),
                "sort_order": int(t.sort_order),
                "title_override": t.title_override,
                "layout_json": t.layout_json,
                "report": item_to_dict(t.saved_report, kind="report") if t.saved_report else None,
            }
        )
    out["tiles"] = tiles
    return out


def _visible_clause(user: dict | None):
    uid = parse_user_id(user)
    role = user_role_str(user)
    if role == "admin":
        return True
    if uid is not None:
        return or_(Dashboard.owner_user_id == uid, Dashboard.visibility == "published")
    return Dashboard.visibility == "published"


@router.get("")
async def list_dashboards(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    q = (
        select(Dashboard)
        .where(Dashboard.tenant_id == tid)
        .options(selectinload(Dashboard.tiles).selectinload(DashboardTile.saved_report))
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

    for i, rid in enumerate(body.saved_report_ids):
        report = await db.get(SavedReport, rid)
        if report is None or report.tenant_id != tid:
            raise HTTPException(status_code=400, detail=f"Saved report {rid} not found in tenant")
        if not can_view_owned_item(
            visibility=report.visibility,
            owner_user_id=report.owner_user_id,
            shared_roles=report.shared_roles,
            user=user,
        ):
            raise HTTPException(status_code=403, detail=f"Cannot add report {rid} to dashboard")
        db.add(
            DashboardTile(
                dashboard_id=row.id,
                saved_report_id=rid,
                sort_order=i,
            )
        )

    await db.commit()
    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == row.id)
        .options(selectinload(Dashboard.tiles).selectinload(DashboardTile.saved_report))
    )
    loaded = result.scalar_one()
    return _dashboard_dict(loaded)


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
        .options(selectinload(Dashboard.tiles).selectinload(DashboardTile.saved_report))
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
    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == dashboard_id, Dashboard.tenant_id == tid)
        .options(selectinload(Dashboard.tiles).selectinload(DashboardTile.saved_report))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if not can_edit_owned_item(owner_user_id=row.owner_user_id, user=user):
        raise HTTPException(status_code=403, detail="Not allowed to edit this dashboard")

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
    await db.refresh(row)
    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == row.id)
        .options(selectinload(Dashboard.tiles).selectinload(DashboardTile.saved_report))
    )
    return _dashboard_dict(result.scalar_one())


@router.put("/{dashboard_id}/tiles")
async def replace_dashboard_tiles(
    dashboard_id: int,
    body: TilesBody,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == dashboard_id, Dashboard.tenant_id == tid)
        .options(selectinload(Dashboard.tiles))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if not can_edit_owned_item(owner_user_id=row.owner_user_id, user=user):
        raise HTTPException(status_code=403, detail="Not allowed to edit this dashboard")

    for existing in list(row.tiles or []):
        await db.delete(existing)
    await db.flush()

    for i, tile in enumerate(body.tiles):
        report = await db.get(SavedReport, tile.saved_report_id)
        if report is None or report.tenant_id != tid:
            raise HTTPException(
                status_code=400, detail=f"Saved report {tile.saved_report_id} not found"
            )
        db.add(
            DashboardTile(
                dashboard_id=row.id,
                saved_report_id=tile.saved_report_id,
                sort_order=tile.sort_order if tile.sort_order else i,
                title_override=tile.title_override,
                layout_json=tile.layout_json,
            )
        )
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == row.id)
        .options(selectinload(Dashboard.tiles).selectinload(DashboardTile.saved_report))
    )
    return _dashboard_dict(result.scalar_one())


@router.post("/{dashboard_id}/publish")
async def publish_dashboard(
    dashboard_id: int,
    body: PublishBody,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == dashboard_id, Dashboard.tenant_id == tid)
        .options(selectinload(Dashboard.tiles).selectinload(DashboardTile.saved_report))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if not can_edit_owned_item(owner_user_id=row.owner_user_id, user=user):
        raise HTTPException(status_code=403, detail="Not allowed to publish this dashboard")
    row.visibility = "published"
    row.shared_roles = normalize_shared_roles(body.shared_roles)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.id == row.id)
        .options(selectinload(Dashboard.tiles).selectinload(DashboardTile.saved_report))
    )
    return _dashboard_dict(result.scalar_one())


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
