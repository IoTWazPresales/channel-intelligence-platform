"""Admin steward audit read API (P2-3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import Role, get_current_user, require_roles
from app.models.steward_audit import StewardAuditEvent

router = APIRouter()


@router.get("/steward-audit")
async def list_steward_audit(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(Role.ADMIN, Role.STEWARD)),
    importer: str | None = Query(default=None),
    import_job_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    tenant_id = (user.get("tenant_id") or "default").strip() or "default"
    stmt = (
        select(StewardAuditEvent)
        .where(StewardAuditEvent.tenant_id == tenant_id)
        .order_by(StewardAuditEvent.id.desc())
        .limit(limit)
    )
    if importer:
        stmt = stmt.where(StewardAuditEvent.importer == importer.strip().lower())
    if import_job_id is not None:
        stmt = stmt.where(StewardAuditEvent.import_job_id == import_job_id)
    if action:
        stmt = stmt.where(StewardAuditEvent.action == action.strip().lower())

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "tenant_id": tenant_id,
        "count": len(rows),
        "events": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "actor": r.actor,
                "actor_user_id": str(r.actor_user_id) if r.actor_user_id is not None else None,
                "action": r.action,
                "importer": r.importer,
                "entity_type": r.entity_type,
                "entity_token": r.entity_token,
                "import_job_id": r.import_job_id,
                "candidate_id": r.candidate_id,
                "target_dim": r.target_dim,
                "target_id": r.target_id,
                "payload_json": r.payload_json,
            }
            for r in rows
        ],
    }
