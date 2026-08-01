from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.feature_flags import commercial_planner_enabled
from app.core.security import get_optional_current_user
from app.core.tenant_scope import tenant_id_from_user, where_tenant
from app.models.derived import ExceptionInboxItem, StockHealth
from app.models.facts import FactBudgetRequest, FactInboundShipment
from app.models.ingestion import ImportJob
from app.services.commercial_planner.plan_readiness import commercial_planner_dashboard_aggregate

router = APIRouter()

_FRESH_STATUSES = ("completed", "completed_with_errors")
_STALE_HOURS = 168  # 7 days


@router.get("/summary")
async def summary(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
):
    tid = tenant_id_from_user(user)

    stock_rows = await db.execute(select(StockHealth.health_state, func.count()).group_by(StockHealth.health_state))
    stock_summary = {row[0]: row[1] for row in stock_rows.all()}

    open_exceptions = await db.scalar(select(func.count()).select_from(ExceptionInboxItem).where(ExceptionInboxItem.status == "open")) or 0
    open_budget = await db.scalar(
        select(func.count()).select_from(FactBudgetRequest).where(FactBudgetRequest.status.in_(["draft", "submitted", "under_review"]))
    ) or 0
    late_risk = await db.scalar(
        select(func.count())
        .select_from(FactInboundShipment)
        .where(FactInboundShipment.status != "received")
        .where(where_tenant(FactInboundShipment.tenant_id, user))
    ) or 0

    cp_kpis = None
    if commercial_planner_enabled():
        cp_kpis = await commercial_planner_dashboard_aggregate(db)

    fresh_rows = (
        await db.execute(
            select(ImportJob.template_slug, func.max(ImportJob.completed_at), func.max(ImportJob.id))
            .where(ImportJob.status.in_(_FRESH_STATUSES))
            .where(ImportJob.completed_at.is_not(None))
            .where(where_tenant(ImportJob.tenant_id, user))
            .group_by(ImportJob.template_slug)
            .order_by(func.max(ImportJob.completed_at).desc())
        )
    ).all()

    now = datetime.now(timezone.utc)
    by_template: list[dict] = []
    newest: datetime | None = None
    for slug, completed_at, job_id in fresh_rows:
        if completed_at is None:
            continue
        ts = completed_at if completed_at.tzinfo else completed_at.replace(tzinfo=timezone.utc)
        if newest is None or ts > newest:
            newest = ts
        age_hours = max(0, int((now - ts).total_seconds() // 3600))
        by_template.append(
            {
                "template_slug": slug or "unknown",
                "completed_at": ts.isoformat(),
                "import_job_id": int(job_id) if job_id is not None else None,
                "age_hours": age_hours,
                "stale": age_hours > _STALE_HOURS,
            }
        )

    overall_age = max(0, int((now - newest).total_seconds() // 3600)) if newest else None
    failed_open = await db.scalar(
        select(func.count())
        .select_from(ImportJob)
        .where(ImportJob.status == "failed")
        .where(ImportJob.archived_at.is_(None))
        .where(where_tenant(ImportJob.tenant_id, user))
    ) or 0

    recommended_actions = [
        {
            "title": "Review exceptions inbox",
            "href": "/exceptions",
            "reason": "Central queue for stock, pricing, and mapping issues.",
        },
        {
            "title": "Validate latest import",
            "href": "/admin/imports",
            "reason": "Trust layer for messy distributor files.",
        },
    ]
    if commercial_planner_enabled():
        recommended_actions.insert(
            0,
            {
                "title": "Commercial plans readiness",
                "href": "/commercial-planner",
                "reason": "Review plans missing terms, SKU assumptions, or economics flags.",
            },
        )
    if failed_open:
        recommended_actions.insert(
            0,
            {
                "title": f"{failed_open} failed import job(s)",
                "href": "/admin/imports",
                "reason": "Open Import Center to inspect failed jobs (Ops monitoring in P2-5).",
            },
        )

    return {
        "kpis": {
            "open_exceptions": open_exceptions,
            "open_budget_requests": open_budget,
            "inbound_shipments_tracked": late_risk,
            "commercial_planner": cp_kpis,
            "failed_import_jobs": int(failed_open),
        },
        "freshness": {
            "tenant_id": tid,
            "as_of": now.isoformat(),
            "newest_completed_at": newest.isoformat() if newest else None,
            "newest_age_hours": overall_age,
            "stale_after_hours": _STALE_HOURS,
            "is_stale": overall_age is None or overall_age > _STALE_HOURS,
            "by_template": by_template[:12],
        },
        "stock_health": stock_summary,
        "recommended_actions": recommended_actions,
    }
