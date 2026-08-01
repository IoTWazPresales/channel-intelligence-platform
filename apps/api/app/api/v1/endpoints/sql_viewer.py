"""P3-6 admin SQL / table viewer — read-only, timeout, row cap, audit."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import Role, require_roles
from app.core.tenant_scope import tenant_id_from_user
from app.db.session_sync import get_sync_session
from app.models.sql_viewer_audit import SqlViewerAudit
from app.services.saved_report_access import parse_user_id
from app.services.sql_viewer import (
    DEFAULT_ROW_CAP,
    DEFAULT_TIMEOUT_MS,
    MAX_ROW_CAP,
    MAX_TIMEOUT_MS,
    execute_readonly_sql,
    list_public_tables,
)

router = APIRouter()


class SqlExecuteBody(BaseModel):
    sql: str = Field(..., min_length=1, max_length=20_000)
    row_limit: int = Field(default=DEFAULT_ROW_CAP, ge=1, le=MAX_ROW_CAP)
    timeout_ms: int = Field(default=DEFAULT_TIMEOUT_MS, ge=500, le=MAX_TIMEOUT_MS)


def _actor_label(user: dict) -> str:
    return (
        (user.get("email") or user.get("display_name") or user.get("id") or "admin")
    )


def _audit_dict(row: SqlViewerAudit) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "tenant_id": row.tenant_id,
        "actor_user_id": int(row.actor_user_id) if row.actor_user_id is not None else None,
        "actor": row.actor,
        "sql_text": row.sql_text,
        "status": row.status,
        "row_count": row.row_count,
        "truncated": bool(row.truncated),
        "duration_ms": row.duration_ms,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/sql-viewer/tables")
async def sql_viewer_tables(
    user: dict = Depends(require_roles(Role.ADMIN)),
    limit: int = Query(default=300, ge=1, le=1000),
) -> dict[str, Any]:
    """List non-system tables — admin browse helper (not a governed metric)."""
    _ = user
    sync = get_sync_session()
    try:
        tables = list_public_tables(sync, limit=limit)
    finally:
        sync.close()
    return {"items": tables, "count": len(tables)}


@router.post("/sql-viewer/execute")
async def sql_viewer_execute(
    body: SqlExecuteBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(Role.ADMIN)),
) -> dict[str, Any]:
    """Execute a single read-only SQL statement. Audited. Admin only."""
    tid = tenant_id_from_user(user)
    sync = get_sync_session()
    try:
        result = execute_readonly_sql(
            sync,
            sql=body.sql,
            row_cap=body.row_limit,
            timeout_ms=body.timeout_ms,
        )
    finally:
        sync.close()

    audit = SqlViewerAudit(
        tenant_id=tid,
        actor_user_id=parse_user_id(user),
        actor=str(_actor_label(user)),
        sql_text=result.sql_text or body.sql[:4000],
        status=result.status,
        row_count=result.row_count,
        truncated=bool(result.truncated),
        duration_ms=result.duration_ms,
        error_message=result.message if result.status != "ok" else None,
    )
    db.add(audit)
    await db.commit()
    await db.refresh(audit)

    payload: dict[str, Any] = {
        "ok": result.status == "ok",
        "status": result.status,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
        "duration_ms": result.duration_ms,
        "message": result.message,
        "row_limit": body.row_limit,
        "timeout_ms": body.timeout_ms,
        "audit_id": int(audit.id),
        "warning": (
            "Raw SQL is not a governed metric. Prefer /reports and /query/execute for "
            "commercial numbers that must match Channel Ops / PvE / CPOR."
        ),
    }
    if result.status == "refused":
        raise HTTPException(status_code=400, detail=payload)
    return payload


@router.get("/sql-viewer/audit")
async def sql_viewer_audit_list(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(Role.ADMIN)),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    tid = tenant_id_from_user(user)
    rows = (
        await db.execute(
            select(SqlViewerAudit)
            .where(SqlViewerAudit.tenant_id == tid)
            .order_by(SqlViewerAudit.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {"items": [_audit_dict(r) for r in rows], "count": len(rows)}
