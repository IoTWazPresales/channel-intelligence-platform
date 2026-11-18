"""Admin ops / monitoring endpoints (P2-5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import Role, require_roles
from app.core.tenant_scope import tenant_id_from_user, where_tenant
from app.models.customer_cst_report_slot import CustomerCstReportSlot
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from app.models.ingestion import ImportJob
from app.services.ops_health import (
    REPORT_RECEIPT_WINDOW_DAYS,
    file_health,
    reports_health,
    state_root,
)

router = APIRouter()


@router.get("/ops/overview")
async def ops_overview(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(Role.ADMIN, Role.STEWARD)),
    failed_limit: int = Query(default=25, ge=1, le=100),
):
    """Failed / running import jobs + counts for the caller's tenant, and operations health
    (services, backups, expected weekly reports; app/services/ops_health.py)."""
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

    now = datetime.now(UTC)
    slot_rows = (
        await db.execute(
            select(CustomerCstReportSlot.status, func.count())
            .join(DimCustomer, DimCustomer.id == CustomerCstReportSlot.customer_id)
            # Only customers whose reports are expected count, as for the other report figures:
            # a disabled customer's retained slot must not keep the card late or missing
            # (Codex review of PR #110, round 2).
            .join(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
            .where(where_tenant(DimCustomer.tenant_id, user))
            .where(CustomerReportConfig.reports_expected.is_(True))
            .where(CustomerCstReportSlot.status.in_(("due", "late", "missing")))
            .group_by(CustomerCstReportSlot.status)
        )
    ).all()
    slot_counts = {str(s): int(n) for s, n in slot_rows}
    newest_received = await db.scalar(
        select(func.max(CustomerCstReportSlot.received_at))
        .join(DimCustomer, DimCustomer.id == CustomerCstReportSlot.customer_id)
        .join(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
        .where(where_tenant(DimCustomer.tenant_id, user))
        .where(CustomerReportConfig.reports_expected.is_(True))
        .where(CustomerCstReportSlot.status == "received")
    )
    expected_customers = await db.scalar(
        select(func.count())
        .select_from(CustomerReportConfig)
        .join(DimCustomer, DimCustomer.id == CustomerReportConfig.customer_id)
        .where(where_tenant(DimCustomer.tenant_id, user))
        .where(CustomerReportConfig.reports_expected.is_(True))
    ) or 0
    # Match cst_d1.advance_cst_report_slots: the prior Mon-Sun week is due this Monday.
    # A previous week's slot, a future slot, or "received" without a valid receipt cannot prove
    # tracking for this week, even when another customer has a fresh receipt.
    today = now.astimezone().date()
    expected_week = today - timedelta(days=today.weekday() + 7)
    current_slot = (
        select(CustomerCstReportSlot.id)
        .where(CustomerCstReportSlot.customer_id == CustomerReportConfig.customer_id)
        .where(CustomerCstReportSlot.week_start_date == expected_week)
        .where(
            or_(
                CustomerCstReportSlot.status.in_(("due", "late", "missing")),
                and_(
                    CustomerCstReportSlot.status == "received",
                    CustomerCstReportSlot.received_at >= now - timedelta(days=REPORT_RECEIPT_WINDOW_DAYS),
                    CustomerCstReportSlot.received_at <= now,
                ),
            )
        )
        .exists()
    )
    untracked_customers = await db.scalar(
        select(func.count())
        .select_from(CustomerReportConfig)
        .join(DimCustomer, DimCustomer.id == CustomerReportConfig.customer_id)
        .where(where_tenant(DimCustomer.tenant_id, user))
        .where(CustomerReportConfig.reports_expected.is_(True))
        .where(~current_slot)
    ) or 0
    health = file_health(state_root(get_settings().cip_ops_state_dir or None), now=now)
    health["reports"] = reports_health(
        due=slot_counts.get("due", 0),
        late=slot_counts.get("late", 0),
        missing=slot_counts.get("missing", 0),
        untracked_customers=int(untracked_customers),
        newest_received=newest_received,
        expected_customers=int(expected_customers),
        now=now,
    )

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
        "health": health,
        "links": {
            "import_center": "/admin/imports",
            "steward_audit": "/admin/steward-audit",
            "health": "/health",
            "ready": "/health/ready",
        },
    }
