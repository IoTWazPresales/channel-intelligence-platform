"""Read-only Administration headline grains. Callers must print current_database() first."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_scope import tenant_id_from_user, where_tenant
from app.models.iam import AppUser
from app.models.ingestion import ImportJob
from app.models.sql_viewer_audit import SqlViewerAudit

logger = logging.getLogger(__name__)

_ROLES = ("admin", "steward", "planner", "viewer")


def role_caption(counts: dict[str, int]) -> str:
    """Always name the four CIP roles so a zero is visible, not omitted."""
    return " · ".join(f"{int(counts.get(role, 0))} {role}" for role in _ROLES)


def _empty(dbname: str | None, tenant: str) -> dict[str, Any]:
    return {
        "database": dbname,
        "tenant_id": tenant,
        "data_unavailable": True,
        "labels": {},
        "captions": {},
        "number_class": {},
        "operations": [],
    }


async def administration_overview(db: AsyncSession, user: dict | None) -> dict[str, Any]:
    dbname = await db.scalar(text("SELECT current_database()"))
    tenant = tenant_id_from_user(user)
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)

    try:
        role_rows = (
            await db.execute(
                select(AppUser.role, func.count())
                .where(where_tenant(AppUser.tenant_id, user))
                .where(AppUser.is_active.is_(True))
                .group_by(AppUser.role)
            )
        ).all()
        users_by_role = {str(role): int(n) for role, n in role_rows}
        users = sum(users_by_role.values())

        running = int(
            await db.scalar(
                select(func.count())
                .select_from(ImportJob)
                .where(where_tenant(ImportJob.tenant_id, user))
                .where(ImportJob.archived_at.is_(None))
                .where(ImportJob.status == "running")
            )
            or 0
        )
        pending = int(
            await db.scalar(
                select(func.count())
                .select_from(ImportJob)
                .where(where_tenant(ImportJob.tenant_id, user))
                .where(ImportJob.archived_at.is_(None))
                .where(ImportJob.status == "pending")
            )
            or 0
        )
        failed_open = int(
            await db.scalar(
                select(func.count())
                .select_from(ImportJob)
                .where(where_tenant(ImportJob.tenant_id, user))
                .where(ImportJob.archived_at.is_(None))
                .where(ImportJob.status == "failed")
            )
            or 0
        )
        failed_ts = func.coalesce(ImportJob.completed_at, ImportJob.updated_at, ImportJob.created_at)
        failed_24h = int(
            await db.scalar(
                select(func.count())
                .select_from(ImportJob)
                .where(where_tenant(ImportJob.tenant_id, user))
                .where(ImportJob.archived_at.is_(None))
                .where(ImportJob.status == "failed")
                .where(failed_ts >= since_24h)
            )
            or 0
        )
        sql_7d = int(
            await db.scalar(
                select(func.count())
                .select_from(SqlViewerAudit)
                .where(where_tenant(SqlViewerAudit.tenant_id, user))
                .where(SqlViewerAudit.created_at >= since_7d)
            )
            or 0
        )
        sql_all = int(
            await db.scalar(
                select(func.count())
                .select_from(SqlViewerAudit)
                .where(where_tenant(SqlViewerAudit.tenant_id, user))
            )
            or 0
        )

        op_rows = (
            await db.execute(
                select(
                    ImportJob.id,
                    ImportJob.template_slug,
                    ImportJob.status,
                    ImportJob.stage,
                    ImportJob.file_name,
                    ImportJob.error_summary,
                )
                .where(where_tenant(ImportJob.tenant_id, user))
                .where(ImportJob.archived_at.is_(None))
                .where(ImportJob.status.in_(("running", "pending", "failed")))
                .order_by(
                    case(
                        (ImportJob.status == "running", 0),
                        (ImportJob.status == "failed", 1),
                        else_=2,
                    ),
                    ImportJob.id.desc(),
                )
                .limit(8)
            )
        ).all()
    except Exception:
        logger.exception("administration_overview query failed")
        return _empty(dbname, tenant)

    operations = [
        {
            "id": r.id,
            "template_slug": r.template_slug,
            "status": r.status,
            "stage": r.stage,
            "file_name": r.file_name,
            "error_summary": (r.error_summary or "")[:240] or None,
        }
        for r in op_rows
    ]

    return {
        "database": dbname,
        "tenant_id": tenant,
        "data_unavailable": False,
        "users": users,
        "users_by_role": {role: int(users_by_role.get(role, 0)) for role in _ROLES},
        "jobs_running": running,
        "jobs_pending": pending,
        "failed_24h": failed_24h,
        "failed_open": failed_open,
        "sql_queries_7d": sql_7d,
        "sql_queries_all": sql_all,
        "operations": operations,
        "labels": {
            "users": "Users",
            "jobs_running": "Background jobs running",
            "failed_24h": "Failed jobs (24h)",
            "sql_queries_7d": "Audited SQL queries (7d)",
        },
        "captions": {
            "users": f"{role_caption(users_by_role)} · active app_user; not lab fixture 14",
            "jobs_running": (
                f"import_job.status='running' and archived_at is null "
                f"(not pending). {pending} pending queued."
            ),
            "failed_24h": (
                f"import_job.status='failed' in last 24h via "
                f"coalesce(completed_at, updated_at, created_at). "
                f"{failed_open} failed still open (not this grain)."
            ),
            "sql_queries_7d": (
                f"sql_viewer_audit.created_at in last 7 days. {sql_all} all-time. "
                "Not lab fixture 38."
            ),
        },
        "number_class": {
            "users": "iii",
            "jobs_running": "iii",
            "failed_24h": "iii",
            "sql_queries_7d": "iii",
        },
    }
