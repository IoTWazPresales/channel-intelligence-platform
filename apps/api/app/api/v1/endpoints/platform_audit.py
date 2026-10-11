"""Admin read of the platform audit trail. Inserts happen on the write paths."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import Role, require_roles
from app.models.platform_audit import PlatformAuditEvent

router = APIRouter()


@router.get("/audit-log")
async def list_platform_audit(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(Role.ADMIN)),
    area: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    tenant_id = (user.get("tenant_id") or "default").strip() or "default"
    stmt = (
        select(PlatformAuditEvent)
        .where(PlatformAuditEvent.tenant_id == tenant_id)
        .order_by(PlatformAuditEvent.id.desc())
        .limit(limit)
    )
    if area:
        stmt = stmt.where(PlatformAuditEvent.area == area.strip().lower())
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "tenant_id": tenant_id,
        "count": len(rows),
        "events": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "actor": r.actor,
                "actor_user_id": str(r.actor_user_id) if r.actor_user_id is not None else None,
                "area": r.area,
                "action": r.action,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "detail_json": r.detail_json,
            }
            for r in rows
        ],
    }
