"""B2 budget position — dual track (money + support-%), profile-driven binding axis.

Domain §1.8 / Q-001: money is binding for current tenant; support-% informational.
Hard enforce stays off until over-budget reapproval workflow ships.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_planner import CommercialSkuAssumption
from app.models.cpor import CporCaseLine
from app.services import commercial_tenant_profile as tenant_profile


async def build_budget_position(
    db: AsyncSession,
    *,
    planned_reservations: list[dict[str, Any]] | None = None,
    period_label: str | None = None,
) -> dict[str, Any]:
    """Aggregate planned reservations vs CPOR line spend (dual track).

    ``planned_reservations`` items: ``{product_id?, customer_id?, reserved_amount, revenue?}``.
    """
    planned = list(planned_reservations or [])
    reserved_money = sum(float(p.get("reserved_amount") or 0) for p in planned)
    planned_revenue = sum(float(p.get("revenue") or 0) for p in planned)
    reserved_pct = (reserved_money / planned_revenue) if planned_revenue > 0 else None

    drawn_usd_f = 0.0
    drawn_zar_f = 0.0
    line_count = 0
    cpor_ok = True
    try:
        stmt = select(
            func.coalesce(func.sum(CporCaseLine.ttl_support_usd), 0),
            func.coalesce(func.sum(CporCaseLine.ttl_support), 0),
            func.count(CporCaseLine.id),
        )
        if period_label:
            stmt = stmt.where(CporCaseLine.pod_quarter == period_label)
        drawn_usd, drawn_zar, n = (await db.execute(stmt)).one()
        drawn_usd_f = float(drawn_usd or 0)
        drawn_zar_f = float(drawn_zar or 0)
        line_count = int(n or 0)
    except Exception:
        cpor_ok = False

    remaining_money = reserved_money - drawn_usd_f
    money_util = (drawn_usd_f / reserved_money) if reserved_money > 0 else None
    money_status = (
        "over"
        if reserved_money > 0 and drawn_usd_f > reserved_money
        else ("ok" if reserved_money > 0 else "no_planned_reservation")
    )

    try:
        sku_n = int(
            (await db.execute(select(func.count()).select_from(CommercialSkuAssumption))).scalar()
            or 0
        )
    except Exception:
        sku_n = 0

    profile = tenant_profile.profile_snapshot()
    return {
        "as_of": date.today().isoformat(),
        "period_label": period_label,
        "hard_enforce": bool(tenant_profile.HARD_ENFORCE_BUDGET),
        "constraint_type": tenant_profile.CONSTRAINT_AXIS,
        "binding_axis": tenant_profile.CONSTRAINT_AXIS,
        "over_budget_action": tenant_profile.OVER_BUDGET_ACTION,
        "tenant_profile": profile,
        "tracks": {
            "money": {
                "planned_reservation_usd": round(reserved_money, 4),
                "drawn_cpor_usd": round(drawn_usd_f, 4),
                "drawn_cpor_zar_display": round(drawn_zar_f, 4),
                "remaining_usd": round(remaining_money, 4),
                "utilisation": money_util,
                "status": money_status,
                "binding": tenant_profile.CONSTRAINT_AXIS in ("money", "dual"),
            },
            "support_pct": {
                "planned_support_pct_of_sell_in": reserved_pct,
                "note": "Informational for money-binding tenants; planned % from reservation÷sell-in",
                "binding": tenant_profile.CONSTRAINT_AXIS in ("support_pct", "dual"),
            },
        },
        "cpor_line_count": line_count,
        "cpor_data_available": cpor_ok,
        "sku_assumption_count": sku_n,
        "planned_line_count": len(planned),
        "basis": "cpor_case_line.ttl_support_usd; optional pod_quarter filter (landed)",
        "reservation_source": tenant_profile.RESERVATION_SOURCE,
        "q002_reservation_source": tenant_profile.RESERVATION_SOURCE,
    }
