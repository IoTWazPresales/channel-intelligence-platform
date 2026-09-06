"""Federated Brief signal rows for grammar-3 landing (NS-2)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.feature_flags import commercial_planner_enabled
from app.core.tenant_scope import tenant_id_from_user, where_tenant
from app.models.iam import Tenant
from app.models.cpor import CporCase, CporCaseLine
from app.models.facts import FactInboundShipment, FactInventoryReconciliation
from app.models.ingestion import ImportJob
from app.services.channel_ops_config import REPLENISHMENT_WOC_THRESHOLD_WEEKS
from app.services.channel_ops_derived_stock import replenishment_flag_v1, weeks_of_cover_or_none
from app.services.cpor.intelligence_scope import where_commercial_intelligence
from app.services.cpor.promotion_type_vocab import CPOR_CASE_STATUS_SET
from app.services.cpor.settle_readiness import case_missing_roe
from app.services.woc_observation_read import latest_woc_observations, observations_to_stock_vel

_FRESH_STATUSES = ("completed", "completed_with_errors")
_STALE_HOURS = 168
_DSI_TEMPLATE = "distributor_sales_inventory"
_OPEN_CPOR_STATUSES = tuple(s for s in CPOR_CASE_STATUS_SET if s not in {"settled", "cancelled", "rejected"})


def _severity_from_rank(rank: int) -> str:
    if rank <= 2:
        return "stop"
    return "warn"


def _signal_row(
    *,
    id: str,
    rank: int,
    title: str,
    detail: str,
    meta: str | None,
    meta_hot: bool,
    action_label: str,
    action_href: str,
    suggested: bool = False,
    data_unavailable: bool = False,
    figures: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "rank": rank,
        "severity": _severity_from_rank(rank),
        "title": title,
        "detail": detail,
        "meta": meta,
        "meta_hot": meta_hot,
        "action_label": action_label,
        "action_href": action_href,
        "suggested": suggested,
        "data_unavailable": data_unavailable,
        "figures": figures or {},
    }


async def _dsi_freshness(db: AsyncSession, user: dict | None) -> dict[str, Any] | None:
    row = (
        await db.execute(
            select(ImportJob.completed_at, ImportJob.id)
            .where(ImportJob.template_slug == _DSI_TEMPLATE)
            .where(ImportJob.status.in_(_FRESH_STATUSES))
            .where(ImportJob.completed_at.is_not(None))
            .where(where_tenant(ImportJob.tenant_id, user))
            .order_by(ImportJob.completed_at.desc())
            .limit(1)
        )
    ).first()
    if not row or row[0] is None:
        return None
    completed_at = row[0] if row[0].tzinfo else row[0].replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age_hours = max(0, int((now - completed_at).total_seconds() // 3600))
    return {
        "completed_at": completed_at.date().isoformat(),
        "age_days": max(0, age_hours // 24),
        "stale": age_hours > _STALE_HOURS,
        "import_job_id": int(row[1]) if row[1] is not None else None,
    }


async def _cover_summary(db: AsyncSession, user: dict | None) -> dict[str, Any]:
    tid = tenant_id_from_user(user if isinstance(user, dict) else None)
    obs = await latest_woc_observations(db, tenant_id=tid, distributor_id=None)
    stock_by_pair, vel_by_pair = observations_to_stock_vel(obs)
    threshold = float(REPLENISHMENT_WOC_THRESHOLD_WEEKS)
    pairs_below = 0
    woc_values: list[float] = []
    for key, stock in stock_by_pair.items():
        woc = weeks_of_cover_or_none(stock, vel_by_pair.get(key))
        if woc is not None:
            woc_values.append(float(woc))
        if replenishment_flag_v1(woc, threshold_weeks=threshold):
            pairs_below += 1
    book_mean = round(sum(woc_values) / len(woc_values), 1) if woc_values else None
    return {
        "pairs_below_threshold": pairs_below,
        "pair_count": len(stock_by_pair),
        "book_mean_weeks": book_mean,
        "grain": "distributor_product",
    }


async def _settlement_aggregates(db: AsyncSession, user: dict | None) -> dict[str, Any]:
    if not commercial_planner_enabled():
        return {
            "open_cases": None,
            "fx_blocked_cases": None,
            "fx_blocked_zar": None,
            "missing_assumption_skus": None,
            "data_unavailable": True,
        }

    open_q = (
        select(CporCase)
        .where(CporCase.status.in_(_OPEN_CPOR_STATUSES))
        .where(where_tenant(CporCase.tenant_id, user))
        .where(where_commercial_intelligence())
    )
    cases = (await db.execute(open_q)).scalars().all()
    fx_blocked = [c for c in cases if case_missing_roe(c)]
    fx_blocked_zar = 0.0  # placeholder — owed amount needs recon batch; count is primary signal

    assumption_lines = (
        await db.execute(
            select(func.count(func.distinct(CporCaseLine.product_id)))
            .join(CporCase, CporCase.id == CporCaseLine.case_id)
            .where(CporCase.status.in_(_OPEN_CPOR_STATUSES))
            .where(where_tenant(CporCase.tenant_id, user))
            .where(where_commercial_intelligence())
            .where(or_(CporCaseLine.cost_basis.is_(None), CporCaseLine.cost_source.is_(None)))
        )
    ).scalar()

    return {
        "open_cases": len(cases),
        "fx_blocked_cases": len(fx_blocked),
        "fx_blocked_zar": fx_blocked_zar if fx_blocked else None,
        "missing_assumption_skus": int(assumption_lines or 0),
        "data_unavailable": False,
    }


async def build_brief_payload(db: AsyncSession, user: dict | None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    failed_open = int(
        await db.scalar(
            select(func.count())
            .select_from(ImportJob)
            .where(ImportJob.status == "failed")
            .where(ImportJob.archived_at.is_(None))
            .where(where_tenant(ImportJob.tenant_id, user))
        )
        or 0
    )

    recon_rows = int(
        await db.scalar(select(func.count()).select_from(FactInventoryReconciliation)) or 0
    )
    soh_recon_not_run = recon_rows == 0

    dsi = await _dsi_freshness(db, user)
    cover = await _cover_summary(db, user)
    settlement = await _settlement_aggregates(db, user)

    inbound_open = int(
        await db.scalar(
            select(func.count())
            .select_from(FactInboundShipment)
            .where(FactInboundShipment.status != "received")
            .where(where_tenant(FactInboundShipment.tenant_id, user))
        )
        or 0
    )

    signals: list[dict[str, Any]] = []
    rank = 1

    if failed_open > 0:
        dsi_date = dsi["completed_at"] if dsi else None
        detail = "steward queue"
        if dsi_date:
            detail += f"; latest batch DSI {dsi_date}"
        signals.append(
            _signal_row(
                id="failed_imports",
                rank=rank,
                title=f"{failed_open} failed imports",
                detail=detail,
                meta=f"{failed_open} jobs",
                meta_hot=True,
                action_label="Open steward queue",
                action_href="/admin/imports?status=failed",
                suggested=True,
                figures={"count": failed_open, "dsi_vintage": dsi_date},
            )
        )
        rank += 1

    if soh_recon_not_run:
        signals.append(
            _signal_row(
                id="soh_recon_not_run",
                rank=rank,
                title="SOH reconciliation not run",
                detail="derived cover and replenish flags are unverified",
                meta="book-wide",
                meta_hot=False,
                action_label="Open Stock · Cover",
                action_href="/sell-out",
                figures={"book_wide": True},
            )
        )
        rank += 1

    if dsi and dsi.get("stale"):
        signals.append(
            _signal_row(
                id="dsi_vintage_stale",
                rank=rank,
                title=f"DSI vintage {dsi['completed_at']}",
                detail=f"stock position is {dsi['age_days']} days stale",
                meta=f"{dsi['age_days']}d",
                meta_hot=True,
                action_label="Import DSI",
                action_href="/admin/imports?template=distributor_sales_inventory",
                figures=dsi,
            )
        )
        rank += 1

    signals.append(
        _signal_row(
            id="sell_out_gap",
            rank=rank,
            title="Sell-out gap",
            detail="customer-account grain sell-out gap read model not available yet",
            meta="n/a",
            meta_hot=False,
            action_label="Import sell-out",
            action_href="/admin/imports?template=customer_sell_through",
            data_unavailable=True,
            figures={},
        )
    )
    rank += 1

    if cover["pairs_below_threshold"] > 0:
        mean = cover["book_mean_weeks"]
        mean_txt = f"{mean}w" if mean is not None else "n/a"
        signals.append(
            _signal_row(
                id="cover_breach",
                rank=rank,
                title=f"{cover['pairs_below_threshold']} pairs under {int(REPLENISHMENT_WOC_THRESHOLD_WEEKS)} weeks of cover",
                detail=f"book mean {mean_txt} ({cover['grain']} grain)",
                meta=f"{cover['pairs_below_threshold']} pairs",
                meta_hot=cover["pairs_below_threshold"] > 0,
                action_label="Open Stock · Cover",
                action_href="/sell-out",
                figures=cover,
            )
        )
        rank += 1

    if inbound_open > 0:
        signals.append(
            _signal_row(
                id="inbound_open",
                rank=rank,
                title=f"{inbound_open} inbound shipments not received",
                detail="pipeline fill % requires line-grain read model",
                meta=f"{inbound_open} shipments",
                meta_hot=True,
                action_label="Open Stock · Inbound",
                action_href="/shipping",
                figures={"open_shipments": inbound_open, "pipeline_fill_pct": None},
            )
        )
        rank += 1

    if settlement.get("fx_blocked_cases"):
        blocked = int(settlement["fx_blocked_cases"])
        signals.append(
            _signal_row(
                id="settlement_blocked",
                rank=rank,
                title="Settlement blocked",
                detail=f"{blocked} case(s) FX undeclared",
                meta=f"{blocked} case" if blocked == 1 else f"{blocked} cases",
                meta_hot=True,
                action_label="Open Settlement",
                action_href="/commercial-planner/cpor-cases",
                figures={"fx_blocked_cases": blocked},
            )
        )
        rank += 1

    if settlement.get("missing_assumption_skus"):
        sku_count = int(settlement["missing_assumption_skus"])
        if sku_count > 0:
            signals.append(
                _signal_row(
                    id="missing_assumptions",
                    rank=rank,
                    title=f"{sku_count} SKUs missing cost basis on open cases",
                    detail="assumption gaps on settlement lines",
                    meta=f"{sku_count} SKUs",
                    meta_hot=True,
                    action_label="Open Settlement",
                    action_href="/commercial-planner/cpor-cases",
                    figures={"sku_count": sku_count},
                )
            )
            rank += 1

    # Re-rank and ensure exactly one suggested action on the top signal
    available = [s for s in signals if not s.get("data_unavailable")]
    for i, sig in enumerate(available, start=1):
        sig["rank"] = i
        sig["severity"] = _severity_from_rank(i)
        sig["suggested"] = i == 1

    display_signals = available if available else signals

    read_parts: list[str] = []
    if failed_open:
        read_parts.append(f"**{failed_open}** imports failed")
    if soh_recon_not_run:
        read_parts.append("SOH recon not run")
    if cover["pairs_below_threshold"] > 0:
        read_parts.append(f"**{cover['pairs_below_threshold']}** pairs under {int(REPLENISHMENT_WOC_THRESHOLD_WEEKS)}w cover")
    if settlement.get("open_cases"):
        read_parts.append(f"**{settlement['open_cases']}** open settlement cases")
    read_text = " · ".join(read_parts) if read_parts else "No material signals — book is clear for this period."

    spine_badges = {
        "brief": len(display_signals),
        "stock": cover["pairs_below_threshold"] if cover["pairs_below_threshold"] else None,
        "settlement": settlement.get("open_cases"),
        "response": None,
        "steward": failed_open if failed_open else None,
    }

    quarter = (date.today().month - 1) // 3 + 1
    year_suffix = str(date.today().year)[-2:]
    tid = tenant_id_from_user(user)
    tenant_row = await db.get(Tenant, tid)
    tenant_name = (tenant_row.name if tenant_row else None) or tid
    tenant_period = f"{year_suffix}Q{quarter}"

    return {
        "as_of": now.isoformat(),
        "tenant_stamp": f"{tenant_name} · {tenant_period}",
        "tenant_name": tenant_name,
        "tenant_period": tenant_period,
        "read": read_text,
        "signals": display_signals,
        "spine_badges": spine_badges,
        "signal_count": len(display_signals),
    }
