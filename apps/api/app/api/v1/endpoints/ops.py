"""Admin ops / monitoring endpoints (P2-5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import Role, require_roles
from app.core.tenant_scope import tenant_id_from_user, where_tenant
from app.models.ingestion import ImportJob

router = APIRouter()


@router.get("/ops/overview")
async def ops_overview(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(Role.ADMIN, Role.STEWARD)),
    failed_limit: int = Query(default=25, ge=1, le=100),
):
    """Failed / running import jobs + counts for the caller's tenant."""
    tid = tenant_id_from_user(user)
    since = datetime.now(timezone.utc) - timedelta(days=14)
    db_name = await db.scalar(text("SELECT current_database()"))
    await db.execute(text("SELECT 1"))

    failed_count = await db.scalar(
        select(func.count())
        .select_from(ImportJob)
        .where(where_tenant(ImportJob.tenant_id, user))
        .where(ImportJob.status == "failed")
        .where(ImportJob.archived_at.is_(None))
    ) or 0
    running_count = await db.scalar(
        select(func.count())
        .select_from(ImportJob)
        .where(where_tenant(ImportJob.tenant_id, user))
        .where(ImportJob.status.in_(("running", "pending")))
        .where(ImportJob.archived_at.is_(None))
    ) or 0

    failed_rows = (
        await db.execute(
            select(
                ImportJob.id,
                ImportJob.template_slug,
                ImportJob.status,
                ImportJob.stage,
                ImportJob.file_name,
                ImportJob.error_summary,
                ImportJob.created_at,
                ImportJob.completed_at,
                ImportJob.updated_at,
            )
            .where(where_tenant(ImportJob.tenant_id, user))
            .where(ImportJob.status == "failed")
            .where(ImportJob.archived_at.is_(None))
            .order_by(ImportJob.id.desc())
            .limit(failed_limit)
        )
    ).all()

    recent_failed = [
        {
            "id": r.id,
            "template_slug": r.template_slug,
            "status": r.status,
            "stage": r.stage,
            "file_name": r.file_name,
            "error_summary": (r.error_summary or "")[:500] or None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in failed_rows
    ]

    completed_14d = await db.scalar(
        select(func.count())
        .select_from(ImportJob)
        .where(where_tenant(ImportJob.tenant_id, user))
        .where(ImportJob.status.in_(("completed", "completed_with_errors")))
        .where(ImportJob.completed_at.is_not(None))
        .where(ImportJob.completed_at >= since)
    ) or 0

    return {
        "tenant_id": tid,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "readiness": {
            "status": "ready",
            "database": db_name,
            "ok": True,
        },
        "counts": {
            "failed_open": int(failed_count),
            "running_or_pending": int(running_count),
            "completed_last_14d": int(completed_14d),
        },
        "failed_jobs": recent_failed,
        "links": {
            "import_center": "/admin/imports",
            "steward_audit": "/admin/steward-audit",
            "health": "/health",
            "ready": "/health/ready",
        },
    }
